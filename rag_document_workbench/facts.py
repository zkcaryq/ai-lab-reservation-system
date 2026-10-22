# -*- coding: utf-8 -*-
"""AI智能实验室预约系统——文档事实基线（唯一数据源）。

数据来源与优先级：
1. 开发数据库只读快照（2026-10-20，PostgreSQL ai_lab_db.app）
2. 后端业务代码（lab_models / equipment_models / reservation_models / 各services）
3. 本提示词数据快照
4. seed脚本
事实冲突已在 db_snapshot 报告中记录；本模块一律采用数据库当前值。
"""

# ---------------- 实验室（与数据库 labs 表一致） ----------------
LABS = [
    dict(id=1, name="人工智能实验室", location="科技楼A区101", capacity=40,
         open_time="08:30", close_time="21:30", status=1,
         description="用于机器学习、深度学习和智能体应用开发。",
         building="科技楼", room="A区101",
         courses="机器学习、深度学习、自然语言处理、智能体（Agent）应用开发、大模型微调与推理部署等课程的配套实验",
         photo_file="lab-01-ai.jpg", photo_kind="ai",
         photo_credit="本图由AI生成，仅作环境示意配图"),
    dict(id=2, name="计算机视觉实验室", location="科技楼A区203", capacity=32,
         open_time="09:00", close_time="20:30", status=1,
         description="配备图像采集设备和GPU工作站，用于视觉算法实验。",
         building="科技楼", room="A区203",
         courses="数字图像处理、计算机视觉、目标检测与跟踪、三维重建等课程的配套实验",
         photo_file="lab-02-cv.jpg", photo_kind="ai",
         photo_credit="本图由AI生成，仅作环境示意配图"),
    dict(id=3, name="机器人创新实验室", location="工程训练中心B区105", capacity=39,
         open_time="08:00", close_time="19:00", status=1,
         description="开展移动机器人、机械臂和智能控制相关实践。",
         building="工程训练中心", room="B区105",
         courses="机器人学、运动控制、SLAM与自主导航、机械臂视觉抓取等实践课程",
         photo_file="lab-03-robotics.jpg", photo_kind="real",
         photo_credit="图片来源：Wikimedia Commons《Controlling robotic arm ESA15746126.jpeg》，作者 ESA–G. Porter，CC BY-SA IGO 3.0 许可"),
    dict(id=4, name="物联网实验室", location="信息楼C区302", capacity=36,
         open_time="08:30", close_time="20:00", status=1,
         description="用于传感器、嵌入式设备和物联网平台开发。",
         building="信息楼", room="C区302",
         courses="传感器原理、嵌入式系统、无线传感网、LoRa与NB-IoT应用开发等课程实验",
         photo_file="lab-04-iot.jpg", photo_kind="real",
         photo_credit="图片来源：Wikimedia Commons《Electronics workbench.jpg》，作者 James Bastow，CC BY-SA 2.0 许可"),
    dict(id=5, name="网络安全实验室", location="信息楼C区406", capacity=30,
         open_time="09:00", close_time="18:30", status=1,
         description="提供隔离网络环境，用于攻防演练与安全分析。",
         building="信息楼", room="C区406",
         courses="网络攻防、渗透测试、防火墙策略、流量分析与安全审计等课程实验",
         photo_file="lab-05-security.jpg", photo_kind="real",
         photo_credit="图片来源：Wikimedia Commons《Ccna security lab.JPG》，作者 Axel Dux，CC BY-SA 3.0 许可"),
    dict(id=6, name="大数据分析实验室", location="数据中心D区201", capacity=45,
         open_time="08:00", close_time="22:00", status=1,
         description="用于数据处理、数据仓库和可视化分析实践。",
         building="数据中心", room="D区201",
         courses="Hadoop/Spark大数据处理、数据仓库、数据可视化和商业分析等课程实验",
         photo_file="lab-06-bigdata.jpg", photo_kind="real",
         photo_credit="图片来源：Wikimedia Commons《A NASA computer server farm -a.jpg》，NASA，公有领域"),
    dict(id=7, name="云计算实验室", location="数据中心D区305", capacity=38,
         open_time="08:30", close_time="21:00", status=1,
         description="用于容器、虚拟化和云原生应用部署实验。",
         building="数据中心", room="D区305",
         courses="虚拟化技术、Docker/Kubernetes容器编排、私有云平台和云原生应用部署实验",
         photo_file="lab-07-cloud.jpg", photo_kind="real",
         photo_credit="图片来源：Wikimedia Commons《Datacenter Server Racks (22370909788).jpg》，作者 Carl Lender，CC BY 2.0 许可"),
    dict(id=11, name="软件工程实验室", location="教学楼E区204", capacity=50,
         open_time="08:00", close_time="21:30", status=1,
         description="支持Web开发、软件测试和团队协作课程。",
         building="教学楼", room="E区204",
         courses="Web开发、软件测试、软件工程导论、团队项目实践和毕业设计等课程",
         photo_file="lab-11-software.jpg", photo_kind="real",
         photo_credit="图片来源：Wikimedia Commons《Students in a computer lab.jpg》，作者 University of Salford Press Office，CC BY 2.0 许可"),
    dict(id=12, name="数字媒体实验室", location="艺术楼F区108", capacity=26,
         open_time="09:30", close_time="18:00", status=1,
         description="用于音视频编辑、三维建模和交互媒体制作。",
         building="艺术楼", room="F区108",
         courses="数字音视频编辑、三维建模与动画、交互媒体设计和影视包装等课程实践",
         photo_file="lab-12-media.jpg", photo_kind="ai",
         photo_credit="本图由AI生成，仅作环境示意配图"),
    dict(id=13, name="综合开放实验室", location="创新中心G区一层", capacity=60,
         open_time="08:00", close_time="22:00", status=0,
         description="面向学生开放的综合实践空间，目前因设备维护暂时关闭。",
         building="创新中心", room="G区一层",
         courses="面向全体学生的跨专业综合实践、电子制作、原型打印与小组项目",
         photo_file="lab-13-open.jpg", photo_kind="real",
         photo_credit="图片来源：Wikimedia Commons《Academic City University Makelab 3D printer Room.jpg》，作者 Afrank4436，CC BY-SA 4.0 许可"),
]

