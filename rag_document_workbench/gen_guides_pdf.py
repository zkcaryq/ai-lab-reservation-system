# -*- coding: utf-8 -*-
"""生成10份《实验室平面导览与安全疏散图》PDF（A4横向，页面一图一表）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Image, Table, TableStyle, PageBreak)
from reportlab.lib.styles import ParagraphStyle

from facts import LABS, LAB_STATUS_TEXT, DOC_VERSION, DOC_DATE, ORG_NAME

IMG = "D:/AI/faceprogram/rag_document_workbench/gen_images"
OUT = "D:/AI/faceprogram/rag_source_documents/02-实验室平面导览"
os.makedirs(OUT, exist_ok=True)

pdfmetrics.registerFont(TTFont("MSYH", "C:/Windows/Fonts/msyh.ttc"))
pdfmetrics.registerFont(TTFont("MSYHB", "C:/Windows/Fonts/msyhbd.ttc"))

PLAN_NAMES = {1: "01-ai", 2: "02-cv", 3: "03-robot", 4: "04-iot", 5: "05-security",
              6: "06-bigdata", 7: "07-cloud", 11: "11-software", 12: "12-media", 13: "13-open"}

# 每间实验室的风险要点与应急要点（差异化文案）
RISK = {
    1: ["GPU机柜区：大功率高压设备，非授权禁止开机柜", "服务器区噪声较大，长时间停留建议听力防护"],
    2: ["强光补光区：勿长时间直视LED光源", "灯架未配重有倾倒风险"],
    3: ["机械臂围栏区：运行时严禁进入，急停按钮位于围栏外侧", "充电与电池柜：锂电池充电有人看护"],
    4: ["仪器测量区：接线先断电，先接地后接信号", "焊接高温：烙铁用毕归架断电"],
    5: ["隔离网络边界：严禁跨网私接设备", "攻防实验仅限授权科目内进行"],
    6: ["机柜区：噪声与热风较大，勿遮挡通风", "存储数据合规：未脱敏个人信息不得带出"],
    7: ["集群节点：禁止物理断电重启，异常报值班员", "NAS设备禁止随意拔插硬盘"],
    11: ["工位用电：禁止私接大功率电器", "通道保持畅通，人员密度高注意秩序"],
    12: ["摄影棚灯架需配重固定", "录音棚隔音门注意开合，内有人勿硬推"],
    13: ["本实验室整体关闭（设备维护），关闭期间禁止进入", "3D打印机维修中，禁止通电"],
}
EMERG = {
    1: "服务器异响/焦味→停任务断机柜电→报值班台(8001)；电气火情用CO₂灭火器；经主入口或东侧紧急出口疏散。",
    2: "灯架倾倒先断电；眼部不适停止拍摄休息；经主入口或东侧紧急出口疏散。",
    3: "机械臂伤人立即拍急停→呼救；电池起火用干粉灭火器并整柜断电；经主入口或东侧紧急出口疏散。",
    4: "触电先断电再施救；烫伤冷水冲15分钟；经主入口或东侧紧急出口疏散。",
    5: "越权访问立即断网线保留现场→报值班台(8005)；经主入口或东北角紧急出口疏散。",
    6: "空调告警/异味远离机柜→报值班员；电气火情用CO₂灭火器；经主入口或东北角紧急出口疏散。",
    7: "集群异常报值班员并保留日志；经主入口或东北角紧急出口疏散。",
    11: "线路打火立即断电→报告教师；经主入口或东侧紧急出口疏散，集合点清点人数。",
    12: "灯架倾倒先断电；录音棚突发不适用急救箱并呼救；经录音棚疏散门或主入口疏散。",
    13: "本室关闭期间不组织活动；恢复后：烫伤冷水冲洗，火情用就近灭火器；经主入口或东北角紧急出口疏散。",
}


def styles():
    s = ParagraphStyle("t", fontName="MSYHB", fontSize=22, leading=28, textColor=colors.HexColor("#1a3a6b"))
    sub = ParagraphStyle("sub", fontName="MSYH", fontSize=12, leading=18, textColor=colors.HexColor("#5f6368"))
    h = ParagraphStyle("h", fontName="MSYHB", fontSize=14, textColor=colors.HexColor("#1a3a6b"),
                       spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", fontName="MSYH", fontSize=10.5, leading=17)
    cap = ParagraphStyle("cap", fontName="MSYH", fontSize=8.5, textColor=colors.HexColor("#5f6368"))
    return s, sub, h, body, cap


def on_page(canv, doc):
    canv.saveState()
    canv.setFont("MSYH", 8.5)
    canv.setFillColor(colors.HexColor("#9aa0a6"))
    canv.drawString(2 * cm, 1.2 * cm, f"{ORG_NAME}｜教学示意图，非施工图")
    canv.drawRightString(doc.pagesize[0] - 2 * cm, 1.2 * cm,
                         f"{DOC_VERSION}｜{DOC_DATE}")
    canv.restoreState()


def build(lab):
    st, sub, h, body, cap = styles()
    pdf = landscape(A4)
    path = f"{OUT}/{lab['id']:02d}-{lab['name']}-平面导览与安全疏散图.pdf"
    doc = BaseDocTemplate(path, pagesize=pdf, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                          topMargin=1.4 * cm, bottomMargin=1.8 * cm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=on_page)])

    story = []
    story.append(Paragraph(f"{lab['name']} · 平面导览与安全疏散图", st))
    story.append(Paragraph(
        f"位置：{lab['location']}｜最大容量：{lab['capacity']} 人｜开放时间："
        f"{lab['open_time']}—{lab['close_time']}（北京时间）｜当前状态："
        f"{LAB_STATUS_TEXT[lab['status']]}"
        + ("（设备维护，关闭期间禁止预约与进入）" if lab["status"] == 0 else ""), sub))
    story.append(Spacer(1, 8))
    plan = f"{IMG}/{PLAN_NAMES[lab['id']]}-平面布局与安全疏散图.png"
    avail_h = doc.height - 92
    ph = avail_h
    pw = ph * 1720 / 1220
    if pw > doc.width:
        pw = doc.width
        ph = pw * 1220 / 1720
    story.append(Image(plan, width=pw, height=ph))
    story.append(Paragraph("上图同时呈现：房间布局、主要设备区域、普通工作区、高风险区域、出入口与紧急出口、"
                           "灭火器、急救箱、总电源/急停位置及人员疏散方向。图中比例仅为示意，现场标识优先。", cap))
    story.append(PageBreak())

    story.append(Paragraph("图例与区域说明", h))
    legend_tbl = Table([
        ["图例", "含义"],
        ["浅蓝/浅绿区块", "普通工作区（可按预约使用）"],
        ["红色斜纹区块", "高风险区域（须遵守区域专项安全要求）"],
        ["绿色门形/标签", "出入口与紧急出口（现场以绿色标识为准）"],
        ["红色圆形\u201c灭\u201d", "灭火器位置"],
        ["绿色十字", "急救箱位置"],
        ["黄色闪电", "总电源/紧急停止位置"],
        ["绿色箭头", "人员疏散方向（撤离至室外集合点）"],
    ], colWidths=[6 * cm, 14 * cm])
    legend_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "MSYH"),
        ("FONTNAME", (0, 0), (-1, 0), "MSYHB"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#b0bec5")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0fe")),
    ]))
    story.append(legend_tbl)

    story.append(Paragraph("高风险区域提示", h))
    for r in RISK[lab["id"]]:
        story.append(Paragraph("• " + r, body))

    story.append(Paragraph("应急处理要点", h))
    story.append(Paragraph(EMERG[lab["id"]], body))
    story.append(Paragraph("通用原则：先断电（如涉及电气）→ 呼救并报值班台 → 视伤情使用急救箱或拨打校医院急救电话 → "
                           "火情使用就近灭火器扑救初起火灾，火势失控立即撤离并拨打119 → 沿绿色箭头疏散至室外集合点。", body))

    story.append(Paragraph("使用与状态说明", h))
    note = f"本实验室当前状态：{LAB_STATUS_TEXT[lab['status']]}。"
    if lab["status"] == 0:
        note += "整室关闭期间，即使部分设备状态为\u201c正常\u201d，也不得预约或使用任何设备。"
    story.append(Paragraph(note, body))
    story.append(Paragraph("本图为教学示意平面图，依据2026-10-20数据库事实与现场通行安全布置规范绘制；"
                           "实际出口、器材位置以现场标识为准。", cap))
    doc.build(story)
    print("saved", path)


def main():
    for lab in LABS:
        build(lab)


if __name__ == "__main__":
    main()
