"""AI助手生成的待确认业务动作。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.chat_models import ChatSession
from app.models.reservation_models import Reservation
from app.models.user_models import User


class AIPendingAction(Base):
    """保存Agent准备好的动作；用户确认前不修改真实预约表。"""

    __tablename__ = "ai_pending_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'expired', 'cancelled')",
            # 命名约定会自动补上ck_表名_前缀，这里只写语义名。
            name="status",
        ),
        {"comment": "AI助手待确认动作"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="待确认动作主键ID",
    )

    # user_id由后端当前登录用户注入，模型和前端都不能自由指定。
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(User.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="动作所属用户ID",
    )

    # 绑定会话后，确认卡片不会被其他会话误用。
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(ChatSession.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="动作所属AI会话ID",
    )

    # 当前只实现create_reservation，以后可扩展cancel_reservation等动作。
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="动作类型",
    )

    # JSONB保存通过Pydantic校验后的预约参数，不保存任意模型原文。
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="结构化动作参数",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
        index=True,
        comment="状态：pending/completed/expired/cancelled",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="确认截止时间",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="完成时间",
    )

    # 成功确认后记录真实预约ID，重复确认时可以幂等返回同一结果。
    reservation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(Reservation.id, ondelete="SET NULL"),
        nullable=True,
        unique=True,
        comment="确认后生成的预约ID",
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