# ---------------- 设备（与数据库 equipments 表一致） ----------------
# status: 1=正常, 0=维修中
EQUIPMENTS = [
    # 人工智能实验室 id=1
    dict(id=1, lab_id=1, name="GPU训练服务器", spec="双RTX4090 / 128G内存", quantity=2, status=1,
         desc="用于模型训练与微调"),
    dict(id=2, lab_id=1, name="AI开发工作站", spec="i9 / 64G / RTX4080", quantity=12, status=1,
         desc="用于算法开发和实验"),
    dict(id=3, lab_id=1, name="推理服务器", spec="A10 24G / 128G内存", quantity=2, status=1,
         desc="用于模型部署和性能测试"),
    dict(id=4, lab_id=1, name="高速存储阵列", spec="80TB RAID6", quantity=1, status=1,
         desc="保存训练数据和模型文件"),
    # 计算机视觉实验室 id=2
    dict(id=5, lab_id=2, name="深度相机", spec="RealSense D435i", quantity=8, status=1,
         desc="采集RGB与深度图像"),
    dict(id=6, lab_id=2, name="工业相机", spec="500万像素全局快门", quantity=6, status=1,
         desc="用于目标检测数据采集"),
    dict(id=7, lab_id=2, name="标注工作站", spec="i7 / 32G / 27英寸显示器", quantity=10, status=1,
         desc="用于图片和视频数据标注"),
    dict(id=8, lab_id=2, name="补光灯组", spec="双色温LED 100W", quantity=4, status=1,
         desc="提供稳定可调的拍摄光源"),
    # 机器人创新实验室 id=3
    dict(id=9, lab_id=3, name="六轴机械臂", spec="负载5kg", quantity=2, status=1,
         desc="用于运动控制与视觉抓取"),
    dict(id=10, lab_id=3, name="移动机器人底盘", spec="差速驱动 / 载重30kg", quantity=4, status=1,
         desc="用于导航和避障实验"),
    dict(id=11, lab_id=3, name="激光雷达", spec="Livox Mid-360", quantity=5, status=1,
         desc="用于SLAM建图"),
    dict(id=12, lab_id=3, name="边缘计算盒", spec="Jetson Orin 32G", quantity=6, status=1,
         desc="运行机器人感知算法"),
    # 物联网实验室 id=4
    dict(id=13, lab_id=4, name="传感器开发套件", spec="ESP32多传感器套件", quantity=20, status=1,
         desc="采集温湿度、光照和气压"),
    dict(id=14, lab_id=4, name="LoRa网关", spec="8通道LoRaWAN", quantity=3, status=1,
         desc="用于低功耗广域网实验"),
    dict(id=15, lab_id=4, name="示波器", spec="100MHz双通道", quantity=8, status=1,
         desc="观察嵌入式电路波形"),
    dict(id=16, lab_id=4, name="可编程电源", spec="30V 5A", quantity=10, status=1,
         desc="为开发板和传感器供电"),
    # 网络安全实验室 id=5
    dict(id=17, lab_id=5, name="攻防靶机服务器", spec="32核 / 256G内存", quantity=3, status=1,
         desc="运行隔离的漏洞练习环境"),
    dict(id=18, lab_id=5, name="硬件防火墙", spec="千兆多端口", quantity=4, status=1,
         desc="用于访问控制与策略实验"),
    dict(id=19, lab_id=5, name="网络流量分析仪", spec="10GbE双口", quantity=2, status=1,
         desc="采集和分析镜像流量"),
    dict(id=20, lab_id=5, name="安全审计工作站", spec="i7 / 32G / 2T SSD", quantity=12, status=1,
         desc="用于日志分析与应急响应"),
    # 大数据分析实验室 id=6
    dict(id=21, lab_id=6, name="数据计算节点", spec="32核 / 128G内存", quantity=8, status=1,
         desc="运行分布式计算任务"),
    dict(id=22, lab_id=6, name="数据存储节点", spec="100TB可用容量", quantity=4, status=1,
         desc="保存教学与实验数据集"),
    dict(id=23, lab_id=6, name="分析工作站", spec="i7 / 64G / 2T SSD", quantity=20, status=1,
         desc="用于数据清洗和可视化"),
    dict(id=24, lab_id=6, name="万兆交换机", spec="24口10GbE", quantity=2, status=1,
         desc="连接计算和存储节点"),
    # 云计算实验室 id=7
    dict(id=25, lab_id=7, name="虚拟化服务器", spec="双路CPU / 512G内存", quantity=6, status=1,
         desc="运行虚拟机和私有云节点"),
    dict(id=26, lab_id=7, name="容器集群节点", spec="32核 / 128G内存", quantity=10, status=1,
         desc="运行Kubernetes教学集群"),
    dict(id=27, lab_id=7, name="共享存储设备", spec="60TB NAS", quantity=2, status=1,
         desc="为集群提供持久化存储"),
    dict(id=28, lab_id=7, name="管理控制台", spec="i5 / 16G / 双显示器", quantity=4, status=1,
         desc="管理云平台和监控系统"),
    # 软件工程实验室 id=11
    dict(id=29, lab_id=11, name="开发主机", spec="i7 / 32G / 1T SSD", quantity=40, status=1,
         desc="用于项目开发和课程实践"),
    dict(id=30, lab_id=11, name="代码服务器", spec="16核 / 64G内存", quantity=2, status=1,
         desc="提供Git与持续集成服务"),
    dict(id=31, lab_id=11, name="投影仪", spec="1080P激光投影", quantity=2, status=1,
         desc="用于课程讲解和项目答辩"),
    dict(id=32, lab_id=11, name="测试移动终端", spec="Android测试机", quantity=12, status=1,
         desc="用于移动端兼容性测试"),
    # 数字媒体实验室 id=12
    dict(id=33, lab_id=12, name="图形工作站", spec="i9 / 64G / RTX4080", quantity=16, status=1,
         desc="用于三维建模和视频渲染"),
    dict(id=34, lab_id=12, name="数位屏", spec="22英寸压感屏", quantity=12, status=1,
         desc="用于数字绘画和界面设计"),
    dict(id=35, lab_id=12, name="专业摄像机", spec="4K摄像机", quantity=4, status=1,
         desc="用于高清视频拍摄"),
    dict(id=36, lab_id=12, name="录音套装", spec="电容麦克风 / 声卡", quantity=6, status=1,
         desc="用于配音和音频采集"),
    # 综合开放实验室 id=13（实验室关闭期间整体不可预约）
    dict(id=37, lab_id=13, name="通用实验工作站", spec="i7 / 32G / 1T SSD", quantity=30, status=1,
         desc="用于跨专业实践项目"),
    dict(id=38, lab_id=13, name="电子工具套装", spec="焊台 / 万用表 / 工具组", quantity=15, status=1,
         desc="用于电路制作和设备检修"),
    dict(id=39, lab_id=13, name="便携投影仪", spec="1080P", quantity=3, status=1,
         desc="用于小组展示和讨论"),
    dict(id=40, lab_id=13, name="3D打印机", spec="FDM / 300mm成型尺寸", quantity=2, status=0,
         desc="用于原型零件打印，目前维护中"),
]

