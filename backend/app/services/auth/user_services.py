"""用户查询和当前用户资料修改相关的数据库业务逻辑。

调用方向：
- ``api/dependencies.py``中的当前用户依赖调用``get_user_by_id()``；
- ``api/routes/user_router.py``中的资料修改Router调用``update_user_info()``。
- 修改密码Router调用``update_password()``；
- 管理员用户列表Router调用``get_user_page_list()``。

Service负责数据库查询、ORM属性修改和事务，不接收Request，不使用Depends，
也不构造ApiResponse或JSONResponse。
"""

# status提供可读的HTTP状态码常量。
from fastapi import status

# func、or_和select用于构造SQLAlchemy 2.x查询语句。
from sqlalchemy import func, or_, select

# IntegrityError用于识别数据库唯一约束等完整性错误。
from sqlalchemy.exc import IntegrityError

# AsyncSession是当前项目执行异步SQL和事务操作的数据库会话类型。
from sqlalchemy.ext.asyncio import AsyncSession

# BusinessException表示可安全返回客户端的预期业务失败。
from app.core.errors import BusinessException

# 安全函数负责生成Argon2id哈希并验证用户提交的旧密码。
from app.core.security import hash_password, verify_password

# User是users表对应的SQLAlchemy ORM模型。
from app.models.user_models import User

# 请求Schema限制不同接口能够写入的字段，防止普通资料接口修改角色等管理员字段。
from app.schemas.user_schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    PasswordUpdateRequest,
    UserUpdateRequest,
)


async def update_user_info(
    session: AsyncSession,
    *,
    user: User,
    data: UserUpdateRequest,
) -> User:
    """修改当前用户提交的非空资料字段，并返回刷新后的User。"""

    # 把Pydantic请求对象转换成普通字典，并排除值为None的字段。
    # 例如只提交name时，结果可能是{"name": "新名称"}，不会清空其他资料。
    update_data = data.model_dump(exclude_none=True)

    # items()依次产生“字段名、字段值”，例如("name", "新名称")。
    for field, value in update_data.items():
        # setattr(user, "name", "新名称")等价于user.name = "新名称"。
        # 字段名只可能来自UserUpdateRequest，因此不会修改角色、状态或密码。
        setattr(user, field, value)

    # 数据库提交可能失败；失败后必须回滚并保留原异常。
    try:
        # AsyncSession.commit()是异步数据库I/O，必须使用await。
        await session.commit()
    except Exception:
        # 让Session退出失败事务状态，然后把异常交给全局500中间件记录。
        await session.rollback()
        raise

    # 重新读取数据库中的最终值；原教程也在commit后执行refresh。
    await session.refresh(user)

    # Service返回ORM对象，响应Schema转换和统一响应由Router负责。
    return user


