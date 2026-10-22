# -*- coding: utf-8 -*-
"""生成8-12份OCR测试原件：真正栅格化的扫描风格PDF（无文本层），带倾斜/阴影/噪声。"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = "D:/AI/faceprogram/rag_source_documents/07-OCR测试原件"
os.makedirs(OUT, exist_ok=True)
random.seed(20261020)

W, H = 1240, 1754  # A4 150dpi
SONG = "C:/Windows/Fonts/simsun.ttc"
HEI = "C:/Windows/Fonts/msyhbd.ttc"
FANG = "C:/Windows/Fonts/simfang.ttf"


def f(size, which="song"):
    path = {"song": SONG, "hei": HEI, "fang": FANG}[which]
    return ImageFont.truetype(path, size)


def paper(noise=True, tint=(250, 249, 245)):
    img = Image.new("RGB", (W, H), tint)
    if noise:
        px = img.load()
        for _ in range(int(W * H * 0.02)):
            x, y = random.randrange(W), random.randrange(H)
            v = random.randint(-18, 12)
            r, g, b = px[x, y]
            px[x, y] = (max(0, min(255, r + v)), max(0, min(255, g + v)), max(0, min(255, b + v)))
    return img


def aging(img):
    """轻微阴影+渐晕+折痕"""
    grad = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(grad)
    for y in range(H):
        v = int(18 * (y / H) ** 2)
        gd.line([(0, y), (W, y)], fill=v)
    img.paste(Image.new("RGB", (W, H), (60, 55, 40)), (0, 0), grad)
    # 折痕
    fd = ImageDraw.Draw(img)
    for _ in range(random.randint(1, 2)):
        y = random.randint(300, H - 300)
        fd.line([(0, y), (W, y + random.randint(-6, 6))], fill=(210, 205, 195), width=2)
        fd.line([(0, y + 1), (W, y + 1 + random.randint(-6, 6))], fill=(255, 255, 252), width=1)
    return img


def scanify(img, fname, angle=None):
    angle = random.uniform(-2.2, 2.2) if angle is None else angle
    img = img.rotate(angle, expand=False, fillcolor=(238, 236, 230), resample=Image.BICUBIC)
    img = aging(img)
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    # 轻微JPEG压缩感
    tmp = f"{OUT}/_tmp.jpg"
    img.save(tmp, "JPEG", quality=62)
    img = Image.open(tmp).convert("RGB")
    os.remove(tmp)
    img.save(f"{OUT}/{fname}", "PDF", resolution=150)
    print("saved", fname)


def stamp(d, xy, r=52, color=(180, 40, 40), text="智能实验中心"):
    x, y = xy
    d.ellipse([x - r, y - r, x + r, y + r], outline=color + (255,), width=4)
    d.ellipse([x - r + 10, y - r + 10, x + r - 10, y + r - 10], outline=color, width=2)
    d.text((x, y - 14), "★", font=f(22, "hei"), fill=color, anchor="mm")
    d.text((x, y + 8), text[:6], font=f(15, "hei"), fill=color, anchor="mm")
    d.text((x, y + 28), text[6:] if len(text) > 6 else "专用章", font=f(13, "hei"), fill=color, anchor="mm")


def table(d, x0, y0, col_w, row_h, nrows, header, data=None):
    x = x0
    for w, htxt in zip(col_w, header):
        d.rectangle([x, y0, x + w, y0 + row_h], outline=(60, 60, 60), width=2)
        d.text((x + 8, y0 + row_h / 2), htxt, font=f(19, "hei"), fill=(30, 30, 30), anchor="lm")
        x += w
    for r in range(1, nrows + 1):
        y = y0 + r * row_h
        x = x0
        for ci, w in enumerate(col_w):
            d.rectangle([x, y, x + w, y + row_h], outline=(70, 70, 70), width=1)
            if data is not None and r - 1 < len(data):
                val = str(data[r - 1][ci]) if ci < len(data[r - 1]) else ""
                if val:
                    d.text((x + 10, y + row_h / 2), val, font=f(21, "song"),
                           fill=(25, 25, 25), anchor="lm")
            x += w
    return y0 + (nrows + 1) * row_h


def sign_line(d, x, y, w, label):
    d.text((x, y), label, font=f(20, "song"), fill=(20, 20, 20))
    d.line([(x + 110, y + 26), (x + 110 + w, y + 26)], fill=(40, 40, 40), width=2)


# ---------- 1 扫描版实验室安全检查表 ----------
def o01():
    img = paper()
    d = ImageDraw.Draw(img)
    d.text((W // 2, 90), "实验室安全检查表（扫描件）", font=f(42, "hei"), fill=(20, 20, 20), anchor="mm")
    d.text((W // 2, 150), "检查单位：智能实验中心    检查日期：2026年10月16日", font=f(24, "song"), fill=(30, 30, 30), anchor="mm")
    rows = [
        ("检查实验室", "计算机视觉实验室（科技楼A区203）"),
        ("检查类别", "月度安全检查"),
        ("灭火器(4具)", "压力正常，有效期至2027-08"),
        ("急救箱", "物资齐全，烫伤膏余量1支"),
        ("紧急出口", "东侧出口标识灯正常"),
        ("补光灯架", "配重块在位，锁扣正常"),
        ("电路与插座", "未发现私拉乱接"),
        ("设备状态", "深度相机2号USB口松动，已报修"),
    ]
    y = table(d, 120, 210, [260, 740], 62, len(rows), ["检查项目", "检查结果"], data=rows)
    d.text((120, y + 30), "检查人签字：王雨桐（手写签名）", font=f(24, "song"), fill=(20, 20, 20))
    d.text((620, y + 30), "复核人签字：李思齐", font=f(24, "song"), fill=(20, 20, 20))
    sign_line(d, 120, y + 90, 300, "实验室主任意见：")
    d.text((430, y + 100), "同意归档。", font=f(24, "fang"), fill=(30, 30, 80))
    stamp(d, (W - 240, H - 260))
    scanify(img, "01-扫描版-实验室安全检查表.pdf")


# ---------- 2 扫描版设备维修工单 ----------
def o02():
    img = paper()
    d = ImageDraw.Draw(img)
    d.text((W // 2, 90), "设备维修工单", font=f(44, "hei"), fill=(15, 15, 15), anchor="mm")
    d.text((W // 2, 148), "工单编号：FX-2026-044    （扫描件）", font=f(24, "song"), fill=(30, 30, 30), anchor="mm")
    rows = [
        ("设备名称", "3D打印机（FDM / 300mm成型尺寸）"),
        ("所属实验室", "综合开放实验室（创新中心G区一层）"),
        ("故障现象", "挤出器步进电机异响，送料卡死，无法正常出丝"),
        ("报修日期", "2026年10月12日"),
        ("报修人", "陈嘉树（联系电话：13800001004）"),
        ("初步判断", "步进电机联轴器松动并伴有驱动板过热痕迹"),
        ("处理措施", "整台返厂维修，期间设备停用并悬挂停用标识"),
        ("预计完成", "2026年11月15日前"),
        ("状态", "维修中（数据库状态已置为维修中，系统不可预约）"),
    ]
    y = table(d, 120, 210, [240, 760], 66, len(rows), ["项目", "内容"], data=rows)
    d.text((120, y + 34), "维修负责人签字：周子墨", font=f(24, "song"), fill=(20, 20, 20))
    d.text((620, y + 34), "管理员签字：孙晓萌", font=f(24, "song"), fill=(20, 20, 20))
    stamp(d, (W - 230, H - 270))
    scanify(img, "02-扫描版-设备维修工单.pdf")


# ---------- 3 扫描版人员培训签到表 ----------
def o03():
    img = paper()
    d = ImageDraw.Draw(img)
    d.text((W // 2, 85), "实验室人员准入培训签到表", font=f(40, "hei"), fill=(15, 15, 15), anchor="mm")
    d.text((W // 2, 143), "培训主题：机械臂安全操作专项培训（机器人创新实验室）", font=f(23, "song"), fill=(30, 30, 30), anchor="mm")
    d.text((W // 2, 180), "培训日期：2026年10月10日 14:00—15:30    地点：工程训练中心B区105", font=f(22, "song"), fill=(30, 30, 30), anchor="mm")
    rows = [
        ("1", "张明宇", "2023301001", "已通过急停考核"),
        ("2", "李思齐", "2023301002", "已通过急停考核"),
        ("3", "王雨桐", "2023301003", "补考预约中"),
        ("4", "陈嘉树", "2023301004", "已通过急停考核"),
        ("5", "刘一诺", "2023301005", "已通过急停考核"),
        ("6", "赵文昊", "2023301006", "现场旁观学习"),
    ]
    y = table(d, 150, 230, [90, 260, 300, 440], 60, len(rows) + 1, ["序号", "姓名(虚构)", "学号(虚构)", "考核情况"])
    # 手写风格备注
    d.text((170, y + 40), "备注：第3位同学下次补考时间为10月24日 14:00，请在值班台登记。",
           font=f(24, "fang"), fill=(25, 40, 110))
    d.text((170, y + 90), "培训教师签字：张明宇", font=f(24, "song"), fill=(20, 20, 20))
    stamp(d, (W - 220, H - 250))
    scanify(img, "03-扫描版-人员培训签到表.pdf")


# ---------- 4 设备铭牌照片风格 ----------
def o04():
    img = Image.new("RGB", (W, H), (196, 199, 202))
    d = ImageDraw.Draw(img)
    # 拍摄透视感的金属铭牌
    plate = Image.new("RGB", (900, 560), (208, 211, 214))
    pd = ImageDraw.Draw(plate)
    pd.rectangle([0, 0, 899, 559], outline=(120, 122, 126), width=6)
    for i in range(4):
        pd.line([(20, 20 + i * 4), (880, 20 + i * 4)], fill=(235, 238, 240), width=2)
    pd.text((450, 70), "六轴机械臂  设备铭牌", font=f(40, "hei"), fill=(40, 42, 46), anchor="mm")
    rows = [("设备名称", "六轴机械臂"), ("规格", "负载5kg"), ("数量", "2台"), ("状态", "正常"),
            ("所属", "机器人创新实验室"), ("管理编号", "ROB-ARM-01 / ROB-ARM-02")]
    y = 150
    for k, v in rows:
        pd.text((60, y), k + "：", font=f(28, "hei"), fill=(40, 42, 46))
        pd.text((250, y), v, font=f(28, "song"), fill=(30, 30, 34))
        y += 62
    pd.text((450, y + 20), "智能实验中心  资产管理", font=f(24, "hei"), fill=(70, 72, 76), anchor="mm")
    # 透视粘贴
    plate = plate.rotate(-3, expand=True, fillcolor=(196, 199, 202))
    img.paste(plate, (170, 520))
    d.text((W // 2, 130), "（设备铭牌拍摄件·用于OCR测试）", font=f(26, "song"), fill=(90, 90, 92), anchor="mm")
    # 暗角
    img = aging(img)
    tmp = f"{OUT}/_t2.jpg"
    img.save(tmp, "JPEG", quality=70)
    img = Image.open(tmp).convert("RGB")
    os.remove(tmp)
    img.save(f"{OUT}/04-拍摄件-设备铭牌.pdf", "PDF", resolution=150)
    print("saved 04-拍摄件-设备铭牌.pdf")


# ---------- 5 带签字印章的实验室申请表 ----------
def o05():
    img = paper()
    d = ImageDraw.Draw(img)
    d.text((W // 2, 88), "实验室使用申请表", font=f(44, "hei"), fill=(15, 15, 15), anchor="mm")
    d.text((W // 2, 148), "编号：SQ-2026-0188（扫描件）", font=f(24, "song"), fill=(30, 30, 30), anchor="mm")
    rows = [
        ("申请人", "郑浩然（学号 2023301010，电话 13800001010）"),
        ("申请实验室", "数字媒体实验室（艺术楼F区108）"),
        ("使用设备", "录音套装（电容麦克风 / 声卡）"),
        ("使用时间", "2026年10月22日 13:00 — 15:00"),
        ("用途说明", "毕业作品配音采集，已取得被录制人授权"),
        ("指导教师", "周老师"),
    ]
    y = table(d, 120, 210, [240, 760], 64, len(rows), ["项目", "内容"], data=rows)
    sign_line(d, 120, y + 40, 300, "申请人签字：")
    d.text((245, y + 50), "郑浩然", font=f(26, "fang"), fill=(25, 40, 110))
    sign_line(d, 620, y + 40, 300, "指导教师签字：")
    d.text((745, y + 50), "周知远", font=f(26, "fang"), fill=(25, 40, 110))
    stamp(d, (W - 240, H - 280), text="数字媒体实验室")
    scanify(img, "05-扫描件-实验室使用申请表.pdf")


# ---------- 6 略微倾斜的巡检记录 ----------
def o06():
    img = paper()
    d = ImageDraw.Draw(img)
    d.text((W // 2, 90), "实验室每日巡检记录（影像留存页）", font=f(40, "hei"), fill=(15, 15, 15), anchor="mm")
    d.text((W // 2, 148), "巡检日期：2026年10月14日    实验室：物联网实验室（信息楼C区302）", font=f(23, "song"), fill=(30, 30, 30), anchor="mm")
    rows = [
        ("巡检时间", "21:05"),
        ("设备外观", "20套传感器开发套件在位，缺1根杜邦线"),
        ("水电安全", "正常，末位断电确认"),
        ("消防器材", "灭火器2具压力正常"),
        ("门窗", "已锁闭"),
        ("异常", "302室后门闭门器回弹变慢，建议报修"),
    ]
    y = table(d, 120, 210, [240, 760], 62, len(rows), ["项目", "记录"], data=rows)
    d.text((120, y + 36), "巡检人：陈嘉树", font=f(24, "song"), fill=(20, 20, 20))
    d.text((620, y + 36), "值班台复核：正常归档", font=f(24, "song"), fill=(20, 20, 20))
    scanify(img, "06-倾斜扫描件-巡检记录.pdf", angle=3.2)


# ---------- 7 带手写备注的故障登记单 ----------
def o07():
    img = paper()
    d = ImageDraw.Draw(img)
    d.text((W // 2, 90), "设备故障登记单", font=f(44, "hei"), fill=(15, 15, 15), anchor="mm")
    rows = [
        ("登记编号", "GZ-2026-033"),
        ("设备名称", "示波器（100MHz双通道）"),
        ("所属实验室", "物联网实验室"),
        ("故障现象", "CH2通道波形显示抖动"),
        ("登记日期", "2026年10月11日"),
        ("登记人", "王雨桐"),
    ]
    y = table(d, 120, 200, [240, 760], 62, len(rows), ["项目", "内容"], data=rows)
    d.text((130, y + 44), "值班员初查备注：", font=f(24, "song"), fill=(20, 20, 20))
    d.text((360, y + 44), "怀疑探头地夹氧化，已换探头复测，CH2仍抖动，", font=f(24, "fang"), fill=(25, 40, 110))
    d.text((360, y + 84), "初步判断通道前端故障，走报修流程外送检测。", font=f(24, "fang"), fill=(25, 40, 110))
    d.text((120, y + 140), "登记人签字：王雨桐          日期：2026年10月11日", font=f(24, "song"), fill=(20, 20, 20))
    stamp(d, (W - 240, H - 280))
    scanify(img, "07-扫描件-故障登记单.pdf")


# ---------- 8 安全标识与文字混排 ----------
def o08():
    img = paper()
    d = ImageDraw.Draw(img)
    d.text((W // 2, 80), "实验室安全标识须知（混排页）", font=f(40, "hei"), fill=(15, 15, 15), anchor="mm")
    signs = [
        ("禁止", (200, 40, 40), "禁止入内\n机械臂运行时任何人员不得进入安全围栏"),
        ("警告", (240, 160, 20), "当心高温\n烙铁尖端300℃以上，用毕断电归架"),
        ("禁止", (200, 40, 40), "禁止用水灭火\n电气火情先断电，使用二氧化碳灭火器"),
        ("指令", (30, 120, 60), "必须佩戴护目镜\n进入打磨、焊接工位须佩戴"),
        ("提示", (30, 90, 160), "紧急集合点\n疏散后至室外集合点清点人数"),
        ("警告", (240, 160, 20), "当心激光\n激光雷达上电后不得直视发射窗口"),
    ]
    y = 150
    for name, color, txt in signs:
        x = 150
        d.ellipse([x, y, x + 110, y + 110], outline=color, width=8)
        # 禁止斜杠
        if name == "禁止":
            d.line([(x + 14, y + 96), (x + 96, y + 14)], fill=color, width=8)
        d.text((x + 55, y + 55), name[0], font=f(44, "hei"), fill=color, anchor="mm")
        head, body = txt.split("\n")
        d.text((290, y + 18), head, font=f(30, "hei"), fill=(20, 20, 20))
        d.text((290, y + 62), body, font=f(22, "song"), fill=(40, 40, 40))
        y += 150
    scanify(img, "08-扫描件-安全标识与文字混排.pdf", angle=1.2)


# ---------- 9 旧版设备交接单 ----------
def o09():
    img = paper(tint=(246, 240, 226))
    d = ImageDraw.Draw(img)
    d.text((W // 2, 90), "设备交接单（旧版表格·存档件）", font=f(42, "hei"), fill=(40, 32, 20), anchor="mm")
    d.text((W // 2, 150), "交接单号：JJ-2025-107    交接日期：2025年12月18日", font=f(24, "song"), fill=(60, 50, 34), anchor="mm")
    rows = [
        ("移交方", "原实验室管理组（版本V0.9制度时期）"),
        ("接收方", "智能实验中心值班台"),
        ("交接设备", "移动机器人底盘×4、激光雷达×5、边缘计算盒×6"),
        ("设备状态", "外观完好；底盘-3左轮有轻微磨损，已备注"),
        ("附件清单", "充电器5只、备用轮2只、专用工具1套"),
        ("备注", "旧版编号规则自2026年1月1日起停用"),
    ]
    y = table(d, 120, 210, [240, 760], 64, len(rows), ["项目", "内容"], data=rows)
    sign_line(d, 120, y + 40, 280, "移交人签字：")
    d.text((245, y + 50), "钱志远", font=f(26, "fang"), fill=(25, 40, 110))
    sign_line(d, 620, y + 40, 280, "接收人签字：")
    d.text((745, y + 50), "孙晓萌", font=f(26, "fang"), fill=(25, 40, 110))
    d.text((120, y + 130), "（本页为历史存档扫描件，人名均为虚构）", font=f(20, "song"), fill=(120, 110, 90))
    stamp(d, (W - 230, H - 300), text="智能实验中心")
    scanify(img, "09-扫描件-旧版设备交接单.pdf", angle=-1.8)


# ---------- 10 夜间值班记录 ----------
def o10():
    img = paper(tint=(240, 242, 246))
    d = ImageDraw.Draw(img)
    d.text((W // 2, 90), "实验室夜间值班记录", font=f(44, "hei"), fill=(15, 15, 15), anchor="mm")
    d.text((W // 2, 150), "值班日期：2026年10月18日（周六）夜班 22:00 — 次日 06:00", font=f(23, "song"), fill=(30, 30, 30), anchor="mm")
    rows = [
        ("22:05", "例行开启夜间巡更，检查各室门禁状态正常"),
        ("23:40", "大数据分析实验室一计算节点风扇告警，降频运行，已报值班台并登记"),
        ("01:15", "机房温湿度正常（24.1℃ / 47%RH）"),
        ("03:30", "巡查无异常"),
        ("05:50", "填写交接班记录，风扇告警已转白班跟进"),
    ]
    y = table(d, 150, 210, [180, 820], 62, len(rows), ["时间", "值班记录"], data=rows)
    d.text((150, y + 40), "值班人签字：赵文昊（虚构）", font=f(24, "song"), fill=(20, 20, 20))
    d.text((620, y + 40), "接班人：吴佳琪", font=f(24, "song"), fill=(20, 20, 20))
    d.text((150, y + 100), "备注：夜间值班期间综合开放实验室保持封场，无人员进出记录。",
           font=f(22, "fang"), fill=(25, 40, 110))
    stamp(d, (W - 230, H - 260))
    scanify(img, "10-扫描件-夜间值班记录.pdf")


def main():
    o01(); o02(); o03(); o04(); o05(); o06(); o07(); o08(); o09(); o10()


if __name__ == "__main__":
    main()
