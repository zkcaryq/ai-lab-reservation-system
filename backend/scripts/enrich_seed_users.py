"""为批量生成的测试用户补充有差异的姓名、手机号和邮箱。

默认只处理 ``student001``～``student100``。生成规则是确定性的：同一个账号每次运行
都会得到相同资料，因此脚本可以重复执行，不会让测试数据不断随机变化。
"""

import argparse
import asyncio

from sqlalchemy import select

from app.core.event_loop import loop_factory
from app.core.settings import get_settings
from app.db.session import engine, session_factory
from app.models.user_models import User
from scripts.seed_users import positive_count

# 10个姓与10个名字组合后正好提供100组不同姓名。
SURNAMES = ("林", "陈", "张", "李", "王", "赵", "周", "吴", "徐", "孙")
GIVEN_NAMES = (
    "子涵",
    "宇轩",
    "雨桐",
    "浩然",
    "欣怡",
    "思远",
    "若曦",
    "嘉宁",
    "明哲",
    "语桐",
)

# 轮换常见手机号号段，让测试页面中的号码具有差异。
# 这些号码仅用于本地开发展示，不能用于真实短信或电话测试。
PHONE_PREFIXES = ("130", "131", "132", "155", "156", "166", "175", "176", "185", "186")

# example.com、example.net和example.org是专门保留给文档与示例使用的域名。
EMAIL_DOMAINS = ("example.com", "example.net", "example.org")


def parse_args() -> argparse.Namespace:
    """读取目标账号数量和前缀，默认匹配上一份脚本生成的100个账号。"""

    parser = argparse.ArgumentParser(description="补全测试用户的姓名、电话和邮箱")
    parser.add_argument(
        "--count",
        type=positive_count,
        default=100,
        help="计划处理的账号数量，默认100，范围1～1000",
    )
    parser.add_argument(
        "--prefix",
        default="test",
        help="账号前缀，默认student；目标账号如student001",
    )
    return parser.parse_args()


def profile_for(index: int, username: str) -> tuple[str, str, str]:
    """根据账号序号生成固定但彼此不同的姓名、手机号和示例邮箱。"""

    # index从1开始；减1后再做整除和取余，可以遍历10×10种姓名组合。
    zero_based_index = index - 1
    surname = SURNAMES[(zero_based_index // len(GIVEN_NAMES)) % len(SURNAMES)]
    given_name = GIVEN_NAMES[zero_based_index % len(GIVEN_NAMES)]
    name = f"{surname}{given_name}"

    # 组合成11位测试手机号：3位号段 + 8位序号。
    phone_prefix = PHONE_PREFIXES[zero_based_index % len(PHONE_PREFIXES)]
    phone = f"{phone_prefix}{index:08d}"

    # 邮箱域名按序号轮换；username保证同一批邮箱地址不会重复。
    email_domain = EMAIL_DOMAINS[zero_based_index % len(EMAIL_DOMAINS)]
    email = f"{username}@{email_domain}"

    return name, phone, email


async def enrich_users(*, count: int, prefix: str) -> tuple[int, list[str]]:
    """更新找到的目标用户，并返回“更新数量、缺失账号列表”。"""

    usernames = [f"{prefix}{index:03d}" for index in range(1, count + 1)]
    if any(len(username) > 50 for username in usernames):
        raise ValueError("账号前缀过长，生成后的username不能超过50个字符")

    # 保存username到序号的映射，查询结果顺序变化也不会生成错误资料。
    index_by_username = {username: index for index, username in enumerate(usernames, start=1)}

    async with session_factory() as session:
        # 只按明确列出的账号查询，避免使用宽泛LIKE误改其他真实用户。
        statement = select(User).where(User.username.in_(usernames))
        result = await session.scalars(statement)
        users = list(result.all())

        found_usernames = {user.username for user in users}
        missing_usernames = [username for username in usernames if username not in found_usernames]

        for user in users:
            index = index_by_username[user.username]
            name, phone, email = profile_for(index, user.username)

            # User对象来自当前Session，修改属性后SQLAlchemy会自动追踪变化。
            # 本脚本故意不修改password、role、status和avatar。
            user.name = name
            user.phone = phone
            user.email = email

        if not users:
            return 0, missing_usernames

        try:
            # commit()会把被追踪的字段变化发送为UPDATE并提交事务。
            await session.commit()
        except Exception:
            # 数据库拒绝任意更新时回滚整批操作，并保留原异常供终端排查。
            await session.rollback()
            raise

        return len(users), missing_usernames


async def async_main(args: argparse.Namespace) -> None:
    """执行资料补全，并在独立脚本结束时释放Engine连接池。"""

    try:
        updated, missing = await enrich_users(count=args.count, prefix=args.prefix)
        print(f"完成：更新{updated}个测试用户，未找到{len(missing)}个目标账号。")

        # 只展示前10个缺失账号，避免数量很大时刷满终端。
        if missing:
            preview = ", ".join(missing[:10])
            suffix = " ..." if len(missing) > 10 else ""
            print(f"缺失账号：{preview}{suffix}")
    finally:
        await engine.dispose()


def main() -> None:
    """同步命令入口：检查环境、展示预览、确认后运行异步更新。"""

    args = parse_args()
    settings = get_settings()

    if settings.APP_ENV == "production":
        raise RuntimeError("禁止在production环境修改测试用户资料")

    first_username = f"{args.prefix}001"
    first_name, first_phone, first_email = profile_for(1, first_username)

    print(
        "即将更新："
        f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} "
        f"(APP_ENV={settings.APP_ENV})"
    )
    print(f"目标账号：{args.prefix}001～{args.prefix}{args.count:03d}；只修改name、phone、email。")
    print(
        f"首条预览：{first_username} -> 姓名={first_name}，电话={first_phone}，邮箱={first_email}"
    )

    answer = input("确认继续？[y/N]：")
    if answer.strip().lower() not in {"y", "yes"}:
        print("已取消，没有修改数据库。")
        return

    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(async_main(args))


if __name__ == "__main__":
    main()
