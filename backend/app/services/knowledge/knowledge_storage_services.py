"""知识文档私有文件存储；不负责数据库事务。

Router调用save_upload()保存原文件；解析器调用resolve_storage_key()取得绝对路径；
知识文档Service在删除数据库记录后调用delete_storage_key()清理文件。
"""

import asyncio
import hashlib
import os
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fastapi import UploadFile

from app.core.settings import get_settings

settings = get_settings()

# 每次从UploadFile读取1MiB。不会把20MiB甚至更大的文件一次性全部读入内存。
COPY_CHUNK_BYTES = 1024 * 1024


class KnowledgeFileTooLargeError(Exception):
    """真实读取字节数超过知识文档上限。"""


ALLOWED_QUERY_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def ensure_knowledge_directories() -> None:
    """创建运行目录，不创建数据库表。"""

    # 目录只承载运行数据，不属于Python包，也不会提交到Git。
    for directory in (
        settings.KNOWLEDGE_STORAGE_DIR / "originals",
        settings.KNOWLEDGE_STORAGE_DIR / "images",
        settings.KNOWLEDGE_STORAGE_DIR / "working",
    ):
        directory.mkdir(parents=True, exist_ok=True)


def create_processing_workspace(document_id: int) -> Path:
    """为一次处理任务创建独立临时目录，避免失败产物污染正式图片目录。"""

    workspace = (
        settings.KNOWLEDGE_STORAGE_DIR / "working" / f"document-{document_id}-{uuid.uuid4().hex}"
    )
    workspace.mkdir(parents=True, exist_ok=False)
    return workspace


def remove_processing_workspace(workspace: Path) -> None:
    """递归删除经过边界校验的单任务临时目录。"""

    working_root = (settings.KNOWLEDGE_STORAGE_DIR / "working").resolve()
    resolved = workspace.resolve()
    if not resolved.is_relative_to(working_root) or resolved == working_root:
        raise ValueError("拒绝删除知识库工作目录之外的路径")
    shutil.rmtree(resolved, ignore_errors=True)


def promote_extracted_image(image_path: Path) -> tuple[Path, str]:
    """把处理成功的临时图片原子移动到正式images目录。"""

    working_root = (settings.KNOWLEDGE_STORAGE_DIR / "working").resolve()
    source = image_path.resolve()
    if not source.is_relative_to(working_root) or not source.is_file():
        raise ValueError("只能发布知识库工作目录中的图片")

    suffix = source.suffix.lower()
    storage_key = f"images/{uuid.uuid4().hex}{suffix}"
    destination = settings.KNOWLEDGE_STORAGE_DIR / storage_key
    # working与images位于同一存储根目录，os.replace不会产生半写入目标文件。
    os.replace(source, destination)
    return destination, storage_key


def normalize_original_name(filename: str) -> str:
    """删除浏览器伪路径，只保留最后一段文件名。"""

    # 某些浏览器或客户端可能提交C:\fakepath\file.pdf。
    # 先统一分隔符，再只取最后一段，阻止原文件名控制服务器目录。
    return PurePosixPath(filename.replace("\\", "/")).name


def _copy_and_hash(
    source: BinaryIO,
    destination: Path,
    *,
    max_bytes: int,
) -> tuple[int, str]:
    """分块写入并同时计算真实大小和SHA256。"""

    total = 0
    digest = hashlib.sha256()
    try:
        # xb表示“只能新建”；理论上的UUID碰撞也不会静默覆盖已有文件。
        with destination.open("xb") as target:
            while chunk := source.read(COPY_CHUNK_BYTES):
                total += len(chunk)
                if total > max_bytes:
                    raise KnowledgeFileTooLargeError

                # 同一遍读取同时完成大小统计、摘要计算和磁盘写入，避免重复扫描文件。
                digest.update(chunk)
                target.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return total, digest.hexdigest()


async def save_upload(
    file: UploadFile,
) -> tuple[str, str, int, str, str | None]:
    """把UploadFile保存到私有originals并返回元数据。"""

    if not file.filename:
        raise ValueError("文件名不能为空")

    original_name = normalize_original_name(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in settings.ALLOWED_KNOWLEDGE_EXTENSIONS:
        raise ValueError(f"不支持的知识文档后缀：{extension or '无后缀'}")

    if file.size is not None and file.size > settings.MAX_KNOWLEDGE_FILE_BYTES:
        raise KnowledgeFileTooLargeError

    # 数据库保存相对storage_key，部署路径从D盘切换到Linux时无需改数据库记录。
    storage_key = f"originals/{uuid.uuid4().hex}{extension}"
    destination = settings.KNOWLEDGE_STORAGE_DIR / storage_key

    # 防止上游组件曾读取过文件头，确保从第一个字节开始复制和计算SHA256。
    file.file.seek(0)
    try:
        size, sha256 = await asyncio.to_thread(
            _copy_and_hash,
            file.file,
            destination,
            max_bytes=settings.MAX_KNOWLEDGE_FILE_BYTES,
        )
    finally:
        await file.close()

    return original_name, storage_key, size, sha256, file.content_type


async def save_query_image(file: UploadFile) -> Path:
    """把本轮以图检索图片临时保存到working目录，并返回绝对路径。

    查询图片只用于本轮向量检索和模型回答，不属于知识库原始资料，因此调用方必须
    在finally中调用``delete_query_image()``，无论请求成功还是失败都不长期保留。
    """

    if not file.filename:
        raise ValueError("图片文件名不能为空")

    original_name = normalize_original_name(file.filename)
    extension = Path(original_name).suffix.lower()
    expected_content_type = ALLOWED_QUERY_IMAGE_TYPES.get(extension)
    if expected_content_type is None:
        raise ValueError("只支持JPG、PNG或WebP查询图片")
    if file.content_type not in {expected_content_type, "application/octet-stream"}:
        raise ValueError("图片后缀与Content-Type不匹配")
    if file.size is not None and file.size > settings.MAX_AI_QUERY_IMAGE_BYTES:
        raise KnowledgeFileTooLargeError

    ensure_knowledge_directories()
    destination = (
        settings.KNOWLEDGE_STORAGE_DIR / "working" / f"query-{uuid.uuid4().hex}{extension}"
    )
    file.file.seek(0)
    try:
        await asyncio.to_thread(
            _copy_and_hash,
            file.file,
            destination,
            max_bytes=settings.MAX_AI_QUERY_IMAGE_BYTES,
        )
    finally:
        await file.close()
    return destination


def delete_query_image(path: Path) -> None:
    """删除一个经过边界校验的临时查询图片。"""

    working_root = (settings.KNOWLEDGE_STORAGE_DIR / "working").resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(working_root) or resolved == working_root:
        raise ValueError("拒绝删除知识库工作目录之外的路径")
    resolved.unlink(missing_ok=True)


def resolve_storage_key(storage_key: str) -> Path:
    """安全地把数据库存储键转换为绝对路径。"""

    root = settings.KNOWLEDGE_STORAGE_DIR.resolve()
    target = (root / storage_key).resolve()

    # is_relative_to防止../../等路径穿越逃出知识库私有目录。
    if not target.is_relative_to(root):
        raise ValueError("非法的知识库文件路径")
    return target


def delete_storage_key(storage_key: str) -> None:
    """只删除知识库根目录内的一个精确文件。"""

    resolve_storage_key(storage_key).unlink(missing_ok=True)
