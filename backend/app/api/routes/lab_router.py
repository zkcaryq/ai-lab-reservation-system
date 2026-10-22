"""实验室 HTTP 路由：学生读取，管理员创建、修改和删除。"""

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import CurrentAdmin, CurrentUser, DbSession
from app.schemas.apiresponse import ApiResponse
from app.schemas.lab_schemas import (
    LabCreateRequest,
    LabPageResponse,
    LabResponse,
    LabUpdateRequest,
)
from app.services.lab import lab_services

router = APIRouter(prefix="/lab", tags=["实验室管理"])


@router.get("/list")
async def get_lab_list(
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    keywords: str | None = Query(default=None, max_length=100),
    lab_status: int | None = Query(
        default=None,
        alias="status",
        ge=0,
        le=1,
    ),
) -> ApiResponse:
    """分页查询当前用户有权查看的实验室。"""

    # URL查询参数仍然叫status，但Python变量使用lab_status，避免和从FastAPI
    # 导入的status状态码模块重名。管理员可以不筛选或筛选0/1；非管理员
    # 无论是否伪造status参数，后端都强制只查询开放状态1。
    effective_status = lab_status if current_user.role == "admin" else 1
    labs, total = await lab_services.get_lab_page_list(
        session,
        page=page,
        page_size=page_size,
        keywords=keywords,
        status=effective_status,
    )

    page_data = LabPageResponse(
        list=[LabResponse.model_validate(lab) for lab in labs],
        total=total,
    )

    return ApiResponse.success(data=page_data)


@router.get("/{lab_id}")
async def get_lab(
    session: DbSession,
    current_user: CurrentUser,
    lab_id: int = Path(gt=0),
) -> ApiResponse:
    """按角色读取单个实验室；普通用户只能看到启用状态。"""

    visible_status = None if current_user.role == "admin" else 1
    lab = await lab_services.get_lab_by_id(session, lab_id=lab_id, status=visible_status)
    return ApiResponse.success(data=LabResponse.model_validate(lab))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lab(
    data: LabCreateRequest,
    session: DbSession,
    _current_admin: CurrentAdmin,
) -> ApiResponse:
    """管理员新增实验室。"""

    # 与用户管理Router相同：存在性检查和写事务都由Service完成。
    lab = await lab_services.create_lab(session, data=data)

    return ApiResponse.success(
        code=status.HTTP_201_CREATED,
        message="实验室创建成功！Ovo!",
        data=LabResponse.model_validate(lab),
    )


@router.patch("/{lab_id}")
async def update_lab(
    data: LabUpdateRequest,
    session: DbSession,
    _current_admin: CurrentAdmin,
    lab_id: int = Path(gt=0),
) -> ApiResponse:
    """管理员部分修改实验室。"""

    updated_lab = await lab_services.update_lab(
        session,
        lab_id=lab_id,
        data=data,
    )

    return ApiResponse.success(
        message="实验室修改成功！Ovo!",
        data=LabResponse.model_validate(updated_lab),
    )


@router.delete("/{lab_id}")
async def delete_lab(
    session: DbSession,
    _current_admin: CurrentAdmin,
    lab_id: int = Path(gt=0),
) -> ApiResponse:
    """管理员删除实验室。"""

    await lab_services.delete_lab(session, lab_id=lab_id)
    return ApiResponse.success(
        message="实验室删除成功！Ovo!",
    )
