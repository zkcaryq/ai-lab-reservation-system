"""登录接口路由。

请求调用链：客户端 -> 本文件的 ``login()`` -> ``services/auth.py`` 中的
``auth_login()`` -> PostgreSQL。Service返回结果后，再由本路由生成HTTP响应。
"""

from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.core.errors import BusinessException
from app.core.security import create_access_token
from app.schemas.apiresponse import ApiResponse
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserResponse
from app.services.auth import auth_login

# 创建认证模块的子路由。
# 该路由稍后会在app/api/router.py中挂到带有“/api”前缀的api_router上，
# 因此下面的“/auth”最终会变成“/api/auth”。
router = APIRouter(prefix="/auth", tags=["登录权限验证"])


@router.post("/login")
async def login(data: LoginRequest, session: DbSession) -> ApiResponse:
    """验证账号与Argon2id密码哈希，成功后签发JWT。

    FastAPI首先把请求JSON解析成LoginRequest，并通过DbSession创建AsyncSession。
    本函数只编排HTTP流程：调用Service、判断业务结果、签发Token并构造响应。
    """

    # Router不直接查询数据库，只把Session和请求字段交给Service。
    # auth_login()是异步函数，内部会等待PostgreSQL查询，所以这里必须使用await。
    user = await auth_login(
        session,
        username=data.username,
        password=data.password,
    )

    # Service用None同时表示“账号不存在”和“密码错误”，避免向攻击者泄露账号是否存在。
    # 这是预期内业务失败，抛BusinessException交给统一处理器，不记录500堆栈。
    if user is None:
        raise BusinessException(
            message="账号或密码错误",
            status_code=400,
        )

    # 能走到这里说明账号密码正确；如果账号被禁用，使用403表示不允许继续访问。
    if user.status != 1:
        raise BusinessException(
            message="账号已被禁用",
            status_code=403,
        )

    # 只有账号、密码和状态都通过后才签发Token，禁用账号不会拿到有效JWT。
    token = create_access_token(user.id)

    # LoginResponse约束data内部必须有token和user两个字段。
    # UserResponse.model_validate()从SQLAlchemy User对象读取同名属性，
    # 而UserResponse没有password字段，所以响应不会输出密码哈希。
    login_data = LoginResponse(
        token=token,
        user=UserResponse.model_validate(user),
    )

    # 登录成功属于普通成功并返回数据，因此真实HTTP状态码和JSON code都使用默认200。
    return ApiResponse.success(
        message="登录成功",
        data=login_data,
    )
