# -*- coding: utf-8 -*-
"""生成18份业务Excel（openpyxl）。基础事实与数据库一致，人名电话邮箱均为虚构。"""
import os
import random
import sys
from datetime import date, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from facts import (EQUIPMENTS, LABS, LAB_BY_ID, EQUIP_BY_LAB, LAB_STATUS_TEXT,
                   EQUIP_STATUS_TEXT, DOC_DATE)

OUT = "D:/AI/faceprogram/rag_source_documents/06-业务表格"
IMG = "D:/AI/faceprogram/rag_document_workbench/gen_images"
PHOTOS = "D:/AI/faceprogram/rag_document_workbench/photos"
os.makedirs(OUT, exist_ok=True)

HEAD_FILL = PatternFill("solid", fgColor="1A3A6B")
HEAD_FONT = Font(name="微软雅黑", size=10.5, bold=True, color="FFFFFF")
BODY_FONT = Font(name="微软雅黑", size=10)
THIN = Side(style="thin", color="B0BEC5")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

# 明确虚构的人员信息（用于示例记录）
FAKE_PEOPLE = [
    ("张明宇", "13800001001", "zhangmy101@example.edu.cn"),
    ("李思齐", "13800001002", "lisq102@example.edu.cn"),
    ("王雨桐", "13800001003", "wangyt103@example.edu.cn"),
    ("陈嘉树", "13800001004", "chenjs104@example.edu.cn"),
    ("刘一诺", "13800001005", "liuyn105@example.edu.cn"),
    ("赵文昊", "13800001006", "zhaowh106@example.edu.cn"),
    ("孙晓萌", "13800001007", "sunxm107@example.edu.cn"),
    ("周子墨", "13800001008", "zhouzm108@example.edu.cn"),
    ("吴佳琪", "13800001009", "wujq109@example.edu.cn"),
    ("郑浩然", "13800001010", "zhenghr110@example.edu.cn"),
]


def style_header(ws, row=1, ncols=None):
    ncols = ncols or ws.max_column
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = CENTER
        cell.border = BORDER
    ws.row_dimensions[row].height = 22


def style_body(ws, first_row=2, max_row=None, max_col=None):
    max_row = max_row or ws.max_row
    max_col = max_col or ws.max_column
    for r in range(first_row, max_row + 1):
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = BODY_FONT
            cell.border = BORDER
            if cell.alignment.horizontal != "center":
                cell.alignment = LEFT


def set_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def add_dv(ws, options, col_letter, first, last, title="选择项"):
    dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"',
                        allow_blank=True, showDropDown=False)
    dv.error = "请从下拉列表中选择"
    ws.add_data_validation(dv)
    dv.add(f"{col_letter}{first}:{col_letter}{last}")


def new_book(sheet_name, headers, widths):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers)
    style_header(ws)
    set_widths(ws, widths)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    return wb, ws


def note_sheet(wb, lines, title="填表说明"):
    ws = wb.create_sheet(title)
    ws.column_dimensions["A"].width = 100
    ws.append(["说明"])
    style_header(ws)
    for ln in lines:
        ws.append([ln])
    style_body(ws)
    return ws


def lab_rows():
    return [[l["id"], l["name"], l["location"], l["capacity"],
             l["open_time"], l["close_time"], LAB_STATUS_TEXT[l["status"]],
             l["description"]] for l in LABS]


def equipment_rows():
    return [[e["id"], LAB_BY_ID[e["lab_id"]]["name"], e["name"], e["spec"],
             e["quantity"], EQUIP_STATUS_TEXT[e["status"]], e["desc"]]
            for e in EQUIPMENTS]


def save(wb, name):
    path = f"{OUT}/{name}.xlsx"
    wb.save(path)
    print("saved", path)


def embed_photo(ws, img_path, anchor, width_cm=6.0):
    img = XLImage(img_path)
    scale = width_cm / 2.54 * 96 / img.width
    img.width = int(img.width * scale)
    img.height = int(img.height * scale)
    ws.add_image(img, anchor)


