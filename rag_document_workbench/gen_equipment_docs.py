# -*- coding: utf-8 -*-
"""生成40份设备操作资料DOCX：12份复杂设备操作手册（6-12页）+28份快速使用指南（3-5页）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx.shared import RGBColor, Pt
from docxlib import (IMG, cover, h1, para, bullets, numbered, kv_table, pic,
                     footer_note, revision_table, new_doc, GREY)
from facts import (EQUIPMENTS, LAB_BY_ID, EQUIP_STATUS_TEXT, DOC_VERSION, DOC_DATE,
                   ORG_NAME, SYSTEM_NAME, COMPLEX_EQUIP_IDS)
from device_content import DEVICE_DOC

OUT = "D:/AI/faceprogram/rag_source_documents/03-设备操作手册"
os.makedirs(OUT, exist_ok=True)

IMG_SUFFIX = {1: "gpu-server", 2: "ws-ai", 3: "infer", 4: "storage-array", 5: "depth-cam",
              6: "industrial-cam", 7: "ws-label", 8: "light", 9: "robot-arm", 10: "mobile-robot",
              11: "lidar", 12: "edge-box", 13: "esp32", 14: "lora", 15: "osc", 16: "psu",
              17: "target", 18: "firewall", 19: "traffic", 20: "ws-audit", 21: "compute",
              22: "storagenode", 23: "ws-data", 24: "switch", 25: "virt", 26: "k8s", 27: "nas",
              28: "console", 29: "ws-dev", 30: "codesrv", 31: "projector", 32: "phones",
              33: "ws-gfx", 34: "pen", 35: "camcorder", 36: "audio", 37: "ws-open", 38: "toolkit",
              39: "mini-projector", 40: "printer3d"}

DOC_TYPE = {1: "操作手册", 3: "操作手册", 9: "操作手册", 11: "操作手册", 15: "操作手册",
            16: "操作手册", 17: "操作手册", 18: "操作手册", 19: "操作手册", 25: "操作手册",
            26: "操作手册", 40: "操作手册"}


def before_checklist(e, lab):
    base = [
        f"确认已在{SYSTEM_NAME}预约成功，且预约时段位于实验室开放时间（{lab['open_time']}—{lab['close_time']}）内；",
        f"携带校园卡完成到场签到；首次使用{e['name']}须已完成对应的准入培训；",
    ]
    if e["status"] == 0:
        base.append("注意：本设备当前为维修中状态，不可预约使用；")
    if lab["status"] == 0:
        base.append("注意：所属实验室当前整室关闭，即使设备状态正常也不可使用；")
    return base


def forbid_list(e, det):
    pairs = []
    from gen_devices import DODONT
    for good, bad in DODONT[e["id"]]:
        pairs.append(bad.rstrip("。") + "。")
    return pairs


def build(e):
    lab = LAB_BY_ID[e["lab_id"]]
    det = DEVICE_DOC[e["id"]]
    dtype = DOC_TYPE.get(e["id"], "快速使用指南")
    status = EQUIP_STATUS_TEXT[e["status"]]
    doc = new_doc()
    footer_note(doc, f"{ORG_NAME}｜{e['name']}{dtype}｜{DOC_VERSION}｜{DOC_DATE}")

    cover(doc, f"{e['name']}", f"{dtype}（{SYSTEM_NAME}配套资料）", ORG_NAME,
          [f"所属实验室：{lab['name']}（{lab['location']}）",
           f"数据库规格：{e['spec']}｜数量：{e['quantity']}台/套",
           f"当前状态：{status}", f"版本 {DOC_VERSION}｜{DOC_DATE}"],
          img_path=f"{IMG}/equip-{e['id']:02d}-{IMG_SUFFIX[e['id']]}.png")

    h1(doc, "一、设备基本信息")
    kv_table(doc, [
        ("设备名称", e["name"]), ("所属实验室", f"{lab['name']}（数据库ID {lab['id']}）"),
        ("所在位置", lab["location"]), ("数据库中的规格", e["spec"]),
        ("数据库中的数量", f"{e['quantity']} 台/套"), ("当前状态", status),
        ("设备说明", e["desc"]),
        ("资料类型", "操作手册（复杂/高风险设备）" if dtype == "操作手册" else "快速使用指南（简单设备）"),
    ], widths=[4.0, 11.2])

    h1(doc, "二、主要用途与适用实验")
    para(doc, f"本设备主要用于：{e['desc']}。")
    para(doc, "适用实验：")
    bullets(doc, [det["uses"]])

    h1(doc, "三、使用前准备")
    numbered(doc, before_checklist(e, lab))

    h1(doc, "四、开机或启用步骤")
    para(doc, det["steps"][0])

    h1(doc, "五、标准操作步骤")
    para(doc, det["steps"][1])

    h1(doc, "六、停机或退出步骤")
    para(doc, det["steps"][2])

    h1(doc, "七、使用后检查")
    numbered(doc, [
        "确认设备外观完好，附件无缺失；",
        "确认已按停机步骤正确关机/断电；",
        "使用登记表已填写（时间、状态、异常）；",
        f"发现异常立即在{SYSTEM_NAME}故障上报入口登记，勿带病使用。",
    ])

    h1(doc, "八、禁止操作")
    bullets(doc, forbid_list(e, det))

    h1(doc, "九、常见故障现象与简单排查")
    for i, (sym, fix) in enumerate(det["faults"], 1):
        para(doc, f"故障{i}：{sym}", bold=True)
        para(doc, f"排查方法：{fix}。")

    h1(doc, "十、无法解决时的上报流程")
    numbered(doc, [
        "在系统中提交故障工单：注明实验室、设备名称、故障现象、发生时间与已尝试的排查；",
        f"同步电话通知值班台（虚构示例：0731-8888{str(lab['id']).zfill(4)}，内部短号 {str(lab['id']).zfill(4)}）；",
        "紧急情况（冒烟/漏水/触电风险）先按安全应急流程处置再报修；",
        "管理员确认后把设备置为\u201c维修中\u201d，修复验收后恢复\u201c正常\u201d；维修期间系统内不可预约。",
    ])

    h1(doc, "十一、日常维护要求")
    para(doc, det["maint"])

    h1(doc, "十二、安全注意事项")
    para(doc, det["safety"])
    if lab["id"] == 5:
        para(doc, "特别提示：本设备属于网络安全实验室，一切操作仅在物理隔离网络环境内进行，"
                  "详见《网络安全实验授权管理制度》。", bold=True)

    sec_no = 13
    for title, paras in det.get("extra", []):
        h1(doc, f"{sec_no}、{title}")
        for p in paras:
            para(doc, p)
        sec_no += 1

    h1(doc, f"{sec_no}、设备结构示意图")
    pic(doc, f"{IMG}/equip-{e['id']:02d}-{IMG_SUFFIX[e['id']]}.png", width_cm=13.0,
        caption="图1 设备结构示意图（教学示意图，非真实产品照片）")
    h2_ = doc.add_paragraph()
    h1(doc, f"{sec_no + 1}、关键接口或控制区域图")
    pic(doc, f"{IMG}/panel-{e['id']:02d}.png", width_cm=13.0,
        caption="图2 关键接口/控制区域图（教学示意图，实际位置以设备实物为准）")
    h1(doc, f"{sec_no + 2}、正确操作与错误操作对比")
    pic(doc, f"{IMG}/dodont-{e['id']:02d}.png", width_cm=14.0,
        caption="图3 正确操作与错误操作对比（教学示意）")

    revision_table(doc, DOC_VERSION, DOC_DATE, [
        (f"首次发布；规格、数量、状态取自2026-10-20数据库快照；"
         + ("含公开技术资料来源标注。" if e["id"] in (5, 11) else ""), ORG_NAME),
    ])

    prefix = f"{e['id']:02d}-{e['name']}"
    path = f"{OUT}/{prefix}-{dtype}.docx"
    doc.save(path)
    print("saved", path)


def main():
    for e in EQUIPMENTS:
        build(e)


if __name__ == "__main__":
    main()
