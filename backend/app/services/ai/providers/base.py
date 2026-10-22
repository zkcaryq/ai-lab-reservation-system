"""AI 供应商抽象基类。

业务层（ai_services 等）只依赖这里的抽象接口，不感知具体供应商的请求格式。
MiniMax 与百炼各自实现 ChatProvider：聊天/视觉/OCR 都走“创建一轮 Response”，
模型列表走“查询可用模型”，请求格式完全封装在各实现类内部。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    """供应商返回的一次函数工具调用。"""

    call_id: str
    name: str
    arguments: str


@dataclass(slots=True)
class ChatResult:
    """一次模型调用的统一返回：文本、工具调用和用量。"""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # 保存Responses本轮完整output，下一轮要原样放回input。
    # MiniMax工具调用可能同时返回reasoning、message和function_call，
    # 只保留function_call会丢失交错思考所需的上下文。
    response_items: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class ModelInfo:
    """统一口径的模型元数据。"""

    id: str
    name: str
    context_window: int = 0
    vision: bool = False
    reasoning: bool = False


def result_from_openai_response(response: Any) -> ChatResult:
    """提取Responses返回的正文、function_call和统一Token用量。"""

    tool_calls: list[ToolCall] = []
    # 官方建议把上一轮完整output放回下一轮input，以保留工具调用和推理连续性。
    response_items = list(getattr(response, "output", None) or [])

    # Responses API把输出放在response.output列表中。
    for item in response_items:
        if getattr(item, "type", None) != "function_call":
            continue
        call_id = str(getattr(item, "call_id", "") or "")
        name = str(getattr(item, "name", "") or "")
        arguments = str(getattr(item, "arguments", "{}") or "{}")
        if call_id and name:
            tool_calls.append(
                ToolCall(
                    call_id=call_id,
                    name=name,
                    arguments=arguments,
                )
            )

    usage = getattr(response, "usage", None)
    if usage is None:
        return ChatResult(
            text=(getattr(response, "output_text", "") or "").strip(),
            tool_calls=tool_calls,
            response_items=response_items,
        )

    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    cached = getattr(input_details, "cached_tokens", None) if input_details else None
    reasoning = getattr(output_details, "reasoning_tokens", None) if output_details else None

    return ChatResult(
        text=(getattr(response, "output_text", "") or "").strip(),
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        reasoning_tokens=int(reasoning) if reasoning is not None else None,
        cached_tokens=int(cached) if cached is not None else None,
        tool_calls=tool_calls,
        response_items=response_items,
    )


# 已知模型的静态元数据：窗口大小、是否多模态、是否支持思考层级。
# 用于给“不返回元数据的供应商接口”（如 MiniMax 的 GET /v1/models）补全信息；
# 窗口大小以官网为准，这里给保守默认值，前端展示“已用X/窗口Y”。
MODEL_CATALOG: dict[str, dict[str, object]] = {
    "MiniMax-M3.1-Flash": {
        "name": "MiniMax M3.1 Flash",
        "context_window": 1_000_000,
        "vision": True,
        "reasoning": True,
    },
    "MiniMax-M3": {
        "name": "MiniMax M3",
        "context_window": 1_000_000,
        "vision": True,
        "reasoning": True,
    },
}


class ChatProvider(ABC):
    """聊天 / 视觉 / OCR 共用的供应商抽象。"""

    provider_name: str = ""

    @abstractmethod
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
        # 管理员可调的采样参数；None 表示不传，由供应商用默认值。
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> ChatResult:
        """发起一轮对话，返回统一文本与用量。请求格式由实现类决定。

        extra_body 用于透传供应商专有参数（如百炼 OCR 的 ocr_options），
        不支持的供应商应忽略该参数。dashscope_base_url 是百炼专有 /api/v1
        入口，其它供应商忽略即可。
        """

    async def stream_response(
        self,
        *,
        on_delta: Callable[[str], Awaitable[None]],
        **kwargs: Any,
    ) -> ChatResult:
        """流式版本：边生成边把文本增量交给 ``on_delta``，最终返回与 create_response 同形的结果。

        为什么用回调而不是异步生成器：Agent 图必须拿到完整的 ChatResult
        （含 tool_calls 和 response_items）才能决定下一步是调工具还是结束，
        纯生成器会把"消费增量"和"取最终结果"两件事拆开，图里要自己再攒一遍。

        默认实现**不流式**：整包取回后把全文当作一次增量回调。
        没覆写本方法的供应商（例如当前百炼路径）因此照样能用于 SSE 接口，
        只是没有打字机效果，过程事件仍然完整。
        """

        result = await self.create_response(**kwargs)
        if result.text:
            await on_delta(result.text)
        return result

    @abstractmethod
    async def list_models(
        self,
        *,
        api_key: str,
        base_url: str,
        capability: str | None = None,
        dashscope_base_url: str | None = None,
    ) -> list[ModelInfo]:
        """查询该供应商可用模型列表；各家用各自接口格式并归一化。

        ``capability`` 用于按能力软过滤（chat/embedding/...）；
        ``dashscope_base_url`` 给百炼使用，其它供应商忽略。
        """
