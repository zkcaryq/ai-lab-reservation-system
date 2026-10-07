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
    # verify_password()会使用Argon2id验证用户输入的明文与数据库哈希是否匹配；
    # 密码错误、数据库仍是旧明文或哈希格式损坏时，它都会安全地返回False。
    if user is None or not verify_password(password, user.password):
        return None

    # 只有密码验证成功后才检查升级：此时同时拥有本次登录的明文和数据库中的旧哈希。
    # 参数没有变化时（绝大多数登录），check_needs_rehash()返回False，不产生数据库写操作。
    if password_needs_rehash(user.password):
        # 使用security.py中当前配置的Argon2id参数重新生成哈希。
        # 已被Session查询出来的user属于持久化ORM对象，修改属性后无需再次session.add(user)。
        user.password = hash_password(password)
        try:
            # 显式提交UPDATE。项目的Session依赖只负责创建和关闭会话，不会自动提交事务。
            await session.commit()
        except Exception:
            # commit失败后必须回滚，让Session退出失败事务状态；随后原样抛出异常，
            # 由现有全局错误中间件记录堆栈、request_id和error_id，不能静默假装升级成功。
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
