"""设备 HTTP 路由。

Router 只负责鉴权、参数声明和中文 HTTP 响应；设备可用性、唯一性与事务处理都交给
``equipment_services``，避免业务规则散落在接口层。
"""

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import CurrentAdmin, CurrentUser, DbSession
from app.models.equipment_models import Equipment
from app.schemas.apiresponse import ApiResponse
from app.schemas.equipment_schemas import (
    EquipmentCreateRequest,
    EquipmentPageResponse,
    EquipmentResponse,
    EquipmentUpdateRequest,
)
from app.services.lab import equipment_services

router = APIRouter(prefix="/equipment", tags=["实验室设备管理"])


def to_equipment_response(equipment: Equipment) -> EquipmentResponse:
    """把已加载lab关系的Equipment转换为包含lab_name的响应。"""

    # model_validate读取Equipment中的id、lab_id、name等同名属性。
    response = EquipmentResponse.model_validate(equipment)

    # lab_name不是设备表字段，需要从已经由Service加载的关系中补充。
    response.lab_name = equipment.lab.name
    return response


@router.get("/list")
async def get_equipment_list(
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    keywords: str | None = Query(default=None, max_length=100),
    lab_id: int | None = Query(default=None, gt=0),
) -> ApiResponse:
    """分页查询当前用户有权查看的设备，可按名称和实验室筛选。"""
    visible_lab_status = None if current_user.role == "admin" else 1
    equipments, total = await equipment_services.get_equipment_page_list(
        session,
        page=page,
        page_size=page_size,
        keywords=keywords,
        lab_id=lab_id,
        lab_status=visible_lab_status,
    )

    page_data = EquipmentPageResponse(
        list=[to_equipment_response(item) for item in equipments],
        total=total,
    )
    return ApiResponse.success(data=page_data)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_equipment(
    data: EquipmentCreateRequest,
    session: DbSession,
    _current_admin: CurrentAdmin,
) -> ApiResponse:
    """管理员新增实验室设备。"""

    equipment = await equipment_services.create_equipment(
        session,
        data=data,
    )
    return ApiResponse.success(
        code=status.HTTP_201_CREATED,
        message="设备创建成功！Ovo!",
        data=to_equipment_response(equipment),
    )


@router.patch("/{equipment_id}")
async def update_equipment(
    data: EquipmentUpdateRequest,
    session: DbSession,
    _current_admin: CurrentAdmin,
    equipment_id: int = Path(gt=0),
) -> ApiResponse:
    """管理员部分修改实验室设备。"""

    equipment = await equipment_services.update_equipment(
        session,
        equipment_id=equipment_id,
        data=data,
    )
    return ApiResponse.success(
        message="设备修改成功！Ovo!",
        data=to_equipment_response(equipment),
    )


@router.delete("/{equipment_id}")
async def delete_equipment(
    session: DbSession,
    _current_admin: CurrentAdmin,
    equipment_id: int = Path(gt=0),
) -> ApiResponse:
    """管理员删除实验室设备。"""

    await equipment_services.delete_equipment(
        session,
        equipment_id=equipment_id,
    )

    return ApiResponse.success(message="设备删除成功！Ovo!")
