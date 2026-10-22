"""知识库原始文档、可检索Chunk和融合向量Model。"""

from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user_models import User


class KnowledgeDocument(Base):
    """管理员上传的一份原始知识文档。"""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        # 同一份二进制文件只保存一条记录，避免重复上传和重复计费。
        UniqueConstraint("sha256", name="uq_knowledge_documents_sha256"),
        {"comment": "RAG知识库原始文档"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="知识文档主键ID",
    )

    # 原文件名只用于页面显示，不能直接用作磁盘路径。
    original_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="上传时的原始文件名",
    )

    # storage_key由后端随机生成，是相对于KNOWLEDGE_STORAGE_DIR的私有路径。
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        comment="私有存储键",
    )

    extension: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="小写文件扩展名",
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="检测到的媒体类型",
    )

    size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="原文件实际字节数",
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="原文件SHA256十六进制摘要",
    )

    # queued表示等待Worker；processing表示处理中；completed才允许被检索；failed表示失败。
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'queued'"),
        comment="处理状态：queued/processing/completed/failed",
    )

    # stage用于页面显示当前步骤，不用根据日志猜测任务卡在哪里。
    stage: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="当前阶段：parsing/ocr/vision/chunking/embedding",
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="处理进度0至100",
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="是否参与检索",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="可供管理员查看的失败原因",
    )

    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="成功写入的Chunk数量",
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="生成当前向量的模型",
    )

    embedding_dimension: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="向量维度",
    )

    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(User.id, ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="上传管理员ID",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


class KnowledgeChunk(Base):
    """从文档中提取的一个可检索知识单元。"""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        # 每份文档内的Chunk序号不能重复。
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_knowledge_chunks_document_id_chunk_index",
        ),
        # HNSW是近似最近邻索引；vector_cosine_ops表示按照余弦距离检索。
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"comment": "RAG知识库分块与融合向量"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="知识Chunk主键ID",
    )

    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(KnowledgeDocument.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属知识文档ID",
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="文档内Chunk序号",
    )

    # text表示纯文字输入；image表示图片和相关文字共同生成的融合向量。
    modality: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Chunk模态：text/image",
    )

    # content包含最终用于检索和交给LLM的文字。
    # 图片Chunk中可组合OCR文字、视觉描述和附近正文。
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Chunk文字内容",
    )

    # 没有图片的文字Chunk为None；图片也保存在私有目录。
    image_storage_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="图片私有存储键",
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="来源页码，从1开始",
    )

    sheet_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Excel工作表名称",
    )

    heading_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="标题层级路径",
    )

    # JSONB保存行号、图片序号、OCR置信信息等不同格式特有的数据。
    source_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="来源定位扩展信息",
    )

    # 所有Chunk统一保存qwen3-vl-embedding生成的1024维融合向量。
    embedding: Mapped[list[float]] = mapped_column(
        VECTOR(1024),
        nullable=False,
        comment="1024维多模态融合向量",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
