"""AI助手HTTP路由。

请求调用链：客户端 → 本文件的 ``chat()`` → ``services/ai_services.py`` 的
``chat()`` → 供应商抽象层（providers 包，按配置路由到 MiniMax/百炼）→ 统一ApiResponse。
"""

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

# APIRouter用于定义AI模块自己的URL前缀、标签和接口。
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi import Path as PathParameter
from fastapi.responses import FileResponse, StreamingResponse

# Router只负责编排HTTP流程，实际模型调用封装在Service中。
from app.api.dependencies import CurrentUser, DbSession
from app.core.errors import BusinessException

# CurrentUser要求请求携带有效Bearer Token，并返回数据库中状态正常的用户。
# ChatRequest负责把请求JSON转换成Python对象并在进入函数前完成字段校验。
from app.schemas.ai_schemas import (
    ChatRequest,
    ProviderConfigUpsertRequest,
    ProviderModelsRequest,
    SessionTitleRequest,
)

# ApiResponse为所有业务接口提供统一的code/message/data响应外壳。
from app.schemas.apiresponse import ApiResponse
from app.services.ai import (
    ai_action_services,
    ai_provider_services,
    ai_services,
    ai_usage_services,
    chat_pipeline_services,
    chat_services,
    stream_services,
)
from app.services.ai.ai_provider_services import (
    VALID_CAPABILITIES,
    VALID_PROVIDERS,
    CapabilityNotConfiguredError,
    validate_provider_for_capability,
)
from app.services.ai.ai_rate_limit_services import rate_limiter
from app.services.knowledge import knowledge_retrieval_services
from app.services.knowledge.bailian_document_services import describe_image
from app.services.knowledge.knowledge_storage_services import (
    KnowledgeFileTooLargeError,
    delete_query_image,
    save_query_image,
)

# 当前子路由前缀是/ai；挂到总/api路由后，最终公共前缀为/api/ai。
# tags控制Swagger文档中的接口分组名称。
router = APIRouter(prefix="/ai", tags=["AI助手"])
logger = logging.getLogger(__name__)