# ---------------- 1 实验室基础信息总表 ----------------
def b01():
    wb, ws = new_book("实验室基础信息", ["实验室ID", "实验室名称", "位置", "容量(人)",
                                     "开放开始", "开放结束", "当前状态", "简介"],
                  [10, 18, 18, 10, 10, 10, 10, 60])
    for row in lab_rows():
        ws.append(row)
    style_body(ws)
    for r in range(2, 12):
        ws.cell(row=r, column=5).number_format = "hh:mm"
        ws.cell(row=r, column=6).number_format = "hh:mm"
    add_dv(ws, ["开放", "关闭"], "G", 2, 12)
    note_sheet(wb, [
        "数据来源：2026-10-20开发数据库labs表只读查询，与系统显示完全一致。",
        "机器人创新实验室容量为39人（数据库当前值，旧seed脚本中的28已废弃）。",
        "综合开放实验室当前状态为关闭（设备维护），关闭期间不可预约。",
        "本表人员信息为空；如后续登记管理员，请使用真实在编人员并经本人同意。",
    ])
    save(wb, "01-实验室基础信息总表")


# ---------------- 2 实验室开放时间表 ----------------
def b02():
    wb, ws = new_book("开放时间", ["实验室名称", "位置", "开放开始", "开放结束", "日开放时长(小时)", "当前状态"],
                  [18, 18, 10, 10, 16, 10])
    for l in LABS:
        oh = (int(l["close_time"][:2]) * 60 + int(l["close_time"][3:])
              - int(l["open_time"][:2]) * 60 - int(l["open_time"][3:])) / 60
        ws.append([l["name"], l["location"], l["open_time"], l["close_time"], oh,
                   LAB_STATUS_TEXT[l["status"]]])
    style_body(ws)
    for r in range(2, 12):
        ws.cell(row=r, column=3).number_format = "hh:mm"
        ws.cell(row=r, column=4).number_format = "hh:mm"
        ws.cell(row=r, column=5).number_format = "0.0"
    add_dv(ws, ["开放", "关闭"], "F", 2, 12)
    note_sheet(wb, ["开放时间为中国北京时间（UTC+8）；预约时段必须位于对应实验室开放时间内。",
                    "综合开放实验室当前关闭，恢复时间以后勤与设备部门联合通知为准。"])
    save(wb, "02-实验室开放时间表")


# ---------------- 3 实验室容量与状态表 ----------------
def b03():
    wb, ws = new_book("容量与状态", ["实验室名称", "容量(人)", "状态", "状态说明"],
                  [18, 10, 10, 46])
    for l in LABS:
        ws.append([l["name"], l["capacity"], LAB_STATUS_TEXT[l["status"]],
                   "设备维护，整室关闭" if l["status"] == 0 else "正常开放"])
    style_body(ws)
    add_dv(ws, ["开放", "关闭"], "C", 2, 12)
    chart = BarChart()
    chart.title = "各实验室容量对比"
    chart.y_axis.title = "容量(人)"
    data = Reference(ws, min_col=2, min_row=1, max_row=11)
    cats = Reference(ws, min_col=1, min_row=2, max_row=11)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.width, chart.height = 22, 10
    ws.add_chart(chart, "F2")
    save(wb, "03-实验室容量与状态表")


# ---------------- 4 设备资产总表 ----------------
def b04():
    wb, ws = new_book("设备资产", ["设备ID", "所属实验室", "设备名称", "规格", "数量", "状态", "用途说明"],
                  [9, 18, 18, 26, 8, 10, 40])
    for row in equipment_rows():
        ws.append(row)
    style_body(ws)
    add_dv(ws, ["正常", "维修中"], "F", 2, 42)
    note_sheet(wb, [
        "40类设备与数据库equipments表一致；状态：正常=1，维修中=0。",
        "当前维修中设备：3D打印机（ID 40，综合开放实验室）。",
        "维修中设备不可预约；所属实验室关闭期间，即使设备正常也不可预约。",
    ])
    save(wb, "04-设备资产总表")


