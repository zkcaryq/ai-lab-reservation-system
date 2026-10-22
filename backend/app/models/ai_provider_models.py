"""AI 供应商能力配置 Model。

把“能力（capability）”与“供应商（provider）”解耦：每个能力一行配置，
由管理员在数据库中指定该能力使用哪家供应商、哪个模型、哪个 base_url 和密钥。
业务代码只按能力名取配置，不关心具体供应商，换供应商只改配置不改代码。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIProviderConfig(Base):
    """某个 AI 能力的供应商配置。"""

    __tablename__ = "ai_provider_configs"
    __table_args__ = (
        # 每个能力只保留一行生效配置。
        UniqueConstraint("capability", name="uq_ai_provider_configs_capability"),
        {"comment": "AI供应商能力配置"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="配置主键ID",
    )

    # 能力标识：chat/vision/ocr/embedding/rerank，预留 intent/decision。
    capability: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="能力：chat/vision/ocr/embedding/rerank/intent/decision",
    )

    # 供应商：minimax / bailian（阿里云百炼）。业务层据此选择对应适配器。
    provider: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="供应商：minimax/bailian",
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="模型ID",
    )

    base_url: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        comment="OpenAI兼容端点(聊天/视觉)，写到/compatible-mode/v1",
    )

    # 百炼专有的 /api/v1 根地址。用于 embedding/rerank/list_models，
    # 与 chat 用的 /compatible-mode/v1 不同；为空时由代码从 base_url 派生，
    # 旧数据无需手工迁移。
    dashscope_base_url: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
        comment="百炼DashScope /api/v1 根地址；空则由 base_url 派生",
    )

    # 密钥加密存储；为空时回退到 .env 中的对应供应商密钥。
    api_key_encrypted: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="加密后的API Key；空则回退.env",
    )

    # 思考深度档位；仅支持 reasoning 的供应商/模型使用。
    reasoning_effort: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="思考深度：low/medium/high/xhigh/max",
    )

    # 单次请求超时秒数；为空时使用该能力的 .env 默认值。
    timeout_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="单次请求超时秒数；空则用.env默认",
    )

    # 以下四项都是管理员可调、可留空的采样/提示词参数，为空表示沿用代码默认。
    temperature: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="采样温度0-2；空则用供应商默认",
    )
    top_p: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="核采样0-1；空则用供应商默认",
    )
    max_output_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="单次输出token上限；空则用全局默认",
    )
    system_prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="自定义系统提示词；空则用内置提示词",
    )
    context_window: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="模型上下文窗口token数；空则查MODEL_CATALOG",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="是否启用",
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


class AIUsageRecord(Base):
    """每次 AI 调用的 token 用量记录，用于按能力统计消耗。"""

    __tablename__ = "ai_usage_records"
    __table_args__ = (
        # 按能力 + 时间聚合查询用；管理员页展示各能力的累计消耗。
        Index("ix_ai_usage_records_capability_created_at", "capability", "created_at"),
        {"comment": "AI调用token用量记录"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="用量记录主键ID",
    )

    capability: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="能力：chat/vision/ocr/embedding/rerank/intent/decision",
    )

    provider: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="供应商：minimax/bailian",
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="模型ID",
    )

    input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="输入token数",
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="输出token数",
    )

    reasoning_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="思考token数（支持推理的模型才有）",
    )

    cached_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Prompt缓存命中的token数",
    )

    total_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="总token数",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="记录时间",
    )