async def require_ai_rate_limit(current_user: CurrentUser) -> None:
    """AI 聊天接口的轻量限流：只挡“请求过密”，不做预算/计费。

    只有会触发外部付费调用的三个入口挂这个依赖；其它只读/管理接口不受影响。
    """

    if not rate_limiter.allow(current_user.id):
        raise BusinessException(
            message="请求太频繁，请稍后再试！Ovo!",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


@router.post("/actions/{action_id}/confirm")
async def confirm_action(
    session: DbSession,
    current_user: CurrentUser,
    action_id: int = PathParameter(gt=0),
) -> ApiResponse:
    """确认本人AI预约草稿，并创建真实预约。"""

    result = await ai_action_services.confirm_reservation_action(
        session,
        user_id=current_user.id,
        action_id=action_id,
    )
    message = (
        "预约已经确认过，无需重复提交！Ovo!"
        if result.already_confirmed
        else ("预约已提交，请等待审核！Ovo!")
    )
    return ApiResponse.success(message=message, data=result)


@router.patch("/actions/{action_id}/cancel")
async def cancel_action(
    session: DbSession,
    current_user: CurrentUser,
    action_id: int = PathParameter(gt=0),
) -> ApiResponse:
    """取消本人尚未确认的AI预约草稿。"""

    await ai_action_services.cancel_reservation_action(
        session,
        user_id=current_user.id,
        action_id=action_id,
    )
    return ApiResponse.success(message="预约草稿已取消！Ovo!")


# 会话管理接口：列表、详情、删除、清空。多轮对话历史持久化在数据库，
# 由这些接口配合前端“历史会话”和“清空会话”功能。
@router.get("/sessions")
async def list_sessions(session: DbSession, current_user: CurrentUser) -> ApiResponse:
    """返回当前用户的会话摘要列表，按最后活跃时间倒序。"""

    sessions = await chat_services.list_sessions(session, user_id=current_user.id)
    return ApiResponse.success(data=sessions)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """返回会话详情（含完整消息历史）。"""

    detail = await chat_services.get_session_detail(
        session,
        user_id=current_user.id,
        session_id=session_id,
    )
    if detail is None:
        raise BusinessException(
            message="会话不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    # 消息表只存 role+content，确认卡片要靠动作表恢复；单独查一次再拼进详情。
    detail.pending_actions = await ai_action_services.list_session_actions(
        session,
        user_id=current_user.id,
        chat_session_id=session_id,
    )
    return ApiResponse.success(data=detail)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """删除会话及其全部消息。"""

    ok = await chat_services.delete_session(
        session,
        user_id=current_user.id,
        session_id=session_id,
    )
    if not ok:
        raise BusinessException(
            message="会话不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return ApiResponse.success(message="删除成功")


@router.delete("/sessions/{session_id}/messages")
async def clear_session(
    session_id: int,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """清空会话消息但保留会话本身（“清空会话”而非删除会话）。"""

    ok = await chat_services.clear_session(
        session,
        user_id=current_user.id,
        session_id=session_id,
    )
    if not ok:
        raise BusinessException(
            message="会话不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return ApiResponse.success(message="清空成功")


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: int,
    data: SessionTitleRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """修改会话标题。

    标题原本只在建会话时由首条提问截前30字生成，问一句"你好"就永久叫"你好"，
    用户没法改成自己认得的名字，所以单独给一个改名接口（只动 title 一列）。
    """

    ok = await chat_services.rename_session(
        session,
        user_id=current_user.id,
        session_id=session_id,
        title=data.title,
    )
    if not ok:
        # 不存在与不属于本人都按404处理，不透露别人会话的存在性。
        raise BusinessException(
            message="会话不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return ApiResponse.success(message="标题修改成功！Ovo!")


# 最终地址是POST /api/ai/chat。
@router.get("/models")
async def list_models(session: DbSession, _current_user: CurrentUser) -> ApiResponse:
    """返回前端展示用的模型元数据（窗口大小等）。

    必须把 ``chat`` 与 ``chat_light`` 都列出来：一次聊天实际用的是哪个模型，
    只有当轮响应里的 ``model`` 说了算。前端拿这里返回的列表按模型名回查窗口，
    少一个就会导致"换了轻量模型后上下文进度条消失"。
    """

    configured: list[tuple[str, int | None]] = []
    for capability in ("chat", "chat_light"):
        config = await ai_provider_services.get_capability_config(session, capability)
        if config is None or not config.model.strip():
            continue
        configured.append((config.model.strip(), config.context_window))
    return ApiResponse.success(data=ai_services.list_available_models(configured))


@router.get("/usage/summary")
async def usage_summary(
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """按能力聚合最近30天的token用量（仅管理员）。"""

    if current_user.role != "admin":
        raise BusinessException(
            message="仅管理员可查看用量！Ovo!",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    summary = await ai_usage_services.get_usage_summary(session)
    return ApiResponse.success(data=summary)


@router.get("/usage/cost")
async def usage_cost(
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """按能力/供应商/模型聚合最近30天用量并估算花费（仅管理员）。"""

    if current_user.role != "admin":
        raise BusinessException(
            message="仅管理员可查看花费！Ovo!",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    summary = await ai_usage_services.get_cost_summary(session)
    return ApiResponse.success(data=summary)


@router.post("/provider/models")
async def list_provider_models(
    data: ProviderModelsRequest,
    current_user: CurrentUser,
) -> ApiResponse:
    """管理员填key后动态查询某供应商的可用模型列表（仅管理员，key不落库）。"""

    if current_user.role != "admin":
        raise BusinessException(
            message="仅管理员可查询模型列表！Ovo!",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    # Pydantic 只做长度校验；这里对照合法集二次校验，避免未登记供应商
    # 直接落到 providers/__init__ 的 ValueError，最终变成无说明 500。
    if data.provider not in VALID_PROVIDERS:
        raise BusinessException(
            message=(f"不支持的供应商：{data.provider}！可选值：{'/'.join(VALID_PROVIDERS)}"),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if data.capability is not None and data.capability not in VALID_CAPABILITIES:
        raise BusinessException(
            message=(f"不支持的能力：{data.capability}！可选值：{'/'.join(VALID_CAPABILITIES)}"),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if data.capability is not None:
        validate_provider_for_capability(data.capability, data.provider)
    models = await ai_services.fetch_provider_models(
        provider=data.provider,
        base_url=data.base_url,
        api_key=data.api_key,
        capability=data.capability,
    )
    return ApiResponse.success(data=models)


@router.get("/admin/configs")
async def list_configs(
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """列出全部能力的供应商配置（仅管理员，密钥脱敏）。"""

    if current_user.role != "admin":
        raise BusinessException(
            message="仅管理员可查看配置！Ovo!",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    configs = await ai_provider_services.list_configs(session)
    return ApiResponse.success(data=configs)


@router.put("/admin/configs/{capability}")
async def upsert_config(
    capability: str,
    data: ProviderConfigUpsertRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """保存/更新某个能力的供应商配置（仅管理员，key加密入库）。"""

    if current_user.role != "admin":
        raise BusinessException(
            message="仅管理员可修改配置！Ovo!",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    await ai_provider_services.upsert_config(
        session,
        capability=capability,
        data=data,
    )
    return ApiResponse.success(message="保存成功")


@router.post("/chat", dependencies=[Depends(require_ai_rate_limit)])
async def chat(
    data: ChatRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """检索当前问题的知识依据，再调用已配置供应商的 Responses 生成回答。

    意图识别、知识检索与工具集选择统一收在 ``chat_pipeline_services`` 里：
    ``intent`` 能力未配置时自动退化为"检索照常、工具全开"，与加入该能力之前一致；
    RAG 依赖能力未配置时仍降级为不带知识库的聊天。
    """

    context = await chat_pipeline_services.prepare_text_chat_context(
        session,
        question=data.message,
        session_id=data.session_id,
        user_id=current_user.id,
    )

    # chat()负责会话历史读写和模型调用；db与user_id用于定位/创建会话。
    result = await ai_services.chat(
        data,
        db=session,
        user_id=current_user.id,
        retrieved_chunks=context.retrieved_chunks,
        tools=context.tools,
        capability=context.capability,
        prompt_style=context.prompt_style,
    )

    return ApiResponse.success(data=result)


def _sse_line(payload: dict) -> str:
    """拼一条 SSE 帧：必须以 ``data: `` 开头，并以空行结束。

    ``ensure_ascii=False`` 让中文原样输出，否则前端拿到一堆 \\uXXXX。
    """

    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/stream", dependencies=[Depends(require_ai_rate_limit)])
async def chat_stream(
    data: ChatRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    """SSE 流式对话：正文逐字输出 + Agent 过程可见。

    鉴权仍走 CurrentUser，所以未登录是在这里就 401，不会先返回一个
    ``text/event-stream`` 再报错 —— 前端据此能区分"没登录"和"流出错"。

    为什么不用 EventSource：它只支持 GET，也带不了 Authorization 头。
    前端改用 fetch + ReadableStream 读同一份帧格式。
    """

    # 意图识别与检索放在返回 StreamingResponse 之前：这一步失败还能返回正常的
    # JSON 错误，一旦开始推流就只能靠 error 事件了。
    context = await chat_pipeline_services.prepare_text_chat_context(
        session,
        question=data.message,
        session_id=data.session_id,
        user_id=current_user.id,
    )

    async def event_gen() -> AsyncIterator[str]:
        """把 Service 产生的结构化事件编码成 SSE 文本帧。"""

        async for event in stream_services.stream_chat(
            data,
            db=session,
            user_id=current_user.id,
            retrieved_chunks=context.retrieved_chunks,
            tools=context.tools,
            capability=context.capability,
            prompt_style=context.prompt_style,
        ):
            yield _sse_line(event)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # 明确不压缩：中间层一旦缓冲整段，"过程可见"就退化成一次性刷出全部事件
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/image", dependencies=[Depends(require_ai_rate_limit)])
async def chat_with_image(
    session: DbSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(description="用于本轮提问的JPG、PNG或WebP图片")],
    message: Annotated[str, Form(max_length=4_000)] = "请根据这张图片回答问题",
    session_id: Annotated[int | None, Form()] = None,
) -> ApiResponse:
    """使用用户上传图片与可选文字进行多模态检索和回答。

    当 RAG（embedding/rerank）未配置时优雅降级为仅基于图片的视觉对话；
    当视觉理解（vision）能力也未配置时，本接口直接返回 503，告知用户
    "AI助手尚未配置"，避免给图片却不给文字的奇怪回答。
    """

    query_image_path: Path | None = None
    try:
        # ChatRequest复用文字接口的去空格和长度校验，避免两套规则逐渐不一致。
        data = ChatRequest(
            message=message,
            session_id=session_id,
        )
        query_image_path = await save_query_image(file)

        # 仅在 RAG 能力可用时执行检索；视觉/OCR 任一可用就允许聊天，
        # 检索与视觉本身不耦合。
        retrieved_chunks: list[knowledge_retrieval_services.RetrievedChunk] = []
        retrieval_query = data.message
        image_description: str | None = None
        try:
            # describe_image 调用 vision 能力；vision 未配置时本调用会抛 503。
            # 此时整条链路不可用，直接抛出由 BusinessExceptionHandler 处理。
            image_description = await describe_image(
                query_image_path,
                surrounding_text=data.message,
            )
        except BusinessException as exc:
            # vision/embedding 没配：把图片理解为"不可用"，按通用错误返回。
            # 这是显式选择"必须依赖视觉能力"的入口，应当显式拒绝。
            logger.warning(
                "image chat requires vision capability: %s",
                exc.message,
            )
            raise

        if image_description:
            retrieval_query = f"{data.message}\n图片内容：{image_description}"

        try:
            retrieved_chunks = await knowledge_retrieval_services.search_knowledge(
                session,
                query=retrieval_query,
                query_image_path=query_image_path,
                limit=5,
            )
        except CapabilityNotConfiguredError as exc:
            # embedding 未配置：降级为空检索，聊天仍能基于图片回答。
            logger.warning(
                "image chat degraded without RAG: capability=%s error=%s",
                exc.capability,
                exc.message,
            )
            retrieved_chunks = []

        result = await ai_services.chat(
            data,
            db=session,
            user_id=current_user.id,
            retrieved_chunks=retrieved_chunks,
            query_image_path=query_image_path,
        )
        return ApiResponse.success(data=result)
    except KnowledgeFileTooLargeError:
        raise BusinessException(
            message="查询图片超过允许大小！Ovo!",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        ) from None
    except ValueError as exc:
        raise BusinessException(
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from None
    finally:
        if query_image_path is not None:
            delete_query_image(query_image_path)


@router.get("/sources/{chunk_id}/image", response_class=FileResponse)
async def get_source_image(
    chunk_id: int,
    session: DbSession,
    _current_user: CurrentUser,
) -> FileResponse:
    """读取回答来源中的私有图片；Bearer Token通过当前用户依赖校验。"""

    image_path = await knowledge_retrieval_services.get_source_image_path(
        session,
        chunk_id=chunk_id,
    )
    if image_path is None:
        raise BusinessException(
            message="来源图片不存在或已停用！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return FileResponse(
        path=image_path,
        filename=image_path.name,
        content_disposition_type="inline",
    )
