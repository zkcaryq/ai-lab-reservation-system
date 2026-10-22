"""管理员知识库文档上传与维护接口。

调用链：管理员请求 → 本Router做HTTP参数编排 → knowledge_storage_services落盘
→ knowledge_services写数据库任务 → 后台Worker异步处理。
"""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi import Path as ApiPath

from app.api.dependencies import CurrentAdmin, DbSession
from app.core.errors import BusinessException
from app.schemas.apiresponse import ApiResponse
from app.schemas.knowledge_schemas import (
    KnowledgeChunkPreviewResponse,
    KnowledgeDocumentPageResponse,
    KnowledgeDocumentQueuedResponse,
    KnowledgeDocumentResponse,
    KnowledgeEnabledRequest,
)
from app.services.knowledge import knowledge_services
from app.services.knowledge.knowledge_storage_services import (
    KnowledgeFileTooLargeError,
    save_upload,
)

router = APIRouter(prefix="/knowledge", tags=["知识库管理"])


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    session: DbSession,
    current_admin: CurrentAdmin,
) -> ApiResponse:
    """保存原文件并创建queued任务；不在HTTP请求中执行OCR和Embedding。"""

    try:
        # save_upload分块保存文件，并返回服务器文件键、真实字节数和SHA256。
        # 它不写数据库，所以保存成功后还要调用下面的Service建立任务记录。
        original_name, storage_key, size, sha256, mime_type = await save_upload(file)
    except KnowledgeFileTooLargeError:
        raise BusinessException(
            message="知识文档超过允许大小！Ovo!",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        ) from None
    except ValueError as exc:
        raise BusinessException(
            message=str(exc),
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        ) from None

    # Service会检查SHA256重复，并把状态写成queued；Worker稍后才能领取它。
    document = await knowledge_services.create_queued_document(
        session,
        original_name=original_name,
        storage_key=storage_key,
        extension=Path(original_name).suffix.lower(),
        mime_type=mime_type,
        size=size,
        sha256=sha256,
        created_by=current_admin.id,
    )
    # HTTP 202表示请求已接收，但后台处理尚未完成；不能在此返回“入库成功”。
    return ApiResponse.success(
        code=status.HTTP_202_ACCEPTED,
        message="文档已上传，正在排队处理！Ovo!",
        data=KnowledgeDocumentQueuedResponse(
            document_id=document.id,
            status="queued",
        ),
    )


@router.get("/documents")
async def get_documents(
    session: DbSession,
    _current_admin: CurrentAdmin,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    keywords: str | None = Query(default=None, max_length=100),
    document_status: Literal["queued", "processing", "completed", "failed"] | None = Query(
        default=None,
        alias="status",
    ),
) -> ApiResponse:
    """分页查询知识文档处理状态，供管理员列表页轮询展示。"""

    documents, total = await knowledge_services.get_document_page(
        session,
        page=page,
        page_size=page_size,
        keywords=keywords,
        document_status=document_status,
    )
    return ApiResponse.success(
        data=KnowledgeDocumentPageResponse(
            list=[KnowledgeDocumentResponse.model_validate(item) for item in documents],
            total=total,
        )
    )


@router.get("/documents/{document_id}")
async def get_document(
    session: DbSession,
    _current_admin: CurrentAdmin,
    document_id: int = ApiPath(gt=0),
) -> ApiResponse:
    """读取一份文档的元数据和当前处理进度。"""

    document = await knowledge_services.get_document_or_404(
        session,
        document_id=document_id,
    )
    return ApiResponse.success(data=KnowledgeDocumentResponse.model_validate(document))


@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(
    session: DbSession,
    _current_admin: CurrentAdmin,
    document_id: int = ApiPath(gt=0),
) -> ApiResponse:
    """预览解析后的文字Chunk，不返回1024维向量。"""

    chunks = await knowledge_services.get_chunk_previews(
        session,
        document_id=document_id,
    )
    return ApiResponse.success(
        data=[KnowledgeChunkPreviewResponse.model_validate(item) for item in chunks]
    )


@router.post("/documents/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    session: DbSession,
    _current_admin: CurrentAdmin,
    document_id: int = ApiPath(gt=0),
) -> ApiResponse:
    """让失败或已完成的文档重新进入后台处理队列。"""

    await knowledge_services.requeue_document(session, document_id=document_id)
    return ApiResponse.success(
        code=status.HTTP_202_ACCEPTED,
        message="文档已重新加入处理队列！Ovo!",
    )


@router.patch("/documents/{document_id}/enabled")
async def update_document_enabled(
    data: KnowledgeEnabledRequest,
    session: DbSession,
    _current_admin: CurrentAdmin,
    document_id: int = ApiPath(gt=0),
) -> ApiResponse:
    """启用或停用检索；停用不会删除Chunk，之后仍可重新开启。"""

    await knowledge_services.set_document_enabled(
        session,
        document_id=document_id,
        enabled=data.enabled,
    )
    return ApiResponse.success(message="知识文档状态修改成功！Ovo!")


@router.delete("/documents/{document_id}")
async def remove_document(
    session: DbSession,
    _current_admin: CurrentAdmin,
    document_id: int = ApiPath(gt=0),
) -> ApiResponse:
    """删除文档记录、关联Chunk以及本地私有文件。"""

    await knowledge_services.delete_document(session, document_id=document_id)
    return ApiResponse.success(message="知识文档删除成功！Ovo!")
