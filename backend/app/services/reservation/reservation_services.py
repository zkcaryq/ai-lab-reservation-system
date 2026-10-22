"""预约业务服务。

核心职责包括开放状态/时段校验、设备归属校验、冲突检测、事务与行锁、取消和审核，
以及后台扫描超时待审核记录。这里才是预约规则的唯一可信实现，AI 只能生成待确认草稿。
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

from fastapi import status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BusinessException
from app.core.settings import get_settings
from app.db.session import session_factory
from app.models.equipment_models import Equipment
from app.models.lab_models import Lab
from app.models.reservation_models import Reservation
from app.models.user_models import User
from app.schemas.reservation_schemas import ReservationCreateRequest

settings = get_settings()
logger = logging.getLogger(__name__)

# 中国全年使用UTC+8，不实行夏令时。显式声明后不会受开发电脑东京时区影响。
CHINA_TIMEZONE = timezone(timedelta(hours=8))


async def process_pending_reservations() -> tuple[int, int]:
    """取消已经开始的待审核预约，并自动通过等待超时的未来预约。

    返回值依次是“自动取消数量、自动通过数量”。两个UPDATE都要求status仍为0，
    因此管理员、用户和后台任务同时修改同一记录时，不会覆盖已经完成的状态变更。
    """

    now = datetime.now(CHINA_TIMEZONE)
    today = now.date()
    current_time = now.time().replace(tzinfo=None)

    # created_at是带时区字段，数据库连接也统一使用UTC；转换成UTC后再计算审核截止时间。
    auto_approve_before = now.astimezone(UTC) - timedelta(
        minutes=settings.RESERVATION_AUTO_APPROVE_MINUTES
    )

    # 待审核记录一旦到达预约开始时间，再批准已经没有意义，统一转为已取消。
    cancel_statement = (
        update(Reservation)
        .where(
            Reservation.status == 0,
            or_(
                Reservation.date < today,
                and_(
                    Reservation.date == today,
                    Reservation.start_time <= current_time,
                ),
            ),
        )
        .values(status=3)
    )

    # 只有等待超过配置时间并且预约尚未开始的记录才自动通过。
    approve_statement = (
        update(Reservation)
        .where(
            Reservation.status == 0,
            Reservation.created_at <= auto_approve_before,
            or_(
                Reservation.date > today,
                and_(
                    Reservation.date == today,
                    Reservation.start_time > current_time,
                ),
            ),
        )
        .values(status=1)
    )

    async with session_factory() as session:
        try:
            cancel_result = await session.execute(cancel_statement)
            approve_result = await session.execute(approve_statement)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return cancel_result.rowcount or 0, approve_result.rowcount or 0


async def run_pending_reservation_scan() -> None:
    """应用运行期间定期处理等待超时或已经开始的待审核预约。"""

    while True:
        try:
            cancelled, approved = await process_pending_reservations()
            if cancelled or approved:
                logger.info(
                    "pending reservations processed cancelled=%s approved=%s",
                    cancelled,
                    approved,
                )
        except asyncio.CancelledError:
            # 应用关闭时取消后台任务是正常生命周期，必须继续抛出以结束循环。
            raise
        except Exception:
            # 单次扫描失败不能让后台任务永久停止；日志保留堆栈，下一轮继续重试。
            logger.exception("pending reservation scan failed")

        await asyncio.sleep(settings.RESERVATION_REVIEW_SCAN_SECONDS)


async def get_reservation_page_list(
    session: AsyncSession,
    *,
    current_user: User,
    page: int,
    page_size: int,
    # Router已经把HTTP查询字符串转换为整数，并校验范围为0～3。
    # Service不重复依赖FastAPI的Query，只接收转换后的整数或None。
    reservation_status: int | None = None,
) -> tuple[list[Reservation], int]:
    """分页查询当前用户有权查看的预约记录。"""

    # conditions会同时提供给count和列表SQL，保证total和list使用相同筛选规则。
    conditions = []

    # 非管理员只能查询自己的预约；即使前端伪造参数也无法看到他人记录。
    if current_user.role != "admin":
        conditions.append(Reservation.user_id == current_user.id)

    # None表示不按状态筛选；0是有效状态，不能写成if reservation_status。
    if reservation_status is not None:
        conditions.append(Reservation.status == reservation_status)

    count_statement = select(func.count()).select_from(Reservation).where(*conditions)
    total = await session.scalar(count_statement)

    list_statement = (
        select(Reservation)
        # Reservation的三个关系都是lazy="raise"，必须在Session仍然可用时提前加载。
        .options(
            selectinload(Reservation.user),
            selectinload(Reservation.lab),
            selectinload(Reservation.equipment),
        )
        .where(*conditions)
        .order_by(Reservation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.scalars(list_statement)
    reservations = list(result.all())
    return reservations, total or 0


async def validate_reservation_request(
    session: AsyncSession,
    *,
    data: ReservationCreateRequest,
    lock_lab: bool = False,
) -> tuple[Lab, Equipment | None]:
    """校验预约参数；真实创建时可锁定实验室以串行化冲突检查。"""

    now = datetime.now(CHINA_TIMEZONE)

    if data.date < now.date():
        raise BusinessException(
            message="预约日期不能早于今天！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if data.end_time <= data.start_time:
        raise BusinessException(
            message="预约结束时间必须晚于开始时间！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    start_datetime = datetime.combine(
        data.date,
        data.start_time,
        tzinfo=CHINA_TIMEZONE,
    )
    if start_datetime <= now:
        raise BusinessException(
            message="预约开始时间不能早于当前时间！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    lab_statement = select(Lab).where(Lab.id == data.lab_id)
    if lock_lab:
        # 两个不同请求同时预约同一实验室时，先锁定同一Lab行再检查冲突。
        # 后到事务会等待前一个事务提交，随后才能看到刚写入的Reservation。
        lab_statement = lab_statement.with_for_update()
    lab = await session.scalar(lab_statement)
    if lab is None:
        raise BusinessException(
            message="实验室不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if lab.status != 1:
        raise BusinessException(
            message="实验室已关闭，暂时不能预约！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )
    if lab.open_time is not None and data.start_time < lab.open_time:
        raise BusinessException(
            message="预约开始时间不能早于实验室开放时间！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if lab.close_time is not None and data.end_time > lab.close_time:
        raise BusinessException(
            message="预约结束时间不能晚于实验室关闭时间！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    equipment: Equipment | None = None
    if data.equipment_id is not None:
        equipment = await session.get(Equipment, data.equipment_id)
        if equipment is None:
            raise BusinessException(
                message="实验室设备不存在！Ovo!",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if equipment.lab_id != data.lab_id:
            raise BusinessException(
                message="该设备不属于所选实验室！Ovo!",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if equipment.status != 1:
            raise BusinessException(
                message="实验室设备正在维修，暂时不能预约！Ovo!",
                status_code=status.HTTP_409_CONFLICT,
            )

    conflict_conditions = [
        Reservation.lab_id == data.lab_id,
        Reservation.date == data.date,
        Reservation.status.in_([0, 1]),
        Reservation.start_time < data.end_time,
        Reservation.end_time > data.start_time,
    ]
    if data.equipment_id is not None:
        # 预约具体设备时，需要同时排除两类占用：
        # 1. 同一实验室的“整室预约”（equipment_id 为 NULL）；
        # 2. 同一台设备在重叠时段的预约。
        # 其它设备的预约可以并存，因此不能只按 lab_id 判定冲突。
        conflict_conditions.append(
            or_(
                Reservation.equipment_id.is_(None),
                Reservation.equipment_id == data.equipment_id,
            )
        )
    # 整室预约不追加设备条件：只要该实验室已有任意重叠预约，就不能再整室占用。

    conflict_statement = select(Reservation.id).where(*conflict_conditions).limit(1)
    conflict_id = await session.scalar(conflict_statement)
    if conflict_id is not None:
        raise BusinessException(
            message="该时段已被预约！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    return lab, equipment


async def create_reservation(
    session: AsyncSession,
    *,
    user_id: int,
    data: ReservationCreateRequest,
    commit: bool = True,
) -> Reservation:
    """校验并创建预约；commit=False供AI确认事务组合使用。"""

    # 确认动作不能相信几分钟前草稿阶段的结果，必须重新执行全部校验。
    await validate_reservation_request(session, data=data, lock_lab=True)

    reservation = Reservation(
        user_id=user_id,
        lab_id=data.lab_id,
        equipment_id=data.equipment_id,
        date=data.date,
        start_time=data.start_time,
        end_time=data.end_time,
        remark=data.remark,
        status=0,
    )
    session.add(reservation)

    try:
        if commit:
            await session.commit()
            await session.refresh(reservation)
        else:
            # flush发送INSERT并取得id，但事务仍由上层统一提交。
            await session.flush()
    except Exception:
        await session.rollback()
        raise

    return reservation


async def cancel_reservation(
    session: AsyncSession,
    *,
    current_user: User,
    reservation_id: int,
) -> None:
    """取消本人待审核或已通过、且距离开始不少于一小时的预约。"""

    reservation = await session.get(Reservation, reservation_id)

    if reservation is None:
        raise BusinessException(
            message="预约记录不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if reservation.user_id != current_user.id:
        raise BusinessException(
            message="无权取消他人的预约！Ovo!",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # 待审核(0)和已通过(1)都允许主动取消；已拒绝(2)和已取消(3)
    # 已经是终态，不能再次执行取消操作。
    if reservation.status not in (0, 1):
        raise BusinessException(
            message="当前预约状态不能取消！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    # 数据库存的是中国当地日期和不带时区的时刻。组合后显式附加UTC+8，
    # 避免开发电脑的东京时区影响“一小时截止时间”的判断。
    now = datetime.now(CHINA_TIMEZONE)
    start_datetime = datetime.combine(
        reservation.date,
        reservation.start_time,
        tzinfo=CHINA_TIMEZONE,
    )

    # 已经开始的预约当然不能取消；单独提示比统一说“不足一小时”更准确。
    if start_datetime <= now:
        raise BusinessException(
            message="预约已经开始，不能取消！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    # “不足一小时”使用严格小于；恰好还剩一小时允许取消。
    if start_datetime - now < timedelta(hours=1):
        raise BusinessException(
            message="距离预约开始不足一小时，不能取消！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    reservation.status = 3

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def audit_reservation(
    session: AsyncSession,
    *,
    reservation_id: int,
    audit_status: Literal[1, 2],
) -> None:
    """把待审核预约改为已通过或已拒绝。"""

    reservation = await session.get(Reservation, reservation_id)

    if reservation is None:
        raise BusinessException(
            message="预约记录不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if reservation.status != 0:
        raise BusinessException(
            message="当前预约状态不支持审核！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    reservation.status = audit_status

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