async def update_password(
    session: AsyncSession,
    *,
    user: User,
    data: PasswordUpdateRequest,
) -> None:
    """验证旧密码并保存新密码哈希。"""

    # 密码正确性和“新旧密码不能相同”都是业务规则，统一由Service判断。
    if not verify_password(data.old_password, user.password):
        raise BusinessException(
            message="原密码错误！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if data.old_password == data.new_password:
        raise BusinessException(
            message="新密码和原密码相同！Ovo!",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user.password = hash_password(data.new_password)

    try:
        # user来自当前Session，修改属性后SQLAlchemy会自动追踪，不需要再次add()。
        await session.commit()
    except Exception:
        # commit失败后必须回滚，使Session退出失败事务状态，再保留原异常向上抛出。
        await session.rollback()
        raise


async def get_user_page_list(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    keywords: str | None = None,
) -> tuple[list[User], int]:
    """按账号或名称模糊搜索用户，并返回当前页User列表与总记录数。

    Args:
        session: Router通过DbSession传入的请求级异步数据库会话。
        page: 从1开始的页码，Router中的Query已经保证它大于等于1。
        page_size: 每页条数，Router限制在1～100之间。
        keywords: 可选搜索词；为空时查询全部用户。

    Returns:
        二元组 ``(users, total)``：users是当前页User对象，total是满足相同
        搜索条件的总记录数。Router会把User转换为UserResponse。
    """

    # conditions保存需要同时放进“总数SQL”和“列表SQL”的WHERE条件。
    # 没有关键词时它保持空列表，where(*conditions)不会添加过滤条件。
    conditions = []

    # 去掉搜索词两端空格；None、空字符串和只包含空格都按“查询全部”处理。
    normalized_keywords = keywords.strip() if keywords else ""

    if normalized_keywords:
        # SQL中的%表示任意长度字符，因此admin可匹配admin01或super_admin。
        # SQLAlchemy会把pattern作为绑定参数传给数据库，不会直接拼成可执行SQL。
        pattern = f"%{normalized_keywords}%"

        # PostgreSQL的ILIKE是不区分英文大小写的模糊匹配。
        # or_表示username或name任意一个字段匹配即可。
        conditions.append(
            or_(
                User.username.ilike(pattern),
                User.name.ilike(pattern),
            )
        )

    # 分页器需要“满足条件的全部记录数”，所以第一条SQL只执行count(*)。
    # 这里与列表SQL复用同一个conditions，避免搜索后的list和total互相矛盾。
    count_statement = select(func.count()).select_from(User).where(*conditions)

    # scalar()适合读取count(*)产生的单个整数；数据库I/O必须使用await。
    total = await session.scalar(count_statement)

    # 第二条SQL查询当前页User对象。这里尚未访问数据库，只是在构造SQL。
    list_statement = (
        select(User)
        .where(*conditions)
        # 按主键倒序，让后创建、ID更大的用户优先显示。
        .order_by(User.id.desc())
        # 第1页跳过0条；第2页跳过page_size条，以此类推。
        .offset((page - 1) * page_size)
        # 限制数据库最多返回page_size条，防止一次加载整张用户表。
        .limit(page_size)
    )

    # scalars()执行SELECT并只保留每行中的User实体，而不是Row包装对象。
    result = await session.scalars(list_statement)

    # all()取出当前页全部User；显式转成list以匹配返回类型list[User]。
    users = list(result.all())

    # count(*)正常会返回整数；“or 0”作为防御性兜底，保证total始终是int。
    # Service不构造ApiResponse，HTTP响应和Schema转换继续由Router负责。
    return users, total or 0


async def get_user_by_id(
    session: AsyncSession,
    *,
    user_id: int,
) -> User | None:
    """根据主键ID查询用户；本函数本身不解析或验证JWT。"""

    # 构造按主键ID查询User的SELECT语句，此时尚未执行SQL。
    statement = select(User).where(User.id == user_id)

    # 执行查询并直接返回User或None，交给get_current_user继续检查账号状态。
    return await session.scalar(statement)


async def create_user(
    session: AsyncSession,
    *,
    data: AdminCreateUserRequest,
) -> User:
    """管理员创建用户；账号冲突时直接抛BusinessException。"""

    # 先构造按username查询的SELECT；此行只是生成SQL表达式，尚未访问数据库。
    statement = select(User).where(User.username == data.username)

    # scalar()执行查询并直接得到User或None。
    existing_user = await session.scalar(statement)

    # 普通重复创建在这里结束，避免继续执行成本较高的Argon2id哈希。
    if existing_user is not None:
        raise BusinessException(
            message="用户已经存在，不能重复创建！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    # 构造只存在于Python内存的新User；此时还没有执行INSERT。
    user = User(
        username=data.username,
        # data.password可能是管理员提交值，也可能是Schema默认初始密码123456。
        # 无论来自哪里，都先生成Argon2id哈希，绝不能把明文写入数据库。
        password=hash_password(data.password),
        # name列不允许NULL；没提供名称时使用username作为显示名称。
        name=data.name or data.username,
        email=data.email,
        phone=data.phone,
        avatar=data.avatar,
        role=data.role,
        status=data.status,
    )

    # add()只把对象加入Session的待写入集合，不发生网络I/O，所以不需要await。
    session.add(user)

    try:
        # commit()会发送INSERT并提交事务，属于异步数据库I/O。
        await session.commit()
    except IntegrityError as exc:
        # PostgreSQL拒绝事务后，必须先rollback才能继续使用或关闭Session。
        await session.rollback()

        # 23505是PostgreSQL唯一约束冲突。
        # 即使两个并发请求都在预查询时看到“不存在”，数据库唯一约束仍能拦住后提交者。
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise BusinessException(
                message="用户已经存在，不能重复创建！Ovo!",
                status_code=status.HTTP_409_CONFLICT,
            ) from None

        # 其他完整性错误不是“账号重复”，保留原异常交给全局500日志处理。
        raise
    except Exception:
        # 连接中断等未知提交错误同样必须回滚，然后原样向上抛出。
        await session.rollback()
        raise

    # 重新读取数据库生成的id、created_at等服务端字段。
    await session.refresh(user)

    # Service返回User ORM；Router负责转换UserResponse和设置HTTP 201。
    return user


async def update_user(
    session: AsyncSession,
    *,
    user_id: int,
    data: AdminUpdateUserRequest,
) -> User:
    """管理员部分修改指定用户；目标不存在时直接抛404。"""

    # get()专门按主键查询。注意行末不能加逗号，否则user会变成(User或None,)元组。
    user = await session.get(User, user_id)

    if user is None:
        raise BusinessException(
            message="用户不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # PATCH只修改本次提交的非None字段；未提交字段保持数据库原值。
    update_data = data.model_dump(exclude_none=True)

    # 字段名只能来自AdminUpdateUserRequest白名单，不会修改username或password。
    for field, value in update_data.items():
        # setattr(user, "name", "新名称")等价于user.name = "新名称"。
        setattr(user, field, value)

    try:
        # User由当前Session查询得到，属性变化会被SQLAlchemy自动追踪并生成UPDATE。
        await session.commit()
    except Exception:
        # 提交失败先回滚，再保留原异常供全局500中间件记录。
        await session.rollback()
        raise

    # 从数据库重新读取最终值，确保响应包含提交后的状态。
    await session.refresh(user)
    return user


async def delete_user(
    session: AsyncSession,
    *,
    user_id: int,
    current_admin_id: int,
) -> None:
    """管理员删除指定用户，并禁止删除当前登录账号。"""

    if user_id == current_admin_id:
        raise BusinessException(
            message="不能删除当前登录的用户！Ovo!",
            status_code=status.HTTP_409_CONFLICT,
        )

    # 按主键查询目标。行末不能有逗号，否则会得到tuple而不是User。
    user = await session.get(User, user_id)

    if user is None:
        raise BusinessException(
            message="用户不存在！Ovo!",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        # AsyncSession.delete()把对象标记为待删除；commit()真正提交DELETE事务。
        await session.delete(user)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        # 用户已有预约等关联记录时，RESTRICT外键会拒绝删除并返回23503。
        if getattr(exc.orig, "sqlstate", None) == "23503":
            raise BusinessException(
                message="用户存在关联业务记录，不能删除！Ovo!",
                status_code=status.HTTP_409_CONFLICT,
            ) from None

        raise
    except Exception:
        # 连接失败等未知异常必须回滚，并交给全局500系统记录。
        await session.rollback()
        raise
