"""知识文档记录、状态和管理员业务。

本文件只处理文档记录、状态、分页和事务；文件解析与模型调用由后台Worker负责。
Router把请求级AsyncSession传进来，Service不使用FastAPI Depends。
"""

import logging

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessException
from app.models.knowledge_models import KnowledgeChunk, KnowledgeDocument
from app.services.knowledge.knowledge_storage_services import delete_storage_key

logger = logging.getLogger(__name__)


def _delete_file_safely(storage_key: str) -> None:
    """数据库事务完成后尽力清理文件，失败时记录日志而不伪装成数据库失败。"""

    try:
        delete_storage_key(storage_key)
    except OSError:
        logger.warning(
            "failed to delete knowledge file storage_key=%s",
            storage_key,
            exc_info=True,
        )


async def create_queued_document(
    session: AsyncSession,
    *,
    original_name: str,
    storage_key: str,
    extension: str,
    mime_type: str | None,
    size: int,
    sha256: str,
    created_by: int,
) -> KnowledgeDocument:
    """建立queued记录；重复文件返回409并删除本次临时保存。"""

    # 预查询可以尽早给出清晰的409，但不能替代数据库唯一约束：并发请求仍可能同时查到不存在。
    duplicate = await session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.sha256 == sha256)
    )
    if duplicate is not None:
        _delete_file_safely(storage_key)
        raise BusinessException(
            message="相同内容的知识文档已经存在！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    # 这里只创建元数据任务，耗时的解析/OCR/Embedding由后台Worker异步处理。
    document = KnowledgeDocument(
        original_name=original_name,
        storage_key=storage_key,
        extension=extension,
        mime_type=mime_type,
        size=size,
        sha256=sha256,
        status="queued",
        progress=0,
        enabled=True,
        created_by=created_by,
    )
    session.add(document)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        _delete_file_safely(storage_key)
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise BusinessException(
                message="相同内容的知识文档已经存在！Ovo!",
                status_code=status.HTTP_409_CONFLICT,
            ) from None
        raise
    except Exception:
        await session.rollback()
        _delete_file_safely(storage_key)
        raise

    await session.refresh(document)
    return document


async def get_document_page(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    keywords: str | None,
    document_status: str | None,
) -> tuple[list[KnowledgeDocument], int]:
    """使用同一组筛选条件返回当前页记录和总数。"""

    # conditions同时用于COUNT和列表SELECT，避免total与实际列表筛选条件不一致。
    conditions = []
    if keywords and keywords.strip():
        conditions.append(KnowledgeDocument.original_name.ilike(f"%{keywords.strip()}%"))
    if document_status is not None:
        conditions.append(KnowledgeDocument.status == document_status)

    total = await session.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(*conditions)
    )
    result = await session.scalars(
        select(KnowledgeDocument)
        .where(*conditions)
        .order_by(KnowledgeDocument.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.all()), total or 0


async def get_document_or_404(
    session: AsyncSession,
    *,
    document_id: int,
) -> KnowledgeDocument:
    """读取文档，不存在时抛出可安全返回客户端的 404 业务异常。"""

    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise BusinessException(
            message="知识文档不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return document


async def requeue_document(session: AsyncSession, *, document_id: int) -> None:
    """把失败或已完成的文档重新排队；处理中的任务禁止重复入队。"""

    document = await get_document_or_404(session, document_id=document_id)
    if document.status == "processing":
        raise BusinessException(
            message="知识文档正在处理中，不能重复提交！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )
    document.status = "queued"
    document.stage = None
    document.progress = 0
    document.error_message = None
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def set_document_enabled(
    session: AsyncSession,
    *,
    document_id: int,
    enabled: bool,
) -> None:
    """控制文档是否参与检索，不删除已经生成的Chunk。"""

    document = await get_document_or_404(session, document_id=document_id)
    document.enabled = enabled
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def delete_document(session: AsyncSession, *, document_id: int) -> None:
    """删除文档记录，并在提交成功后清理原文件和提取图片。"""

    document = await get_document_or_404(session, document_id=document_id)
    if document.status == "processing":
        raise BusinessException(
            message="知识文档正在处理中，暂时不能删除！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )
    storage_key = document.storage_key
    # 先保存Chunk提取图片的私有存储键。数据库提交后级联删除Chunk，届时已无法再查询。
    image_keys = list(
        (
            await session.scalars(
                select(KnowledgeChunk.image_storage_key).where(
                    KnowledgeChunk.document_id == document_id,
                    KnowledgeChunk.image_storage_key.is_not(None),
                )
            )
        ).all()
    )
    try:
        await session.delete(document)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    # 数据库删除成功后，再删除原文件和解析阶段提取的图片。
    # 不先删文件，是为了避免数据库提交失败却已经永久丢失原始资料。
    _delete_file_safely(storage_key)
    for image_key in set(image_keys):
        _delete_file_safely(image_key)


async def get_chunk_previews(
    session: AsyncSession,
    *,
    document_id: int,
) -> list[KnowledgeChunk]:
    """按原始顺序返回Chunk预览；向量字段不会进入响应Schema。"""

    await get_document_or_404(session, document_id=document_id)
    result = await session.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document_id)
        .order_by(KnowledgeChunk.chunk_index)
    )
    return list(result.all())
