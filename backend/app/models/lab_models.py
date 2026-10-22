"""实验室 ORM 模型，保存开放时段、容量、状态与展示信息。"""

from datetime import datetime, time

from sqlalchemy import BigInteger, DateTime, Identity, Integer, String, Text, Time, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Lab(Base):
    """对应PostgreSQL中的labs表。"""

    __tablename__ = "labs"
    __table_args__ = {"comment": "实验室信息表"}

    # 当前Base不提供公共主键，因此Lab显式声明自增BigInteger主键。
    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="实验室主键ID",
    )

    # unique=True让数据库最终保证实验室名称不能重复。
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="实验室名称",
    )

    location: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="实验室位置",
    )

    # server_default让直接SQL插入未提供capacity时也得到0。
    capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="容纳人数",
    )

    # 一天中的开放时间不需要时区，也不包含具体日期。
    open_time: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
        comment="开放开始时间",
    )

    close_time: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
        comment="开放结束时间",
    )

    # 简介可能比普通varchar字段长，使用PostgreSQL TEXT。
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="实验室简介",
    )

    # 只保存上传接口返回的相对URL，不把图片二进制直接存进业务表。
    img: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="实验室封面地址",
    )

    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="状态：0-关闭，1-开放",
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
