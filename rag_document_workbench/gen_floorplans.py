# -*- coding: utf-8 -*-
"""生成10间实验室平面布局与安全疏散图（每间布局按实验室类型单独设计）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from imglib import (F, new_canvas, rrect, dashed_rect, arrow, hatch, north_arrow,
                    legend, title_block, info_card, sign_extinguisher, sign_firstaid,
                    sign_exit, door, window, server_rack, workstation, text_c, save_png)
from facts import LABS, LAB_BY_ID, EQUIP_BY_LAB, LAB_STATUS_TEXT

OUT = "D:/AI/faceprogram/rag_document_workbench/gen_images"
os.makedirs(OUT, exist_ok=True)

W, H = 1720, 1220
RX0, RY0, RX1, RY1 = 70, 120, 1250, 1040   # 房间外墙范围

DARK = "#1a3a6b"
ZONE_F = "#e8f0fe"
ZONE_F2 = "#f1f8e9"
HAZ = "#d93025"


def room(d, label, cap):
    d.rectangle([RX0, RY0, RX1, RY1], outline="#202124", width=6)
    # 外墙双层
    d.rectangle([RX0 - 6, RY0 - 6, RX1 + 6, RY1 + 6], outline="#9aa0a6", width=2)
    text_c(d, ((RX0 + RX1) / 2, RY0 + 26), label, F(24, True), fill=DARK)


def facility_markers(d, exts, aid, power):
    for (x, y) in exts:
        sign_extinguisher(d, (x, y))
    if aid:
        sign_firstaid(d, aid)
    if power:
        x, y = power
        d.polygon([(x, y - 12), (x - 9, y + 8), (x + 9, y + 8)], fill="#f9ab00")
        d.line([(x, y + 8), (x, y + 16)], fill="#f9ab00", width=4)
        text_c(d, (x, y + 30), "总电源/急停", F(14, True), fill="#b06000")


def evac(d, flows, target_xy, target_label="疏散集合点（室外空地）"):
    for pts in flows:
        for i in range(len(pts) - 1):
            arrow(d, pts[i], pts[i + 1], color="#1e8e3e", width=6, head=16)
    x, y = target_xy
    d.rectangle([x - 90, y - 26, x + 90, y + 26], fill="#1e8e3e")
    text_c(d, (x, y), "疏散集合点", F(17, True), fill="white")
    text_c(d, (x, y + 40), "（室外空地）", F(14), fill="#1e8e3e")


def finish(img, lab, note_lines, fname):
    d = ImageDraw.Draw(img)
    # 右侧信息栏
    ix = RX1 + 40
    info_card(d, ix, RY0, 400, [
        f"实验室名称：{lab['name']}",
        f"数据库ID：{lab['id']}",
        f"位置：{lab['location']}",
        f"最大容量：{lab['capacity']} 人",
        f"开放时间：{lab['open_time']}—{lab['close_time']}",
        f"当前状态：{LAB_STATUS_TEXT[lab['status']]}" + ("（设备维护）" if lab["status"] == 0 else ""),
    ], title="基本信息")
    y2 = RY0 + 220
    legend([
        ("rect", "普通工作区"), ("warn", "高风险区域"), ("exit", "出入口/紧急出口"),
        ("ext", "灭火器"), ("aid", "急救箱"), ("power", "总电源/急停"),
        ("arrow", "疏散方向"),
    ], ix, y2, d, dx=200, per_row=2)
    if lab["status"] == 0:
        info_card(d, ix, y2 + 170, 400, [
            "⚠ 本实验室当前处于关闭状态（设备维护），",
            "关闭期间禁止一切预约与进入。",
        ], title="关闭提示")
    y3 = RY1 - 150
    info_card(d, ix, y3, 400, note_lines, title="图面说明")
    north_arrow(d, (ix + 340, RY1 - 260))
    title_block(d, W, H, f"{lab['name']}·平面布局与安全疏散图",
                subtitle=f"{lab['location']}｜比例示意，非施工图",
                meta=f"{ORG}｜{VER}" if False else f"智能实验中心｜2026-10-20｜V1.0")
    save_png(img, f"{OUT}/{fname}")


def main():
    # ---------- 01 人工智能实验室 A101 ----------
    lab = LAB_BY_ID[1]
    img, d = new_canvas(W, H)
    room(d, "人工智能实验室（科技楼A区101）", 40)
    zones = [
        ([RX0 + 30, RY0 + 70, RX0 + 330, RY0 + 400], "GPU训练服务器机柜区", "双RTX4090×2台"),
        ([RX0 + 30, RY0 + 440, RX0 + 330, RY0 + 640], "推理服务器与存储阵列区", "A10×2台｜80TB RAID6×1套"),
        ([RX0 + 380, RY0 + 70, RX1 - 340, RY0 + 560], "AI开发工作站区（12台，4×3排列）", "i9 / 64G / RTX4080"),
        ([RX0 + 380, RY0 + 600, RX1 - 340, RY1 - 80], "研讨与成果展示区", "移动白板＋讨论桌"),
        ([RX1 - 300, RY0 + 70, RX1 - 30, RY1 - 260], "讲台与课程教学区", "教师机＋投影幕"),
    ]
    for box, name, sub in zones:
        rrect(d, box, r=10, fill=ZONE_F, outline=DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    # 工作站阵列
    for r in range(3):
        for c in range(4):
            workstation(d, RX0 + 420 + c * 130, RY0 + 120 + r * 130, 64)
    server_rack(d, RX0 + 60, RY0 + 110, 80, 130, "GPU-1")
    server_rack(d, RX0 + 180, RY0 + 110, 80, 130, "GPU-2")
    server_rack(d, RX0 + 60, RY0 + 490, 80, 110, "推理")
    server_rack(d, RX0 + 180, RY0 + 490, 80, 110, "存储")
    # 门窗
    door(d, ((RX0 + 560, RY1), (RX0 + 660, RY1)), "h")
    text_c(d, (RX0 + 610, RY1 + 24), "主入口", F(16, True))
    window(d, ((RX0, RY0 + 200), (RX0, RY0 + 360)))
    window(d, ((RX0, RY0 + 420), (RX0, RY0 + 580)))
    door(d, ((RX1, RY0 + 620), (RX1, RY0 + 720)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 590), label="紧急出口")
    facility_markers(d, [(RX0 + 344, RY0 + 80), (RX1 - 320, RY1 - 40)], aid=(RX0 + 500, RY0 + 40), power=(RX0 + 380, RY1 - 46))
    evac(d, [
        [(RX0 + 900, RY0 + 620), (RX0 + 900, RY1 - 40), (RX0 + 640, RY1 - 40), (RX0 + 620, RY1 + 6)],
        [(RX1 - 160, RY0 + 760), (RX1 + 6, RY0 + 680)],
    ], (RX0 + 610, RY1 + 120))
    finish(img, lab, [
        "1. GPU机柜区为高压大功率设备区，",
        "    非授权人员禁止开启机柜；",
        "2. 服务器区噪声较大，长时间停留",
        "    建议佩戴听力防护；",
        "3. 疏散时沿绿色箭头从主入口或",
        "    东侧紧急出口撤离至集合点。",
    ], "01-ai-平面布局与安全疏散图.png")

    # ---------- 02 计算机视觉实验室 A203 ----------
    lab = LAB_BY_ID[2]
    img, d = new_canvas(W, H)
    room(d, "计算机视觉实验室（科技楼A区203）", 32)
    zones = [
        ([RX0 + 30, RY0 + 70, RX0 + 430, RY0 + 430], "光学采集台（拍摄区）", "工业相机×6｜深度相机×8"),
        ([RX0 + 30, RY0 + 470, RX0 + 430, RY1 - 80], "补光与背景幕布区", "双色温LED 100W×4套"),
        ([RX0 + 470, RY0 + 70, RX1 - 40, RY0 + 620], "标注工作站区（10台）", "i7 / 32G / 27英寸显示器"),
        ([RX0 + 470, RY0 + 660, RX1 - 340, RY1 - 80], "算法调试区", "视觉算法实验工位"),
        ([RX1 - 300, RY0 + 660, RX1 - 40, RY1 - 80], "标定器材柜", "棋盘格标定板等"),
    ]
    for box, name, sub in zones:
        rrect(d, box, r=10, fill=ZONE_F2 if "光学" in name or "补光" in name else ZONE_F, outline=DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    for c in range(4):
        for r in range(3):
            workstation(d, RX0 + 510 + c * 150, RY0 + 120 + r * 140, 66)
    # 拍摄台
    d.rectangle([RX0 + 90, RY0 + 160, RX0 + 370, RY0 + 330], fill="#fff", outline="#5f6368", width=3)
    text_c(d, (RX0 + 230, RY0 + 240), "光学平台", F(18, True), fill="#5f6368")
    d.rectangle([RX0 + 130, RY0 + 120, RX0 + 180, RY0 + 150], fill="#333")
    text_c(d, (RX0 + 155, RY0 + 105), "相机", F(13))
    hatch(d, [RX0 + 30, RY0 + 500, RX0 + 430, RY0 + 620], color="#f9ab00", spacing=22, width=2)
    text_c(d, (RX0 + 230, RY0 + 560), "强光区：勿直视LED光源", F(16, True), fill="#b06000")
    door(d, ((RX0 + 200, RY1), (RX0 + 300, RY1)), "h")
    text_c(d, (RX0 + 250, RY1 + 24), "主入口", F(16, True))
    window(d, ((RX1, RY0 + 150), (RX1, RY0 + 330)))
    door(d, ((RX1, RY0 + 700), (RX1, RY0 + 800)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 670), label="紧急出口")
    facility_markers(d, [(RX0 + 444, RY0 + 90), (RX0 + 444, RY1 - 50)], aid=(RX0 + 460, RY0 + 640), power=(RX0 + 350, RY1 - 46))
    evac(d, [
        [(RX0 + 900, RY0 + 660), (RX0 + 900, RY1 - 44), (RX0 + 280, RY1 - 44), (RX0 + 260, RY1 + 6)],
        [(RX1 - 180, RY0 + 740), (RX1 + 6, RY0 + 760)],
    ], (RX0 + 250, RY1 + 120))
    finish(img, lab, [
        "1. 拍摄期间补光灯亮度较高，请勿",
        "    长时间直视光源；",
        "2. 相机器材轻拿轻放，用毕归柜；",
        "3. 涉及人像采集须先取得被摄者同意。",
    ], "02-cv-平面布局与安全疏散图.png")

    # ---------- 03 机器人创新实验室 B105 ----------
    lab = LAB_BY_ID[3]
    img, d = new_canvas(W, H)
    room(d, "机器人创新实验室（工程训练中心B区105）", 39)
    zones = [
        ([RX0 + 30, RY0 + 70, RX0 + 400, RY0 + 430], "机械臂工作区（安全围栏内）", "六轴机械臂 负载5kg×2台"),
        ([RX0 + 30, RY0 + 470, RX0 + 400, RY1 - 80], "移动机器人测试跑道", "差速底盘×4｜避障实验"),
        ([RX0 + 440, RY0 + 70, RX1 - 40, RY0 + 400], "感知传感器标定区", "Livox Mid-360×5"),
        ([RX0 + 440, RY0 + 440, RX1 - 40, RY0 + 720], "边缘计算开发工位", "Jetson Orin 32G×6"),
        ([RX0 + 440, RY0 + 760, RX1 - 300, RY1 - 80], "组装调试工作台", "工具与备件区"),
        ([RX1 - 260, RY0 + 760, RX1 - 40, RY1 - 80], "充电与电池柜", "动力锂电池专用"),
    ]
    for box, name, sub in zones:
        hz = "机械臂" in name or "充电" in name
        rrect(d, box, r=10, fill="#fce8e6" if hz else (ZONE_F2 if "跑道" in name else ZONE_F), outline=HAZ if hz else DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=HAZ if hz else DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    # 围栏
    dashed_rect(d, [RX0 + 50, RY0 + 100, RX0 + 380, RY0 + 410], color=HAZ, width=3, dash=14, gap=6)
    text_c(d, (RX0 + 215, RY0 + 250), "安全围栏", F(17, True), fill=HAZ)
    # 机械臂
    for i, bx in enumerate((RX0 + 120, RX0 + 260)):
        d.ellipse([bx - 30, RY0 + 300, bx + 30, RY0 + 360], fill="#5f6368")
        d.line([(bx, RY0 + 330), (bx + 50, RY0 + 220)], fill="#f9ab00", width=14)
        d.line([(bx + 50, RY0 + 220), (bx + 110, RY0 + 260)], fill="#f9ab00", width=10)
        text_c(d, (bx, RY0 + 380), f"机械臂-{i+1}", F(14, True))
    # 跑道
    d.rounded_rectangle([RX0 + 60, RY0 + 540, RX0 + 370, RY0 + 680], radius=60, outline="#1a73e8", width=5)
    text_c(d, (RX0 + 215, RY0 + 610), "导航测试环线", F(16), fill="#1a73e8")
    # 充电柜高风险
    hatch(d, [RX1 - 260, RY0 + 760, RX1 - 40, RY1 - 80], color=HAZ, spacing=18, width=2)
    text_c(d, (RX1 - 150, RY0 + 900), "锂电池安全区", F(15, True), fill=HAZ)
    door(d, ((RX0 + 500, RY1), (RX0 + 600, RY1)), "h")
    text_c(d, (RX0 + 550, RY1 + 24), "主入口", F(16, True))
    door(d, ((RX1, RY0 + 150), (RX1, RY0 + 250)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 120), label="紧急出口")
    facility_markers(d, [(RX0 + 414, RY0 + 90), (RX0 + 414, RY1 - 50), (RX1 - 276, RY0 + 90)],
                     aid=(RX0 + 420, RY0 + 740), power=(RX0 + 60, RY1 - 46))
    # 急停按钮
    d.ellipse([RX0 + 70, RY0 + 435, RX0 + 110, RY0 + 475], fill=HAZ, outline="black", width=3)
    text_c(d, (RX0 + 125, RY0 + 455), "机械臂急停", F(14, True), fill=HAZ, anchor="lm")
    evac(d, [
        [(RX0 + 900, RY0 + 760), (RX0 + 900, RY1 - 44), (RX0 + 580, RY1 - 44), (RX0 + 560, RY1 + 6)],
        [(RX1 - 140, RY0 + 300), (RX1 + 6, RY0 + 210)],
    ], (RX0 + 560, RY1 + 120))
    finish(img, lab, [
        "1. 机械臂运行时任何人不得进入围栏，",
        "    急停按钮位于围栏外侧立柱；",
        "2. 移动机器人测试期间注意避让，",
        "    不得在跑道内放置个人物品；",
        "3. 电池充电须在专用充电柜进行。",
    ], "03-robot-平面布局与安全疏散图.png")

    # ---------- 04 物联网实验室 C302 ----------
    lab = LAB_BY_ID[4]
    img, d = new_canvas(W, H)
    room(d, "物联网实验室（信息楼C区302）", 36)
    zones = [
        ([RX0 + 30, RY0 + 70, RX1 - 300, RY0 + 560], "嵌入式开发工位区（20套件）", "ESP32多传感器套件｜每工位配防静电垫"),
        ([RX0 + 30, RY0 + 600, RX0 + 560, RY1 - 80], "仪器测量区", "示波器×8｜可编程电源×10"),
        ([RX1 - 260, RY0 + 70, RX1 - 30, RY0 + 560], "LoRa网关与天线区", "8通道LoRaWAN×3"),
        ([RX0 + 600, RY0 + 600, RX1 - 300, RY1 - 80], "器件与耗材柜", "传感器备件／杜邦线"),
    ]
    for box, name, sub in zones:
        hz = "仪器" in name
        rrect(d, box, r=10, fill=ZONE_F2 if hz else ZONE_F, outline=DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    for r in range(3):
        for c in range(5):
            workstation(d, RX0 + 70 + c * 150, RY0 + 120 + r * 130, 62)
    # 示波器
    for c in range(4):
        bx = RX0 + 80 + c * 120
        rrect(d, [bx, RY0 + 660, bx + 90, RY0 + 740], r=6, fill="#e6f4ea", outline="#137333", width=3)
        d.rectangle([bx + 10, RY0 + 670, bx + 80, RY0 + 700], fill="#137333")
        text_c(d, (bx + 45, RY0 + 756), "示波器", F(13))
    for c in range(4):
        bx = RX0 + 80 + c * 120
        rrect(d, [bx, RY0 + 810, bx + 90, RY0 + 880], r=6, fill="#fef7e0", outline="#b06000", width=3)
        d.ellipse([bx + 30, RY0 + 825, bx + 60, RY0 + 855], outline="#b06000", width=3)
        text_c(d, (bx + 45, RY0 + 896), "可编程电源", F(13))
    # 天线
    for i, ax in enumerate((RX1 - 200, RX1 - 140)):
        d.line([(ax, RY0 + 300), (ax, RY0 + 200)], fill="#137333", width=4)
        d.line([(ax - 20, RY0 + 220), (ax + 20, RY0 + 200)], fill="#137333", width=4)
    text_c(d, (RX1 - 170, RY0 + 340), "网关天线（靠窗）", F(14))
    door(d, ((RX0 + 660, RY1), (RX0 + 760, RY1)), "h")
    text_c(d, (RX0 + 710, RY1 + 24), "主入口", F(16, True))
    window(d, ((RX1, RY0 + 120), (RX1, RY0 + 300)))
    door(d, ((RX1, RY0 + 620), (RX1, RY0 + 720)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 590), label="紧急出口")
    facility_markers(d, [(RX0 + 540, RY0 + 620), (RX1 - 280, RY1 - 46)], aid=(RX0 + 590, RY0 + 90), power=(RX0 + 60, RY1 - 46))
    hatch(d, [RX0 + 30, RY0 + 600, RX0 + 560, RY1 - 80], color="#f9ab00", spacing=40, width=1)
    evac(d, [
        [(RX0 + 1000, RY0 + 600), (RX0 + 1000, RY1 - 44), (RX0 + 740, RY1 - 44), (RX0 + 720, RY1 + 6)],
        [(RX1 - 160, RY0 + 680), (RX1 + 6, RY0 + 690)],
    ], (RX0 + 720, RY1 + 120))
    finish(img, lab, [
        "1. 测量区为用电安全重点区：接线先",
        "    断电，电源限压限流后再上电；",
        "2. 电烙铁使用后必须归位断电；",
        "3. 网关天线勿私自拆卸或外接功放。",
    ], "04-iot-平面布局与安全疏散图.png")

    # ---------- 05 网络安全实验室 C406 ----------
    lab = LAB_BY_ID[5]
    img, d = new_canvas(W, H)
    room(d, "网络安全实验室（信息楼C区406）", 30)
    zones = [
        ([RX0 + 30, RY0 + 70, RX0 + 420, RY0 + 470], "攻防靶机服务器机柜区（隔离网段）", "32核/256G×3台"),
        ([RX0 + 30, RY0 + 510, RX0 + 420, RY1 - 80], "防火墙与流量分析配线区", "防火墙×4｜流量分析仪×2"),
        ([RX0 + 460, RY0 + 70, RX1 - 40, RY0 + 640], "安全审计工作站区（12台）", "i7 / 32G / 2T SSD"),
        ([RX0 + 460, RY0 + 680, RX1 - 40, RY1 - 80], "红蓝对抗演练区", "内网隔离，物理断外网"),
    ]
    for box, name, sub in zones:
        hz = "靶机" in name or "配线" in name
        rrect(d, box, r=10, fill="#fce8e6" if hz else ZONE_F, outline=HAZ if hz else DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=HAZ if hz else DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    server_rack(d, RX0 + 70, RY0 + 120, 80, 150, "靶机-1")
    server_rack(d, RX0 + 190, RY0 + 120, 80, 150, "靶机-2")
    server_rack(d, RX0 + 310, RY0 + 120, 80, 150, "靶机-3")
    server_rack(d, RX0 + 70, RY0 + 570, 80, 130, "防火墙")
    server_rack(d, RX0 + 190, RY0 + 570, 80, 130, "流量分析")
    # 隔离边界
    dashed_rect(d, [RX0 + 20, RY0 + 60, RX0 + 430, RY1 - 70], color=HAZ, width=3, dash=16, gap=8)
    text_c(d, (RX0 + 225, RY1 - 95), "—— 隔离网络边界（禁止接入校园网/互联网）——", F(16, True), fill=HAZ)
    for r in range(3):
        for c in range(4):
            workstation(d, RX0 + 500 + c * 150, RY0 + 130 + r * 140, 64)
    door(d, ((RX0 + 700, RY1), (RX0 + 800, RY1)), "h")
    text_c(d, (RX0 + 750, RY1 + 24), "主入口", F(16, True))
    door(d, ((RX1, RY0 + 180), (RX1, RY0 + 280)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 150), label="紧急出口")
    facility_markers(d, [(RX0 + 440, RY0 + 90), (RX1 - 60, RY1 - 46)], aid=(RX0 + 450, RY0 + 660), power=(RX0 + 60, RY1 - 46))
    evac(d, [
        [(RX0 + 900, RY0 + 680), (RX0 + 900, RY1 - 44), (RX0 + 780, RY1 - 44), (RX0 + 760, RY1 + 6)],
        [(RX1 - 140, RY0 + 240), (RX1 + 6, RY0 + 240)],
    ], (RX0 + 760, RY1 + 120))
    finish(img, lab, [
        "1. 本实验室为物理隔离网络环境，",
        "    严禁携带私接设备跨网连接；",
        "2. 所有攻防实验只能在隔离网段内",
        "    进行，须事先取得实验授权；",
        "3. 配线区线缆不得随意插拔。",
    ], "05-security-平面布局与安全疏散图.png")

    # ---------- 06 大数据分析实验室 D201 ----------
    lab = LAB_BY_ID[6]
    img, d = new_canvas(W, H)
    room(d, "大数据分析实验室（数据中心D区201）", 45)
    zones = [
        ([RX0 + 30, RY0 + 70, RX0 + 430, RY0 + 560], "数据计算节点机柜区", "32核/128G×8台"),
        ([RX0 + 30, RY0 + 600, RX0 + 430, RY1 - 80], "数据存储节点机柜区", "100TB×4台"),
        ([RX0 + 470, RY0 + 70, RX1 - 40, RY0 + 700], "分析工作站区（20台）", "i7 / 64G / 2T SSD"),
        ([RX0 + 470, RY0 + 740, RX1 - 300, RY1 - 80], "可视化大屏与研讨区", "数据看板演示"),
        ([RX1 - 260, RY0 + 740, RX1 - 40, RY1 - 80], "万兆交换机配线架", "24口10GbE×2"),
    ]
    for box, name, sub in zones:
        hz = "机柜" in name or "配线" in name
        rrect(d, box, r=10, fill=ZONE_F2 if hz else ZONE_F, outline=DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    for i in range(4):
        server_rack(d, RX0 + 60 + i * 95, RY0 + 120, 70, 140, f"计算{i+1}")
    for i in range(4):
        server_rack(d, RX0 + 60 + i * 95, RY0 + 650, 70, 140, f"存储{i+1}")
    for r in range(4):
        for c in range(5):
            workstation(d, RX0 + 510 + c * 140, RY0 + 120 + r * 130, 60)
    door(d, ((RX0 + 760, RY1), (RX0 + 860, RY1)), "h")
    text_c(d, (RX0 + 810, RY1 + 24), "主入口", F(16, True))
    door(d, ((RX1, RY0 + 250), (RX1, RY0 + 350)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 220), label="紧急出口")
    facility_markers(d, [(RX0 + 446, RY0 + 90), (RX0 + 446, RY1 - 50)], aid=(RX0 + 480, RY0 + 730), power=(RX0 + 60, RY1 - 46))
    evac(d, [
        [(RX0 + 1000, RY0 + 740), (RX0 + 1000, RY1 - 44), (RX0 + 840, RY1 - 44), (RX0 + 820, RY1 + 6)],
        [(RX1 - 160, RY0 + 310), (RX1 + 6, RY0 + 310)],
    ], (RX0 + 820, RY1 + 120))
    finish(img, lab, [
        "1. 机柜区噪声与散热风量较大，", "    请勿长时间停留、勿遮挡通风；",
        "2. 数据集存放于存储节点，本地", "    不落地保存涉敏数据。",
    ], "06-bigdata-平面布局与安全疏散图.png")

    # ---------- 07 云计算实验室 D305 ----------
    lab = LAB_BY_ID[7]
    img, d = new_canvas(W, H)
    room(d, "云计算实验室（数据中心D区305）", 38)
    zones = [
        ([RX0 + 30, RY0 + 70, RX0 + 430, RY0 + 560], "虚拟化服务器机柜区", "双路CPU/512G×6台"),
        ([RX0 + 30, RY0 + 600, RX0 + 430, RY1 - 80], "容器集群节点机柜区", "32核/128G×10台"),
        ([RX0 + 470, RY0 + 70, RX0 + 830, RY0 + 470], "共享存储NAS区", "60TB NAS×2"),
        ([RX0 + 470, RY0 + 510, RX1 - 40, RY0 + 900], "管理控制台区（4台，双显示器）", "云平台与监控管理"),
        ([RX0 + 870, RY0 + 70, RX1 - 40, RY0 + 470], "K8s教学演示区", "集群拓扑白板"),
    ]
    for box, name, sub in zones:
        hz = "机柜" in name
        rrect(d, box, r=10, fill=ZONE_F2 if hz else ZONE_F, outline=DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    for i in range(3):
        server_rack(d, RX0 + 70 + i * 110, RY0 + 120, 85, 150, f"虚化{i+1}")
    for i in range(3):
        server_rack(d, RX0 + 70 + i * 110, RY0 + 650, 85, 150, f"容器{i+1}")
    for i in range(2):
        server_rack(d, RX0 + 520 + i * 120, RY0 + 140, 90, 130, f"NAS-{i+1}")
    for r in range(2):
        for c in range(2):
            workstation(d, RX0 + 560 + c * 170, RY0 + 580 + r * 150, 70, dual=True)
    door(d, ((RX0 + 460, RY1), (RX0 + 560, RY1)), "h")
    text_c(d, (RX0 + 510, RY1 + 24), "主入口", F(16, True))
    door(d, ((RX1, RY0 + 200), (RX1, RY0 + 300)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 170), label="紧急出口")
    facility_markers(d, [(RX0 + 446, RY0 + 90), (RX0 + 446, RY1 - 50)], aid=(RX0 + 490, RY0 + 500), power=(RX0 + 60, RY1 - 46))
    evac(d, [
        [(RX0 + 700, RY0 + 920), (RX0 + 700, RY1 - 44), (RX0 + 540, RY1 - 44), (RX0 + 520, RY1 + 6)],
        [(RX1 - 140, RY0 + 260), (RX1 + 6, RY0 + 260)],
    ], (RX0 + 520, RY1 + 120))
    finish(img, lab, [
        "1. 集群节点禁止物理断电重启，", "    异常须报值班管理员处理；",
        "2. NAS存储设备禁止随意拔插硬盘。",
    ], "07-cloud-平面布局与安全疏散图.png")

    # ---------- 11 软件工程实验室 E204 ----------
    lab = LAB_BY_ID[11]
    img, d = new_canvas(W, H)
    room(d, "软件工程实验室（教学楼E区204）", 50)
    zones = [
        ([RX0 + 30, RY0 + 70, RX1 - 300, RY1 - 200], "开发主机工位区（40台，5×8排列）", "i7 / 32G / 1T SSD｜小组岛式布局"),
        ([RX1 - 260, RY0 + 70, RX1 - 30, RY0 + 470], "讲台与投影幕区", "1080P激光投影×2"),
        ([RX1 - 260, RY0 + 510, RX1 - 30, RY1 - 200], "设备机柜与充电柜", "代码服务器×2｜测试终端×12"),
    ]
    for box, name, sub in zones:
        rrect(d, box, r=10, fill=ZONE_F, outline=DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    for r in range(4):
        for c in range(5):
            workstation(d, RX0 + 90 + c * 160, RY0 + 130 + r * 150, 64)
    text_c(d, (RX1 - 145, RY0 + 300), "投影幕", F(16), fill=DARK)
    server_rack(d, RX1 - 230, RY0 + 550, 70, 120, "代码 srv")
    for i in range(3):
        rrect(d, [RX1 - 130 + i * 34, RY0 + 560, RX1 - 106 + i * 34, RY0 + 650], r=4, fill="#e8f0fe", outline=DARK, width=2)
    text_c(d, (RX1 - 90, RY0 + 668), "终端充电柜", F(13))
    door(d, ((RX0 + 800, RY1), (RX0 + 900, RY1)), "h")
    text_c(d, (RX0 + 850, RY1 + 24), "主入口", F(16, True))
    window(d, ((RX0, RY0 + 150), (RX0, RY0 + 700)))
    door(d, ((RX1, RY0 + 560), (RX1, RY0 + 660)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 530), label="紧急出口")
    facility_markers(d, [(RX0 + 44, RY0 + 90), (RX0 + 44, RY1 - 220)], aid=(RX0 + 60, RY0 + 60), power=(RX1 - 290, RY0 + 60))
    evac(d, [
        [(RX0 + 850, RY1 - 210), (RX0 + 850, RY1 - 44), (RX0 + 890, RY1 - 44), (RX0 + 880, RY1 + 6)],
        [(RX1 - 140, RY0 + 610), (RX1 + 6, RY0 + 620)],
    ], (RX0 + 880, RY1 + 120))
    finish(img, lab, [
        "1. 工位电源禁止串接大功率电器；",
        "2. 测试终端用毕放回充电柜并登记。",
    ], "11-software-平面布局与安全疏散图.png")

    # ---------- 12 数字媒体实验室 F108 ----------
    lab = LAB_BY_ID[12]
    img, d = new_canvas(W, H)
    room(d, "数字媒体实验室（艺术楼F区108）", 26)
    zones = [
        ([RX0 + 30, RY0 + 70, RX0 + 830, RY0 + 620], "图形工作站与数位屏工位区", "图形工作站×16｜22英寸数位屏×12"),
        ([RX0 + 30, RY0 + 660, RX0 + 500, RY1 - 80], "录音棚（隔音）", "电容麦克风/声卡×6套"),
        ([RX0 + 540, RY0 + 660, RX1 - 40, RY1 - 80], "摄影棚（绿幕＋灯位）", "4K摄像机×4"),
        ([RX0 + 870, RY0 + 70, RX1 - 40, RY0 + 620], "器材间与审核室", "存储卡／灯架／三脚架"),
    ]
    for box, name, sub in zones:
        hz = "摄影棚" in name
        rrect(d, box, r=10, fill=ZONE_F2 if "录音" in name else ZONE_F, outline=DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    for r in range(3):
        for c in range(4):
            workstation(d, RX0 + 80 + c * 180, RY0 + 120 + r * 150, 68)
    # 绿幕
    d.rectangle([RX0 + 700, RY0 + 700, RX0 + 1150, RY0 + 900], fill="#ceead6", outline="#137333", width=3)
    text_c(d, (RX0 + 925, RY0 + 800), "绿幕拍摄区", F(18, True), fill="#137333")
    # 隔音
    hatch(d, [RX0 + 30, RY0 + 660, RX0 + 500, RY1 - 80], color="#137333", spacing=30, width=1)
    text_c(d, (RX0 + 265, RY0 + 830), "隔音墙体", F(15), fill="#137333")
    door(d, ((RX0 + 900, RY1), (RX0 + 1000, RY1)), "h")
    text_c(d, (RX0 + 950, RY1 + 24), "主入口", F(16, True))
    door(d, ((RX0 + 250, RY1), (RX0 + 350, RY1)), "h")
    sign_exit(d, (RX0 + 300, RY1 + 24), label="录音棚疏散门")
    window(d, ((RX1, RY0 + 150), (RX1, RY0 + 400)))
    facility_markers(d, [(RX0 + 850, RY0 + 690), (RX0 + 520, RY1 - 50)], aid=(RX0 + 850, RY0 + 90), power=(RX0 + 560, RY0 + 90))
    evac(d, [
        [(RX0 + 400, RY0 + 640), (RX0 + 400, RY1 - 44), (RX0 + 330, RY1 - 44), (RX0 + 320, RY1 + 6)],
        [(RX0 + 950, RY1 - 90), (RX0 + 960, RY1 + 6)],
    ], (RX0 + 620, RY1 + 120))
    finish(img, lab, [
        "1. 摄影棚灯架需配重固定，防止倾倒；",
        "2. 录音期间请勿敲门，手机静音；",
        "3. 涉及人像/声音采集须签署授权书。",
    ], "12-media-平面布局与安全疏散图.png")

    # ---------- 13 综合开放实验室 G区一层（关闭） ----------
    lab = LAB_BY_ID[13]
    img, d = new_canvas(W, H)
    room(d, "综合开放实验室（创新中心G区一层）——当前关闭", 60)
    zones = [
        ([RX0 + 30, RY0 + 70, RX0 + 800, RY0 + 560], "通用实验工作站区（30台）", "i7 / 32G / 1T SSD｜开放工位"),
        ([RX0 + 30, RY0 + 600, RX0 + 430, RY1 - 80], "电子制作区（高风险）", "焊台/万用表/工具组×15套"),
        ([RX0 + 470, RY0 + 600, RX0 + 800, RY1 - 80], "3D打印区（设备维修中）", "FDM 300mm×2台"),
        ([RX0 + 840, RY0 + 70, RX1 - 40, RY0 + 560], "小组讨论与展示区", "便携投影仪×3"),
        ([RX0 + 840, RY0 + 600, RX1 - 40, RY1 - 80], "器材寄存柜", "个人物品与器材"),
    ]
    for box, name, sub in zones:
        hz = "电子制作" in name or "3D打印" in name
        rrect(d, box, r=10, fill="#fce8e6" if hz else ZONE_F, outline=HAZ if hz else DARK, width=3)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 24), name, F(19, True), fill=HAZ if hz else DARK)
        text_c(d, ((box[0] + box[2]) / 2, box[1] + 50), sub, F(15), fill="#444")
    for r in range(3):
        for c in range(5):
            workstation(d, RX0 + 70 + c * 140, RY0 + 120 + r * 130, 60)
    hatch(d, [RX0 + 470, RY0 + 600, RX0 + 800, RY1 - 80], color="#9aa0a6", spacing=20, width=2)
    text_c(d, (RX0 + 635, RY0 + 800), "设备维修中·停用", F(18, True), fill="#5f6368")
    # 整体关闭
    hatch(d, [RX0 + 8, RY0 + 8, RX1 - 8, RY1 - 8], color="#9aa0a6", spacing=60, width=1)
    door(d, ((RX0 + 700, RY1), (RX0 + 800, RY1)), "h")
    text_c(d, (RX0 + 750, RY1 + 24), "主入口（关闭期间封闭）", F(16, True))
    door(d, ((RX1, RY0 + 300), (RX1, RY0 + 400)), "v")
    sign_exit(d, (RX1 - 46, RY0 + 270), label="紧急出口")
    facility_markers(d, [(RX0 + 446, RY0 + 620), (RX1 - 60, RY1 - 46)], aid=(RX0 + 450, RY0 + 80), power=(RX0 + 60, RY1 - 46))
    evac(d, [
        [(RX0 + 400, RY0 + 580), (RX0 + 400, RY1 - 44), (RX0 + 760, RY1 - 44), (RX0 + 770, RY1 + 6)],
    ], (RX0 + 770, RY1 + 120))
    finish(img, lab, [
        "1. 本实验室因设备维护整体关闭，",
        "    关闭期间所有区域禁止进入；",
        "2. 即使部分设备状态为正常，",
        "    也不能预约或使用；",
        "3. 3D打印机维修期间禁止通电。",
    ], "13-open-平面布局与安全疏散图.png")


if __name__ == "__main__":
    main()
