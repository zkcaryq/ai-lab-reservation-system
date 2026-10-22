# -*- coding: utf-8 -*-
"""生成05-安全与应急资料、08-Markdown通知与指南（含流程图与.media相对引用）。"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from imglib import F, new_canvas, rrect, arrow, text_c, save_png
from facts import DOC_VERSION, DOC_DATE, ORG_NAME, SYSTEM_NAME, LABS

IMG = "D:/AI/faceprogram/rag_document_workbench/gen_images"
SAFETY = "D:/AI/faceprogram/rag_source_documents/05-安全与应急"
MD = "D:/AI/faceprogram/rag_source_documents/08-Markdown通知与指南"
os.makedirs(SAFETY, exist_ok=True)
os.makedirs(MD, exist_ok=True)

# ---------- 流程图 ----------
def flow_chart(title, steps, out, color="#1a3a6b"):
    w = 900
    h = 160 + len(steps) * 110
    img, d = new_canvas(w, h)
    d.rectangle([0, 0, w, 64], fill=color)
    text_c(d, (24, 32), title, F(26, True), fill="white", anchor="lm")
    y = 110
    centers = []
    for i, s in enumerate(steps):
        box = (90, y, w - 90, y + 74)
        rrect(d, box, r=14, fill="#e8f0fe" if i % 2 == 0 else "#f1f8e9", outline=color, width=3)
        text_c(d, (w / 2, y + 37), s, F(21, True), fill="#202124")
        centers.append((w / 2, y))
        if i < len(steps) - 1:
            arrow(d, (w / 2, y + 74), (w / 2, y + 108), color=color, width=5, head=14)
        y += 110
    save_png(img, f"{IMG}/{out}")


def main():
    # ---- 流程图图片 ----
    flow_chart("实验室预约流程（当前系统规则）", [
        "① 登录系统，选择实验室（可选具体设备）",
        "② 选择日期与时段（当天起、晚于当前、在开放时间内）",
        "③ 提交预约 → 状态：待审核（占用时段）",
        "④ 管理员审核，或超15分钟未开始自动通过（每60秒扫描）",
        "⑤ 已通过 → 按时到场刷卡签到使用",
        "⑥ 如需取消：距开始≥1小时可在系统内取消",
    ], "flow-reservation.png")
    flow_chart("设备故障上报流程", [
        "① 发现故障：停止使用并确保安全（必要时断电）",
        "② 系统提交故障工单（实验室/设备/现象/时间）",
        "③ 电话通知值班台（紧急事件先处置再报修）",
        "④ 管理员确认 → 设备置为维修中（系统不可预约）",
        "⑤ 维修完成验收 → 状态恢复正常",
    ], "flow-fault.png")

    # ---- Markdown 通知与指南 ----
    notice_closed = """# 关于综合开放实验室临时关闭的通知

各位同学、老师：

因综合开放实验室（创新中心G区一层）3D打印机等设备维修需要，经研究决定对该实验室实施**整室临时关闭**，现将有关事项通知如下：

## 一、关闭时间

自 2026 年 10 月 12 日起，至设备维修验收合格后恢复，恢复时间另行通知。

## 二、关闭期间要求

1. 综合开放实验室停止一切预约、教学与开放活动；
2. **即使实验室内部分设备状态显示为正常，也不得预约或使用**——整室关闭期间，室内所有设备均不可用；
3. 3D 打印机当前处于维修中状态，任何人不得通电试机；
4. 请已预约该实验室相关时段的师生配合取消或改约其他实验室。

## 三、预约系统提示

在 {sysname} 中，该实验室状态已置为"关闭"，系统将自动拒绝新预约。

## 四、联系方式

- 值班台（虚构示例）：0731-88880013（内部短号 8013）
- 咨询：创新中心综合管理办公室

由此带来的不便敬请谅解。

智能实验中心
2026年10月12日
""".replace("{sysname}", SYSTEM_NAME)

    guide_reservation = f"""# 实验室预约操作指南

本指南说明 {SYSTEM_NAME} 当前的预约规则与操作步骤。规则与后端服务当前实现一致。

![预约流程图](.media/flow-reservation.png)

## 一、预约前须知

- 必须先登录系统才能预约；
- 预约日期不能早于中国北京时间（UTC+8）当天；
- 开始时间必须早于结束时间，且必须晚于当前时间；
- 预约时段必须位于目标实验室开放时间内；
- **关闭状态的实验室不能预约**（当前：综合开放实验室）；
- 预约设备时：设备必须属于所选实验室，维修中的设备不能预约。

## 二、状态说明

| 状态码 | 含义 | 是否占用时段 |
| --- | --- | --- |
| 0 | 待审核 | 占用 |
| 1 | 已通过 | 占用 |
| 2 | 已拒绝 | 不占用 |
| 3 | 已取消 | 不占用 |

