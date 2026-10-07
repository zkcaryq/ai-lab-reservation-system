from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.schemas.apiresponse import ApiResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/user", tags=["用户信息接口"])


@router.get("/info")
async def get_user_info(current_user: CurrentUser) -> ApiResponse:
    """返回Bearer Token对应的当前用户信息。

    Router开始执行时，CurrentUser已经完成Token验证、数据库查询和状态检查，
    因此这里拿到的一定是仍然存在且状态正常的User对象。
    """

    # UserResponse只选择允许公开的用户字段，不会把password哈希返回客户端。
    user_data = UserResponse.model_validate(current_user)

    # 由ApiResponse.success()统一生成code/message/data外层结构。
    return ApiResponse.success(data=user_data)
