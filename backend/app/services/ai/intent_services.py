"""意图识别：在检索之前判断"这轮要不要查知识库、要开哪些工具"。

能力名 ``intent``，由管理员在 AI 供应商配置页单独配置供应商/模型/密钥。
这是**可选增强**：未配置、调用失败或输出无法解析时一律返回 ``None``，
调用方必须按"知识库要查、工具全开"处理，即完全退回加意图识别之前的行为。

两条调用路径（按模型名自动选择）：

1. 百炼专用意图理解模型 ``tongyi-intent-detect-v3``：
   走 **OpenAI 兼容 Chat Completions**（不是 Responses API），按官方文档用
   "tag 列表 + just reply with the chosen tag" 的 system prompt，模型只回一个字母。
2. 其它文本模型：走项目统一的 Responses API，让它输出 JSON。

之所以要分成两条，是因为专用模型有自己的提示词协议，套用通用 JSON 提示词会返回
非预期结构；反过来通用模型也输出不了单字母 tag。
"""

import json
import logging
import re

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import ai_provider_services, ai_usage_services
from app.services.ai.providers import get_provider
from app.services.ai.providers.base import ChatResult

logger = logging.getLogger(__name__)

# 分类只需要极短输出；给太大会让模型开始"解释自己"，反而更容易破坏 JSON。
INTENT_MAX_OUTPUT_TOKENS = 600
# 意图识别的兜底超时。分类任务卡住 60 秒会直接把聊天拖死，所以这里给得很短；
# 管理员仍可在配置页用 timeout_seconds 覆盖。
INTENT_DEFAULT_TIMEOUT = 15.0
# 提问过长没有意义，截断避免把整个对话塞进分类请求。
_QUESTION_CHARS = 1200

# 百炼「意图理解」专用模型：只支持 Chat Completions，走 tag 模式。
BAILIAN_INTENT_MODEL = "tongyi-intent-detect-v3"

# tag 表：官方文档建议用单个大写字母指代分类，模型只输出 1 个 token，响应最快。
# 字段含义：分类描述、是否需要查知识库、需要开启哪些工具、
# 走哪个对话能力位（chat / chat_light）、用哪套系统提示词（full / light）。
INTENT_TAG_SPECS: dict[str, dict[str, object]] = {
    "A": {
        "desc": "知识库问答：使用方法、操作步骤、安全规范、管理制度、开放安排、预约规则等",
        "knowledge": True,
        "tools": [],
        "capability": "chat",
        "prompt": "full",
    },
    "B": {
        "desc": "实时数据查询：当前有哪些实验室开放、某个实验室登记了哪些设备",
        "knowledge": False,
        "tools": ["list_open_labs", "list_lab_equipments"],
        "capability": "chat",
        "prompt": "full",
    },
    "C": {
        "desc": "创建预约：用户明确要求帮他预约某个实验室或设备",
        "knowledge": True,
        "tools": ["list_open_labs", "list_lab_equipments", "prepare_reservation"],
        "capability": "chat",
        "prompt": "full",
    },
    "D": {
        "desc": "寒暄、感谢、与实验室预约系统无关的闲聊",
        "knowledge": False,
        "tools": [],
        # 闲聊不需要那 105 行实验室规矩，也不值得用最贵的模型。
        # chat_light 未配置时 ai_services 会自动回退到 chat。
        "capability": "chat_light",
        "prompt": "light",
    },
    "E": {
        "desc": (
            "混合查询：同一问题既需要当前实验室/设备实时数据，又需要知识库中的"
            "制度、手册、安全规则或开放安排进行综合判断"
        ),
        "knowledge": True,
        "tools": ["list_open_labs", "list_lab_equipments"],
        "capability": "chat",
        "prompt": "full",
    },
}

_JSON_OBJECT = re.compile(r"\{.*\}", re.S)
_TAG_LETTER = re.compile(r"[A-Z]")

INTENT_INSTRUCTION = """你是"AI智能实验室预约系统"的意图分类器。只输出一个 JSON 对象，不要输出任何解释或 Markdown 代码块。

字段：
- "need_knowledge"（布尔）：回答该问题是否需要查阅实验室知识库（使用手册、安全规范、管理制度、设备参数、开放安排等）。寒暄、感谢、纯闲聊、与本系统无关的问题填 false；其余情况填 true。
- "need_tools"（字符串数组）：回答该问题需要调用的实时数据工具，只能是以下三个值：
  "list_open_labs"：查询当前开放的实验室；
  "list_lab_equipments"：查询某个实验室登记了哪些设备；
  "prepare_reservation"：用户明确要求创建预约（如"帮我约""预约一下"）。
  不需要任何工具时填空数组。
- "reason"（字符串）：一句话理由，不超过 20 字。

判断规则：
1. 不确定时 need_knowledge 填 true，宁可多查。
2. 只有用户明确表达预约意图时才放 prepare_reservation；只是询问预约规则时不要放。
3. 询问当前有哪些实验室、某实验室有哪些设备时，把对应的查询工具放进 need_tools。
"""


