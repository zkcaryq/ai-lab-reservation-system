"""预约 ORM 模型。

数据库字段保存预约对象、日期时段和审核状态；跨行的“时间是否冲突”等业务规则由
Service 在事务和行锁保护下校验，不能只依赖单行约束表达。
"""

from datetime import date as date_type
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Time,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.equipment_models import Equipment
from app.models.lab_models import Lab
from app.models.user_models import User


class Reservation(Base):
    """对应PostgreSQL中的reservations预约记录表。"""

    __tablename__ = "reservations"
    __table_args__ = {"comment": "实验室与设备预约信息表"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="预约主键ID",
    )

    # 预约人必须来自已经登录的User，不能由前端自由指定。
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(User.id, ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="预约用户ID",
    )

    # 每条预约都必须属于一个实验室。
    lab_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(Lab.id, ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="预约实验室ID",
    )

    # NULL表示只预约实验室；有值表示预约该实验室中的指定设备。
    equipment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(Equipment.id, ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="预约设备ID，NULL表示只预约实验室",
    )

    # 使用真正的PostgreSQL DATE，而不是字符串。
    date: Mapped[date_type] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="预约日期",
    )

    # 一天中的时刻不单独携带时区；它和date共同表示中国当地预约时间。
    start_time: Mapped[time] = mapped_column(
        Time(timezone=False),
        nullable=False,
        comment="预约开始时间",
    )

    end_time: Mapped[time] = mapped_column(
        Time(timezone=False),
        nullable=False,
        comment="预约结束时间",
    )

    remark: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="预约备注",
    )

    # server_default保证直接执行SQL且未提供status时，同样得到待审核状态0。
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="预约状态：0-待审核，1-已通过，2-已拒绝，3-已取消",
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

    # lazy="raise"禁止代码在不知情时隐式发SQL。
    # 本章创建接口暂时不读取这些relationship；后续列表接口需要selectinload。
    user: Mapped[User] = relationship(lazy="raise")
    lab: Mapped[Lab] = relationship(lazy="raise")
    equipment: Mapped[Equipment | None] = relationship(lazy="raise")