# ---------------- 5 实验室与设备对应关系表 ----------------
def b05():
    wb, ws = new_book("对应关系", ["实验室ID", "实验室名称", "设备ID", "设备名称", "规格", "数量", "状态"],
                  [9, 18, 9, 18, 26, 8, 10])
    for e in EQUIPMENTS:
        l = LAB_BY_ID[e["lab_id"]]
        ws.append([l["id"], l["name"], e["id"], e["name"], e["spec"], e["quantity"],
                   EQUIP_STATUS_TEXT[e["status"]]])
    style_body(ws)
    add_dv(ws, ["正常", "维修中"], "G", 2, 42)
    # 统计sheet
    ws2 = wb.create_sheet("各室设备统计")
    ws2.append(["实验室名称", "设备种类数", "设备总数量"])
    style_header(ws2)
    for l in LABS:
        eqs = EQUIP_BY_LAB.get(l["id"], [])
        ws2.append([l["name"], len(eqs), sum(e["quantity"] for e in eqs)])
    style_body(ws2)
    chart = PieChart()
    chart.title = "各实验室设备数量占比"
    data = Reference(ws2, min_col=3, min_row=1, max_row=11)
    cats = Reference(ws2, min_col=1, min_row=2, max_row=11)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.width, chart.height = 16, 9
    ws2.add_chart(chart, "F2")
    save(wb, "05-实验室与设备对应关系表")


# ---------------- 6 设备维护计划 ----------------
def b06():
    wb, ws = new_book("维护计划", ["计划编号", "设备名称", "所属实验室", "维护类型", "计划周期",
                               "下次执行日期", "责任人(虚构)", "备注"],
                  [12, 18, 18, 14, 14, 13, 12, 34])
    plans = [
        ("WM-2026-001", "GPU训练服务器", "人工智能实验室", "深度保养", "每季度", date(2026, 12, 15), "张明宇", "清灰、风扇与驱动检查"),
        ("WM-2026-002", "高速存储阵列", "人工智能实验室", "健康巡检", "每月", date(2026, 11, 5), "张明宇", "RAID健康与坏盘预警"),
        ("WM-2026-003", "六轴机械臂", "机器人创新实验室", "精度标定", "每半年", date(2027, 4, 20), "李思齐", "厂商协同标定润滑"),
        ("WM-2026-004", "移动机器人底盘", "机器人创新实验室", "常规保养", "每月", date(2026, 11, 10), "李思齐", "轮胎轴承电池检查"),
        ("WM-2026-005", "示波器", "物联网实验室", "计量校准", "每年", date(2027, 3, 1), "陈嘉树", "外送校准"),
        ("WM-2026-006", "可编程电源", "物联网实验室", "精度校验", "每年", date(2027, 3, 1), "陈嘉树", "标准表比对"),
        ("WM-2026-007", "硬件防火墙", "网络安全实验室", "固件评估", "每季度", date(2026, 12, 20), "刘一诺", "备份配置后升级"),
        ("WM-2026-008", "数据计算节点", "大数据分析实验室", "健康巡检", "每季度", date(2026, 12, 25), "赵文昊", "集群健康与补丁"),
        ("WM-2026-009", "共享存储设备", "云计算实验室", "滤网更换", "每半年", date(2027, 4, 10), "孙晓萌", "风扇滤网除尘"),
        ("WM-2026-010", "3D打印机", "综合开放实验室", "返厂维修", "一次性", date(2026, 10, 18), "周子墨", "当前维修中，验收后恢复"),
        ("WM-2026-011", "投影仪", "软件工程实验室", "滤网清洁", "每学期", date(2027, 1, 8), "吴佳琪", "吊装机型由管理员操作"),
        ("WM-2026-012", "专业摄像机", "数字媒体实验室", "传感器除尘", "每学期", date(2027, 1, 15), "郑浩然", "镜头清洁与固件评估"),
    ]
    for p in plans:
        ws.append(list(p))
    style_body(ws)
    for r in range(2, 14):
        ws.cell(row=r, column=6).number_format = "yyyy-mm-dd"
    add_dv(ws, ["每月", "每季度", "每半年", "每年", "一次性"], "E", 2, 14)
    note_sheet(wb, ["责任人姓名、电话、邮箱均为虚构示例，用于表格制作演示。",
                    "3D打印机维修完成后须验收并更新《设备维修记录》。"])
    save(wb, "06-设备维护计划")


