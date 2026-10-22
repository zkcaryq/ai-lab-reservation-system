"""向开发数据库写入10条可重复生成的实验室测试数据。

运行方式：

    uv run python -m scripts.seed_labs

脚本不会由FastAPI自动调用，也不会自动创建表。运行前必须先完成Labs表迁移。
重复执行时会跳过已经存在的同名实验室，只补充缺少的数据。
"""

import asyncio
from dataclasses import dataclass
from datetime import time

from sqlalchemy import select

from app.core.event_loop import loop_factory
from app.core.settings import get_settings
from app.db.session import engine, session_factory
from app.models.lab_models import Lab


@dataclass(frozen=True)
class LabSeed:
    """描述一条准备写入数据库的实验室测试数据。"""

    name: str
    location: str
    capacity: int
    open_time: time
    close_time: time
    description: str
    status: int = 1


# 使用固定数据而不是随机数据，保证每次运行的结果可预测、方便调试。
LAB_SEEDS: tuple[LabSeed, ...] = (
    LabSeed(
        name="人工智能实验室",
        location="科技楼A区101",
        capacity=40,
        open_time=time(8, 30),
        close_time=time(21, 30),
        description="用于机器学习、深度学习和智能体应用开发。",
    ),
    LabSeed(
        name="计算机视觉实验室",
        location="科技楼A区203",
        capacity=32,
        open_time=time(9, 0),
        close_time=time(20, 30),
        description="配备图像采集设备和GPU工作站，用于视觉算法实验。",
    ),
    LabSeed(
        name="机器人创新实验室",
        location="工程训练中心B区105",
        capacity=28,
        open_time=time(8, 0),
        close_time=time(19, 0),
        description="开展移动机器人、机械臂和智能控制相关实践。",
    ),
    LabSeed(
        name="物联网实验室",
        location="信息楼C区302",
        capacity=36,
        open_time=time(8, 30),
        close_time=time(20, 0),
        description="用于传感器、嵌入式设备和物联网平台开发。",
    ),
    LabSeed(
        name="网络安全实验室",
        location="信息楼C区406",
        capacity=30,
        open_time=time(9, 0),
        close_time=time(18, 30),
        description="提供隔离网络环境，用于攻防演练与安全分析。",
    ),
    LabSeed(
        name="大数据分析实验室",
        location="数据中心D区201",
        capacity=45,
        open_time=time(8, 0),
        close_time=time(22, 0),
        description="用于数据处理、数据仓库和可视化分析实践。",
    ),
    LabSeed(
        name="云计算实验室",
        location="数据中心D区305",
        capacity=38,
        open_time=time(8, 30),
        close_time=time(21, 0),
        description="用于容器、虚拟化和云原生应用部署实验。",
    ),
    LabSeed(
        name="软件工程实验室",
        location="教学楼E区204",
        capacity=50,
        open_time=time(8, 0),
        close_time=time(21, 30),
        description="支持Web开发、软件测试和团队协作课程。",
    ),
    LabSeed(
        name="数字媒体实验室",
        location="艺术楼F区108",
        capacity=26,
        open_time=time(9, 30),
        close_time=time(18, 0),
        description="用于音视频编辑、三维建模和交互媒体制作。",
    ),
    LabSeed(
        name="综合开放实验室",
        location="创新中心G区一层",
        capacity=60,
        open_time=time(8, 0),
        close_time=time(22, 0),
        description="面向学生开放的综合实践空间，目前因设备维护暂时关闭。",
        status=0,
    ),
)


async def seed_labs() -> tuple[int, int]:
    """插入缺少的实验室，并返回“新增数量、跳过数量”。"""

    # 提取全部目标名称，以便用一条SELECT查出已经存在的数据。
    target_names = [seed.name for seed in LAB_SEEDS]

    async with session_factory() as session:
        # 只查询name列，不加载不需要的完整Lab对象。
        existing_statement = select(Lab.name).where(Lab.name.in_(target_names))
        existing_result = await session.scalars(existing_statement)
        existing_names = set(existing_result.all())

        new_labs: list[Lab] = []

        for seed in LAB_SEEDS:
            # 同名实验室已经存在时保持原数据不变，避免重复运行覆盖人工修改。
            if seed.name in existing_names:
                continue

            new_labs.append(
                Lab(
                    name=seed.name,
                    location=seed.location,
                    capacity=seed.capacity,
                    open_time=seed.open_time,
                    close_time=seed.close_time,
                    description=seed.description,
                    # 暂不填写虚假的图片地址，避免前端请求不存在的图片。
                    img=None,
                    status=seed.status,
                )
            )

        # 10条数据都已存在时，不执行空事务提交。
        if not new_labs:
            return 0, len(existing_names)

        # add_all()只把对象加入待写入集合，commit()才真正发送INSERT。
        session.add_all(new_labs)

        try:
            # 整批数据使用同一个事务：全部成功，或者失败后全部回滚。
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        return len(new_labs), len(existing_names)


async def async_main() -> None:
    """执行数据写入，并在独立脚本结束时释放Engine连接池。"""

    try:
        created, skipped = await seed_labs()
        print(f"完成：新增{created}个实验室，跳过已存在实验室{skipped}个。")
    finally:
        # 独立脚本不经过FastAPI lifespan，因此需要主动释放连接池。
        await engine.dispose()


def main() -> None:
    """同步命令入口：检查环境、展示目标数据库并请求确认。"""

    settings = get_settings()

    # 测试数据脚本只允许在非生产环境执行，防止误写正式数据库。
    if settings.APP_ENV == "production":
        raise RuntimeError("禁止在production环境生成测试实验室")

    # 只显示必要的数据库位置，不输出用户名、密码或完整连接URL。
    print(
        "即将写入："
        f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} "
        f"(APP_ENV={settings.APP_ENV})"
    )
    print(f"计划确保存在{len(LAB_SEEDS)}个预设实验室；同名数据会被跳过。")

    answer = input("确认继续？[y/N]：")
    if answer.strip().lower() not in {"y", "yes"}:
        print("已取消，没有修改数据库。")
        return

    # 使用项目已有事件循环工厂，兼容Windows上的异步psycopg。
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(async_main())


if __name__ == "__main__":
    main()
