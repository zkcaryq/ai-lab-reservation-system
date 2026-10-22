"""为预设实验室写入可重复执行的设备测试数据。

运行方式：

    uv run python -m scripts.seed_equipments

脚本按实验室名称查询真实主键，不硬编码lab_id。每间预设实验室准备4种设备，
重复运行时根据``(lab_id, name)``跳过已有设备，不覆盖人工修改的数据。
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.core.event_loop import loop_factory
from app.core.settings import get_settings
from app.db.session import engine, session_factory
from app.models.equipment_models import Equipment
from app.models.lab_models import Lab


@dataclass(frozen=True)
class EquipmentSeed:
    """描述一条准备写入数据库的设备测试数据。"""

    lab_name: str
    name: str
    description: str
    spec: str
    quantity: int
    status: int = 1


# 数据与seed_labs.py中的10个实验室名称对应；每间实验室放4种设备。
EQUIPMENT_SEEDS: tuple[EquipmentSeed, ...] = (
    EquipmentSeed(
        "人工智能实验室", "GPU训练服务器", "用于模型训练与微调", "双RTX4090 / 128G内存", 2
    ),
    EquipmentSeed("人工智能实验室", "AI开发工作站", "用于算法开发和实验", "i9 / 64G / RTX4080", 12),
    EquipmentSeed(
        "人工智能实验室", "推理服务器", "用于模型部署和性能测试", "A10 24G / 128G内存", 2
    ),
    EquipmentSeed("人工智能实验室", "高速存储阵列", "保存训练数据和模型文件", "80TB RAID6", 1),
    EquipmentSeed("计算机视觉实验室", "深度相机", "采集RGB与深度图像", "RealSense D435i", 8),
    EquipmentSeed("计算机视觉实验室", "工业相机", "用于目标检测数据采集", "500万像素全局快门", 6),
    EquipmentSeed(
        "计算机视觉实验室", "标注工作站", "用于图片和视频数据标注", "i7 / 32G / 27英寸显示器", 10
    ),
    EquipmentSeed("计算机视觉实验室", "补光灯组", "提供稳定可调的拍摄光源", "双色温LED 100W", 4),
    EquipmentSeed("机器人创新实验室", "六轴机械臂", "用于运动控制与视觉抓取", "负载5kg", 2),
    EquipmentSeed(
        "机器人创新实验室", "移动机器人底盘", "用于导航和避障实验", "差速驱动 / 载重30kg", 4
    ),
    EquipmentSeed("机器人创新实验室", "激光雷达", "用于SLAM建图", "Livox Mid-360", 5),
    EquipmentSeed("机器人创新实验室", "边缘计算盒", "运行机器人感知算法", "Jetson Orin 32G", 6),
    EquipmentSeed(
        "物联网实验室", "传感器开发套件", "采集温湿度、光照和气压", "ESP32多传感器套件", 20
    ),
    EquipmentSeed("物联网实验室", "LoRa网关", "用于低功耗广域网实验", "8通道LoRaWAN", 3),
    EquipmentSeed("物联网实验室", "示波器", "观察嵌入式电路波形", "100MHz双通道", 8),
    EquipmentSeed("物联网实验室", "可编程电源", "为开发板和传感器供电", "30V 5A", 10),
    EquipmentSeed(
        "网络安全实验室", "攻防靶机服务器", "运行隔离的漏洞练习环境", "32核 / 256G内存", 3
    ),
    EquipmentSeed("网络安全实验室", "硬件防火墙", "用于访问控制与策略实验", "千兆多端口", 4),
    EquipmentSeed("网络安全实验室", "网络流量分析仪", "采集和分析镜像流量", "10GbE双口", 2),
    EquipmentSeed(
        "网络安全实验室", "安全审计工作站", "用于日志分析与应急响应", "i7 / 32G / 2T SSD", 12
    ),
    EquipmentSeed("大数据分析实验室", "数据计算节点", "运行分布式计算任务", "32核 / 128G内存", 8),
    EquipmentSeed("大数据分析实验室", "数据存储节点", "保存教学与实验数据集", "100TB可用容量", 4),
    EquipmentSeed(
        "大数据分析实验室", "分析工作站", "用于数据清洗和可视化", "i7 / 64G / 2T SSD", 20
    ),
    EquipmentSeed("大数据分析实验室", "万兆交换机", "连接计算和存储节点", "24口10GbE", 2),
    EquipmentSeed(
        "云计算实验室", "虚拟化服务器", "运行虚拟机和私有云节点", "双路CPU / 512G内存", 6
    ),
    EquipmentSeed("云计算实验室", "容器集群节点", "运行Kubernetes教学集群", "32核 / 128G内存", 10),
    EquipmentSeed("云计算实验室", "共享存储设备", "为集群提供持久化存储", "60TB NAS", 2),
    EquipmentSeed("云计算实验室", "管理控制台", "管理云平台和监控系统", "i5 / 16G / 双显示器", 4),
    EquipmentSeed("软件工程实验室", "开发主机", "用于项目开发和课程实践", "i7 / 32G / 1T SSD", 40),
    EquipmentSeed("软件工程实验室", "代码服务器", "提供Git与持续集成服务", "16核 / 64G内存", 2),
    EquipmentSeed("软件工程实验室", "投影仪", "用于课程讲解和项目答辩", "1080P激光投影", 2),
    EquipmentSeed("软件工程实验室", "测试移动终端", "用于移动端兼容性测试", "Android测试机", 12),
    EquipmentSeed(
        "数字媒体实验室", "图形工作站", "用于三维建模和视频渲染", "i9 / 64G / RTX4080", 16
    ),
    EquipmentSeed("数字媒体实验室", "数位屏", "用于数字绘画和界面设计", "22英寸压感屏", 12),
    EquipmentSeed("数字媒体实验室", "专业摄像机", "用于高清视频拍摄", "4K摄像机", 4),
    EquipmentSeed("数字媒体实验室", "录音套装", "用于配音和音频采集", "电容麦克风 / 声卡", 6),
    EquipmentSeed(
        "综合开放实验室", "通用实验工作站", "用于跨专业实践项目", "i7 / 32G / 1T SSD", 30
    ),
    EquipmentSeed(
        "综合开放实验室", "电子工具套装", "用于电路制作和设备检修", "焊台 / 万用表 / 工具组", 15
    ),
    EquipmentSeed("综合开放实验室", "便携投影仪", "用于小组展示和讨论", "1080P", 3),
    EquipmentSeed(
        "综合开放实验室", "3D打印机", "用于原型零件打印，目前维护中", "FDM / 300mm成型尺寸", 2, 0
    ),
)


async def seed_equipments() -> tuple[int, int, list[str]]:
    """插入缺少的设备，并返回新增数、跳过数和缺失实验室名称。"""

    target_lab_names = sorted({seed.lab_name for seed in EQUIPMENT_SEEDS})

    async with session_factory() as session:
        # 一次查询取得实验室名称与真实ID，避免依赖某次数据库中的固定主键值。
        lab_statement = select(Lab).where(Lab.name.in_(target_lab_names))
        lab_result = await session.scalars(lab_statement)
        labs = list(lab_result.all())
        lab_by_name = {lab.name: lab for lab in labs}

        missing_lab_names = [
            lab_name for lab_name in target_lab_names if lab_name not in lab_by_name
        ]

        # 只查询已经找到的实验室中的设备；没有实验室时跳过这条SQL。
        lab_ids = [lab.id for lab in labs]
        existing_pairs: set[tuple[int, str]] = set()

        if lab_ids:
            existing_statement = select(Equipment.lab_id, Equipment.name).where(
                Equipment.lab_id.in_(lab_ids)
            )
            existing_result = await session.execute(existing_statement)
            existing_pairs = set(existing_result.tuples().all())

        new_equipments: list[Equipment] = []
        skipped = 0

        for seed in EQUIPMENT_SEEDS:
            lab = lab_by_name.get(seed.lab_name)

            # 对应实验室不存在时不构造无效外键数据，最后统一显示缺失名称。
            if lab is None:
                continue

            pair = (lab.id, seed.name)
            if pair in existing_pairs:
                skipped += 1
                continue

            new_equipments.append(
                Equipment(
                    lab_id=lab.id,
                    name=seed.name,
                    description=seed.description,
                    # 暂不填写虚假图片地址，避免前端显示破图。
                    img=None,
                    spec=seed.spec,
                    quantity=seed.quantity,
                    status=seed.status,
                )
            )

        if not new_equipments:
            return 0, skipped, missing_lab_names

        session.add_all(new_equipments)

        try:
            # 所有新增设备作为一个事务提交，任意一条失败就整批回滚。
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        return len(new_equipments), skipped, missing_lab_names


async def async_main() -> None:
    """执行数据写入，并在脚本结束时释放Engine连接池。"""

    try:
        created, skipped, missing = await seed_equipments()
        print(f"完成：新增{created}条设备，跳过已存在设备{skipped}条。")

        if missing:
            print("未找到实验室，因此未写入其设备：" + "、".join(missing))
    finally:
        # 独立脚本不会进入FastAPI lifespan，需要自己释放连接池。
        await engine.dispose()


def main() -> None:
    """同步命令入口：检查环境、显示目标数据库并请求确认。"""

    settings = get_settings()

    if settings.APP_ENV == "production":
        raise RuntimeError("禁止在production环境生成测试设备")

    print(
        "即将写入："
        f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} "
        f"(APP_ENV={settings.APP_ENV})"
    )
    print(
        f"预设{len(EQUIPMENT_SEEDS)}条设备，分配给"
        f"{len({seed.lab_name for seed in EQUIPMENT_SEEDS})}间实验室。"
    )
    print("同一实验室中的同名设备会被跳过，已有数据不会被覆盖。")

    answer = input("确认继续？[y/N]：")
    if answer.strip().lower() not in {"y", "yes"}:
        print("已取消，没有修改数据库。")
        return

    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(async_main())


if __name__ == "__main__":
    main()
