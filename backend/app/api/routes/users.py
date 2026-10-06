from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.schemas.user import UserResponse

router = APIRouter(prefix="/user", tags=["用户信息接口"])


@router.get("/info")
async def get_user_info(current_user: CurrentUser):
    """返回Bearer Token对应的当前用户信息。"""

    return {
        "code": 200,
        "message": "请求成功",
        "data": UserResponse.model_validate(current_user),
    }
