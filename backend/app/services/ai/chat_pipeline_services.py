"""对话前置编排：意图门控 → 知识检索 → 工具集选择。

放在 Service 层而不是 Router，是为了让 Router 只做 HTTP 入参/出参。
``intent`` 能力未配置时，``intent_services.classify`` 返回 None，
本模块自动退化为"知识库照常检索、工具全开"，与加意图识别之前完全一致。

[链路定位] 本文件是"一次文字聊天"进模型之前的编排层，不碰模型、不落库：

    上游：ai_router.chat() / ai_router.chat_stream() 调用
          prepare_text_chat_context()
    下游：intent_services.classify()                          —— 意图门控（可选）
          knowledge_retrieval_services.search_knowledge()     —— RAG 检索（可选）
    产出：ChatContext{retrieved_chunks, tools, capability, prompt_style}
          交给 ai_services.chat() 真正去调模型。
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_models import ChatSession
from app.services.ai import intent_services
from app.services.ai.agent_tool_services import AGENT_TOOLS
from app.services.ai.ai_provider_services import CapabilityNotConfiguredError
from app.services.ai.chat_services import load_history
from app.services.ai.intent_services import IntentResult
from app.services.knowledge import knowledge_retrieval_services
from app.services.knowledge.knowledge_retrieval_services import RetrievedChunk

logger = logging.getLogger(__name__)

# 交给聊天模型的知识片段条数；与加入意图识别之前保持一致。
CHAT_RETRIEVAL_LIMIT = 5

# 检索只需要最近几轮来消解“它、这个实验室、刚才那个设备”等指代，不能把整段
# 长会话都塞进Embedding，否则旧话题会稀释当前问题。
RETRIEVAL_HISTORY_LIMIT = 4
RETRIEVAL_HISTORY_ITEM_CHARS = 500


@dataclass(slots=True)
class ChatContext:
    """一次聊天请求在进入模型之前已经确定好的上下文。"""

    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    # None 表示"不限制"（按全部工具处理）；空列表表示"本轮不给工具"。
    tools: list[dict[str, Any]] | None = None
    intent: IntentResult | None = None
    # 走哪个对话能力位：默认 chat；闲聊可切到 chat_light（未配置时自动回退 chat）。
    capability: str = "chat"
    # 用哪套系统提示词：full / light。
    prompt_style: str = "full"


def _tools_for_intent(intent: IntentResult, question: str) -> list[dict[str, Any]]:
    """按意图结果裁剪工具白名单；模型给出的未知工具名直接忽略。

    额外的安全约束：明显的越权/注入式要求（“忽略规则”“直接执行SQL”
    “不要告诉管理员”等）即使被意图模型判成“创建预约”，也不挂
    prepare_reservation。写库工具只应该出现在正常的预约请求里；这类请求
    由系统提示词负责明确拒绝。
    """

    allowed = set(intent.need_tools)
    selected = [tool for tool in AGENT_TOOLS if tool["name"] in allowed]
    if _BYPASS_PATTERN.search(question):
        logger.warning("bypass-style request detected; prepare_reservation withheld")
        selected = [tool for tool in selected if tool["name"] != "prepare_reservation"]
    return selected


# 越权/注入式要求的低成本兜底。不是“安全过滤器”，而是给写库工具加一道
# 确定性的闸门：哪怕意图模型判错了，也不会把 prepare_reservation 挂上去。
_BYPASS_PATTERN = re.compile(
    r"忽略.{0,8}(规则|指令|限制|系统)"
    r"|不要(检查|校验|验证).{0,8}(权限|管理员)"
    r"|执行\s*sql|直接(改|修改|写入).{0,10}(数据库|状态|表)"
    r"|不要(告诉|通知)(管理员|任何人)"
    r"|绕过.{0,8}(权限|审核|管理员)",
    re.IGNORECASE,
)


async def _build_contextual_retrieval_query(
    db: AsyncSession,
    *,
    question: str,
    session_id: int | None,
    user_id: int,
) -> str:
    """用最近对话补全检索语境，但不修改真正发送给聊天模型的用户问题。"""

    if session_id is None:
        return question

    chat_session = await db.get(ChatSession, session_id)
    if chat_session is None or chat_session.user_id != user_id:
        # 不读取不属于当前用户的历史。会话不存在的正式业务错误仍由chat()统一返回。
        return question

    history = await load_history(
        db,
        session_id=session_id,
        limit=RETRIEVAL_HISTORY_LIMIT,
    )
    if not history:
        return question

    # 当前问题放在最前面：Embedding和字面词提取都应优先关注本轮，而不是被较长的
    # 历史回答抢占前部。历史只负责补充“它/那个”等指代对象。
    lines = ["【当前问题】", question, "【最近对话，仅用于消解指代】"]
    for role, content in history:
        speaker = "用户" if role == "user" else "助手"
        normalized = content.strip().replace("\n", " ")
        if normalized:
            lines.append(f"{speaker}：{normalized[:RETRIEVAL_HISTORY_ITEM_CHARS]}")
    return "\n".join(lines)


async def prepare_text_chat_context(
    db: AsyncSession,
    *,
    question: str,
    session_id: int | None,
    user_id: int,
) -> ChatContext:
    """为纯文本提问准备检索结果与工具集。"""

    started_at = time.perf_counter()
    retrieval_query = await _build_contextual_retrieval_query(
        db,
        question=question,
        session_id=session_id,
        user_id=user_id,
    )

    # 意图模型也需要最近语境，否则“那它现在开放吗”无法判断该查知识还是实时工具。
    intent = await intent_services.classify(db, question=retrieval_query)
    intent_finished_at = time.perf_counter()

    # 未启用意图识别时 need_knowledge 视为 True，保证行为与以前一致。
    need_knowledge = True if intent is None else intent.need_knowledge
    retrieved_chunks: list[RetrievedChunk] = []
    if need_knowledge:
        try:
            retrieved_chunks = await knowledge_retrieval_services.search_knowledge(
                db,
                query=retrieval_query,
                focus_question=question,
                limit=CHAT_RETRIEVAL_LIMIT,
            )
        except CapabilityNotConfiguredError as exc:
            # 仅"能力未配置"允许降级：向量/精排没配好时，聊天仍可基于提示词回答。
            logger.warning(
                "chat degraded without RAG: capability=%s error=%s",
                exc.capability,
                exc.message,
            )
            retrieved_chunks = []

    # 检索与意图是模型调用之前的两段固定开销，单独记一行，慢的时候一眼能看出
    # 是“查资料慢”还是“模型慢”。
    logger.info(
        "chat pipeline intent=%.2fs retrieval=%.2fs chunks=%d intent_tools=%s need_knowledge=%s",
        intent_finished_at - started_at,
        time.perf_counter() - intent_finished_at,
        len(retrieved_chunks),
        None if intent is None else intent.need_tools,
        need_knowledge,
    )

    return ChatContext(
        retrieved_chunks=retrieved_chunks,
        tools=None if intent is None else _tools_for_intent(intent, question),
        intent=intent,
        # 未启用意图识别时保持原样：用 chat + 完整提示词。
        capability="chat" if intent is None else intent.chat_capability,
        prompt_style="full" if intent is None else intent.prompt_style,
    )
