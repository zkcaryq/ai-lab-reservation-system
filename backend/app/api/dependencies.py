"""依赖注入：定义路由里可直接声明的数据库会话类型。"""
# ↑ 模块 docstring：这个文件很小，只定义一个"快捷类型"。

# 从 typing 导入 Annotated（给类型附加额外元信息的工具）。
from typing import Annotated

# 从 FastAPI 导入 Depends（声明依赖的标记）。
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError

# 从 SQLAlchemy 导入 AsyncSession（异步会话类型）。
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token

# 导入依赖注入函数（负责创建和关闭 Session）。
from app.db.session import get_db_session
from app.models.user import User
from app.services.auth import get_user_by_id

# 路由只声明依赖；不让 Service 依赖 FastAPI 的 Depends 或 HTTPException。
# ↑ 设计说明：依赖只在这一层声明，Service 层保持"不依赖 FastAPI"的纯净。
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
# ↑ 定义一个"带依赖的类型"：DbSession 本质是 AsyncSession 类型，
#   但附带了 Depends(get_db_session) 这个元信息。
#   这样路由函数参数写成 `session: DbSession`，FastAPI 就会自动调用
#   get_db_session 来创建并注入 Session，用完自动关闭。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: DbSession,
) -> User:
    """解析Bearer Token，并返回仍然存在且状态正常的用户。"""

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # JWT的sub是字符串（签发时str(user_id)），查询数据库前要转回整数。
    # sub缺失时是None（int(None)抛TypeError），内容不是数字时抛ValueError。
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的登录凭证",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = await get_user_by_id(session, user_id=user_id)
    if user is None or user.status != 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
