"""设备 ORM 模型及其数据库级约束。

外键保证设备必须属于真实实验室，联合唯一约束防止同一实验室出现重名设备；关系采用
``lazy='raise'``，要求查询方显式预加载，避免异步环境中发生隐式数据库 I/O。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.lab_models import Lab


class Equipment(Base):
    """对应PostgreSQL中的equipments表。"""

    __tablename__ = "equipments"

    # 元组中先放表级联合唯一约束，最后一个字典保存表注释。
    __table_args__ = (
        UniqueConstraint(
            "lab_id",
            "name",
            name="uq_equipments_lab_id_name",
        ),
        {"comment": "实验室设备信息表"},
    )

    # 当前Base不统一提供主键，因此每个业务Model显式声明BigInteger自增主键。
    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
        comment="设备主键ID",
    )

    # 直接引用Lab.id列对象，SQLAlchemy能够自动带上当前app Schema。
    # RESTRICT表示实验室仍有设备时，数据库拒绝删除该实验室。
    lab_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(Lab.id, ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="所属实验室ID",
    )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="设备名称",
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="设备说明",
    )

    # 与现有上传接口一致，只保存/uploads/...相对地址，不保存图片二进制。
    img: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="设备图片地址",
    )

    spec: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="型号规格",
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="设备数量",
    )

    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="状态：0-维修，1-正常",
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

    # lazy="raise"禁止未预加载时偷偷访问数据库。
    # Service列表查询会使用selectinload(Equipment.lab)显式加载它。
    lab: Mapped[Lab] = relationship(lazy="raise")
