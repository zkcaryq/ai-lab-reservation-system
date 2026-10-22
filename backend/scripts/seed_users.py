"""向开发数据库批量写入可重复生成的测试学生账号。

运行方式：

    uv run python -m scripts.seed_users

脚本不会在应用启动时自动执行，也不会在生产环境运行。重复执行时，已经存在的
``student001``等账号会被跳过，只补充缺少的账号。
"""

import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select

from app.core.event_loop import loop_factory
from app.core.security import hash_password
from app.core.settings import get_settings
from app.db.session import engine, session_factory
from app.models.user_models import User


def positive_count(value: str) -> int:
    """把命令行中的数量转换成1～1000之间的整数。"""

    count = int(value)
    if not 1 <= count <= 1000:
        raise argparse.ArgumentTypeError("count必须在1到1000之间")
    return count


def parse_args() -> argparse.Namespace:
    """读取命令行参数；默认生成100个student前缀的账号。"""

    parser = argparse.ArgumentParser(description="为开发数据库生成测试用户")
    parser.add_argument(
        "--count",
        type=positive_count,
        default=100,
        help="计划生成的账号数量，默认100，范围1～1000",
    )
    parser.add_argument(
        "--prefix",
        default="test",
        help="账号前缀，默认student；结果如student001",
    )
    return parser.parse_args()


def read_password() -> str:
    """从终端隐藏读取统一初始密码，并要求输入两次防止输错。"""

    password = getpass("请输入测试用户的统一初始密码：")
    if not password:
        raise ValueError("初始密码不能为空")

    confirmation = getpass("请再次输入初始密码：")
    if password != confirmation:
        raise ValueError("两次输入的密码不一致")

    return password


async def seed_users(*, count: int, prefix: str, password: str) -> tuple[int, int]:
    """插入缺少的测试用户，并返回“新增数、跳过数”。"""

    # 三位序号足够覆盖默认100条，例如student001～student100。
    usernames = [f"{prefix}{index:03d}" for index in range(1, count + 1)]

    # User.username最多50字符，脚本在访问数据库前直接拒绝过长结果。
    if any(len(username) > 50 for username in usernames):
        raise ValueError("账号前缀过长，生成后的username不能超过50个字符")

    async with session_factory() as session:
        # 一次查询找出已经存在的目标账号，避免逐个用户访问数据库。
        existing_statement = select(User.username).where(User.username.in_(usernames))
        existing_result = await session.scalars(existing_statement)
        existing_usernames = set(existing_result.all())

        new_users: list[User] = []

        for index, username in enumerate(usernames, start=1):
            # 重复运行脚本时不修改已有账号，也不会重置已有用户密码。
            if username in existing_usernames:
                continue

            new_users.append(
                User(
                    username=username,
                    # 每次调用都会生成独立随机salt；即使明文相同，哈希也不相同。
                    password=hash_password(password),
                    name=f"测试学生{index:03d}",
                    role="student",
                    email=f"{username}@example.test",
                    phone=None,
                    avatar=None,
                    status=1,
                )
            )

        # 全部目标账号都已存在时，不产生空提交。
        if not new_users:
            return 0, len(existing_usernames)

        # add_all()只把ORM对象加入待写入集合，真正的INSERT发生在commit()。
        session.add_all(new_users)

        try:
            # 100条用户作为同一个事务提交：全部成功或全部回滚。
            await session.commit()
        except Exception:
            # 提交失败后必须回滚，并保留原异常供终端显示具体原因。
            await session.rollback()
            raise

        return len(new_users), len(existing_usernames)


async def async_main(args: argparse.Namespace, password: str) -> None:
    """执行写入，并在结束时释放数据库连接池。"""

    try:
        created, skipped = await seed_users(
            count=args.count,
            prefix=args.prefix,
            password=password,
        )
        print(f"完成：新增{created}个，跳过已存在账号{skipped}个。")
    finally:
        # 脚本是独立进程，不经过FastAPI lifespan，因此需要自己释放Engine连接池。
        await engine.dispose()


def main() -> None:
    """同步命令行入口；Windows使用项目已有Selector事件循环。"""

    args = parse_args()
    settings = get_settings()

    # 在读取密码和连接数据库之前拦截生产环境，避免误操作。
    if settings.APP_ENV == "production":
        raise RuntimeError("禁止在production环境运行测试用户生成脚本")

    # 只显示主机、端口和数据库名，不打印用户名、密码或完整数据库URL。
    print(
        "即将写入："
        f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} "
        f"(APP_ENV={settings.APP_ENV})"
    )
    answer = input(f"计划确保存在{args.count}个测试账号，确认继续？[y/N]：")
    if answer.strip().lower() not in {"y", "yes"}:
        print("已取消，没有修改数据库。")
        return

    # 用户确认目标数据库后再隐藏读取密码，密码不会出现在PowerShell历史中。
    password = read_password()

    # asyncio.Runner允许显式复用项目事件循环工厂，兼容Windows异步psycopg。
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(async_main(args, password))


if __name__ == "__main__":
    main()