LAB_BY_ID = {l["id"]: l for l in LABS}
EQUIP_BY_LAB = {}
for _e in EQUIPMENTS:
    EQUIP_BY_LAB.setdefault(_e["lab_id"], []).append(_e)

LAB_STATUS_TEXT = {1: "开放", 0: "关闭"}
EQUIP_STATUS_TEXT = {1: "正常", 0: "维修中"}

# 复杂/高风险设备（6-12页操作手册）；其余为简单设备（3-5页快速指南）
COMPLEX_EQUIP_IDS = {1, 3, 9, 11, 15, 16, 17, 18, 19, 25, 26, 40}

# ---------------- 预约规则（严格对应 reservation_services.py 当前实现） ----------------
RESERVATION_RULES = {
    "login_required": "用户登录后才能预约",
    "date_not_before_today": "预约日期不能早于中国北京时间当天",
    "end_after_start": "开始时间必须早于结束时间",
    "start_after_now": "预约开始时间必须晚于当前时间",
    "within_open_hours": "预约时段必须位于该实验室开放时间内",
    "closed_lab_no_reservation": "状态为关闭的实验室不能预约",
    "equipment_belongs_to_lab": "设备必须属于选择的实验室",
    "broken_equipment_no_reservation": "维修中的设备不能预约",
    "status_codes": {0: "待审核", 1: "已通过", 2: "已拒绝", 3: "已取消"},
    "occupying_status": [0, 1],
    "occupying_note": "待审核和已通过记录会占用对应资源时段",
    "not_occupying_status": [2, 3],
    "not_occupying_note": "已拒绝和已取消记录不占用时段",
    "lab_conflict_scope": "只预约实验室时，冲突检查对象是同一实验室的实验室预约",
    "equipment_conflict_scope": "预约具体设备时，冲突检查对象是同一台设备类型对应的预约",
    "auto_approve_minutes": 15,
    "auto_approve_note": "待审核超过15分钟且预约尚未开始时自动通过",
    "scan_seconds": 60,
    "scan_note": "后台当前每60秒扫描一次，因此自动通过可能发生在超过15分钟后的下一次扫描",
    "auto_cancel_note": "已到预约开始时间但仍为待审核的记录自动取消",
    "cancel_own": "用户可以取消本人的待审核或已通过预约",
    "cancel_final_state": "已拒绝或已取消记录不能再次取消",
    "cancel_started": "已经开始的预约不能取消",
    "cancel_one_hour": "距离开始不足1小时不能取消；恰好剩余1小时允许取消",
    "audit_only_pending": "管理员只能审核待审核状态的预约",
    "timezone": "所有预约时间判断按中国北京时间UTC+8执行",
}

DOC_VERSION = "V1.0"
DOC_DATE = "2026-10-20"
ORG_NAME = "智能实验中心"
SYSTEM_NAME = "AI智能实验室预约系统"
