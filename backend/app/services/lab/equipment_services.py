"""设备业务服务。

本模块执行查询、业务校验和显式事务；Router 不直接操作 ORM。关系字段使用
``selectinload`` 预加载，以配合 ORM 模型的 ``lazy='raise'`` 约束。
"""

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BusinessException
from app.models.equipment_models import Equipment
from app.models.lab_models import Lab
from app.schemas.equipment_schemas import (
    EquipmentCreateRequest,
    EquipmentUpdateRequest,
)


async def get_equipment_page_list(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    keywords: str | None = None,
    lab_id: int | None = None,
    lab_status: int | None = None,
) -> tuple[list[Equipment], int]:
    """按名称和实验室筛选设备，并返回当前页与总数。"""

    conditions = []
    normalized_keywords = keywords.strip() if keywords else ""

    # 不能写if lab_id，因为逻辑上应该明确判断是否提供了筛选值。
    if lab_id is not None:
        conditions.append(Equipment.lab_id == lab_id)

    if normalized_keywords:
        pattern = f"%{normalized_keywords}%"
        conditions.append(Equipment.name.ilike(pattern))
    if lab_status is not None:
        conditions.append(Equipment.lab.has(Lab.status == lab_status))

    # 总数SQL和列表SQL复用相同conditions，防止分页total不准确。
    count_statement = select(func.count()).select_from(Equipment).where(*conditions)
    total = await session.scalar(count_statement)

    list_statement = (
        select(Equipment)
        # 批量提前加载所属实验室，Router读取equipment.lab时不会异步懒加载。
        .options(selectinload(Equipment.lab))
        .where(*conditions)
        .order_by(Equipment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.scalars(list_statement)
    equipments = list(result.all())
    return equipments, total or 0


async def create_equipment(
    session: AsyncSession,
    *,
    data: EquipmentCreateRequest,
) -> Equipment:
    """创建设备；实验室不存在或名称冲突时直接抛业务异常。"""

    # 与实验室、用户管理相同，存在性判断放在Service内部。
    lab = await session.get(Lab, data.lab_id)
    if lab is None:
        raise BusinessException(
            message="所属实验室不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    duplicate_statement = select(Equipment).where(
        Equipment.lab_id == data.lab_id,
        Equipment.name == data.name,
    )
    duplicate = await session.scalar(duplicate_statement)
    if duplicate is not None:
        raise BusinessException(
            message="该实验室已存在同名设备！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    equipment = Equipment(**data.model_dump())

    # 同时设置关系对象，使成功返回时equipment.lab已经可用。
    equipment.lab = lab
    session.add(equipment)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        sqlstate = getattr(exc.orig, "sqlstate", None)

        # 两个并发请求仍可能同时通过预查询，最终由联合唯一约束兜底。
        if sqlstate == "23505":
            raise BusinessException(
                message="该实验室已存在同名设备！Ovo!",
                status_code=status.HTTP_409_CONFLICT,
            ) from None

        # 查询之后实验室被另一个事务删除时，外键约束可能产生23503。
        if sqlstate == "23503":
            raise BusinessException(
                message="所属实验室不存在！Ovo!",
                status_code=status.HTTP_404_NOT_FOUND,
            ) from None

        raise
    except Exception:
        await session.rollback()
        raise

    # 刷新数据库生成的id和时间字段，再显式加载lab关系供Router读取lab_name。
    await session.refresh(equipment)
    await session.refresh(equipment, attribute_names=["lab"])
    return equipment


async def update_equipment(
    session: AsyncSession,
    *,
    equipment_id: int,
    data: EquipmentUpdateRequest,
) -> Equipment:
    """部分更新设备；预期业务失败直接抛BusinessException。"""

    # 使用selectinload提前加载当前所属实验室，成功返回时可直接读取lab.name。
    equipment_statement = (
        select(Equipment).options(selectinload(Equipment.lab)).where(Equipment.id == equipment_id)
    )
    equipment = await session.scalar(equipment_statement)
    if equipment is None:
        raise BusinessException(
            message="实验室设备不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    update_data = data.model_dump(exclude_none=True)

    # 没有提交lab_id时继续使用原实验室。
    target_lab_id = update_data.get("lab_id", equipment.lab_id)

    if target_lab_id == equipment.lab_id:
        target_lab = equipment.lab
    else:
        target_lab = await session.get(Lab, target_lab_id)

    if target_lab is None:
        raise BusinessException(
            message="所属实验室不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # 没有提交name时继续使用原设备名称。
    target_name = update_data.get("name", equipment.name)

    duplicate_statement = select(Equipment).where(
        Equipment.lab_id == target_lab_id,
        Equipment.name == target_name,
        Equipment.id != equipment.id,
    )
    duplicate = await session.scalar(duplicate_statement)
    if duplicate is not None:
        raise BusinessException(
            message="该实验室已存在同名设备！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    for field, value in update_data.items():
        setattr(equipment, field, value)

    # 当lab_id变化时同步更新关系对象，保证返回的lab_name正确。
    equipment.lab = target_lab

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        sqlstate = getattr(exc.orig, "sqlstate", None)

        if sqlstate == "23505":
            raise BusinessException(
                message="该实验室已存在同名设备！Ovo!",
                status_code=status.HTTP_409_CONFLICT,
            ) from None
        if sqlstate == "23503":
            raise BusinessException(
                message="所属实验室不存在！Ovo!",
                status_code=status.HTTP_404_NOT_FOUND,
            ) from None
        raise
    except Exception:
        await session.rollback()
        raise

    await session.refresh(equipment)
    await session.refresh(equipment, attribute_names=["lab"])
    return equipment


async def delete_equipment(
    session: AsyncSession,
    *,
    equipment_id: int,
) -> None:
    """按ID删除设备；不存在或已有预约时直接抛业务异常。"""

    equipment = await session.get(Equipment, equipment_id)
    if equipment is None:
        raise BusinessException(
            message="实验室设备不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        await session.delete(equipment)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23503":
            raise BusinessException(
                message="设备存在预约记录，不能删除！Ovo!",
                status_code=status.HTTP_409_CONFLICT,
            ) from None
        raise
    except Exception:
        await session.rollback()
        raise
