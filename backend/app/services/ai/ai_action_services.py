"""AI待确认动作的创建、确认和取消。"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessException
from app.models.ai_action_models import AIPendingAction
from app.models.equipment_models import Equipment
from app.models.lab_models import Lab
from app.schemas.ai_schemas import (
    ConfirmedReservationAction,
    PendingReservationAction,
    SessionPendingAction,
)
from app.schemas.reservation_schemas import ReservationCreateRequest
from app.services.reservation import reservation_services

logger = logging.getLogger(__name__)

ACTION_TTL_MINUTES = 10


async def prepare_reservation_action(
    session: AsyncSession,
    *,
    user_id: int,
    chat_session_id: int,
    data: ReservationCreateRequest,
) -> PendingReservationAction:
    """校验并保存预约草稿；不向reservations表插入记录。"""

    # 草稿阶段先校验一次，尽早告诉用户实验室关闭、设备维修或时段冲突。
    lab, equipment = await reservation_services.validate_reservation_request(
        session,
        data=data,
    )

    # 同一会话准备新预约时，取消以前仍等待确认的草稿，避免页面出现多个有效按钮。
    await session.execute(
        update(AIPendingAction)
        .where(
            AIPendingAction.user_id == user_id,
            AIPendingAction.session_id == chat_session_id,
            AIPendingAction.action_type == "create_reservation",
            AIPendingAction.status == "pending",
        )
        .values(status="cancelled")
    )

    expires_at = datetime.now(UTC) + timedelta(minutes=ACTION_TTL_MINUTES)
    action = AIPendingAction(
        user_id=user_id,
        session_id=chat_session_id,
        action_type="create_reservation",
        # mode="json"把date和time转换成JSONB可保存的ISO字符串。
        payload=data.model_dump(mode="json"),
        status="pending",
        expires_at=expires_at,
    )
    session.add(action)
    # 只flush取得action.id；ai_services最后与消息、用量一起commit。
    await session.flush()

    return PendingReservationAction(
        action_id=action.id,
        lab_id=lab.id,
        lab_name=lab.name,
        equipment_id=equipment.id if equipment is not None else None,
        equipment_name=equipment.name if equipment is not None else None,
        date=data.date,
        start_time=data.start_time,
        end_time=data.end_time,
        remark=data.remark,
        expires_at=expires_at,
    )


async def confirm_reservation_action(
    session: AsyncSession,
    *,
    user_id: int,
    action_id: int,
) -> ConfirmedReservationAction:
    """锁定本人草稿，重新校验并原子创建真实预约。"""

    statement = (
        select(AIPendingAction)
        .where(
            AIPendingAction.id == action_id,
            AIPendingAction.user_id == user_id,
            AIPendingAction.action_type == "create_reservation",
        )
        # 两个确认请求同时到达时，只允许一个事务先处理该行。
        .with_for_update()
    )
    action = await session.scalar(statement)
    if action is None:
        raise BusinessException(
            message="待确认预约不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # 已完成动作直接返回原预约ID，不再重复插入，形成幂等行为。
    if action.status == "completed" and action.reservation_id is not None:
        return ConfirmedReservationAction(
            action_id=action.id,
            reservation_id=action.reservation_id,
            already_confirmed=True,
        )

    if action.status != "pending":
        raise BusinessException(
            message="该预约草稿已经失效！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    now = datetime.now(UTC)
    if action.expires_at <= now:
        action.status = "expired"
        await session.commit()
        raise BusinessException(
            message="预约确认已过期，请重新发起！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    # JSONB中的ISO日期和时间会由Pydantic重新解析成date/time对象。
    data = ReservationCreateRequest.model_validate(action.payload)

    try:
        # commit=False让预约INSERT和动作状态变更属于同一个数据库事务。
        reservation = await reservation_services.create_reservation(
            session,
            user_id=user_id,
            data=data,
            commit=False,
        )
        action.status = "completed"
        action.completed_at = now
        action.reservation_id = reservation.id
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return ConfirmedReservationAction(
        action_id=action.id,
        reservation_id=reservation.id,
        already_confirmed=False,
    )


async def cancel_reservation_action(
    session: AsyncSession,
    *,
    user_id: int,
    action_id: int,
) -> None:
    """取消本人仍处于pending状态的预约草稿。"""

    statement = (
        select(AIPendingAction)
        .where(
            AIPendingAction.id == action_id,
            AIPendingAction.user_id == user_id,
        )
        .with_for_update()
    )
    action = await session.scalar(statement)
    if action is None:
        raise BusinessException(
            message="待确认预约不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if action.status != "pending":
        raise BusinessException(
            message="该预约草稿已经不能取消！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    action.status = "cancelled"
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def list_session_actions(
    session: AsyncSession,
    *,
    user_id: int,
    chat_session_id: int,
) -> list[SessionPendingAction]:
    """列出本会话还没作废的预约草稿，供前端刷新后恢复确认卡片。

    实时响应里的 pending_action 只在那一轮存在；用户刷新页面或从会话列表切回来时
    前端拿不到 action_id，卡片就再也点不了了，而草稿在 TTL 内其实仍然有效。

    cancelled 是"被同会话的新草稿顶掉"，对用户没有意义，不返回。
    这里只读不写：过期的 pending 仍按 pending 返回，由前端结合 expires_at 判断能否点击，
    真正确认时 confirm_reservation_action 会给出权威的 409。
    """

    rows = (
        await session.scalars(
            select(AIPendingAction)
            .where(
                AIPendingAction.session_id == chat_session_id,
                AIPendingAction.user_id == user_id,
                AIPendingAction.action_type == "create_reservation",
                AIPendingAction.status != "cancelled",
            )
            .order_by(AIPendingAction.id)
        )
    ).all()
    if not rows:
        return []

    # payload 里只存ID，卡片要让用户看清"哪个实验室、哪台设备"，所以名称得现查一次。
    # 用两次批量查询而不是循环里逐条查，避免草稿多了产生 N+1。
    lab_ids = {row.payload.get("lab_id") for row in rows if row.payload.get("lab_id")}
    equipment_ids = {
        row.payload.get("equipment_id") for row in rows if row.payload.get("equipment_id")
    }
    lab_names: dict[int, str] = {}
    equipment_names: dict[int, str] = {}
    if lab_ids:
        for lab in (await session.scalars(select(Lab).where(Lab.id.in_(lab_ids)))).all():
            lab_names[lab.id] = lab.name
    if equipment_ids:
        for item in (
            await session.scalars(select(Equipment).where(Equipment.id.in_(equipment_ids)))
        ).all():
            equipment_names[item.id] = item.name

    result: list[SessionPendingAction] = []
    for row in rows:
        try:
            # 预约结构变过的话这条草稿就恢复不了，跳过它而不是让整段历史打不开。
            data = ReservationCreateRequest.model_validate(row.payload)
        except Exception:
            logger.warning("跳过无法解析的预约草稿 %s", row.id)
            continue
        result.append(
            SessionPendingAction(
                action_id=row.id,
                lab_id=data.lab_id,
                lab_name=lab_names.get(data.lab_id, f"实验室 #{data.lab_id}"),
                equipment_id=data.equipment_id,
                equipment_name=equipment_names.get(data.equipment_id)
                if data.equipment_id
                else None,
                date=data.date,
                start_time=data.start_time,
                end_time=data.end_time,
                remark=data.remark,
                expires_at=row.expires_at,
                status=row.status,
                reservation_id=row.reservation_id,
            )
        )
    return result
