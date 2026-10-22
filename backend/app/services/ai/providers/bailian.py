"""阿里云百炼供应商适配器。

聊天/视觉/OCR 走百炼的 OpenAI 兼容 Responses 端点（/compatible-mode/v1），
支持 extra_body 透传百炼专有参数（如 OCR 的 ocr_options）；
模型列表走 DashScope 专有 GET /api/v1/models（返回自带上下文长度与模态能力）。
请求格式与错误处理完全封装在本类内，业务层不感知。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import status
from openai import AsyncOpenAI, OpenAIError

from app.core.errors import BusinessException
from app.services.ai.providers.base import (
    ChatProvider,
    ChatResult,
    ModelInfo,
    result_from_openai_response,
)

logger = logging.getLogger(__name__)


def resolve_dashscope_base(openai_base: str, override: str | None = None) -> str:
    """从百炼 OpenAI 兼容地址派生 DashScope 根地址。

    - 若显式提供 ``override``（数据库列 ``dashscope_base_url``），优先使用；
    - 否则把 ``.../compatible-mode/v1`` 替换为 ``.../api/v1``；
    - 已形如 ``.../api/v1`` 的原样返回；
    - 其余情况原样返回，由调用方承担 404 后果。

    官方"查询模型列表"是 ``GET https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/models``，
    不同能力（embedding / rerank / list_models）的 endpoint 必须落在 ``/api/v1`` 根地址下。
    """
    if override:
        return override.rstrip("/")
    suffix = "/compatible-mode/v1"
    normalized = openai_base.rstrip("/")
    if normalized.endswith(suffix):
        return normalized.removesuffix(suffix) + "/api/v1"
    if normalized.endswith("/api/v1"):
        return normalized
    return normalized


# 项目内部能力名与百炼“查询模型列表”接口返回的官方能力码不是同一套值。
# 例如项目写 ``embedding``，百炼返回 ``ME``；不能直接比较字符串。
BAILIAN_CAPABILITY_CODES: dict[str, set[str]] = {
    "chat": {"TG"},
    # chat_light：「轻量对话」能力位，同样是通用文本生成模型。
    "chat_light": {"TG"},
    "vision": {"VU"},
    "embedding": {"ME"},
    # intent / decision 当前也是文本生成模型承担，因此按 TG 筛选。
    "intent": {"TG"},
    "decision": {"TG"},
}


# 把项目能力下推成百炼官方的服务端筛选参数。
# 不这么做的话，每查一次模型列表都要把 300+ 个模型全量翻页（4~5 次请求），
# 既慢又容易触发 429 限流 —— 管理员点"查询"会随机失败。
_SERVER_FILTER: dict[str, dict[str, str]] = {
    "chat": {"capabilities": "TG"},
    "chat_light": {"capabilities": "TG"},
    "intent": {"capabilities": "TG"},
    "decision": {"capabilities": "TG"},
    "vision": {"capabilities": "VU"},
    "embedding": {"capabilities": "ME"},
    # OCR / Rerank 没有同名官方能力码，用模型名模糊搜索代替全量翻页。
    "ocr": {"name": "ocr"},
    "rerank": {"name": "rerank"},
}

# 有专用模型的能力：把 ID 命中的排到最前，前端默认选中第一项。
# 注意这两个专用模型不走 Responses API（见 services/ai/intent_services.py 与
# decision_services.py 里的专用适配路径），但仍要出现在下拉框里，否则管理员选不到。
_PRIORITY_KEYWORDS: dict[str, str] = {
    "intent": "intent",
    "decision": "decision",
    "ocr": "ocr",
    "rerank": "rerank",
}


def _model_matches_capability(item: dict[str, Any], capability: str | None) -> bool:
    """按百炼官方能力码和专用模型名称筛选项目能力。

    OCR、Rerank 在模型列表中没有与项目同名的通用能力码，因此使用模型 ID
    关键词筛选；其余能力使用官方 ``capabilities`` 代码。没有指定能力时不过滤。
    """

    if capability is None:
        return True

    normalized = capability.strip().lower()
    model_id = str(item.get("model") or "").lower()
    if normalized == "ocr":
        return "ocr" in model_id
    if normalized == "rerank":
        return "rerank" in model_id

    if normalized in {"chat", "chat_light", "intent", "decision"} and any(
        marker in model_id for marker in ("ocr", "embedding", "rerank")
    ):
        return False

    wanted_codes = BAILIAN_CAPABILITY_CODES.get(normalized)
    if wanted_codes is None:
        return False
    capabilities = {str(value).upper() for value in (item.get("capabilities") or [])}
    return bool(capabilities & wanted_codes)


class BailianProvider(ChatProvider):
    """阿里云百炼适配器，把供应商接口统一成项目内部 ChatProvider 协议。"""

    provider_name = "bailian"

    @staticmethod
    def _build_options(
        *,
        reasoning_effort: str | None,
        extra_body: dict[str, Any] | None,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float | None,
        top_p: float | None,
    ) -> dict[str, Any]:
        """构造百炼 Responses 参数，供整包与流式调用共用。"""

        request_options: dict[str, Any] = {}
        if reasoning_effort is not None:
            request_options["reasoning"] = {"effort": reasoning_effort}
        if extra_body is not None:
            request_options["extra_body"] = extra_body
        if tools:
            request_options["tools"] = tools
        if tool_choice is not None:
            request_options["tool_choice"] = tool_choice
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
        """调用百炼 Responses 兼容端点，并转换成统一 ``ChatResult``。"""

        request_options = self._build_options(
            reasoning_effort=reasoning_effort,
            extra_body=extra_body,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            top_p=top_p,
        )

        # chat / vision / ocr 走 OpenAI 兼容端点（用户配置的 base_url）。
        # 若调用方意外传入了 dashscope_base_url，仍然使用原始 base_url，
        # 避免给 chat 端下发 /api/v1 后接口路径错误。
        openai_base = base_url
        try:
            async with AsyncOpenAI(
                api_key=api_key, base_url=openai_base, timeout=timeout
            ) as client:
                response = await client.responses.create(
                    model=model,
                    instructions=instructions,
                    input=input,
                    max_output_tokens=max_output_tokens,
                    **request_options,
                )
        except OpenAIError:
            logger.exception("bailian responses request failed")
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
        """调用百炼兼容 Responses 的原生流式接口。

        百炼与 MiniMax 都遵循 Responses 事件格式，但分别保留适配器实现，
        这样以后某家事件字段变化时不会污染另一家供应商。
        """

        request_options = self._build_options(
            reasoning_effort=reasoning_effort,
            extra_body=extra_body,
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
                raise OpenAIError("stream finished without response.completed")
        except OpenAIError:
            logger.exception("bailian responses stream failed")
            if emitted_any:
                raise BusinessException(
                    message="AI助手回复中断，请重新提问！Ovo!",
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                ) from None
            # 网关不支持流式或在首个 token 前失败时退回整包调用，保证可用性。
            return await self.create_response(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                model=model,
                instructions=instructions,
                input=input,
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
                extra_body=extra_body,
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
        """查询百炼全部可用模型并按项目 capability 过滤。

        - 官方 endpoint: GET ``{baseUrl}/api/v1/models``，Bearer 鉴权；
        - 返回结构在 ``output.models``，元素含 ``model``/``name``/
          ``capabilities``/``model_info.context_window``/
          ``inference_metadata.request_modality`` 等；
        - 401/403/404/5xx 会按业务类型抛出 400/401/403/502，方便前端按
          弹层文案提示"密钥错误/无权限/链接错误"等，不混为通用 500。
        """
        url = resolve_dashscope_base(base_url, dashscope_base_url) + "/models"
        all_models: list[dict[str, Any]] = []
        page_no = 1
        page_size = 100
        server_filter = _SERVER_FILTER.get((capability or "").strip().lower(), {})
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                while True:
                    params = {"page_no": page_no, "page_size": page_size, **server_filter}
                    # 429 是频率限制而不是参数错误：短退避重试两次，比让管理员
                    # 看到"查询失败"更友好；仍失败则走下面统一的 HTTP 错误处理。
                    for attempt in range(3):
                        response = await client.get(
                            url,
                            headers={"Authorization": "Bearer " + api_key},
                            params=params,
                        )
                        if response.status_code != 429 or attempt == 2:
                            break
                        await asyncio.sleep(1.5 * (attempt + 1))
                    # 4xx/5xx：先按状态码映射到具体业务错误，输出更可读的中文 message。
                    if response.status_code in (401, 403):
                        request_id = response.headers.get("x-request-id", "-")
                        logger.warning(
                            "bailian list models unauthorized status=%s provider_request_id=%s",
                            response.status_code,
                            request_id,
                        )
                        raise BusinessException(
                            message="查询模型列表失败：密钥错误或无权限，请检查 API Key！Ovo!",
                            # 不能透传上游的 401：本项目的 HTTP 401 专指"调用方的登录
                            # 凭证失效"，前端 request.js 见 401 会清 token 并跳登录页，
                            # 于是"管理员填错百炼 Key"会把人从系统里踢出去。
                            # 上游鉴权失败属于本次请求的参数问题 → 400，与 MiniMax 一致。
                            status_code=status.HTTP_400_BAD_REQUEST,
                        )
                    if response.status_code == 404:
                        request_id = response.headers.get("x-request-id", "-")
                        logger.warning(
                            "bailian list models not found status=%s provider_request_id=%s",
                            response.status_code,
                            request_id,
                        )
                        raise BusinessException(
                            message=(
                                "查询模型列表失败：链接无效（404），"
                                "请确认 base_url 与地域/工作空间匹配！Ovo!"
                            ),
                            status_code=status.HTTP_400_BAD_REQUEST,
                        )
                    if response.status_code >= 500:
                        request_id = response.headers.get("x-request-id", "-")
                        logger.warning(
                            "bailian list models upstream error status=%s provider_request_id=%s",
                            response.status_code,
                            request_id,
                        )
                        raise BusinessException(
                            message="查询模型列表失败：上游服务暂时不可用，请稍后重试！Ovo!",
                            status_code=status.HTTP_502_BAD_GATEWAY,
                        )
                    response.raise_for_status()
                    data = response.json()
                    output = data.get("output") or {}
                    page_models = output.get("models") or []
                    all_models.extend(page_models)

                    total = int(output.get("total") or 0)
                    reached_total = total > 0 and len(all_models) >= total
                    short_page_without_total = total == 0 and len(page_models) < page_size
                    if not page_models or reached_total or short_page_without_total:
                        break
                    page_no += 1
                    if page_no > 100:
                        logger.warning("bailian model pagination stopped after 100 pages")
                        break
        except BusinessException:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            request_id = getattr(getattr(exc, "response", None), "headers", {}).get(
                "x-request-id", "-"
            )
            logger.exception(
                "bailian list models failed provider_request_id=%s",
                request_id,
            )
            raise BusinessException(
                message="查询模型列表失败，请检查密钥和链接！Ovo!",
                status_code=status.HTTP_400_BAD_REQUEST,
            ) from None

        result: list[ModelInfo] = []
        seen_ids: set[str] = set()
        for item in all_models:
            model_id = item.get("model", "")
            if not model_id or model_id in seen_ids:
                continue
            if not _model_matches_capability(item, capability):
                continue
            seen_ids.add(model_id)
            capabilities = item.get("capabilities") or []
            model_info = item.get("model_info") or {}
            request_modality = (item.get("inference_metadata") or {}).get("request_modality") or []
            result.append(
                ModelInfo(
                    id=model_id,
                    name=item.get("name", model_id),
                    context_window=int(model_info.get("context_window") or 0),
                    vision=("VU" in capabilities) or ("Image" in request_modality),
                    reasoning=("Reasoning" in capabilities),
                )
            )

        # 专用模型优先：意图识别、决策、OCR、重排序都有官方专用模型，
        # 排到前面可以让前端默认选中它们，而不是某个通用文本模型。
        priority = _PRIORITY_KEYWORDS.get((capability or "").strip().lower())
        if priority:
            result.sort(key=lambda model: (priority not in model.id.lower(), model.id))
        return result
