"""知识库管理接口的请求与响应Schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KnowledgeStatus = Literal["queued", "processing", "completed", "failed"]


class KnowledgeDocumentResponse(BaseModel):
    """知识文档列表和详情的公开字段。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    original_name: str
    extension: str
    mime_type: str | None
    size: int
    status: KnowledgeStatus
    stage: str | None
    progress: int
    enabled: bool
    error_message: str | None
    chunk_count: int
    embedding_model: str | None
    embedding_dimension: int | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentPageResponse(BaseModel):
    """知识文档分页列表。"""

    list: list[KnowledgeDocumentResponse]
    total: int


class KnowledgeDocumentQueuedResponse(BaseModel):
    """上传成功但尚未处理完成时返回。"""

    document_id: int
    status: Literal["queued"]


class KnowledgeEnabledRequest(BaseModel):
    """管理员启用或停用一份知识文档。"""

    enabled: bool


class KnowledgeChunkPreviewResponse(BaseModel):
    """管理员预览Chunk，不能返回完整向量。"""

    # item是SQLAlchemy KnowledgeChunk对象，不是普通字典；允许按同名属性读取。
    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_index: int
    modality: str
    content: str
    page_number: int | None
    sheet_name: str | None
    heading_path: str | None
    image_storage_key: str | None
    source_metadata: dict = Field(default_factory=dict)
