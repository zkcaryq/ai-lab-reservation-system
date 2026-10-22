"""AI 对话的 SSE 事件编排。

本模块只负责把 ``ai_services.chat()`` 的整体协程转换为可逐条消费的事件流；
会话、Agent、模型调用与落库仍由 ``ai_services`` 负责，HTTP 帧格式由 Router 负责。
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessException
from app.schemas.ai_schemas import ChatRequest
from app.services.ai import ai_services
from app.services.knowledge.knowledge_retrieval_services import RetrievedChunk

logger = logging.getLogger(__name__)


async def stream_chat(
    data: ChatRequest,
    *,
    db: AsyncSession,
    user_id: int,
    retrieved_chunks: list[RetrievedChunk],
    query_image_path: Path | None = None,
    tools: list[dict[str, Any]] | None = None,
    capability: str = "chat",
    prompt_style: str = "full",
) -> AsyncIterator[dict[str, Any]]:
    """边执行一轮聊天，边产生 status/tool/token/done/error 事件。"""

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        """生产者回调：把业务事件放入本请求专属队列。"""

        await queue.put(event)

    async def runner() -> None:
        """在后台执行完整聊天，并保证最终写入完成或错误哨兵。"""

        try:
            result = await ai_services.chat(
                data,
                db=db,
                user_id=user_id,
                retrieved_chunks=retrieved_chunks,
                query_image_path=query_image_path,
                emit=emit,
                tools=tools,
                capability=capability,
                prompt_style=prompt_style,
            )
            # message 是最终写入数据库的规范正文。前端实时展示 token，收到 done 后
            # 用 message 校正中间轮文本，保证当前视图与刷新后的历史记录一致。
            await queue.put(
                {
                    "type": "done",
                    "message": result.message,
                    "session_id": result.session_id,
                    "model": result.model,
                    "usage": result.usage.model_dump() if result.usage else None,
                    "sources": [source.model_dump(mode="json") for source in result.sources],
                    "used_tools": result.used_tools,
                    "duration_ms": result.duration_ms,
                    "pending_action": (
                        result.pending_action.model_dump(mode="json")
                        if result.pending_action is not None
                        else None
                    ),
                }
            )
        except BusinessException as exc:
            await queue.put({"type": "error", "message": exc.message})
        except Exception:
            logger.exception("AI流式对话失败")
            await queue.put({"type": "error", "message": "AI助手暂时不可用，请稍后重试！Ovo!"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        # 浏览器中途断开时取消后台模型调用，避免无人接收时仍消耗 token、占用 Session。
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
