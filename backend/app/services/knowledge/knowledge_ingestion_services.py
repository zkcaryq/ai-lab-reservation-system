"""编排解析、OCR/视觉、融合向量和数据库原子替换。

调用链：knowledge_worker_services领取queued任务 → 本文件process_document()
→ document_parser_services解析 → bailian_embedding_services生成向量
→ 在一个短数据库事务中替换KnowledgeChunk。

[链路定位] RAG 入库链路的编排入口（与检索链路独立，属于后台 Worker 的一次任务，
不是 HTTP 请求；一次可能跑几十秒甚至更久）：

    上游：knowledge_worker_services.run_knowledge_worker() 领取 queued 任务后
          调用 process_document(document_id=...)
    内部依次：读元数据 → 建任务独享临时目录 → parse_document()（解析/OCR/视觉）
              → _build_chunks()（逐块生成 1024 维融合向量）→ 短事务"删旧 Chunk + 插新 Chunk"
    下游：document_parser_services.parse_document()
          bailian_document_services（图片 OCR / 视觉理解，经解析器间接调用）
          bailian_embedding_services.create_fused_embedding()
          knowledge_storage_services（私有目录/临时目录/图片发布/路径安全）
    关键原则：所有模型调用成功后才开短事务原子替换旧 Chunk，失败则旧知识库保持不变。
"""

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from app.core.settings import get_settings
from app.db.session import session_factory
from app.models.knowledge_models import KnowledgeChunk, KnowledgeDocument
from app.services.ai import ai_provider_services
from app.services.knowledge.bailian_embedding_services import create_fused_embedding
from app.services.knowledge.document_parser_services import ParsedChunk, parse_document
from app.services.knowledge.knowledge_storage_services import (
    create_processing_workspace,
    delete_storage_key,
    promote_extracted_image,
    remove_processing_workspace,
    resolve_storage_key,
)

settings = get_settings()
logger = logging.getLogger(__name__)