## 三、审核与自动通过

- 管理员只能审核"待审核"状态的预约；
- 待审核超过 **15 分钟** 且预约尚未开始时自动通过；后台每 60 秒扫描一次，因此自动通过可能发生在超过 15 分钟后的下一次扫描；
- 已到预约开始时间仍为"待审核"的记录自动取消。

## 四、冲突规则

- 只预约实验室时，冲突检查对象是同一实验室的实验室预约；
- 预约具体设备时，冲突检查对象是同一设备对应的预约；
- 待审核与已通过的记录都会占用时段。

## 五、取消规则

- 可取消本人"待审核"或"已通过"的预约；
- 已拒绝或已取消的记录不能再次取消；
- **已经开始的预约不能取消**；
- 距离开始不足 1 小时不能取消；恰好剩余 1 小时允许取消。

## 六、常见问题

**Q：为什么我约不了综合开放实验室？**
A：该实验室因设备维护整室关闭，恢复前系统会拒绝预约。

**Q：为什么 3D 打印机选不了？**
A：该设备维修中；且其所属实验室也处于关闭状态。

**Q：系统还有哪些限制？**
A：当前系统**没有**"提前一天预约""每人每天一次""单次最长两小时""周末关闭""收费""信用分"等规则；如通知中出现此类说法，请以本指南为准并向管理员核实。
"""

    guide_fault = f"""# 设备故障上报流程指南

![故障上报流程图](.media/flow-fault.png)

## 一、发现故障后立即做什么

1. **停止使用**故障设备，必要时先断电（电气异常、冒烟、异响）；
2. 在设备旁放置"停用"提示（或告知值班台）；
3. 不要自行拆修。

## 二、上报渠道

1. 登录 {SYSTEM_NAME}，在"故障上报"入口提交工单，写明：实验室、设备名称、故障现象、发生时间、已尝试的排查；
2. 同步电话通知值班台（各室短号见各室手册）；
3. 紧急情况（触电、火情、漏水）先按应急流程处置，再补报工单。

## 三、后续流程

- 管理员确认后，设备在系统中置为"维修中"，自动不可预约；
- 维修完成经验收后恢复"正常"状态；
- 维修进展可在《设备维修记录》中查询。

## 四、当前维修中设备

- 3D 打印机（综合开放实验室）：2026-10-12 起返厂维修；
- 注意：其所属实验室同步整室关闭。

## 五、参考制度

《设备故障报修与停用制度》《实验室安全管理总则》
"""

    safety_newbie = f"""# 实验室安全须知（新生版）

欢迎来到智能实验中心！第一次进入实验室前，请花 5 分钟读完本页。

## 进门三件事

1. **看**：门口张贴的《平面布局与安全疏散图》——记住你所在位置、最近的两个出口、灭火器和急救箱在哪；
2. **学**：完成线上安全测试并通过对应实验室的专项培训；
3. **约**：通过 {SYSTEM_NAME} 预约成功后再到场，到场先签到。

## 十条红线

1. 严禁在实验室饮食、吸烟；
2. 严禁私拉乱接电线、使用大功率电器；
3. 机械臂运行时严禁进入围栏；
4. 焊接作业必须开排风、烙铁用毕断电归架；
5. 严禁将攻防实验指向隔离网段之外的任何目标；
6. 严禁在关闭状态的实验室逗留（当前：综合开放实验室）；
7. 严禁拍摄、录制他人而未取得授权；
8. 严禁删除、篡改他人实验数据；
9. 严禁转借账号或替人代约；
10. 遇突发情况：先保证人身安全，再处置、再报告。

## 应急联系（虚构示例）

- 校园保卫/火警协助：0731-88119119
- 校医院急救：0731-88120120
- 各实验室值班台短号：8001—8013

## 更多资料