# ---------------- 7 设备维修记录 ----------------
def b07():
    wb, ws = new_book("维修记录", ["工单号", "设备名称", "所属实验室", "故障描述", "报修日期",
                               "完成日期", "维修结果", "报修人(虚构)"],
                  [13, 18, 18, 34, 12, 12, 12, 12])
    rows = [
        ("FX-2026-041", "深度相机", "计算机视觉实验室", "USB接口接触不良，偶发掉线", date(2026, 9, 12), date(2026, 9, 14), "已修复", "张明宇"),
        ("FX-2026-042", "投影仪", "软件工程实验室", "画面偏色，更换信号线", date(2026, 9, 20), date(2026, 9, 21), "已修复", "李思齐"),
        ("FX-2026-043", "移动机器人底盘", "机器人创新实验室", "左驱动轮异响，清理缠绕线缆", date(2026, 9, 28), date(2026, 9, 28), "已修复", "王雨桐"),
        ("FX-2026-044", "3D打印机", "综合开放实验室", "挤出器步进电机故障，无法送料", date(2026, 10, 12), None, "维修中", "陈嘉树"),
        ("FX-2026-045", "数位屏", "数字媒体实验室", "压感笔笔尖磨损，更换笔尖", date(2026, 10, 8), date(2026, 10, 8), "已修复", "刘一诺"),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    for rr in range(2, 7):
        ws.cell(row=rr, column=5).number_format = "yyyy-mm-dd"
        ws.cell(row=rr, column=6).number_format = "yyyy-mm-dd"
    add_dv(ws, ["已修复", "维修中", "待配件", "报废"], "G", 2, 7)
    note_sheet(wb, ["3D打印机当前维修中（数据库状态=维修中），与04-设备资产总表一致。",
                    "维修期间设备在系统中不可预约；所属实验室关闭期间同样不可预约。"])
    save(wb, "07-设备维修记录")


# ---------------- 8 实验室每日巡检记录 ----------------
def b08():
    wb, ws = new_book("巡检记录", ["日期", "实验室名称", "设备外观", "水电安全", "消防器材",
                               "门窗", "卫生", "异常情况", "巡检人(虚构)"],
                  [12, 18, 10, 10, 10, 8, 8, 30, 12])
    d0 = date(2026, 10, 12)
    opts_ok = ["正常", "异常"]
    for i, l in enumerate(LABS):
        if l["status"] == 0:
            continue
        d = d0 + timedelta(days=i % 5)
        ws.append([d, l["name"], "正常", "正常", "正常", "正常", "正常",
                   "无" if i != 2 else "机房空调出风温度偏高，已报值班台", FAKE_PEOPLE[i][0]])
    style_body(ws)
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=1).number_format = "yyyy-mm-dd"
    for col in "CDEFGH":
        add_dv(ws, opts_ok, col, 2, ws.max_row)
    note_sheet(wb, ["综合开放实验室关闭期间执行封场检查，不进行常规巡检，故无巡检行。",
                    "巡检异常项转入《设备维修记录》或《安全隐患整改跟踪表》闭环。"])
    save(wb, "08-实验室每日巡检记录")


