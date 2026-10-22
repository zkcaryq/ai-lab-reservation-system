"""认证业务逻辑：登录验证和用户注册。

调用方向：
- Router的``login()``调用``auth_login()``；
- Router的``register()``调用``auth_register()``；

Service负责数据库查询、密码处理、业务校验和事务，不接收Request、Depends，
也不构造ApiResponse或JSONResponse。预期内业务失败直接抛BusinessException。
"""

# status提供可读的HTTP状态码常量。
from fastapi import status

# select用于构造SQLAlchemy 2.x的SELECT语句。
from sqlalchemy import select

# IntegrityError表示唯一约束、外键约束、非空约束等数据库完整性错误。
from sqlalchemy.exc import IntegrityError

# AsyncSession是当前项目执行异步SQL和事务操作的数据库会话类型。
from sqlalchemy.ext.asyncio import AsyncSession

# BusinessException由全局处理器转换成统一错误响应。
from app.core.errors import BusinessException

# 三个安全函数分别用于生成哈希、判断旧哈希参数和验证登录密码。
from app.core.security import hash_password, password_needs_rehash, verify_password

# User是users表对应的SQLAlchemy ORM模型。
from app.models.user_models import User


async def auth_login(
    session: AsyncSession,
    *,
    username: str,
    password: str,
) -> User:
    """根据账号查询用户并核对密码。

    Args:
        session: Router传入的异步数据库Session。Session最初由FastAPI通过
            ``DbSession`` 依赖创建，本函数只使用它，不负责创建或关闭它。
        username: ``LoginRequest`` 解析出来的账号。
        password: ``LoginRequest`` 解析出来的密码。

    Returns:
        账号存在、密码正确且账号正常时返回 ``User`` ORM对象；预期业务失败
        直接抛出 ``BusinessException``。

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
        raise BusinessException(
            message="账号或密码错误!Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 账号存在且密码正确，但已经被管理员禁用时不签发JWT。
    if user.status != 1:
        raise BusinessException(
            message="账号已被禁用!Ovo!",
            status_code=status.HTTP_403_FORBIDDEN,
        )

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


async def auth_register(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    name: str | None,
) -> User:
    """创建普通学生账号；账号已存在时直接抛BusinessException。

    Args:
        session: Router传入的请求级AsyncSession，本函数不负责创建或关闭。
        username: RegisterRequest解析得到的账号。
        password: 用户提交的明文密码，只用于本次Argon2id哈希。
        name: 可选显示名称；为None或空字符串时回退到username。

    Returns:
        创建成功返回已刷新的User对象；账号已存在或并发插入发生用户名
        唯一冲突时抛出HTTP 409业务异常。
    """

    # 先构造“按username查询User”的SELECT语句，此行还没有访问数据库。
    statement = select(User).where(User.username == username)

    # scalar()真正执行查询；第一列是User实体，所以返回User对象或None。
    existing_user = await session.scalar(statement)

    # 普通重复注册会在这里被发现，避免继续计算Argon2哈希和执行INSERT。
    if existing_user is not None:
        raise BusinessException(
            message="账号已经存在!Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    # 构造新的User ORM对象；此时对象只存在于Python内存，还没有写入数据库。
    user = User(
        # 账号使用请求值；数据库中的唯一约束负责最终防止重复。
        username=username,
        # 数据库只保存Argon2id哈希，绝不能直接保存请求中的明文password。
        password=hash_password(password),
        # 没有提供名称或传入空字符串时，使用账号作为默认显示名称。
        name=name or username,
        # 普通注册接口只能创建学生；不能接受客户端自行指定admin。
        role="student",
        # 新注册账号默认正常；以后若增加审核流程，再由对应章节修改规则。
        status=1,
    )

    # add()只把对象加入Session的待写入集合，没有网络I/O，因此不需要await。
    session.add(user)

    # 数据库写操作可能失败，必须用try保护事务并在失败后rollback。
    try:
        # commit()会先把待写入对象发送为INSERT，再提交当前事务。
        await session.commit()

    # ``as exc``把本次完整性异常保存到变量exc，后面才能读取底层SQLSTATE。
    except IntegrityError as exc:
        # PostgreSQL拒绝事务后，Session会处于失败状态；判断前先执行回滚。
        await session.rollback()

        # psycopg把PostgreSQL错误码放在原始异常的sqlstate属性中。
        # 23505表示唯一约束冲突，可覆盖“两个请求同时查询到不存在”的并发情况。
        if getattr(exc.orig, "sqlstate", None) == "23505":
            # 当前User业务唯一字段是username，并发冲突与预查询冲突使用同一业务响应。
            raise BusinessException(
                message="账号已经存在!Ovo!",
                status_code=status.HTTP_409_CONFLICT,
            ) from None

        # 其他完整性错误不能伪装成账号重复，继续抛给全局500处理并记录日志。
        raise

    # 捕获其他提交异常的目的只是确保回滚，不是把错误静默吞掉。
    except Exception:
        # 清理失败事务，使Session能够被依赖函数正常关闭。
        await session.rollback()

        # 原样重新抛出，UnexpectedErrorMiddleware会记录traceback和error_id。
        raise

    # commit成功后重新读取数据库生成的id、created_at等服务端字段。
    await session.refresh(user)

    # 能执行到这里说明注册成功；冲突已经在上方直接抛出BusinessException。
    # 返回User便于以后需要“注册后展示用户信息”等场景复用。
    return user
