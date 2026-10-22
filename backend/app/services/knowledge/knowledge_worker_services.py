"""领取queued文档并执行解析、增强、向量化和入库。

本Worker由main.py的lifespan启动，不属于HTTP请求。上传接口只负责把状态写成queued，
Worker在后台领取后调用knowledge_ingestion_services.process_document()完成耗时任务。
"""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.errors import BusinessException
from app.core.settings import get_settings
from app.db.session import session_factory
from app.models.knowledge_models import KnowledgeDocument
from app.services.knowledge.knowledge_ingestion_services import process_document

settings = get_settings()
logger = logging.getLogger(__name__)


async def claim_next_document() -> int | None:
    """使用行锁领取一条任务，多个Worker不会重复处理同一文档。"""

    async with session_factory() as session:
        # FOR UPDATE SKIP LOCKED的含义：锁定自己领取的行；遇到其他Worker已锁的行就跳过。
        # 即使以后启动多个进程，也不会让两个Worker同时领取同一条queued记录。
        statement = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.status == "queued")
            .order_by(KnowledgeDocument.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        document = await session.scalar(statement)
        if document is None:
            return None

        document.status = "processing"
        document.stage = "parsing"
        document.progress = 5
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        return document.id


async def mark_document_failed(document_id: int, message: str) -> None:
    """使用新Session记录失败，不能复用已经回滚或关闭的处理Session。"""

    async with session_factory() as session:
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:
            return
        document.status = "failed"
        document.progress = 0
        # 数据库字段是Text，但仍限制长度，避免把完整外部响应或超长堆栈写入管理员页面。
        # 详细异常已经由logger.exception写入服务端日志。
        document.error_message = message[:2000]
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("failed to persist knowledge task failure document_id=%s", document_id)


async def requeue_interrupted_document(document_id: int) -> None:
    """应用正常关闭时把未完成任务放回队列，避免永久停在processing。"""

    async with session_factory() as session:
        document = await session.get(KnowledgeDocument, document_id)
        if document is None or document.status != "processing":
            return
        document.status = "queued"
        document.stage = None
        document.progress = 0
        document.error_message = "服务重启导致处理暂停，任务已自动重新排队"
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("failed to requeue interrupted document document_id=%s", document_id)


async def recover_stale_documents() -> int:
    """重新排队超过任务时限仍为processing的异常任务。"""

    cutoff = datetime.now(UTC) - timedelta(seconds=settings.KNOWLEDGE_TASK_TIMEOUT_SECONDS)
    async with session_factory() as session:
        statement = (
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.status == "processing",
                KnowledgeDocument.updated_at < cutoff,
            )
            .values(
                status="queued",
                stage=None,
                progress=0,
                error_message="检测到上次处理异常中断，任务已自动重新排队",
            )
        )
        result = await session.execute(statement)
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        return int(result.rowcount or 0)


async def run_knowledge_worker() -> None:
    """应用生命周期内持续处理知识文档队列。"""

    recovered = await recover_stale_documents()
    if recovered:
        logger.warning("requeued stale knowledge tasks count=%s", recovered)

    # 空闲时按固定间隔再次检查孤儿任务。刚重启后“中断还不满时限”的任务不会被
    # 启动检查恢复；时限一到，运行期间的空闲检查就会把它们放回队列，
    # 不再依赖下一次进程重启。monotonic时钟不受系统时间调整影响，适合测间隔。
    last_stale_check = time.monotonic()
    while True:
        # 每轮只领取一条，处理完成或失败后再领取下一条，第一版保持调用成本可控。
        document_id = await claim_next_document()
        if document_id is None:
            # 空闲分支里worker没有正在处理的文档，此时恢复不会误伤在途任务。
            if time.monotonic() - last_stale_check >= settings.KNOWLEDGE_STALE_RECHECK_SECONDS:
                last_stale_check = time.monotonic()
                recovered = await recover_stale_documents()
                if recovered:
                    logger.warning("requeued stale knowledge tasks count=%s", recovered)
            await asyncio.sleep(settings.KNOWLEDGE_WORKER_SCAN_SECONDS)
            continue

        try:
            # 总时限覆盖解析、OCR、视觉理解、Embedding和数据库写入。
            async with asyncio.timeout(settings.KNOWLEDGE_TASK_TIMEOUT_SECONDS):
                await process_document(document_id=document_id)
            logger.info("knowledge ingestion completed document_id=%s", document_id)
        except asyncio.CancelledError:
            # FastAPI关闭时main.py会cancel任务；必须继续抛出才能真正结束循环。
            await requeue_interrupted_document(document_id)
            raise
        except TimeoutError:
            logger.exception("knowledge ingestion timed out document_id=%s", document_id)
            await mark_document_failed(document_id, "文档处理超时，请检查文档规模后重试")
        except BusinessException as exc:
            logger.exception("knowledge ingestion business failure document_id=%s", document_id)
            await mark_document_failed(document_id, exc.message)
        except ValueError as exc:
            logger.exception("knowledge ingestion rejected document_id=%s", document_id)
            await mark_document_failed(document_id, str(exc))
        except Exception:
            # 未知异常保留完整堆栈；数据库只保存适合管理员查看的稳定提示。
            logger.exception("knowledge ingestion failed document_id=%s", document_id)
            await mark_document_failed(document_id, "文档处理失败，请查看服务端日志后重试")