def _remove_nul(value: Any) -> Any:
    """递归移除PostgreSQL文本/JSON字段不允许的NUL字符。

    返回类型标注为Any：输入可能是str、dict、list或其他JSON安全类型，
    逐层递归后类型与输入一致；显式Any也避免IDE把递归返回值推断为未知类型，
    导致它被用作字典key时误报类型错误。
    """

    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {_remove_nul(key): _remove_nul(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_remove_nul(item) for item in value]
    return value


def _delete_extracted_images(storage_keys: set[str]) -> None:
    """尽力清理已不再被Chunk引用的提取图片。"""

    for storage_key in storage_keys:
        try:
            delete_storage_key(storage_key)
        except OSError:
            # 数据库事务已经结束时，文件清理失败不能伪装成数据库失败。
            # 日志保留具体storage_key，管理员之后可以手工清理孤儿文件。
            logger.warning(
                "failed to delete extracted knowledge image storage_key=%s",
                storage_key,
                exc_info=True,
            )


async def _update_progress(document_id: int, *, stage: str, progress: int) -> None:
    """使用独立短Session更新后台任务进度。"""

    # 外部模型调用可能持续较久，进度更新不能复用一个长期打开的数据库Session。
    async with session_factory() as session:
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:
            raise RuntimeError("知识文档在处理期间被删除")
        document.stage = stage
        document.progress = progress
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _build_chunks(
    document_id: int,
    parsed_chunks: list[ParsedChunk],
    *,
    workspace: Path,
    promoted_image_keys: set[str],
) -> list[KnowledgeChunk]:
    """把解析结果逐块向量化，并构造尚未写入数据库的ORM对象。"""

    result: list[KnowledgeChunk] = []
    total = len(parsed_chunks)
    for index, parsed in enumerate(parsed_chunks):
        # 标题是正文语义的一部分。例如正文只有“开放时间：08:00—22:00”时，
        # 不带“人工智能实验室/开放时间”标题生成向量，很容易和其他实验室混淆。
        # 数据库content仍保存干净正文；这里只补充向量模型真正需要的上下文。
        embedding_text = parsed.content
        if parsed.heading_path:
            embedding_text = f"章节：{parsed.heading_path}\n正文：{parsed.content}"

        # 纯文字Chunk只会传text；图片Chunk会同时传文字和私有图片路径。
        # enable_fusion=true后，百炼为二者返回同一个1024维向量。
        embedding = await create_fused_embedding(
            text=embedding_text,
            image_path=parsed.image_path,
        )

        # 解析器先把提取图片写到本任务独享的working目录。只有该图片已成功完成
        # OCR、视觉理解和向量化后，才移动到正式images目录并生成数据库存储键。
        image_storage_key = parsed.image_storage_key
        if parsed.image_path is not None and parsed.image_path.resolve().is_relative_to(
            workspace.resolve()
        ):
            parsed.image_path, image_storage_key = promote_extracted_image(parsed.image_path)
            promoted_image_keys.add(image_storage_key)

        result.append(
            KnowledgeChunk(
                document_id=document_id,
                chunk_index=index,
                modality=parsed.modality,
                # 数据库写入前再做最后一道防线。除了content，标题、工作表名称和
                # JSON元数据中的字符串也可能从外部文档带入NUL控制字符。
                content=_remove_nul(parsed.content),
                image_storage_key=_remove_nul(image_storage_key),
                page_number=parsed.page_number,
                sheet_name=_remove_nul(parsed.sheet_name),
                heading_path=_remove_nul(parsed.heading_path),
                source_metadata=_remove_nul(parsed.source_metadata),
                embedding=embedding,
            )
        )
        # 不必每个Chunk更新数据库；每10个或最后一个更新一次即可。
        if (index + 1) % 10 == 0 or index + 1 == total:
            progress = 50 + int((index + 1) / max(total, 1) * 40)
            await _update_progress(document_id, stage="embedding", progress=progress)
    return result


async def process_document(*, document_id: int) -> None:
    """Worker调用的完整单文档处理入口。"""

    # 只读取文档元数据后立即关闭Session，外部AI调用期间不占用数据库事务。
    async with session_factory() as session:
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:
            raise RuntimeError("待处理知识文档不存在")
        source_path = resolve_storage_key(document.storage_key)
        extension = document.extension

    workspace = create_processing_workspace(document_id)
    new_image_keys: set[str] = set()
    try:
        await _update_progress(document_id, stage="parsing", progress=10)

        # 每个任务使用独立working目录。解析、OCR或向量化在任意位置失败时，finally
        # 都会清理未发布的临时文件，不再留下无法追踪的孤儿图片。
        parsed_chunks = await parse_document(
            source_path,
            extension=extension,
            working_dir=workspace,
        )
        if not parsed_chunks:
            raise ValueError("文档解析后没有得到可入库内容")

        await _update_progress(document_id, stage="embedding", progress=50)
        try:
            new_chunks = await _build_chunks(
                document_id,
                parsed_chunks,
                workspace=workspace,
                promoted_image_keys=new_image_keys,
            )
        except Exception:
            _delete_extracted_images(new_image_keys)
            raise

    finally:
        # 已发布图片已经移出working；这里仅删除剩余临时文件和空目录。
        remove_processing_workspace(workspace)

    # 所有模型调用成功后，才用短事务替换旧Chunk。
    async with session_factory() as session:
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:
            raise RuntimeError("知识文档在入库前被删除")
        # 在删除旧Chunk前保存其图片键；commit成功后这些旧图片已不再被数据库引用。
        old_image_keys = set(
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
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
            )
            session.add_all(new_chunks)
            document.status = "completed"
            document.stage = None
            document.progress = 100
            document.error_message = None
            document.chunk_count = len(new_chunks)
            # 记录生成向量所用的模型（从数据库配置读取）。
            embedding_config = await ai_provider_services.get_capability_config(
                session, "embedding"
            )
            document.embedding_model = embedding_config.model if embedding_config else None
            document.embedding_dimension = settings.BAILIAN_EMBEDDING_DIMENSION
            await session.commit()
        except Exception:
            await session.rollback()

            # 事务回滚后旧Chunk仍然有效；本次新提取图片则没有引用，可以安全删除。
            _delete_extracted_images(new_image_keys)
            raise

    # 只有新Chunk提交成功后才能清理旧图片，否则会破坏仍可使用的旧知识库版本。
    _delete_extracted_images(old_image_keys - new_image_keys)