class IntentResult(BaseModel):
    """一次意图识别的结构化结果。"""

    need_knowledge: bool = True
    need_tools: list[str] = Field(default_factory=list)
    reason: str = ""
    # 走哪个对话能力位（chat / chat_light）；默认 chat，等于"不分级"。
    chat_capability: str = "chat"
    # 用哪套系统提示词：full（完整实验室规矩）/ light（闲聊短提示词）。
    prompt_style: str = "full"


def _extract_json(raw: str) -> dict[str, object] | None:
    """从模型输出里抠出第一个 JSON 对象；失败返回 None。"""

    text = (raw or "").strip()
    if not text:
        return None
    match = _JSON_OBJECT.search(text)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_intent(raw: str) -> IntentResult | None:
    """把模型输出解析成 IntentResult；任何异常都返回 None 由调用方降级。"""

    payload = _extract_json(raw)
    if payload is None:
        return None
    try:
        return IntentResult.model_validate(payload)
    except ValidationError:
        # 例如模型把 need_tools 返回成布尔值。这里不猜测它想表达什么，
        # 直接降级成"全部都要"，行为等同于未启用该能力。
        return None


def _build_tag_prompt() -> str:
    """按官方文档拼"只输出意图"的 system prompt。"""

    tag_list = {key: spec["desc"] for key, spec in INTENT_TAG_SPECS.items()}
    return (
        "You are Qwen, created by Alibaba Cloud. You are a helpful assistant.\n"
        "You should choose one tag from the tag list:\n"
        f"{json.dumps(tag_list, ensure_ascii=False)}\n"
        "just reply with the chosen tag."
    )


def _intent_from_tag(raw: str) -> IntentResult | None:
    """把单字母 tag 映射成 IntentResult；不在表里就返回 None。"""

    match = _TAG_LETTER.search((raw or "").upper())
    if match is None:
        return None
    spec = INTENT_TAG_SPECS.get(match.group(0))
    if spec is None:
        return None
    return IntentResult(
        need_knowledge=bool(spec["knowledge"]),
        need_tools=list(spec["tools"]),  # type: ignore[arg-type]
        reason=str(spec["desc"]),
        chat_capability=str(spec["capability"]),
        prompt_style=str(spec["prompt"]),
    )


def _chat_result_from_usage(data: dict, text: str) -> ChatResult:
    """把 Chat Completions 的 usage 映射成项目统一的 ChatResult。"""

    usage = data.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
    return ChatResult(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


async def _classify_with_tag_model(
    config: ai_provider_services.CapabilityConfig,
    *,
    question: str,
) -> tuple[IntentResult | None, ChatResult]:
    """调用百炼意图理解专用模型（Chat Completions + tag 模式）。"""

    url = config.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": config.model.strip(),
        "messages": [
            {"role": "system", "content": _build_tag_prompt()},
            {"role": "user", "content": question[:_QUESTION_CHARS]},
        ],
        # 只回一个字母，8 个 token 足够；温度 0 让同一问题结果稳定。
        "max_tokens": 8,
        "temperature": 0,
    }
    timeout = config.timeout_seconds or INTENT_DEFAULT_TIMEOUT
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": "Bearer " + config.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    content = ""
    if choices:
        content = str((choices[0].get("message") or {}).get("content") or "")
    return _intent_from_tag(content), _chat_result_from_usage(data, content)


async def _classify_with_generic_model(
    config: ai_provider_services.CapabilityConfig,
    *,
    question: str,
) -> tuple[IntentResult | None, ChatResult]:
    """调用通用文本模型（Responses API + JSON 提示词）。"""

    provider_impl = get_provider(config.provider)
    result = await provider_impl.create_response(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds or INTENT_DEFAULT_TIMEOUT,
        model=config.model.strip(),
        instructions=INTENT_INSTRUCTION,
        input=question[:_QUESTION_CHARS],
        max_output_tokens=INTENT_MAX_OUTPUT_TOKENS,
        # 分类不需要思考链；固定关闭，避免思考 token 吃掉输出预算后返回空文本。
        reasoning_effort=None,
        dashscope_base_url=config.dashscope_base_url,
    )
    return parse_intent(result.text), result


async def classify(db: AsyncSession | None, *, question: str) -> IntentResult | None:
    """识别一条用户提问的意图；未配置或失败时返回 None。"""

    config = await ai_provider_services.get_capability_config(db, "intent")
    if config is None or not config.api_key or not config.model.strip():
        # 没配置就是没启用，静默返回，不算错误。
        return None

    is_tag_model = config.model.strip() == BAILIAN_INTENT_MODEL
    try:
        if is_tag_model:
            intent, result = await _classify_with_tag_model(config, question=question)
        else:
            intent, result = await _classify_with_generic_model(config, question=question)
    except Exception:
        # 任何失败（网络、鉴权、上游 5xx、响应结构异常）都不能影响聊天主流程。
        logger.warning("intent classification failed; falling back to full pipeline", exc_info=True)
        return None

    await ai_usage_services.record_usage(
        db,
        capability="intent",
        provider=config.provider,
        model=config.model,
        result=result,
        commit=False,
    )

    if intent is None:
        logger.warning(
            "intent output was not recognized; falling back to full pipeline raw=%r",
            (result.text or "")[:200],
        )
    return intent
