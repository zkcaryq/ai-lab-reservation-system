"""路由层依赖注入：提供数据库Session和JWT当前用户。

本文件只服务于FastAPI Router：
- ``DbSession`` 自动创建并关闭每次请求独立的AsyncSession；
- ``CurrentUser`` 提取Bearer Token、验证JWT并查询数据库中的有效用户。

Service层不导入本文件，避免业务逻辑依赖FastAPI的Depends和HTTPException。
"""

# 从 typing 导入 Annotated（给类型附加额外元信息的工具）。
from typing import Annotated

# Depends声明依赖关系；HTTPException负责中断请求；status提供可读的HTTP状态常量。
from fastapi import Depends, HTTPException, status

# OAuth2PasswordBearer负责从Authorization: Bearer <token>请求头中提取Token字符串。
from fastapi.security import OAuth2PasswordBearer

# PyJWT的所有无效Token异常都继承InvalidTokenError，可以统一转换成HTTP 401。
from jwt.exceptions import InvalidTokenError

# 从 SQLAlchemy 导入 AsyncSession（异步会话类型）。
from sqlalchemy.ext.asyncio import AsyncSession

# decode_access_token验证JWT签名与过期时间，成功后返回Token载荷字典。
from app.core.security import decode_access_token

# 导入依赖注入函数（负责创建和关闭 Session）。
from app.db.session import get_db_session

# User既是get_current_user的返回类型，也是CurrentUser最终注入Router的对象类型。
from app.models.user_models import User

# get_user_by_id通过AsyncSession查询Token中用户ID对应的数据库用户。
from app.services.auth.user_services import get_user_by_id

# 路由只声明依赖；不让 Service 依赖 FastAPI 的 Depends 或 HTTPException。
# ↑ 设计说明：依赖只在这一层声明，Service 层保持"不依赖 FastAPI"的纯净。
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
# ↑ 定义一个"带依赖的类型"：DbSession 本质是 AsyncSession 类型，
#   但附带了 Depends(get_db_session) 这个元信息。
#   这样路由函数参数写成 `session: DbSession`，FastAPI 就会自动调用
#   get_db_session 来创建并注入 Session，用完自动关闭。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# ↑ 请求没有Bearer Token时，oauth2_scheme会直接产生HTTP 401；
#   请求带Token时，它只负责提取字符串，不负责验证JWT签名。
#   tokenUrl主要用于OpenAPI描述认证入口，不会替我们调用JSON登录接口。


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: DbSession,
) -> User:
    """解析Bearer Token，并返回仍然存在且状态正常的User ORM对象。

    FastAPI调用顺序：
    1. oauth2_scheme从请求头提取Token并注入token；
    2. DbSession创建AsyncSession并注入session；
    3. 本函数验证Token、读取sub并查询用户；
    4. 成功时把User返回给声明CurrentUser的Router；
    5. 失败时抛HTTPException，由统一HTTP异常处理器输出401 JSON。
    """

    try:
        # 验证JWT签名、格式和exp过期时间；成功后得到sub/iat/exp等载荷。
        payload = decode_access_token(token)
    except InvalidTokenError:
        # 签名错误、Token过期或格式损坏都统一视为登录失效。
        # from None隐藏底层JWT异常上下文，避免响应或调试信息出现无关异常链。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已失效，请重新登录！OVo!",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # JWT的sub是字符串（签发时str(user_id)），查询数据库前要转回整数。
    # sub缺失时是None（int(None)抛TypeError），内容不是数字时抛ValueError。
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的登录凭证！OVo!",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # JWT只证明Token曾由本服务签发，不能证明数据库中的用户现在仍存在且可用。
    # 因此每次访问受保护接口时，都根据sub重新查询当前用户状态。
    user = await get_user_by_id(session, user_id=user_id)

    # 用户被删除或被禁用时，即使Token还没有过期，也不允许继续访问。
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在！OVo!",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用！OVo!",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 成功时返回User，而不是ApiResponse：依赖负责“提供当前用户”，
    # Router拿到User后再决定本接口要返回什么业务数据和成功响应。
    return user


# CurrentUser不是一个新的User类，而是“User类型 + get_current_user依赖”的快捷写法。
# Router声明current_user: CurrentUser时，FastAPI会先执行get_current_user()，
# 鉴权成功后把返回的User对象注入参数；失败时Router函数根本不会开始执行。
CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(current_user: CurrentUser) -> User:
    """在普通登录鉴权成功后，继续检查当前用户是否为管理员。

    依赖执行顺序是：
    ``oauth2_scheme → get_current_user → get_current_admin → Router``。
    因此本函数不需要再次解析JWT、查询数据库或检查status，只增加角色授权判断。
    """

    # 数据库中的角色不是admin，说明用户已经登录但没有访问管理员资源的权限。
    if current_user.role != "admin":
        # 403表示“身份已经确认，但没有权限”；这里不能使用401，401表示尚未通过认证。
        # HTTPException会被项目的全局HTTP异常处理器转换成统一ApiResponse结构。
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限访问！Ovo!",
        )

    # 角色检查通过后原样返回User，FastAPI会把它注入声明CurrentAdmin的Router参数。
    return current_user


# CurrentAdmin与CurrentUser的关系类似“在已有登录依赖外再包一层管理员检查”。
# Router只需声明 ``_current_admin: CurrentAdmin``，不必同时再声明CurrentUser。
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