# ---------------- 9 月度安全检查表 ----------------
def b09():
    wb, ws = new_book("月度安全检查", ["检查项", "人工智能", "计算机视觉", "机器人创新", "物联网",
                                   "网络安全", "大数据", "云计算", "软件工程", "数字媒体", "综合开放"],
                  [30, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11])
    items = [
        "灭火器压力与有效期", "急救箱物资齐全", "疏散通道畅通", "紧急出口标识完好",
        "总电源/急停可用", "无私拉乱接电线", "无大功率私用电器", "机柜通风无遮挡",
        "高危区域警戒完好", "门禁与监控正常",
    ]
    for it in items:
        row = [it]
        for l in LABS:
            if l["status"] == 0 and "总电源" not in it:
                row.append("关闭豁免")
            else:
                row.append("合格")
        ws.append(row)
    style_body(ws)
    note_sheet(wb, ["综合开放实验室关闭期间多数项目豁免检查，总电源等仍定期确认。",
                    "检查人（虚构）：赵文昊；检查日期：2026-10-09。"])
    save(wb, "09-月度安全检查表")


# ---------------- 10 设备借用与归还登记表 ----------------
def b10():
    wb, ws = new_book("借用登记", ["编号", "器材名称", "所属实验室", "借用人(虚构)", "借用日期",
                               "预计归还", "实际归还", "状态", "经手人(虚构)"],
                  [10, 18, 18, 12, 12, 12, 12, 10, 12])
    rows = [
        ("JY-2601", "深度相机", "计算机视觉实验室", "张明宇", date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 10), "已归还", "孙晓萌"),
        ("JY-2602", "补光灯组", "计算机视觉实验室", "李思齐", date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 11), "已归还", "孙晓萌"),
        ("JY-2603", "移动机器人底盘", "机器人创新实验室", "王雨桐", date(2026, 10, 12), date(2026, 10, 13), None, "未归还", "周子墨"),
        ("JY-2604", "专业摄像机", "数字媒体实验室", "陈嘉树", date(2026, 10, 13), date(2026, 10, 15), None, "未归还", "郑浩然"),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    for rr in range(2, 6):
        for c in (5, 6, 7):
            ws.cell(row=rr, column=c).number_format = "yyyy-mm-dd"
    add_dv(ws, ["未归还", "已归还", "逾期", "损坏"], "H", 2, 6)
    note_sheet(wb, ["综合开放实验室关闭期间，便携投影仪、电子工具套装等器材暂停借用（表中未列出借用记录）。",
                    "本表人名、联系方式均为虚构。"])
    save(wb, "10-设备借用与归还登记表")


