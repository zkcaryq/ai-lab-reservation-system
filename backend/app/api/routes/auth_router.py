"""认证接口路由：负责登录和注册的HTTP流程。

登录调用链：客户端 -> ``login()`` -> ``auth_login()`` -> PostgreSQL。
注册调用链：客户端 -> ``register()`` -> ``auth_register()`` -> PostgreSQL。

本文件只负责HTTP输入输出、调用Service和选择业务错误；数据库查询、密码哈希
与事务提交都放在Service中。
"""

# APIRouter用于声明一组具有共同前缀和标签的FastAPI路由。
from fastapi import APIRouter, status

# DbSession是带Depends元信息的AsyncSession类型，FastAPI会为每次请求自动注入会话。
from app.api.dependencies import DbSession

# create_access_token在登录验证成功后根据用户ID签发JWT。
from app.core.security import create_access_token

# ApiResponse统一成功响应最外层的code、message和data字段。
from app.schemas.apiresponse import ApiResponse

# 三个Schema分别描述登录请求、登录成功数据和注册请求。
from app.schemas.auth_schemas import LoginRequest, LoginResponse, RegisterRequest

# UserResponse从User ORM对象中选择允许返回客户端的字段，不包含password。
from app.schemas.user_schemas import UserResponse

# Router调用Service完成数据库查询、密码验证、注册写入和事务操作。
from app.services.auth.auth_services import auth_login, auth_register

# 创建认证模块的子路由。
# 该路由稍后会在app/api/router.py中挂到带有“/api”前缀的api_router上，
# 因此下面的“/auth”最终会变成“/api/auth”。
router = APIRouter(prefix="/auth", tags=["登录权限验证"])


@router.post("/login")
# 装饰器把下面的login函数注册为POST /api/auth/login；/api来自上层api_router。
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

    # Service成功返回说明账号、密码和状态都通过，才允许签发Token。
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
        message="登录成功!Ovo!",
        data=login_data,
    )


@router.post("/register")
# 装饰器把下面的register函数注册为POST /api/auth/register。
async def register(data: RegisterRequest, session: DbSession) -> ApiResponse:
    """创建普通学生账号。

    FastAPI先把请求JSON解析成RegisterRequest，并创建AsyncSession注入session。
    Router随后调用Service；它自己不执行SQL、不哈希密码，也不提交事务。
    """

    # 把同一个请求级Session以及Schema中解析出的普通字段交给注册Service。
    # auth_register内部包含异步数据库操作，所以这里必须使用await等待结果。
    await auth_register(
        # 第一个位置参数是FastAPI通过DbSession创建的AsyncSession。
        session,
        # 星号后面的Service参数必须用名称传递，避免多个字符串参数顺序写错。
        username=data.username,
        # 此时仍是请求中的明文密码，Service会立即使用Argon2id进行哈希。
        password=data.password,
        # name允许为None；Service会在缺省时回退到username。
        name=data.name,
    )

    # 能执行到这里说明用户已经写入数据库；本章不自动登录，也不返回JWT。
    # 真实HTTP状态码由装饰器的status_code=201设置，响应体code也显式保持201。
    return ApiResponse.success(
        code=status.HTTP_201_CREATED,
        message="注册成功!Ovo!",
    )
