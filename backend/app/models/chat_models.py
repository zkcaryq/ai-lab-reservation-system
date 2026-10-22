"""AI助手对话会话与消息Model。

多轮对话历史持久化到数据库：ChatSession 是一次完整对话，ChatMessage 是其中
一条消息（用户问题或模型回答）。MiniMax 的 Responses API 不支持
previous_response_id（会被忽略），因此多轮续聊必须由后端从这两张表读取历史
messages 拼进 input，而不是依赖服务端上下文。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user_models import User


class ChatSession(Base):
    """一次完整对话会话。"""

    __tablename__ = "chat_sessions"
    __table_args__ = {"comment": "AI助手对话会话"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="会话主键ID",
    )

    # 会话归属用户；用户删除时级联删除其会话。
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(User.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="会话所属用户ID",
    )

    # 列表页展示用的简短标题，取首条用户消息的前若干字符。
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="新对话",
        comment="会话标题",
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
        comment="最后活跃时间",
    )


class ChatMessage(Base):
    """会话中的一条消息。"""

    __tablename__ = "chat_messages"
    __table_args__ = {"comment": "AI助手对话消息"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="消息主键ID",
    )

    # 会话删除时级联删除其全部消息。
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(ChatSession.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属会话ID",
    )

    # role 只取 user 或 assistant；system 提示词由后端注入，不落库。
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="消息角色：user/assistant",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息正文",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