# ---------------- 11 用户准入培训记录 ----------------
def b11():
    wb, ws = new_book("培训记录", ["序号", "姓名(虚构)", "学号(虚构)", "培训类型", "所属实验室",
                               "培训日期", "成绩", "结果"],
                  [8, 12, 14, 22, 18, 12, 8, 10])
    rows = [
        (1, "张明宇", "2023301001", "通用安全培训", "全校通用", date(2026, 9, 3), 92, "通过"),
        (2, "李思齐", "2023301002", "机械臂专项培训", "机器人创新实验室", date(2026, 9, 10), 88, "通过"),
        (3, "王雨桐", "2023301003", "仪器操作考核", "物联网实验室", date(2026, 9, 12), 76, "通过"),
        (4, "陈嘉树", "2023301004", "网络与信息安全承诺", "网络安全实验室", date(2026, 9, 15), 95, "通过"),
        (5, "刘一诺", "2023301005", "摄影摄像与隐私保护", "数字媒体实验室", date(2026, 9, 18), 90, "通过"),
        (6, "赵文昊", "2023301006", "焊接安全小测试", "综合开放实验室", date(2026, 9, 20), 58, "未通过"),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    for rr in range(2, 8):
        ws.cell(row=rr, column=6).number_format = "yyyy-mm-dd"
    add_dv(ws, ["通过", "未通过"], "H", 2, 8)
    note_sheet(wb, ["所有姓名、学号均为虚构示例。",
                    "未通过者须补考，通过后方可使用对应区域设备。"])
    save(wb, "11-用户准入培训记录")


# ---------------- 12 实验室预约记录 ----------------
def b12():
    wb, ws = new_book("预约记录", ["预约ID", "预约人(虚构)", "实验室", "设备(空=只约实验室)",
                               "日期", "开始", "结束", "状态", "状态说明", "备注"],
                  [9, 12, 18, 18, 12, 9, 9, 8, 10, 26])
    rows = [
        (9001, "张明宇", "人工智能实验室", "", date(2026, 10, 21), "14:00", "16:00", 1, "已通过", "深度学习课程实验"),
        (9002, "李思齐", "机器人创新实验室", "六轴机械臂", date(2026, 10, 21), "09:00", "11:00", 1, "已通过", "视觉抓取调试"),
        (9003, "王雨桐", "物联网实验室", "示波器", date(2026, 10, 22), "10:00", "12:00", 0, "待审核", "传感器波形观测"),
        (9004, "陈嘉树", "网络安全实验室", "攻防靶机服务器", date(2026, 10, 22), "14:00", "17:00", 0, "待审核", "授权科目：内网渗透"),
        (9005, "刘一诺", "数字媒体实验室", "录音套装", date(2026, 10, 23), "09:30", "11:30", 2, "已拒绝", "与课程安排冲突"),
        (9006, "赵文昊", "大数据分析实验室", "", date(2026, 10, 20), "18:00", "20:00", 3, "已取消", "用户主动取消（开始前2小时）"),
        (9007, "孙晓萌", "综合开放实验室", "", date(2026, 10, 23), "10:00", "12:00", 2, "已拒绝", "实验室关闭，不可预约"),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    for rr in range(2, 9):
        ws.cell(row=rr, column=5).number_format = "yyyy-mm-dd"
    add_dv(ws, ["0-待审核", "1-已通过", "2-已拒绝", "3-已取消"], "H", 2, 9)
    note_sheet(wb, [
        "状态含义：0-待审核、1-已通过、2-已拒绝、3-已取消（与后端一致）。",
        "待审核与已通过占用时段；已拒绝与已取消不占用。",
        "9007为关闭实验室预约示例：系统在创建时即会拒绝，此处为历史演示记录。",
        "所有判断按中国北京时间UTC+8执行。",
    ])
    save(wb, "12-实验室预约记录")


# ---------------- 13 预约审核记录 ----------------
def b13():
    wb, ws = new_book("审核记录", ["审核ID", "预约ID", "预约人(虚构)", "实验室", "审核人(虚构)",
                               "审核时间", "审核结果", "审核意见"],
                  [9, 9, 12, 18, 12, 17, 12, 30])
    rows = [
        (5101, 9001, "张明宇", "人工智能实验室", "周子墨", "2026-10-20 09:05", "已通过", "课程实验，资源充足"),
        (5102, 9002, "李思齐", "机器人创新实验室", "周子墨", "2026-10-20 09:10", "已通过", "已确认急停考核通过"),
        (5103, 9005, "刘一诺", "数字媒体实验室", "吴佳琪", "2026-10-20 10:20", "已拒绝", "时段与课程安排冲突"),
        (5104, 9007, "孙晓萌", "综合开放实验室", "吴佳琪", "2026-10-20 10:40", "已拒绝", "实验室关闭，恢复后再约"),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    for rr in range(2, 6):
        ws.cell(row=rr, column=6).number_format = "yyyy-mm-dd hh:mm"
    add_dv(ws, ["已通过", "已拒绝"], "G", 2, 6)
    note_sheet(wb, ["管理员只能审核待审核状态的预约（系统约束）。",
                    "待审核超过15分钟且未开始的预约由后台自动通过（每60秒扫描一次）。"])
    save(wb, "13-预约审核记录")


# ---------------- 14 预约取消记录 ----------------
def b14():
    wb, ws = new_book("取消记录", ["取消ID", "预约ID", "预约人(虚构)", "实验室", "原预约时间",
                               "取消发起时间", "距开始剩余", "是否满足取消条件", "取消原因"],
                  [9, 9, 12, 18, 20, 17, 12, 14, 26])
    rows = [
        (7101, 9006, "赵文昊", "大数据分析实验室", "2026-10-20 18:00-20:00", "2026-10-20 16:00", "2小时", "满足(≥1小时)", "课程调整"),
        (7102, 8912, "郑浩然", "云计算实验室", "2026-10-20 15:00-17:00", "2026-10-20 13:30", "1.5小时", "满足(≥1小时)", "实验提前完成"),
        (7103, 8903, "吴佳琪", "软件工程实验室", "2026-10-20 14:30-16:30", "2026-10-20 14:00", "0.5小时", "不满足(<1小时)", "系统拒绝：距开始不足1小时"),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    for rr in range(2, 5):
        ws.cell(row=rr, column=6).number_format = "yyyy-mm-dd hh:mm"
    add_dv(ws, ["满足(≥1小时)", "不满足(<1小时)"], "H", 2, 5)
    note_sheet(wb, ["取消规则：距开始不足1小时不能取消；恰好剩余1小时允许取消；已开始的预约不能取消。",
                    "7103为系统拦截示例记录。"])
    save(wb, "14-预约取消记录")


# ---------------- 15 实验室月度使用统计 ----------------
def b15():
    wb, ws = new_book("使用统计", ["实验室名称", "月预约次数", "月使用人次", "月开放小时", "使用率(次数/开放日)"],
                  [18, 12, 12, 12, 18])
    usage = [
        ("人工智能实验室", 86, 642, 390), ("计算机视觉实验室", 54, 380, 345),
        ("机器人创新实验室", 71, 512, 330), ("物联网实验室", 63, 448, 345),
        ("网络安全实验室", 47, 296, 285), ("大数据分析实验室", 78, 690, 420),
        ("云计算实验室", 52, 371, 375), ("软件工程实验室", 96, 1150, 405),
        ("数字媒体实验室", 38, 205, 255), ("综合开放实验室", 0, 0, 0),
    ]
    for r in usage:
        ws.append([r[0], r[1], r[2], r[3], None])
    style_body(ws)
    for rr in range(2, 12):
        # 使用率=月预约次数/当月开放天数；关闭室写0避免除零
        ws.cell(row=rr, column=5).value = f'=IF(C{rr}=0,0,B{rr}/22)'
        ws.cell(row=rr, column=5).number_format = "0.00"
    chart = BarChart()
    chart.title = "月预约次数对比"
    data = Reference(ws, min_col=2, min_row=1, max_row=11)
    cats = Reference(ws, min_col=1, min_row=2, max_row=11)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.width, chart.height = 20, 10
    ws.add_chart(chart, "G2")
    note_sheet(wb, ["统计周期：2026年9月21日—10月20日（演示数据，非系统导出）。",
                    "综合开放实验室关闭期间无使用记录。"])
    save(wb, "15-实验室月度使用统计")


# ---------------- 16 设备使用率统计 ----------------
def b16():
    wb, ws = new_book("使用率", ["设备名称", "所属实验室", "数量", "月预约次数", "单台月均使用次数"],
                  [18, 18, 8, 12, 16])
    rows = [
        ("GPU训练服务器", "人工智能实验室", 2, 44), ("AI开发工作站", "人工智能实验室", 12, 96),
        ("深度相机", "计算机视觉实验室", 8, 38), ("工业相机", "计算机视觉实验室", 6, 25),
        ("六轴机械臂", "机器人创新实验室", 2, 21), ("移动机器人底盘", "机器人创新实验室", 4, 32),
        ("示波器", "物联网实验室", 8, 29), ("可编程电源", "物联网实验室", 10, 34),
        ("攻防靶机服务器", "网络安全实验室", 3, 18), ("数据计算节点", "大数据分析实验室", 8, 52),
        ("虚拟化服务器", "云计算实验室", 6, 36), ("开发主机", "软件工程实验室", 40, 88),
        ("图形工作站", "数字媒体实验室", 16, 42), ("3D打印机", "综合开放实验室", 2, 0),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    for rr in range(2, 16):
        # 单台月均=次数/数量；数量最小为1，不会除零
        ws.cell(row=rr, column=5).value = f"=D{rr}/C{rr}"
        ws.cell(row=rr, column=5).number_format = "0.0"
    note_sheet(wb, ["演示统计数据。3D打印机维修中+实验室关闭，使用为0。",
                    "设备名称、数量与04-设备资产总表一致。"])
    save(wb, "16-设备使用率统计")


# ---------------- 17 安全隐患整改跟踪表 ----------------
def b17():
    wb, ws = new_book("隐患跟踪", ["隐患编号", "发现日期", "实验室", "隐患描述", "等级",
                               "整改措施", "责任人(虚构)", "整改期限", "状态"],
                  [12, 12, 18, 34, 8, 34, 12, 12, 10])
    rows = [
        ("YH-2612", date(2026, 9, 15), "机器人创新实验室", "充电柜内电池摆放过密", "一般",
         "增加分隔托架并张贴充电看护标识", "李思齐", date(2026, 9, 25), "已闭环"),
        ("YH-2613", date(2026, 9, 22), "物联网实验室", "测量区一台可编程电源接地端子松动", "较大",
         "停用维修并校验接地", "陈嘉树", date(2026, 9, 30), "已闭环"),
        ("YH-2614", date(2026, 10, 12), "综合开放实验室", "3D打印机故障引发整室维护关闭", "较大",
         "返厂维修；恢复开放前全室安全复查", "周子墨", date(2026, 11, 15), "整改中"),
        ("YH-2615", date(2026, 10, 15), "大数据分析实验室", "机柜通道临时堆放纸箱", "一般",
         "当场清理并重申通道禁放", "赵文昊", date(2026, 10, 16), "已闭环"),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    for rr in range(2, 6):
        ws.cell(row=rr, column=2).number_format = "yyyy-mm-dd"
        ws.cell(row=rr, column=8).number_format = "yyyy-mm-dd"
    add_dv(ws, ["一般", "较大", "重大"], "E", 2, 6)
    add_dv(ws, ["整改中", "已闭环", "挂起"], "I", 2, 6)
    save(wb, "17-安全隐患整改跟踪表")


# ---------------- 18 应急物资检查表 ----------------
def b18():
    wb, ws = new_book("应急物资", ["检查项", "位置说明", "检查内容", "检查频次", "10月检查结果", "备注"],
                  [16, 34, 30, 10, 12, 24])
    rows = [
        ("灭火器", "各实验室入口及高风险区（见各室平面导览图）", "压力表指针在绿区、铅封完好、有效期", "每月", "合格", "机柜区为二氧化碳型"),
        ("急救箱", "各实验室值班台/信息卡位置", "纱布、创可贴、烫伤膏、三角巾齐全", "每月", "合格", "机器人室增加烧伤敷料"),
        ("紧急出口标识", "各室紧急出口上方", "灯亮、指向正确、无遮挡", "每月", "合格", ""),
        ("疏散通道", "主入口与紧急出口连线路径", "无杂物堆放、地面无绊倒隐患", "每周", "合格", ""),
        ("总电源/急停", "进门侧墙面或设备立柱", "标识清晰、操作可用", "每月", "合格", "机械臂三处急停均测试"),
        ("应急照明", "各室走廊与出口", "断电自亮、持续≥30分钟", "每季度", "合格", ""),
        ("消防警报按钮", "各楼层走廊", "外观完好、月检记录在位", "每月", "合格", ""),
    ]
    for r in rows:
        ws.append(list(r))
    style_body(ws)
    add_dv(ws, ["合格", "不合格", "待复检"], "E", 2, 9)
    note_sheet(wb, ["检查人（虚构）：孙晓萌；检查日期：2026-10-16。",
                    "应急物资位置详见各室《平面导览与安全疏散图》PDF。"])
    save(wb, "18-应急物资检查表")


def main():
    b01(); b02(); b03(); b04(); b05(); b06(); b07(); b08(); b09()
    b10(); b11(); b12(); b13(); b14(); b15(); b16(); b17(); b18()


if __name__ == "__main__":
    main()
