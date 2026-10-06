"""登录接口路由。

请求调用链：客户端 -> 本文件的 ``login()`` -> ``services/auth.py`` 中的
``auth_login()`` -> PostgreSQL。Service返回结果后，再由本路由生成HTTP响应。
"""

from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest
from app.schemas.user import UserResponse
from app.services.auth import auth_login

# 创建认证模块的子路由。
# 该路由稍后会在app/api/router.py中挂到带有“/api”前缀的api_router上，
# 因此下面的“/auth”最终会变成“/api/auth”。
router = APIRouter(prefix="/auth", tags=["登录权限验证"])


@router.post("/login")
async def login(data: LoginRequest, session: DbSession):
    """接收登录请求，并把查询与密码比较交给Service处理。

    FastAPI会完成两件事：
    1. 把请求JSON解析成 ``LoginRequest``，然后传给data参数；
    2. 根据 ``DbSession`` 中的依赖声明创建 ``AsyncSession``，传给session参数，
       请求结束后再自动关闭Session。

    最终接口地址是 ``POST /api/auth/login``。
    """

    # 调用Service层。因为auth_login是异步函数，所以这里必须使用await。
    # ``*`` 后面的参数必须按名称传入，因此要写username=和password=。
    user = await auth_login(
        session,
        username=data.username,
        password=data.password,
    )

    # Service用None表示“账号不存在或密码不同”。
    # 本章按照原教程直接返回字典，暂时不加入统一响应和全局异常处理。
    if user is None:
        return {
            "code": 400,
            "message": "账号或密码错误",
        }
    if user.status != 1:
        return {
            "code": 403,
            "message": "账号已被禁用",
        }
    token = create_access_token(user.id)

    # 此时user是SQLAlchemy的User ORM对象。
    # UserResponse配置了from_attributes=True，因此可以从user.id、user.username
    # 等对象属性读取数据，并且只输出UserResponse中声明过的字段，不返回password。
    return {
        "code": 200,
        "message": "登录成功",
        "data": {
            "token": token,
            "user": UserResponse.model_validate(user),
        },
    }
