"""登录业务逻辑。

调用方向：``app/api/routes/auth.py`` 中的 ``login()`` 路由函数
会调用本文件的 ``auth_login()``。Service只负责查询数据库和判断账号密码，
不负责接收HTTP请求，也不负责生成HTTP响应。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, password_needs_rehash, verify_password
from app.models.user import User


async def auth_login(
    session: AsyncSession,
    *,
    username: str,
    password: str,
) -> User | None:
    """根据账号查询用户并核对密码。

    Args:
        session: Router传入的异步数据库Session。Session最初由FastAPI通过
            ``DbSession`` 依赖创建，本函数只使用它，不负责创建或关闭它。
        username: ``LoginRequest`` 解析出来的账号。
        password: ``LoginRequest`` 解析出来的密码。

    Returns:
        账号存在且密码相同时返回 ``User`` ORM对象；账号不存在或密码不同时
        返回 ``None``。Router会根据这个返回值生成对应的HTTP响应。

    Notes:
        参数列表中的 ``*`` 表示它后面的username和password必须使用参数名传入，
        例如 ``auth_login(session, username=..., password=...)``，避免两个字符串
        参数的位置写反。
    """

    # 这里只是在Python中构造查询语句，还没有真正访问数据库。
    # User.username是ORM字段；右侧username是调用本函数时传入的字符串。
    statement = select(User).where(User.username == username)

    # session.scalar()在这里真正执行SELECT。
    # 因为查询目标是User，找到记录时得到User对象，找不到时得到None。
    # 数据库操作是异步I/O，所以必须使用await等待查询结果。
    user = await session.scalar(statement)

    # ``or``具有短路特性：如果user是None，Python不会继续访问user.password，
    # 因此不会发生“None没有password属性”的错误。
    # 本章严格对应原教程，暂时直接比较明文密码，不提前加入密码哈希或JWT。
    if user is None or not verify_password(password, user.password):
        return None
        # 密码验证成功后才可能升级：此时同时拥有明文password和旧哈希user.password。
        # 参数没有变化时（绝大多数登录），这里什么也不做，不产生任何写操作。
        # 密码验证成功后才可能升级：此时同时拥有明文password和旧哈希user.password。
        # 参数没有变化时（绝大多数登录），这里什么也不做，不产生任何写操作。
    if password_needs_rehash(user.password):
        user.password = hash_password(password)
        try:
            await session.commit()
        except Exception:
            # 写操作失败由Service回滚。这是本项目事务规则的第一次实际落地：
            # 依赖函数不自动commit，Service对写操作显式commit/rollback。
            await session.rollback()
            raise
    # 能执行到这里，说明用户存在并且密码相同，把User对象交还给Router。
    return user


async def get_user_by_id(
    session: AsyncSession,
    *,
    user_id: int,
) -> User | None:
    """根据JWT中的用户ID查询当前用户。"""

    statement = select(User).where(User.id == user_id)
    return await session.scalar(statement)
