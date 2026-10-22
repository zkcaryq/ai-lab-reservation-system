"""用户 ORM 模型；密码字段只保存哈希，角色和状态由后端鉴权依赖解释。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """对应 PostgreSQL 中的 users 表。"""

    __tablename__ = "users"
    __table_args__ = {"comment": "用户信息表"}

    # 原教程把 id 放在 Base 中；当前模板 Base 不提供公共字段，所以写在 User 中。
    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="用户信息主键ID",
    )

    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="账号",
    )

    # 这里保存的是完整的Argon2id哈希字符串，不是用户输入的明文密码。
    # 长度扩大到255，是为了容纳算法、版本、参数、salt和哈希摘要等编码信息。
    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="密码",
    )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="名称",
    )

    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="角色：student-学生，admin-管理员",
    )

    email: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="邮箱",
    )

    phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="手机号",
    )

    avatar: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="头像地址",
    )

    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="状态：0-禁用，1-正常",
    )

    # 原教程的 create_time 在 Base 中；当前模板需要显式写在 User 中。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )

    # onupdate 只对应原教程已有的“更新时间”行为，不增加其他业务功能。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
