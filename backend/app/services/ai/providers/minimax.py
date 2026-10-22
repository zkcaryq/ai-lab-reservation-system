"""MiniMax 供应商适配器：OpenAI 兼容 Responses API。

聊天/视觉/OCR 走 client.responses.create；模型列表走 OpenAI 兼容 GET /v1/models。
MiniMax 的 Responses 支持 reasoning.effort 调节思考深度，不支持 previous_response_id。
请求格式与错误处理完全封装在本类内，业务层不感知。
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import status
from openai import AsyncOpenAI, OpenAIError

from app.core.errors import BusinessException
from app.services.ai.providers.base import (
    MODEL_CATALOG,
    ChatProvider,
    ChatResult,
    ModelInfo,
    result_from_openai_response,
)

logger = logging.getLogger(__name__)


def _supports_capability(capability: str | None, meta: dict[str, object]) -> bool:
    """用本地元数据判断 MiniMax 模型是否支持项目能力。"""

    if capability is None:
        return True
    normalized = capability.strip().lower()
    # chat_light 是本项目的"轻量对话"能力位，与 chat 一样由通用文本模型承担。
    if normalized in {"chat", "chat_light", "intent", "decision"}:
        return True
    if normalized == "vision":
        return bool(meta.get("vision", False))
    # 当前 MiniMax 适配器没有实现 OCR、Embedding、Rerank 专用协议。
    return False


class MiniMaxProvider(ChatProvider):
    """MiniMax Responses 兼容接口适配器。"""

    provider_name = "minimax"

    @staticmethod
    def _build_options(
        *,
        reasoning_effort: str | None,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> dict[str, Any]:
        """拼 MiniMax 特有的请求选项；整包与流式两条路径共用，避免两处各写一遍。"""

        request_options: dict[str, Any] = {}
        if reasoning_effort is not None:
            # MiniMax M3.1-Flash 的 effort 档位：low/medium/high/xhigh/max。
            request_options["reasoning"] = {"effort": reasoning_effort}
        if tools:
            request_options["tools"] = tools
        if tool_choice is not None:
            request_options["tool_choice"] = tool_choice
        # 采样参数：只有管理员显式配置过才传，否则交给供应商默认值。
        if temperature is not None:
            request_options["temperature"] = temperature
        if top_p is not None:
            request_options["top_p"] = top_p
        return request_options

    async def create_response(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float,
        model: str,
        instructions: str,
        input: Any,
        max_output_tokens: int,
        reasoning_effort: str | None,
        extra_body: dict[str, Any] | None = None,
        dashscope_base_url: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> ChatResult:
        """执行非流式模型调用，并把供应商异常翻译为稳定业务异常。"""

        # MiniMax 不支持 extra_body 专有参数，也不使用 dashscope_base_url。
        request_options = self._build_options(
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            top_p=top_p,
        )

        try:
            async with AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout) as client:
                response = await client.responses.create(
                    model=model,
                    instructions=instructions,
                    input=input,
                    max_output_tokens=max_output_tokens,
                    **request_options,
                )
        except OpenAIError:
            logger.exception("minimax responses request failed")
            raise BusinessException(
                message="AI助手暂时不可用，请稍后重试！Ovo!",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from None
        return result_from_openai_response(response)

    async def stream_response(
        self,
        *,
        on_delta: Callable[[str], Awaitable[None]],
        api_key: str,
        base_url: str,
        timeout: float,
        model: str,
        instructions: str,
        input: Any,
        max_output_tokens: int,
        reasoning_effort: str | None,
        extra_body: dict[str, Any] | None = None,
        dashscope_base_url: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> ChatResult:
        """Responses 流式：逐字回调增量，最终结果取 ``response.completed`` 里的完整对象。

        不在前端自己拼工具调用：MiniMax 的 function_call 参数是分片下发的，
        手工攒 JSON 容易出错；``response.completed`` 带的就是和非流式完全一样的
        Response 对象，直接交给同一个提取函数，两条路径产出的 ChatResult 同形。
        """

        request_options = self._build_options(
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            top_p=top_p,
        )
        emitted_any = False
        final_response: Any = None

        try:
            async with AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout) as client:
                stream = await client.responses.create(
                    model=model,
                    instructions=instructions,
                    input=input,
                    max_output_tokens=max_output_tokens,
                    stream=True,
                    **request_options,
                )
                async for event in stream:
                    event_type = getattr(event, "type", "") or ""
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", "") or ""
                        if delta:
                            emitted_any = True
                            await on_delta(delta)
                    elif event_type == "response.completed":
                        final_response = getattr(event, "response", None)
            if final_response is None:
                # 流正常结束却没收到完成事件（网关行为不一致）：按失败处理，
                # 一个字都没发出去时还能走下面的回退，不至于给用户半截回答。
                raise OpenAIError("stream finished without response.completed")
        except OpenAIError:
            logger.exception("minimax responses stream failed")
            if emitted_any:
                # 已经吐过字了，回退重发会让前端出现重复正文，只能报错让用户重试。
                raise BusinessException(
                    message="AI助手回复中断，请重新提问！Ovo!",
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                ) from None
            # 还没输出任何内容 → 退回整包请求。用户最多是"没有打字机效果"，
            # 不会因为某一家网关不支持流式而整个助手不可用。
            return await self.create_response(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                model=model,
                instructions=instructions,
                input=input,
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                top_p=top_p,
            )
        return result_from_openai_response(final_response)

    async def list_models(
        self,
        *,
        api_key: str,
        base_url: str,
        capability: str | None = None,
        dashscope_base_url: str | None = None,
    ) -> list[ModelInfo]:
        """读取供应商模型列表，并按项目能力位做保守过滤。"""

        # OpenAI 兼容 GET /v1/models 只返回模型ID，元数据由 MODEL_CATALOG 补齐。
        # capability 软过滤：MiniMax 不返回能力字段，只能在元数据目录中查找。
        try:
            async with AsyncOpenAI(api_key=api_key, base_url=base_url) as client:
                page = await client.models.list()
        except OpenAIError:
            logger.exception("minimax list models failed")
            raise BusinessException(
                message="查询模型列表失败，请检查密钥和链接！Ovo!",
                status_code=status.HTTP_400_BAD_REQUEST,
            ) from None

        result: list[ModelInfo] = []
        for item in page.data:
            model_id = getattr(item, "id", "")
            if not model_id:
                continue
            meta = MODEL_CATALOG.get(model_id, {})
            # 旧代码使用 ``model_id not in meta``，实际是在检查模型ID是否是
            # 元数据字典的键，导致指定任何 capability 时全部模型都被过滤掉。
            if not _supports_capability(capability, meta):
                continue
            result.append(
                ModelInfo(
                    id=model_id,
                    name=str(meta.get("name", model_id)),
                    context_window=int(meta.get("context_window", 0)),
                    vision=bool(meta.get("vision", False)),
                    reasoning=bool(meta.get("reasoning", False)),
                )
            )
        return result
