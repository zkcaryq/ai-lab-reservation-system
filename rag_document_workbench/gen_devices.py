# -*- coding: utf-8 -*-
"""生成40类设备结构示意图、关键接口/控制面板图、正确/错误操作对比图。
所有图为教学示意图，非真实产品照片。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from imglib import F, new_canvas, rrect, arrow, text_c, title_block, hatch, dashed_rect

OUT = "D:/AI/faceprogram/rag_document_workbench/gen_images"
os.makedirs(OUT, exist_ok=True)
W, H = 1280, 860
DARK = "#1a3a6b"
METAL = "#cfd8dc"
METAL_D = "#90a4ae"
GREEN = "#1e8e3e"
RED = "#d93025"
BLUE = "#1a73e8"


def callout(d, xy, txy, label, font=None):
    font = font or F(16, True)
    d.line([xy, txy], fill="#5f6368", width=2)
    d.ellipse([xy[0] - 5, xy[1] - 5, xy[0] + 5, xy[1] + 5], fill=RED)
    tw = d.textlength(label, font=font)
    bx = txy[0] if txy[0] <= W / 2 else txy[0] - tw - 16
    d.rectangle([bx - 6, txy[1] - 15, bx + tw + 6, txy[1] + 15], fill="#fffde7", outline="#f9ab00", width=2)
    text_c(d, (bx + tw / 2, txy[1]), label, font, anchor="mm")


def base(name, en=""):
    img, d = new_canvas(W, H)
    title_block(d, W, H, f"{name}·设备结构示意图",
                subtitle="教学示意图，非真实产品照片",
                meta="智能实验中心｜V1.0")
    return img, d


def caption(d, s):
    text_c(d, (W / 2, H - 28), s, F(18), fill="#5f6368")


def finish(img, name, fname):
    img.save(f"{OUT}/{fname}")
    print("saved", fname)


def rack_chassis(d, x, y, w, h, units, accent=BLUE, label=""):
    rrect(d, [x, y, x + w, y + h], r=8, fill=METAL, outline="#546e7a", width=3)
    uh = (h - 30) / units
    for i in range(units):
        uy = y + 12 + i * uh
        d.rectangle([x + 14, uy + 3, x + w - 14, uy + uh - 5], fill="#455a64")
        d.ellipse([x + 22, uy + uh / 2 - 5, x + 34, uy + uh / 2 + 5], fill=GREEN)
        for k in range(3):
            d.line([(x + w - 60 + k * 12, uy + uh / 2 - 6), (x + w - 60 + k * 12, uy + uh / 2 + 6)], fill="#b0bec5", width=3)
    d.ellipse([x + 20, y + h - 14, x + 32, y + h - 4], fill=GREEN)
    if label:
        text_c(d, (x + w / 2, y + h + 20), label, F(15, True))


# ============ 各设备类型绘图 ============
def draw_gpu_server():
    img, d = base("GPU训练服务器")
    rack_chassis(d, 340, 130, 600, 320, 4)
    # GPU 卡
    for i, uy in enumerate((205, 290)):
        d.rectangle([420, uy, 860, uy + 55], fill="#263238", outline="#111", width=2)
        d.rectangle([450, uy + 12, 560, uy + 45], fill="#7c4dff")
        for k in range(6):
            d.rectangle([580 + k * 44, uy + 14, 616 + k * 44, uy + 43], fill="#37474f")
        d.text((835, uy + 27), "GPU", font=F(16, True), fill="#7c4dff", anchor="rm")
    callout(d, (860, 232), (1050, 190), "GPU加速卡×2（RTX4090）")
    callout(d, (500, 232), (230, 190), "散热风扇模组")
    callout(d, (940, 158), (1080, 320), "管理网口／电源模块")
    callout(d, (640, 400), (300, 430), "128G内存（大容量训练任务）")
    caption(d, "数据库规格：双RTX4090 / 128G内存｜所属：人工智能实验室")
    finish(img, "GPU训练服务器", "equip-01-gpu-server.png")


def draw_workstation(name, fname, note):
    img, d = base(name)
    rrect(d, [430, 150, 850, 330], r=10, fill="#e8eaf6", outline=DARK, width=4)
    d.rectangle([630, 330, 650, 370], fill="#9aa0a6")
    d.rectangle([560, 370, 720, 390], fill="#5f6368")
    text_c(d, (640, 240), "显示器", F(20, True), fill=DARK)
    rrect(d, [430, 430, 660, 660], r=10, fill="#eceff1", outline="#546e7a", width=4)
    d.rectangle([450, 445, 640, 465], fill="#b0bec5")
    d.rectangle([455, 480, 500, 530], fill="#7c4dff")
    d.ellipse([590, 610, 610, 630], fill=GREEN)
    callout(d, (850, 240), (1000, 200), "显示器")
    callout(d, (477, 505), (250, 460), "独立显卡（如RTX4080）")
    callout(d, (600, 620), (900, 620), "电源指示灯")
    callout(d, (660, 455), (900, 480), "前置USB/音频接口")
    caption(d, note)
    finish(img, name, fname)


def draw_infer_server(name, fname, note, accent="#00acc1"):
    img, d = base(name)
    rack_chassis(d, 340, 170, 600, 260, 3, accent=accent)
    d.rectangle([420, 240, 860, 300], fill="#263238", outline="#111", width=2)
    d.rectangle([450, 255, 540, 285], fill=accent)
    callout(d, (860, 270), (1040, 240), "加速计算卡")
    callout(d, (450, 200), (240, 180), "散热风道")
    callout(d, (500, 340), (260, 380), "系统盘／内存插槽")
    caption(d, note)
    finish(img, name, fname)


def draw_storage_array():
    img, d = base("高速存储阵列")
    rack_chassis(d, 340, 150, 600, 380, 8, accent="#8e24aa")
    for r in range(2):
        for c in range(6):
            d.rectangle([420 + c * 72, 200 + r * 60, 480 + c * 72, 250 + r * 60],
                        fill="#37474f", outline="#90a4ae", width=2)
            d.rectangle([428 + c * 72, 218 + r * 60, 436 + c * 72, 234 + r * 60], fill="#8e24aa")
    callout(d, (480, 225), (230, 180), "硬盘槽位（RAID6冗余）")
    callout(d, (500, 300), (1050, 260), "双控制器（冗余）")
    callout(d, (900, 470), (1080, 430), "主机光纤/万兆接口")
    caption(d, "数据库规格：80TB RAID6｜用途：保存训练数据和模型文件")
    finish(img, "高速存储阵列", "equip-04-storage-array.png")


def draw_nas():
    img, d = base("共享存储设备")
    rrect(d, [440, 220, 840, 480], r=14, fill=METAL, outline="#546e7a", width=4)
    for i in range(4):
        d.rectangle([480, 260 + i * 52, 700, 300 + i * 52], fill="#37474f", outline="#90a4ae", width=2)
    d.ellipse([770, 250, 800, 280], fill=GREEN)
    d.ellipse([770, 300, 800, 330], fill=BLUE)
    callout(d, (600, 280), (240, 220), "硬盘仓×4（RAID）")
    callout(d, (785, 265), (1000, 220), "状态指示灯")
    callout(d, (840, 380), (1050, 400), "千兆/万兆网口")
    caption(d, "数据库规格：60TB NAS｜所属：云计算实验室")
    finish(img, "共享存储设备", "equip-27-nas.png")


def draw_depth_cam():
    img, d = base("深度相机（RealSense D435i）")
    rrect(d, [400, 260, 880, 440], r=26, fill="#263238", outline="#111", width=3)
    for cx in (470, 810):
        d.ellipse([cx - 36, 300, cx + 36, 400], fill="#0d1117", outline="#90a4ae", width=3)
    d.ellipse([590 - 34, 306, 590 + 34, 394], fill="#101418", outline="#8ab4f8", width=3)
    d.ellipse([530, 320, 560, 350], fill="#4dd0e1")
    callout(d, (470, 350), (240, 300), "红外左相机")
    callout(d, (590, 350), (330, 520), "RGB彩色相机")
    callout(d, (810, 350), (1010, 300), "红外右相机")
    callout(d, (545, 335), (260, 200), "红外结构光投射器")
    d.rectangle([600, 440, 680, 470], fill="#455a64")
    text_c(d, (640, 490), "USB-C", F(14, True))
    d.rectangle([430, 130, 850, 160], fill="#455a64")
    callout(d, (640, 145), (1010, 180), "标准1/4英寸三脚架接口")
    caption(d, "公开资料整理：Intel RealSense D435i，双目红外+RGB+结构光，含IMU；来源：Intel产品页面")
    finish(img, "深度相机", "equip-05-depth-cam.png")


def draw_industrial_cam():
    img, d = base("工业相机（500万像素全局快门）")
    rrect(d, [480, 280, 800, 480], r=14, fill="#37474f", outline="#111", width=3)
    d.ellipse([520, 300, 640, 420], fill="#0d1117", outline="#90a4ae", width=3)
    d.ellipse([556, 336, 604, 384], fill="#1a237e")
    d.rectangle([640, 350, 720, 410], fill="#546e7a")
    d.ellipse([700, 352, 780, 408], fill="#263238", outline="#111", width=3)
    d.ellipse([716, 368, 764, 392], fill="#0d1117")
    d.rectangle([560, 480, 720, 520], fill="#455a64")
    text_c(d, (640, 545), "C口镜头卡口", F(15, True))
    d.ellipse([490, 500, 510, 520], fill=GREEN)
    callout(d, (530, 510), (250, 560), "状态指示灯")
    callout(d, (860, 380), (1040, 330), "定焦工业镜头")
    callout(d, (770, 380), (1020, 460), "触发/GPIO接口（后侧）")
    caption(d, "数据库规格：500万像素全局快门｜用途：目标检测数据采集")
    finish(img, "工业相机", "equip-06-industrial-cam.png")


def draw_light():
    img, d = base("补光灯组（双色温LED 100W）")
    d.line([(640, 250), (640, 600)], fill="#546e7a", width=10)
    d.line([(560, 620), (720, 620)], fill="#37474f", width=14)
    d.rectangle([520, 180, 760, 250], fill="#37474f")
    d.rectangle([535, 195, 745, 238], fill="#fff59d", outline="#f9ab00", width=3)
    for i in range(6):
        d.ellipse([550 + i * 32, 205, 574 + i * 32, 228], fill="#fff176")
    d.rectangle([600, 380, 690, 440], fill="#eceff1", outline="#546e7a", width=3)
    text_c(d, (645, 400), "色温", F(14, True))
    text_c(d, (645, 422), "亮度", F(14, True))
    callout(d, (745, 216), (1000, 180), "LED阵列灯板")
    callout(d, (690, 410), (1000, 380), "双色温/亮度调节旋钮")
    callout(d, (640, 600), (1000, 600), "灯架底座（配重固定）")
    caption(d, "数据库规格：双色温LED 100W×4套｜所属：计算机视觉实验室")
    finish(img, "补光灯组", "equip-08-light.png")


def draw_robot_arm():
    img, d = base("六轴机械臂（负载5kg）")
    # 围栏
    dashed_rect(d, [180, 170, 900, 700], color=RED, width=3, dash=16, gap=8)
    text_c(d, (540, 155), "安全围栏（运行时禁止进入）", F(18, True), fill=RED)
    # 底座
    d.rectangle([430, 600, 650, 660], fill="#37474f")
    d.rectangle([470, 560, 610, 600], fill="#546e7a")
    # 大臂小臂
    d.line([(540, 570), (540, 380)], fill="#f9ab00", width=26)
    d.line([(540, 380), (760, 300)], fill="#f9ab00", width=20)
    d.line([(760, 300), (830, 380)], fill="#f9ab00", width=14)
    # 腕部
    d.ellipse([520, 550, 560, 590], fill="#546e7a")
    d.ellipse([745, 285, 775, 315], fill="#546e7a")
    d.ellipse([820, 368, 840, 388], fill="#37474f")
    # 夹爪
    d.line([(840, 380), (880, 360)], fill="#37474f", width=6)
    d.line([(840, 380), (880, 400)], fill="#37474f", width=6)
    callout(d, (540, 470), (240, 420), "关节J2/J3（回转驱动）")
    callout(d, (650, 340), (420, 260), "大臂（铝合金壳体）")
    callout(d, (860, 385), (1050, 430), "末端夹爪（负载≤5kg）")
    d.ellipse([180, 640, 224, 684], fill=RED, outline="black", width=3)
    text_c(d, (202, 710), "急停按钮", F(15, True), fill=RED)
    rrect(d, [950, 560, 1180, 660], r=8, fill="#eceff1", outline="#546e7a", width=3)
    text_c(d, (1065, 585), "示教器", F(16, True))
    d.ellipse([990, 615, 1030, 645], outline="#137333", width=4)
    d.rectangle([1050, 610, 1150, 645], fill="#cfd8dc")
    callout(d, (1000, 630), (900, 730), "示教器（使能键+确认键）")
    caption(d, "数据库规格：负载5kg×2台｜所属：机器人创新实验室")
    finish(img, "六轴机械臂", "equip-09-robot-arm.png")


def draw_mobile_robot():
    img, d = base("移动机器人底盘（差速驱动）")
    # 侧视
    rrect(d, [300, 380, 720, 540], r=26, fill="#37474f", outline="#111", width=3)
    d.ellipse([330, 500, 420, 590], fill="#212121", outline="#616161", width=5)
    d.ellipse([600, 500, 690, 590], fill="#212121", outline="#616161", width=5)
    d.ellipse([355, 525, 395, 565], fill="#9e9e9e")
    d.ellipse([625, 525, 665, 565], fill="#9e9e9e")
    d.ellipse([490, 340, 530, 380], fill="#00acc1", outline="#111", width=3)
    text_c(d, (510, 322), "激光雷达安装位", F(14, True))
    callout(d, (375, 545), (230, 640), "驱动轮（差速）")
    callout(d, (665, 545), (820, 640), "万向支撑轮")
    callout(d, (450, 460), (240, 440), "电池仓（载重30kg）")
    callout(d, (620, 430), (860, 420), "控制器仓＋急停开关")
    d.ellipse([700, 400, 724, 424], fill=RED)
    # 俯视小图
    rrect(d, [900, 240, 1140, 420], r=20, fill="#eceff1", outline="#546e7a", width=3)
    d.ellipse([1000, 260, 1040, 300], fill="#00acc1")
    d.rectangle([915, 260, 935, 400], fill="#212121")
    d.rectangle([1105, 260, 1125, 400], fill="#212121")
    text_c(d, (1020, 440), "俯视图", F(15, True))
    caption(d, "数据库规格：差速驱动 / 载重30kg×4台｜所属：机器人创新实验室")
    finish(img, "移动机器人底盘", "equip-10-mobile-robot.png")


def draw_lidar():
    img, d = base("激光雷达（Livox Mid-360）")
    d.ellipse([430, 480, 850, 620], fill="#37474f", outline="#111", width=3)
    d.rectangle([430, 300, 850, 550], fill="#455a64")
    # 三条倾斜视窗
    for i, dy in enumerate((320, 400, 480)):
        d.rectangle([455, dy, 825, dy + 46], fill="#0d1117", outline="#8ab4f8", width=3)
    callout(d, (640, 340), (300, 260), "上部半球视场窗口")
    callout(d, (640, 420), (1020, 380), "中部360°水平视场窗口")
    callout(d, (640, 500), (300, 560), "下部补盲视场窗口")
    d.ellipse([620, 590, 660, 610], fill="#101418", outline="#90a4ae", width=2)
    text_c(d, (740, 600), "网线接口（底部）", F(14, True))
    caption(d, "公开资料整理：Livox Mid-360，360°×59°非重复扫描，底部出线；来源：Livox官网产品页")
    finish(img, "激光雷达", "equip-11-lidar.png")


def draw_edge_box():
    img, d = base("边缘计算盒（Jetson Orin 32G）")
    rrect(d, [420, 300, 860, 560], r=14, fill="#37474f", outline="#111", width=3)
    for i in range(9):
        d.line([(450 + i * 30, 320), (450 + i * 30, 360)], fill="#546e7a", width=8)
    for i, (lab, cx) in enumerate([("DC电源", 480), ("HDMI", 560), ("USB", 630), ("ETH", 700), ("GPIO", 780)]):
        d.rectangle([cx - 26, 520, cx + 26, 548], fill="#212121", outline="#90a4ae", width=2)
        text_c(d, (cx, 566), lab, F(13, True))
    callout(d, (500, 335), (280, 260), "散热鳍片（禁止遮挡）")
    callout(d, (700, 534), (1000, 480), "外设接口区（前面板）")
    caption(d, "数据库规格：Jetson Orin 32G×6台｜用途：运行机器人感知算法")
    finish(img, "边缘计算盒", "equip-12-edge-box.png")


def draw_esp32():
    img, d = base("传感器开发套件（ESP32多传感器）")
    rrect(d, [280, 300, 1000, 640], r=10, fill="#f5f5f5", outline="#9e9e9e", width=3)
    for gx in range(300, 990, 22):
        d.ellipse([gx - 3, 320, gx + 3, 326], fill="#bdbdbd")
        d.ellipse([gx - 3, 610, gx + 3, 616], fill="#bdbdbd")
    # ESP32 板
    rrect(d, [560, 400, 760, 560], r=6, fill="#1565c0", outline="#0d47a1", width=3)
    d.rectangle([620, 420, 700, 470], fill="#212121")
    for i in range(8):
        d.ellipse([575 + i * 23, 530, 585 + i * 23, 540], fill="#ffd54f")
    text_c(d, (660, 510), "ESP32", F(16, True), fill="white")
    # 传感器
    rrect(d, [330, 430, 440, 500], r=6, fill="#2e7d32", outline="#1b5e20", width=2)
    text_c(d, (385, 465), "温湿度", F(14, True), fill="white")
    rrect(d, [830, 430, 950, 500], r=6, fill="#6a1b9a", outline="#4a148c", width=2)
    text_c(d, (890, 465), "光照", F(14, True), fill="white")
    rrect(d, [330, 540, 440, 600], r=6, fill="#ef6c00", outline="#e65100", width=2)
    text_c(d, (385, 570), "气压", F(14, True), fill="white")
    rrect(d, [830, 540, 950, 600], r=6, fill="#37474f", outline="#111", width=2)
    text_c(d, (890, 570), "OLED屏", F(14, True), fill="white")
    callout(d, (660, 445), (1040, 340), "ESP32主控（WiFi/蓝牙）")
    callout(d, (385, 465), (230, 400), "温湿度传感器")
    callout(d, (890, 465), (1060, 540), "光照传感器")
    caption(d, "数据库规格：ESP32多传感器套件×20套｜所属：物联网实验室")
    finish(img, "传感器开发套件", "equip-13-esp32.png")


def draw_lora_gw():
    img, d = base("LoRa网关（8通道LoRaWAN）")
    rrect(d, [440, 320, 840, 560], r=12, fill="#eceff1", outline="#546e7a", width=4)
    for i in range(8):
        d.ellipse([480 + i * 44, 360, 508 + i * 44, 388], fill=GREEN if i < 5 else "#cfd8dc")
    text_c(d, (640, 440), "8通道射频前端", F(17, True))
    d.rectangle([500, 480, 620, 510], fill="#212121")
    text_c(d, (560, 495), "ETH", F(13, True), fill="white")
    d.line([(790, 320), (790, 200)], fill="#137333", width=6)
    d.line([(760, 230), (820, 200)], fill="#137333", width=5)
    callout(d, (524, 374), (280, 300), "通道指示灯（1-8）")
    callout(d, (790, 250), (1020, 220), "LoRa外置天线（禁止空载开机）")
    caption(d, "数据库规格：8通道LoRaWAN×3台｜用途：低功耗广域网实验")
    finish(img, "LoRa网关", "equip-14-lora.png")


def draw_oscilloscope():
    img, d = base("示波器（100MHz双通道）")
    rrect(d, [320, 220, 960, 660], r=16, fill="#eceff1", outline="#546e7a", width=4)
    d.rectangle([360, 260, 720, 460], fill="#0d1117", outline="#111", width=3)
    # 波形
    pts = []
    for i in range(72):
        x = 372 + i * 4.6
        y = 360 + 60 * (0.5 if 8 <= i % 16 < 12 else -0.7 if 12 <= i % 16 < 14 else -0.2)
        pts.append((x, y))
    d.line(pts, fill="#4dd0e1", width=3)
    text_c(d, (700, 285), "CH1", F(15, True), fill="#4dd0e1", anchor="rm")
    # 旋钮
    for i, lab in enumerate(["VERT", "HORIZ", "TRIG"]):
        cx = 800 + i * 55
        d.ellipse([cx - 22, 300, cx + 22, 344], fill="#cfd8dc", outline="#546e7a", width=3)
        text_c(d, (cx, 366), lab, F(13, True))
    for i, lab in enumerate(["CH1", "CH2"]):
        d.ellipse([790 + i * 80, 520, 826 + i * 80, 556], fill="#212121", outline="#90a4ae", width=3)
        text_c(d, (808 + i * 80, 578), lab + " BNC", F(13, True))
    d.rectangle([500, 500, 680, 545], fill="#fdd663")
    text_c(d, (590, 522), "AUTO SET", F(15, True))
    callout(d, (808, 538), (300, 620), "探头接线柱（先接地后接信号）")
    callout(d, (822, 322), (1030, 280), "垂直/水平档位旋钮")
    callout(d, (590, 522), (980, 600), "AUTO一键设置（新手推荐）")
    caption(d, "数据库规格：100MHz双通道×8台｜所属：物联网实验室")
    finish(img, "示波器", "equip-15-osc.png")


def draw_psu():
    img, d = base("可编程电源（30V 5A）")
    rrect(d, [380, 240, 900, 640], r=16, fill="#eceff1", outline="#546e7a", width=4)
    d.rectangle([430, 290, 850, 400], fill="#0d1117", outline="#111", width=3)
    d.text((470, 320), "00.00 V", font=F(34, True), fill="#4dd0e1")
    d.text((660, 320), "0.000 A", font=F(34, True), fill="#fdd663")
    for i, (lab, cx) in enumerate([("电压粗调", 500), ("电压细调", 590), ("电流设定", 690), ("OVP", 780)]):
        d.ellipse([cx - 24, 440, cx + 24, 488], fill="#cfd8dc", outline="#546e7a", width=3)
        text_c(d, (cx, 512), lab, F(14, True))
    for i, (lab, cx, col) in enumerate([("+", 470, RED), ("−", 540, "#212121"), ("GND", 610, GREEN)]):
        d.ellipse([cx - 18, 560, cx + 18, 596], fill="#212121", outline="#90a4ae", width=3)
        d.text((cx, 578), lab, font=F(16, True), fill=col, anchor="mm")
    d.rectangle([800, 560, 870, 596], fill="#388e3c", outline="#111", width=2)
    text_c(d, (835, 578), "OUT", F(14, True), fill="white", anchor="mm")
    callout(d, (640, 340), (240, 300), "双显：实际电压/电流")
    callout(d, (835, 578), (1020, 500), "输出开关（先设参数后开输出）")
    callout(d, (610, 578), (240, 620), "输出端子：红+ 黑− 绿GND")
    caption(d, "数据库规格：30V 5A×10台｜所属：物联网实验室")
    finish(img, "可编程电源", "equip-16-psu.png")


def draw_firewall():
    img, d = base("硬件防火墙（千兆多端口）")
    rack_chassis(d, 340, 260, 620, 170, 2, accent="#e8710a")
    groups = [("WAN", 4), ("LAN", 8), ("DMZ", 2)]
    gx = 380
    for name, n in groups:
        for k in range(n):
            d.rectangle([gx + k * 34, 320, gx + k * 34 + 24, 348], fill="#111", outline="#90a4ae", width=2)
            d.ellipse([gx + k * 34 + 6, 352, gx + k * 34 + 14, 360], fill=GREEN)
        text_c(d, (gx + n * 17, 380), name, F(14, True))
        gx += n * 34 + 40
    callout(d, (420, 334), (250, 240), "WAN口（接外网侧）")
    callout(d, (700, 334), (1050, 260), "LAN口（接隔离内网）")
    callout(d, (620, 290), (350, 180), "状态/告警指示灯")
    caption(d, "数据库规格：千兆多端口×4台｜所属：网络安全实验室")
    finish(img, "硬件防火墙", "equip-18-firewall.png")


def draw_traffic():
    img, d = base("网络流量分析仪（10GbE双口）")
    rack_chassis(d, 340, 260, 620, 170, 2, accent="#7b1fa2")
    for i, lab in enumerate(["SFP+1", "SFP+2"]):
        cx = 470 + i * 120
        d.rectangle([cx - 30, 320, cx + 30, 356], fill="#111", outline="#90a4ae", width=2)
        text_c(d, (cx, 382), lab, F(14, True))
    d.rectangle([740, 320, 860, 356], fill="#212121")
    text_c(d, (800, 382), "管理口/Console", F(13, True))
    callout(d, (500, 338), (280, 240), "镜像流量输入口×2")
    callout(d, (800, 338), (1040, 300), "配置管理接口")
    caption(d, "数据库规格：10GbE双口×2台｜用途：采集和分析镜像流量")
    finish(img, "网络流量分析仪", "equip-19-traffic.png")


def draw_switch():
    img, d = base("万兆交换机（24口10GbE）")
    rack_chassis(d, 340, 260, 620, 170, 2, accent="#0b8043")
    for i in range(24):
        cx = 372 + i * 22
        d.rectangle([cx, 322, cx + 16, 348], fill="#111", outline="#90a4ae", width=1)
    for i in range(4):
        cx = 372 + 24 * 22 + 14 + (i % 2) * 46
        if i < 2:
            d.rectangle([890 + i * 40, 322, 920 + i * 40, 348], fill="#111", outline="#90a4ae", width=2)
    text_c(d, (640, 384), "24×10GbE电口 + 4×SFP+光口", F(14, True))
    callout(d, (400, 335), (260, 250), "计算/存储节点上联口")
    caption(d, "数据库规格：24口10GbE×2台｜所属：大数据分析实验室")
    finish(img, "万兆交换机", "equip-24-switch.png")


def draw_projector(name, fname, note):
    img, d = base(name)
    rrect(d, [400, 330, 880, 520], r=24, fill="#eceff1", outline="#546e7a", width=4)
    d.ellipse([430, 380, 570, 500], fill="#37474f", outline="#111", width=3)
    d.ellipse([468, 410, 532, 470], fill="#0d1117")
    d.rectangle([700, 380, 840, 410], fill="#cfd8dc")
    for i in range(4):
        d.ellipse([705 + i * 36, 445, 725 + i * 36, 465], fill=GREEN)
    d.rectangle([560, 520, 720, 560], fill="#9aa0a6")
    callout(d, (500, 440), (260, 420), "镜头（勿直视光路）")
    callout(d, (770, 395), (1030, 340), "HDMI×2 / USB / 电源口")
    callout(d, (745, 455), (1030, 470), "状态指示灯")
    callout(d, (640, 540), (300, 620), "吊装臂/支脚")
    caption(d, note)
    finish(img, name, fname)


def draw_phones():
    img, d = base("测试移动终端（Android测试机）")
    rrect(d, [380, 220, 900, 640], r=14, fill="#eceff1", outline="#546e7a", width=4)
    text_c(d, (640, 250), "多机充电柜", F(18, True), fill=DARK)
    for r in range(3):
        for c in range(4):
            x, y = 430 + c * 115, 290 + r * 110
            rrect(d, [x, y, x + 56, y + 92], r=8, fill="#212121", outline="#616161", width=2)
            d.rectangle([x + 6, y + 12, x + 50, y + 72], fill="#4dd0e1")
    callout(d, (640, 336), (1020, 280), "测试终端（分区编号）")
    callout(d, (570, 400), (240, 460), "独立充电槽位")
    caption(d, "数据库规格：Android测试机×12台｜所属：软件工程实验室")
    finish(img, "测试移动终端", "equip-32-phones.png")


def draw_pen_display():
    img, d = base("数位屏（22英寸压感屏）")
    rrect(d, [400, 220, 880, 500], r=14, fill="#111", outline="#111", width=3)
    d.rectangle([420, 240, 860, 480], fill="#e8f0fe")
    # 画笔
    d.line([(700, 400), (790, 300)], fill="#f9ab00", width=10)
    d.ellipse([786, 292, 800, 306], fill="#37474f")
    for i in range(5):
        d.ellipse([820, 430 + i * 12, 838, 448 + i * 12], outline="#1a73e8", width=2)
    d.rectangle([560, 500, 720, 530], fill="#546e7a")
    callout(d, (640, 360), (280, 300), "压感屏（禁止用尖锐物触压）")
    callout(d, (795, 300), (1030, 260), "压感笔（笔尖磨损及时更换）")
    callout(d, (829, 470), (1030, 430), "快捷键区")
    caption(d, "数据库规格：22英寸压感屏×12台｜所属：数字媒体实验室")
    finish(img, "数位屏", "equip-34-pen.png")


def draw_camcorder():
    img, d = base("专业摄像机（4K）")
    rrect(d, [440, 320, 800, 540], r=18, fill="#37474f", outline="#111", width=3)
    d.ellipse([680, 360, 820, 480], fill="#0d1117", outline="#90a4ae", width=3)
    d.ellipse([730, 395, 775, 440], fill="#1a237e")
    d.rectangle([480, 260, 720, 300], fill="#212121")
    d.rectangle([470, 540, 640, 620], fill="#263238")
    d.ellipse([540, 390, 600, 450], fill="#eceff1", outline="#616161", width=3)
    callout(d, (750, 420), (1030, 380), "4K镜头（手动对焦环）")
    callout(d, (600, 280), (350, 230), "提手（内置拾音麦）")
    callout(d, (570, 420), (300, 420), "翻转监视屏")
    callout(d, (555, 580), (330, 660), "电池仓与存储卡槽")
    caption(d, "数据库规格：4K摄像机×4台｜所属：数字媒体实验室")
    finish(img, "专业摄像机", "equip-35-camcorder.png")


def draw_audio():
    img, d = base("录音套装（电容麦克风/声卡）")
    d.line([(560, 620), (560, 360)], fill="#546e7a", width=8)
    d.ellipse([510, 280, 610, 380], fill="#37474f", outline="#111", width=3)
    for i in range(5):
        d.line([(525 + i * 15, 292), (525 + i * 15, 368)], fill="#616161", width=2)
    d.line([(520, 300), (700, 250)], fill="#546e7a", width=4)
    rrect(d, [760, 360, 1020, 560], r=12, fill="#eceff1", outline="#546e7a", width=4)
    for i in range(4):
        d.ellipse([790 + i * 56, 400, 830 + i * 56, 440], fill="#cfd8dc", outline="#546e7a", width=3)
    for i in range(6):
        d.ellipse([795 + i * 38, 490, 813 + i * 38, 508], fill="#43a047")
    callout(d, (560, 330), (330, 260), "电容麦克风（48V幻象供电）")
    callout(d, (610, 258), (860, 220), "防震架")
    callout(d, (890, 500), (350, 640), "声卡：增益/监听旋钮+电平表")
    caption(d, "数据库规格：电容麦克风 / 声卡×6套｜所属：数字媒体实验室")
    finish(img, "录音套装", "equip-36-audio.png")


def draw_toolkit():
    img, d = base("电子工具套装（焊台/万用表/工具组）")
    rrect(d, [340, 420, 560, 600], r=12, fill="#eceff1", outline="#546e7a", width=4)
    d.rectangle([380, 450, 520, 500], fill="#0d1117")
    d.text((395, 458), "350", font=F(26, True), fill="#fdd663")
    d.line([(540, 470), (640, 470)], fill="#9aa0a6", width=6)
    d.line([(640, 470), (640, 420)], fill="#c62828", width=6)
    d.ellipse([632, 404, 648, 420], fill="#c62828")
    rrect(d, [620, 480, 780, 620], r=10, fill="#fdd835", outline="#546e7a", width=3)
    d.rectangle([650, 500, 750, 545], fill="#0d1117")
    d.text((658, 505), "12.00", font=F(20, True), fill="#4dd0e1")
    callout(d, (450, 475), (280, 350), "恒温焊台（用毕断电归位）")
    callout(d, (700, 522), (900, 560), "数字万用表（测前选对档位）")
    callout(d, (560, 620), (420, 680), "烙铁架／吸锡器／镊子组")
    caption(d, "数据库规格：焊台 / 万用表 / 工具组×15套｜所属：综合开放实验室")
    finish(img, "电子工具套装", "equip-38-toolkit.png")


def draw_printer3d():
    img, d = base("3D打印机（FDM 300mm成型尺寸）·当前维修中")
    # 框架
    d.line([(400, 200), (400, 640)], fill="#546e7a", width=10)
    d.line([(880, 200), (880, 640)], fill="#546e7a", width=10)
    d.line([(400, 200), (880, 200)], fill="#546e7a", width=10)
    d.rectangle([380, 620, 900, 660], fill="#37474f")
    d.rectangle([420, 600, 860, 620], fill="#263238")
    text_c(d, (640, 610), "打印平台（300×300mm）", F(14, True), fill="white")
    # 挤出头
    d.rectangle([600, 230, 680, 300], fill="#e8710a")
    d.polygon([(625, 300), (655, 300), (640, 330)], fill="#37474f")
    d.line([(640, 200), (640, 230)], fill="#111", width=4)
    # 料盘
    d.ellipse([920, 260, 1040, 380], outline="#546e7a", width=10)
    d.ellipse([955, 295, 1005, 345], fill="#bdbdbd")
    rrect(d, [830, 480, 950, 560], r=8, fill="#eceff1", outline="#546e7a", width=3)
    text_c(d, (890, 520), "控制屏", F(15, True))
    hatch(d, [390, 190, 900, 670], color="#9aa0a6", spacing=30, width=2)
    callout(d, (640, 265), (300, 240), "挤出加热头（高温200℃+）")
    callout(d, (980, 320), (1100, 240), "耗材料盘")
    callout(d, (890, 520), (1090, 520), "控制屏（维修中·禁用）")
    text_c(d, (640, 720), "⚠ 设备维修中，暂不可预约、禁止通电", F(20, True), fill=RED)
    caption(d, "数据库规格：FDM / 300mm成型尺寸×2台｜所属：综合开放实验室（实验室关闭期间）")
    finish(img, "3D打印机", "equip-40-printer3d.png")


def draw_server_generic(name, fname, note, accent="#00acc1", extra=""):
    img, d = base(name)
    rack_chassis(d, 380, 200, 560, 300, 6, accent=accent)
    callout(d, (940, 240), (1080, 200), "电源模块×2（冗余）")
    callout(d, (940, 350), (1080, 350), "管理网口＋业务网口")
    callout(d, (660, 500), (300, 560), "散热风道（保持前后通风）")
    if extra:
        callout(d, (500, 260), (250, 300), extra)
    caption(d, note)
    finish(img, name, fname)


def draw_compute_node():
    img, d = base("数据计算节点")
    rack_chassis(d, 380, 200, 560, 300, 6, accent="#0b8043")
    callout(d, (940, 240), (1080, 200), "双电源（冗余）")
    callout(d, (940, 350), (1080, 350), "万兆上联网口")
    callout(d, (660, 500), (300, 560), "散热风道（保持前后通风）")
    callout(d, (500, 260), (250, 300), "32核CPU／128G内存")
    caption(d, "数据库规格：32核 / 128G内存×8台｜用途：运行分布式计算任务")
    finish(img, "数据计算节点", "equip-21-compute.png")


def draw_storage_node():
    img, d = base("数据存储节点")
    rack_chassis(d, 380, 180, 560, 340, 8, accent="#8e24aa")
    for r in range(2):
        for c in range(6):
            d.rectangle([420 + c * 62, 220 + r * 55, 470 + c * 62, 264 + r * 55],
                        fill="#37474f", outline="#90a4ae", width=2)
    callout(d, (460, 240), (250, 200), "大容量硬盘槽位")
    callout(d, (900, 300), (1080, 260), "双控制器/万兆接口")
    caption(d, "数据库规格：100TB可用容量×4台｜用途：保存教学与实验数据集")
    finish(img, "数据存储节点", "equip-22-storagenode.png")


def draw_target_server():
    img, d = base("攻防靶机服务器")
    rack_chassis(d, 380, 200, 560, 300, 6, accent="#d93025")
    d.rectangle([420, 250, 560, 300], fill="#b71c1c")
    text_c(d, (490, 275), "靶场环境", F(16, True), fill="white")
    callout(d, (940, 240), (1080, 200), "双电源（冗余）")
    callout(d, (490, 275), (260, 320), "隔离靶标虚拟化层")
    callout(d, (940, 420), (1080, 420), "仅连接隔离实验网段")
    caption(d, "数据库规格：32核 / 256G内存×3台｜所属：网络安全实验室（物理隔离网段）")
    finish(img, "攻防靶机服务器", "equip-17-target.png")


def draw_virt_server():
    img, d = base("虚拟化服务器")
    rack_chassis(d, 380, 200, 560, 300, 6, accent="#3949ab")
    d.rectangle([420, 250, 880, 300], fill="#263238")
    for i in range(4):
        d.rectangle([440 + i * 110, 262, 530 + i * 110, 288], fill="#3949ab")
    text_c(d, (640, 275), "VM VM VM VM", F(14, True), fill="white", anchor="mm")
    callout(d, (940, 275), (1080, 240), "虚拟化层（VM资源池）")
    callout(d, (940, 350), (1080, 380), "双路CPU / 512G内存")
    caption(d, "数据库规格：双路CPU / 512G内存×6台｜用途：运行虚拟机和私有云节点")
    finish(img, "虚拟化服务器", "equip-25-virt.png")


def draw_console():
    img, d = base("管理控制台（i5 / 16G / 双显示器）")
    workstation_draw = None
    for i, dx in enumerate((430, 700)):
        rrect(d, [dx, 200, dx + 260, 380], r=10, fill="#e8eaf6", outline=DARK, width=4)
        d.rectangle([dx + 120, 380, dx + 140, 410], fill="#9aa0a6")
        d.rectangle([dx + 60, 410, dx + 200, 424], fill="#5f6368")
        text_c(d, (dx + 130, 290), f"显示器{i+1}", F(16, True), fill=DARK)
    rrect(d, [470, 460, 690, 640], r=10, fill="#eceff1", outline="#546e7a", width=4)
    text_c(d, (580, 550), "主机（i5/16G）", F(16, True))
    callout(d, (690, 410), (1000, 380), "双显示器（监控+操作分屏）")
    callout(d, (580, 550), (300, 580), "主机（仅授权管理员使用）")
    caption(d, "数据库规格：i5 / 16G / 双显示器×4台｜用途：管理云平台和监控系统")
    finish(img, "管理控制台", "equip-28-console.png")


def draw_code_server():
    img, d = base("代码服务器")
    rack_chassis(d, 380, 200, 560, 300, 5, accent="#00897b")
    d.rectangle([420, 250, 880, 300], fill="#263238")
    text_c(d, (650, 275), "Git / CI 服务", F(16, True), fill="#80cbc4", anchor="mm")
    callout(d, (940, 240), (1080, 200), "双电源（冗余）")
    callout(d, (650, 275), (300, 330), "代码仓库与持续集成服务")
    callout(d, (660, 500), (300, 560), "散热风道（保持前后通风）")
    caption(d, "数据库规格：16核 / 64G内存×2台｜用途：提供Git与持续集成服务")
    finish(img, "代码服务器", "equip-30-codesrv.png")


# ============ 正确/错误操作对比图 ============
DODONT = {
    1: [("使用个人分配账号登录任务调度系统排队提交训练任务", "不带账号直接在服务器本地新建任务或拔插电源"),
        ("训练数据统一写入存储阵列并按项目建目录", "把数据散落在本地C盘导致节点空间爆满")],
    2: [("锁定工位后离开，锁屏并保管好个人文件", "离开不锁屏，账号被他人冒用")],
    3: [("部署前先在测试环境验证，控制并发与超时", "把未测试的大并发服务直接跑满推理服务器")],
    4: [("按项目目录规范读写存储阵列", "随意删除他人目录或存放与实验无关文件")],
    5: [("先装三脚架固定、再接USB，热插拔前先停止取流", "带电拔插USB线或手持相机晃动拍摄")],
    6: [("拍摄前设置好曝光与触发模式，镜头朝下放置", "镜头随意朝上落灰、用手直接触摸镜片")],
    7: [("标注文件按项目命名规范保存并定期提交", "把标注数据存到桌面且不备份")],
    8: [("调整角度后固定灯架并配重", "灯架不固定，人走过碰倒")],
    9: [("先低速试运行确认安全区无人后再执行程序", "围栏内有人时启动机械臂或从臂下穿行")],
    10: [("在指定测试跑道内以低速测试避障", "在工位区高速跑动撞人撞物")],
    11: [("上电前检查网线与安装支架牢固", "通电时用手触摸激光发射窗口")],
    12: [("使用官方镜像烧录系统，接线断电操作", "带电插拔排线或随意刷第三方系统")],
    13: [("实验前核对套件清单，接线断电操作", "带电改接线路导致芯片烧毁")],
    14: [("接好天线后再上电", "不接天线直接开机烧射频前端")],
    15: [("先接探头地线，选对档位与倍率再测量", "用1x探头直接测高压或带电换档")],
    16: [("先设限压限流，接线正负极确认后再开输出", "先开输出后接线，正负极反接")],
    17: [("仅在隔离网段内按授权科目演练", "把靶机网段接入校园网或互联网")],
    18: [("变更策略前备份配置并记录变更单", "随意清空策略或恢复出厂设置")],
    19: [("只镜像指定端口的流量进行分析", "私自串接到生产链路造成断网")],
    20: [("日志分析使用脱敏数据并按规范留存", "把日志数据带出实验室或外传")],
    21: [("通过调度系统提交分布式任务", "直接在节点上跑任务挤占他人资源")],
    22: [("数据集按目录规范存放并登记", "私人文件占满存储导致配额告警")],
    23: [("大数据集直接在存储节点上处理", "把百GB数据集拷到工作站本地")],
    24: [("变更跳线后在配线表登记", "随意拔插跳线导致集群掉线")],
    25: [("创建虚拟机前先申请资源配额", "超配资源导致宿主机宕机")],
    26: [("使用命名空间隔离并限额部署", "在默认命名空间直接部署大服务")],
    27: [("重要数据定期快照并异地备份", "单份存储不备份，误删无法恢复")],
    28: [("操作前登录个人管理员账号并留痕", "共享管理员账号操作不留日志")],
    29: [("按工位号使用并锁屏保管账号", "用完不关机、不锁屏、私接大功率电器")],
    30: [("代码按分支规范提交，CI任务排队执行", "向主干直接推送未测试代码")],
    31: [("使用前确认吊装牢固、关机冷却后再断电", "投影中直接拔电源，灯泡骤冷损坏")],
    32: [("测试前登记编号，用毕放回充电柜", "私自带走测试机或恢复出厂设置不报告")],
    33: [("渲染任务提交至队列，大工程文件存共享盘", "本地渲染跑满GPU导致过热死机")],
    34: [("用配套压感笔轻触操作，定期校准", "用指甲或硬物划伤屏面")],
    35: [("拍摄前检查存储卡容量与电池，三脚架固定", "手持奔跑拍摄摔机，素材不备份")],
    36: [("录音前试音调节增益，人像声音采集签授权", "未取得授权私自录制他人声音")],
    37: [("按工位号登记使用，离座锁屏", "占座不走、私拉排插")],
    38: [("焊接时开排风、烙铁归架，用毕断电", "烙铁随手放桌面烫伤人或点燃杂物")],
    39: [("借用登记，散热孔勿遮挡", "投影中遮挡散热孔或带电插拔HDMI")],
    40: [("（维修中）等待管理员确认修复后再预约", "维修期间私自通电打印造成二次损坏")],
}

CHECK = dict(fill="#e6f4ea", outline="#137333", mark="#137333", title="正确操作")
CROSS = dict(fill="#fce8e6", outline="#c5221f", mark="#c5221f", title="错误操作")


def gen_dodont(eid, name):
    pairs = DODONT[eid]
    img, d = new_canvas(W, 320 + len(pairs) * 190)
    title_block(d, W, img.height, f"{name}·正确操作与错误操作对比",
                subtitle="教学示意", meta="智能实验中心｜V1.0")
    y = 120
    for good, bad in pairs:
        for col, txt, st in ((0, good, CHECK), (1, bad, CROSS)):
            x0 = 70 + col * 640
            rrect(d, [x0, y, x0 + 600, y + 160], r=14, fill=st["fill"], outline=st["outline"], width=3)
            d.ellipse([x0 + 20, y + 20, x0 + 72, y + 72], fill="white", outline=st["mark"], width=5)
            if st is CHECK:
                d.line([(x0 + 32, y + 46), (x0 + 44, y + 60), (x0 + 62, y + 32)], fill=st["mark"], width=6)
            else:
                d.line([(x0 + 33, y + 33), (x0 + 59, y + 59)], fill=st["mark"], width=6)
                d.line([(x0 + 59, y + 33), (x0 + 33, y + 59)], fill=st["mark"], width=6)
            text_c(d, (x0 + 86, y + 46), st["title"], F(20, True), fill=st["mark"], anchor="lm")
            _wrap_text(d, x0 + 30, y + 92, 550, txt)
        y += 190
    img.save(f"{OUT}/dodont-{eid:02d}.png")
    print("saved", f"dodont-{eid:02d}.png")


def _wrap_text(d, x, y, maxw, s, font=None, color="#202124", lh=30):
    font = font or F(19)
    line = ""
    yy = y
    for ch in s:
        if d.textlength(line + ch, font=font) > maxw:
            d.text((x, yy), line, font=font, fill=color)
            line = ch
            yy += lh
        else:
            line += ch
    if line:
        d.text((x, yy), line, font=font, fill=color)


def draw_panel(eid, name, kind):
    """关键接口/控制区域放大图"""
    img, d = new_canvas(W, 620)
    title_block(d, W, 620, f"{name}·关键接口与控制区域图",
                subtitle="教学示意图", meta="智能实验中心｜V1.0")
    if kind == "server_front":
        rrect(d, [240, 150, 1040, 470], r=12, fill=METAL, outline="#546e7a", width=4)
        for i, (lab, col) in enumerate([("电源", GREEN), ("告警", RED), ("定位", "#f9ab00"), ("网络", BLUE)]):
            d.ellipse([300 + i * 90, 200, 340 + i * 90, 240], fill=col)
            text_c(d, (320 + i * 90, 264), lab, F(15, True))
        for k in range(6):
            d.rectangle([300 + k * 90, 310, 370 + k * 90, 380], fill="#212121", outline="#90a4ae", width=2)
            text_c(d, (335 + k * 90, 404), f"网口{k+1}", F(13))
    elif kind == "bench_front":
        rrect(d, [240, 130, 1040, 480], r=12, fill=METAL, outline="#546e7a", width=4)
        d.rectangle([300, 170, 660, 300], fill="#0d1117")
        text_c(d, (480, 235), "显示屏区", F(18, True), fill="#4dd0e1")
        for i in range(4):
            d.ellipse([700 + i * 90, 190, 750 + i * 90, 240], fill="#cfd8dc", outline="#546e7a", width=3)
            text_c(d, (725 + i * 90, 264), f"旋钮{i+1}", F(13))
        for i in range(3):
            d.ellipse([560 + i * 110, 360, 610 + i * 110, 410], fill="#212121", outline="#90a4ae", width=3)
            text_c(d, (585 + i * 110, 436), ["CH1", "CH2", "OUT"][i], F(14, True))
    elif kind == "io_front":
        rrect(d, [240, 150, 1040, 470], r=12, fill=METAL, outline="#546e7a", width=4)
        ports = ["DC", "HDMI", "USB×2", "RJ45", "Console", "复位"]
        for i, p in enumerate(ports):
            x = 300 + i * 120
            d.rectangle([x - 40, 240, x + 40, 320], fill="#212121", outline="#90a4ae", width=2)
            text_c(d, (x, 350), p, F(15, True))
        d.ellipse([900, 180, 940, 220], fill=RED)
        text_c(d, (920, 244), "电源灯", F(13))
    elif kind == "panel_control":
        rrect(d, [240, 130, 1040, 500], r=12, fill=METAL, outline="#546e7a", width=4)
        d.ellipse([330, 200, 450, 320], fill=RED, outline="black", width=4)
        text_c(d, (390, 350), "急停按钮", F(16, True))
        d.ellipse([520, 210, 610, 300], fill="#cfd8dc", outline="#546e7a", width=3)
        text_c(d, (565, 330), "模式开关", F(15, True))
        rrect(d, [700, 190, 980, 330], r=8, fill="#0d1117")
        text_c(d, (840, 260), "状态显示屏", F(16, True), fill="#4dd0e1")
        text_c(d, (640, 430), "控制区域：急停→模式→确认，操作前请熟记位置", F(17, True))
    elif kind == "cam_front":
        rrect(d, [300, 170, 900, 460], r=14, fill="#37474f", outline="#111", width=3)
        d.ellipse([700, 220, 850, 370], fill="#0d1117", outline="#90a4ae", width=3)
        for i, lab in enumerate(["REC", "电源", "菜单", "回放"]):
            d.ellipse([340 + i * 90, 390, 390 + i * 90, 440], outline="#90a4ae", width=3)
            text_c(d, (365 + i * 90, 330), lab, F(14, True))
        text_c(d, (775, 400), "镜头卡口", F(14), fill="white")
    caption_h = 560
    text_c(d, (W / 2, caption_h), "图中编号仅为讲解用途，实际位置以设备实物为准。", F(17), fill="#5f6368")
    img.save(f"{OUT}/panel-{eid:02d}.png")
    print("saved", f"panel-{eid:02d}.png")


PANEL_KIND = {
    1: "server_front", 3: "server_front", 17: "server_front", 21: "server_front",
    22: "server_front", 25: "server_front", 26: "server_front", 30: "server_front",
    15: "bench_front", 16: "bench_front",
    5: "io_front", 6: "io_front", 11: "io_front", 12: "io_front", 13: "io_front",
    14: "io_front", 18: "io_front", 19: "io_front", 24: "io_front", 27: "io_front",
    9: "panel_control", 40: "panel_control",
    35: "cam_front",
}


def main():
    # 40台设备的示意图映射
    draw_gpu_server()
    draw_workstation("AI开发工作站", "equip-02-ws-ai.png", "数据库规格：i9 / 64G / RTX4080×12台｜所属：人工智能实验室")
    draw_infer_server("推理服务器", "equip-03-infer.png", "数据库规格：A10 24G / 128G内存×2台｜用途：模型部署和性能测试")
    draw_storage_array()
    draw_depth_cam()
    draw_industrial_cam()
    draw_workstation("标注工作站", "equip-07-ws-label.png", "数据库规格：i7 / 32G / 27英寸显示器×10台｜用途：图片和视频数据标注")
    draw_light()
    draw_robot_arm()
    draw_mobile_robot()
    draw_lidar()
    draw_edge_box()
    draw_esp32()
    draw_lora_gw()
    draw_oscilloscope()
    draw_psu()
    draw_target_server()
    draw_firewall()
    draw_traffic()
    draw_workstation("安全审计工作站", "equip-20-ws-audit.png", "数据库规格：i7 / 32G / 2T SSD×12台｜用途：日志分析与应急响应")
    draw_compute_node()
    draw_storage_node()
    draw_workstation("分析工作站", "equip-23-ws-data.png", "数据库规格：i7 / 64G / 2T SSD×20台｜用途：数据清洗和可视化")
    draw_switch()
    draw_virt_server()
    draw_server_generic("容器集群节点", "equip-26-k8s.png", "数据库规格：32核 / 128G内存×10台｜用途：运行Kubernetes教学集群", accent="#0b8043")
    draw_nas()
    draw_console()
    draw_workstation("开发主机", "equip-29-ws-dev.png", "数据库规格：i7 / 32G / 1T SSD×40台｜用途：项目开发和课程实践")
    draw_code_server()
    draw_projector("投影仪", "equip-31-projector.png", "数据库规格：1080P激光投影×2台｜所属：软件工程实验室")
    draw_phones()
    draw_workstation("图形工作站", "equip-33-ws-gfx.png", "数据库规格：i9 / 64G / RTX4080×16台｜用途：三维建模和视频渲染")
    draw_pen_display()
    draw_camcorder()
    draw_audio()
    draw_workstation("通用实验工作站", "equip-37-ws-open.png", "数据库规格：i7 / 32G / 1T SSD×30台｜所属：综合开放实验室（实验室关闭期间不可预约）")
    draw_toolkit()
    draw_projector("便携投影仪", "equip-39-mini-projector.png", "数据库规格：1080P×3台｜所属：综合开放实验室（实验室关闭期间不可预约）")
    draw_printer3d()
    # 面板图 + 对错图
    for e in facts_all():
        eid = e["id"]
        draw_panel(eid, e["name"], PANEL_KIND.get(eid, "io_front"))
        gen_dodont(eid, e["name"])


def facts_all():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from facts import EQUIPMENTS
    return EQUIPMENTS


if __name__ == "__main__":
    main()
