"""实验室查询和写事务相关的数据库业务逻辑。

调用方向：``api/routes/lab_router.py``调用本模块。
本模块处理AsyncSession、SQLAlchemy ORM、业务校验和数据库事务；不接收
Depends，也不构造ApiResponse。预期业务失败直接抛BusinessException。
"""

from fastapi import status as http_status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessException
from app.models.lab_models import Lab
from app.schemas.lab_schemas import LabCreateRequest, LabUpdateRequest


async def get_lab_page_list(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    keywords: str | None = None,
    status: int | None = None,
) -> tuple[list[Lab], int]:
    """按名称或位置模糊搜索，并返回当前页实验室与总记录数。"""

    # conditions会同时用于总数SQL和列表SQL，避免分页数量与列表条件不一致。
    conditions = []

    # None、空字符串和纯空格都按“没有搜索条件”处理。
    normalized_keywords = keywords.strip() if keywords else ""

    if normalized_keywords:
        # 百分号是SQL LIKE通配符，可匹配关键词前后的任意内容。
        pattern = f"%{normalized_keywords}%"
        conditions.append(
            or_(
                # PostgreSQL ILIKE执行不区分英文大小写的模糊查询。
                Lab.name.ilike(pattern),
                Lab.location.ilike(pattern),
            )
        )
    if status is not None:
        conditions.append(Lab.status == status)
    # 第一条SQL只统计符合相同条件的记录总数。
    count_statement = select(func.count()).select_from(Lab).where(*conditions)
    total = await session.scalar(count_statement)

    # 第二条SQL查询当前页的Lab ORM对象。
    list_statement = (
        select(Lab)
        .where(*conditions)
        .order_by(Lab.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    # scalars()只保留每一行中的Lab实体；all()取出当前页全部结果。
    result = await session.scalars(list_statement)
    labs = list(result.all())

    # count(*)正常会得到整数；or 0保证返回类型始终是int。
    return labs, total or 0


async def get_lab_by_id(
    session: AsyncSession,
    *,
    lab_id: int,
    status: int | None = None,
) -> Lab:
    """查询当前角色可见的实验室；不存在或不可见时统一抛404。"""

    statement = select(Lab).where(Lab.id == lab_id)
    if status is not None:
        statement = statement.where(Lab.status == status)
    lab = await session.scalar(statement)
    if lab is None:
        raise BusinessException(
            message="实验室不存在或当前不可访问！Ovo!",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )
    return lab


async def create_lab(
    session: AsyncSession,
    *,
    data: LabCreateRequest,
) -> Lab:
    """创建实验室；名称冲突时直接抛409。"""

    # 与create_user()先查询username相同，这里先查询实验室名称。
    statement = select(Lab).where(Lab.name == data.name)
    existing_lab = await session.scalar(statement)

    # 普通重复创建在这里结束；Service直接抛出可预期的409业务异常。
    if existing_lab is not None:
        raise BusinessException(
            message="实验室名称已存在！Ovo!",
            status_code=http_status.HTTP_409_CONFLICT,
        )

    # 把Pydantic请求转换成普通字典，再用关键字参数创建Lab ORM对象。
    lab = Lab(**data.model_dump())

    # add()只把对象加入Session待写入集合，此时还没有执行INSERT。
    session.add(lab)

    try:
        # commit()真正发送INSERT并提交事务。
        await session.commit()
    except IntegrityError as exc:
        # PostgreSQL拒绝事务后必须先回滚，Session才能离开失败状态。
        await session.rollback()

        # 23505表示唯一约束冲突。即使两个请求同时通过上方预查询，
        # 数据库中的labs.name唯一约束仍会阻止重复名称写入。
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise BusinessException(
                message="实验室名称已存在！Ovo!",
                status_code=http_status.HTTP_409_CONFLICT,
            ) from None

        # 其他完整性错误不是已知的“名称重复”，交给全局500处理器记录。
        raise
    except Exception:
        # 连接失败等未知提交错误同样先回滚，再保留原异常。
        await session.rollback()
        raise

    # 重新读取数据库生成的id、created_at等字段。
    await session.refresh(lab)
    return lab


async def update_lab(
    session: AsyncSession,
    *,
    lab_id: int,
    data: LabUpdateRequest,
) -> Lab:
    """按ID更新实验室；不存在或名称冲突时直接抛业务异常。"""

    # 与update_user()相同，目标存在性由Service自己查询和判断。
    lab = await session.get(Lab, lab_id)

    if lab is None:
        raise BusinessException(
            message="实验室不存在！Ovo!",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )

    # 用户更新不能修改username，所以User Service不需要这一段。
    # 实验室名称允许修改且有唯一约束，因此改名时必须检查其他同名记录。
    if data.name is not None and data.name != lab.name:
        duplicate_statement = select(Lab).where(
            Lab.name == data.name,
            Lab.id != lab_id,
        )
        duplicate_lab = await session.scalar(duplicate_statement)

        if duplicate_lab is not None:
            raise BusinessException(
                message="实验室名称已存在！Ovo!",
                status_code=http_status.HTTP_409_CONFLICT,
            )

    # PATCH只修改请求中值不为None的字段，未提交字段保持数据库原值。
    update_data = data.model_dump(exclude_none=True)

    # 字段名来自LabUpdateRequest白名单。
    for field, value in update_data.items():
        # setattr(lab, "name", "新名称")等价于lab.name = "新名称"。
        setattr(lab, field, value)

    try:
        # lab由当前Session查询得到，属性变化会被自动追踪并生成UPDATE。
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        # 提交前的重名查询不能完全避免并发改名，因此仍保留数据库兜底。
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise BusinessException(
                message="实验室名称已存在！Ovo!",
                status_code=http_status.HTTP_409_CONFLICT,
            ) from None

        raise
    except Exception:
        await session.rollback()
        raise

    # 刷新后返回数据库最终保存的Lab对象。
    await session.refresh(lab)
    return lab


async def delete_lab(
    session: AsyncSession,
    *,
    lab_id: int,
) -> None:
    """按ID删除实验室；不存在或仍被引用时直接抛业务异常。"""

    # 与delete_user()相同，Service内部先查询目标。
    lab = await session.get(Lab, lab_id)

    if lab is None:
        raise BusinessException(
            message="实验室不存在！Ovo!",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )

    try:
        # delete()标记待删除对象，commit()真正提交DELETE事务。
        await session.delete(lab)
        await session.commit()
    except IntegrityError as exc:
        # 完整性错误发生后先回滚，让Session恢复到可继续使用的状态。
        await session.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23503":
            raise BusinessException(
                message="实验室仍有关联设备或预约记录，不能删除！Ovo!",
                status_code=http_status.HTTP_409_CONFLICT,
            ) from None
        raise
    except Exception:
        await session.rollback()
        raise
