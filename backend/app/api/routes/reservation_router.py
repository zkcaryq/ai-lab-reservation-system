"""预约 HTTP 路由：学生发起/取消预约，管理员分页查看并审核。"""

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import CurrentAdmin, CurrentUser, DbSession
from app.models.reservation_models import Reservation
from app.schemas.apiresponse import ApiResponse
from app.schemas.reservation_schemas import (
    AuditReservationRequest,
    ReservationCreateRequest,
    ReservationPageResponse,
    ReservationResponse,
)
from app.services.reservation import reservation_services

router = APIRouter(prefix="/reservation", tags=["预约相关接口"])


def to_reservation_response(
    reservation: Reservation,
) -> ReservationResponse:
    """把已加载关系的Reservation转换成列表响应。"""

    response = ReservationResponse.model_validate(reservation)

    # user和lab是非空外键，查询时也已经通过selectinload加载。
    response.user_name = reservation.user.name
    response.lab_name = reservation.lab.name

    # equipment_id为空表示只预约实验室；设备关系此时也是None。
    if reservation.equipment is None:
        response.equipment_name = None
        response.type = "实验室"
    else:
        response.equipment_name = reservation.equipment.name
        response.type = "设备"

    return response


@router.get("/list")
async def get_reservation_list(
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    # URL查询参数在HTTP层都是字符串，例如前端选择“待审核”时实际发送status=0。
    # 这里使用int让FastAPI先把字符串"0"转换成整数0，再用ge/le限制合法范围。
    # 不能写成Literal[0, 1, 2, 3]：Pydantic不会把查询字符串"0"转换为整数Literal，
    # 即使前端传的是数字，进入URL后也会变成字符串，从而错误地返回422。
    reservation_status: int | None = Query(
        default=None,
        alias="status",
        ge=0,
        le=3,
    ),
) -> ApiResponse:
    """学生查看自己的预约；管理员查看全部预约。"""

    reservations, total = await reservation_services.get_reservation_page_list(
        session,
        current_user=current_user,
        page=page,
        page_size=page_size,
        reservation_status=reservation_status,
    )

    page_data = ReservationPageResponse(
        list=[to_reservation_response(item) for item in reservations],
        total=total,
    )
    return ApiResponse.success(data=page_data)


@router.patch("/{reservation_id}/cancel")
async def cancel_reservation(
    session: DbSession,
    current_user: CurrentUser,
    reservation_id: int = Path(gt=0),
) -> ApiResponse:
    """取消本人待审核或已通过、且距离开始不少于一小时的预约。"""

    await reservation_services.cancel_reservation(
        session,
        current_user=current_user,
        reservation_id=reservation_id,
    )

    return ApiResponse.success(message="预约取消成功！Ovo!")


@router.patch("/{reservation_id}/audit")
async def audit_reservation(
    data: AuditReservationRequest,
    session: DbSession,
    _current_admin: CurrentAdmin,
    reservation_id: int = Path(gt=0),
) -> ApiResponse:
    """管理员通过或拒绝待审核预约。"""

    await reservation_services.audit_reservation(
        session,
        reservation_id=reservation_id,
        audit_status=data.status,
    )

    action = "通过" if data.status == 1 else "拒绝"
    return ApiResponse.success(message=f"预约审核{action}！Ovo!")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_reservation(
    data: ReservationCreateRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> ApiResponse:
    """当前登录用户提交实验室或设备预约。"""

    # Service完成全部预约业务校验；预期失败会直接抛BusinessException，
    # 再由全局异常处理器转换成统一错误响应，因此Router不重复逐项判断。
    await reservation_services.create_reservation(
        session,
        user_id=current_user.id,
        data=data,
    )

    return ApiResponse.success(
        code=status.HTTP_201_CREATED,
        message="预约已提交，请等待审核！Ovo!",
    )