- 各实验室《综合介绍与使用手册》（01 目录）
- 各室《平面导览与安全疏散图》（02 目录）
- 《突发事件应急处置总预案》（04 目录）
"""

    def write_md(name, content, media=None):
        mdir = os.path.join(MD, name.rsplit(".", 1)[0] + ".media")
        text = content
        if media:
            os.makedirs(mdir, exist_ok=True)
            for img in media:
                shutil.copy(f"{IMG}/{img}", f"{mdir}/{img}")
        with open(f"{MD}/{name}", "w", encoding="utf-8") as fp:
            fp.write(text)
        print("saved md", name)

    write_md("关于综合开放实验室临时关闭的通知.md", notice_closed)
    write_md("实验室预约操作指南.md", guide_reservation, media=["flow-reservation.png"])
    write_md("设备故障上报流程指南.md", guide_fault, media=["flow-fault.png"])
    write_md("实验室安全须知（新生版）.md", safety_newbie)

    # ---- 05 安全与应急（PDF速查卡） ----
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle

    pdfmetrics.registerFont(TTFont("MSYH", "C:/Windows/Fonts/msyh.ttc"))
    pdfmetrics.registerFont(TTFont("MSYHB", "C:/Windows/Fonts/msyhbd.ttc"))
    st_t = ParagraphStyle("t", fontName="MSYHB", fontSize=20, textColor=colors.HexColor("#1a3a6b"))
    st_h = ParagraphStyle("h", fontName="MSYHB", fontSize=13, spaceBefore=10, spaceAfter=3)
    st_b = ParagraphStyle("b", fontName="MSYH", fontSize=10.5, leading=16)

    def pdf_doc(name):
        path = f"{SAFETY}/{name}.pdf"
        doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                                topMargin=1.6 * cm, bottomMargin=1.8 * cm)
        return doc, path

    # 1) 应急处置速查卡
    doc, path = pdf_doc("突发事件应急处置速查卡")
    story = [Paragraph("突发事件应急处置速查卡", st_t),
             Paragraph(f"{ORG_NAME}｜{DOC_VERSION}｜{DOC_DATE}｜打印后建议张贴于各实验室门口", st_b),
             Spacer(1, 8)]
    rows = [
        ["事件类型", "第一步", "第二步", "第三步"],
        ["电气火情", "断开总电源", "CO₂/干粉灭火器扑救初起火", "火势失控立即撤离并拨打119"],
        ["人身触电", "断电或用绝缘物挑开导线", "呼救并施行急救", "拨打校医院急救电话"],
        ["烫伤", "冷水冲洗15分钟以上", "急救箱简单包扎", "严重时送医"],
        ["机械臂伤人", "立即拍急停按钮", "呼救并施救", "报值班台并保留现场"],
        ["电池冒烟起火", "断开充电柜电源", "干粉灭火器扑救", "整柜停用并报修"],
        ["网络越权事件", "断开相关网线", "保留现场与日志", "报值班台与安全负责人"],
        ["设备异响/焦味", "停止任务并断电", "悬挂停用标识", "提交故障工单"],
    ]
    t = Table(rows, colWidths=[2.8 * cm, 4.2 * cm, 4.6 * cm, 5.4 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "MSYH"),
        ("FONTNAME", (0, 0), (-1, 0), "MSYHB"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#b0bec5")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fce8e6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [t, Spacer(1, 8),
              Paragraph("疏散要点", st_h),
              Paragraph("沿各室《平面导览与安全疏散图》绿色箭头方向撤离 → 从主入口或紧急出口离开 → 到室外集合点集合清点人数 → 服从值班人员指挥，勿乘电梯。", st_b),
              Paragraph("应急电话（虚构示例）", st_h),
              Paragraph("保卫/火警协助 0731-88119119｜校医院急救 0731-88120120｜各室值班台短号 8001—8013", st_b)]
    doc.build(story)
    print("saved", path)

    # 2) 消防与用电安全图册
    doc, path = pdf_doc("消防与用电安全图册")
    story = [Paragraph("消防与用电安全图册", st_t),
             Paragraph(f"{ORG_NAME}｜{DOC_VERSION}｜{DOC_DATE}", st_b), Spacer(1, 6)]
    img = RLImage(f"{IMG}/dodont-38-电子工具套装.png".replace("dodont-38-电子工具套装", "dodont-38"), width=15 * cm, height=15 * cm * 0.36)
    story += [Paragraph("焊接与用电：正确 vs 错误", st_h), img, Spacer(1, 6)]
    for txt in [
        "1. 实验室内所有电气区域配置二氧化碳或干粉灭火器，位置见各室平面导览图；",
        "2. 接线顺序：先断电→先接地/负极→再接信号/正极→检查→上电；",
        "3. 可编程电源先设限压限流再开输出；示波器先接地夹后接信号钩；",
        "4. 禁止用湿手操作电气开关；禁止在机柜前0.5米内堆放物品；",
        "5. 每月检查灭火器压力表与急救箱物资并记录《应急物资检查表》。",
    ]:
        story.append(Paragraph(txt, st_b))
    doc.build(story)
    print("saved", path)

    # 3) 安全疏散要点海报
    doc, path = pdf_doc("安全疏散要点海报")
    story = [Paragraph("安全疏散要点", st_t),
             Paragraph("（建议按A4打印张贴）", st_b), Spacer(1, 6)]
    plan = f"{IMG}/03-robot-平面布局与安全疏散图.png"
    story.append(RLImage(plan, width=17 * cm, height=17 * cm * 1220 / 1720))
    story += [Paragraph("1. 保持冷静，就近沿绿色箭头撤离；2. 低姿捂口鼻（烟雾时）；3. 勿乘电梯；"
                        "4. 到室外集合点清点人数；5. 不返回取物。", st_b)]
    doc.build(story)
    print("saved", path)


if __name__ == "__main__":
    main()
