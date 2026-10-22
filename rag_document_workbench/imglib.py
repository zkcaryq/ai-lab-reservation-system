# -*- coding: utf-8 -*-
"""Pillow 绘图辅助库：字体、画布、常用图元。"""
import math
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "C:/Windows/Fonts"

_font_cache = {}


def F(size, bold=False, serif=False):
    key = (size, bold, serif)
    if key not in _font_cache:
        if serif:
            path = f"{FONT_DIR}/simsun.ttc"
        elif bold:
            path = f"{FONT_DIR}/msyhbd.ttc"
        else:
            path = f"{FONT_DIR}/msyh.ttc"
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]


def new_canvas(w=1600, h=1100, bg="white"):
    img = Image.new("RGB", (w, h), bg)
    return img, ImageDraw.Draw(img)


def text_c(d, xy, s, font, fill="black", anchor="mm"):
    d.text(xy, s, font=font, fill=fill, anchor=anchor)


def rrect(d, box, r=8, fill=None, outline="black", width=2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def dashed_rect(d, box, color="black", width=2, dash=12, gap=8):
    x0, y0, x1, y1 = box
    def seg(a, b, fixed, horiz):
        pos = a
        while pos < b:
            end = min(pos + dash, b)
            if horiz:
                d.line([(pos, fixed), (end, fixed)], fill=color, width=width)
            else:
                d.line([(fixed, pos), (fixed, end)], fill=color, width=width)
            pos = end + gap
    seg(x0, x1, y0, True); seg(x0, x1, y1, True)
    seg(y0, y1, x0, False); seg(y0, y1, x1, False)


def arrow(d, p0, p1, color="black", width=4, head=14):
    d.line([p0, p1], fill=color, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for da in (math.radians(150), math.radians(-150)):
        x = p1[0] + head * math.cos(ang + da)
        y = p1[1] + head * math.sin(ang + da)
        d.line([p1, (x, y)], fill=color, width=width)


def hatch(d, box, color="red", spacing=14, width=2, direction="\\"):
    x0, y0, x1, y1 = box
    # 裁剪到矩形范围
    mask = Image.new("L", (int(x1 - x0), int(y1 - y0)), 0)
    md = ImageDraw.Draw(mask)
    W, H = mask.size
    if direction == "\\":
        for off in range(-H, W, spacing):
            md.line([(off, 0), (off + H, H)], fill=180, width=width)
    else:
        for off in range(0, W + H, spacing):
            md.line([(off, 0), (off - H, H)], fill=180, width=width)
    overlay = Image.new("RGB", mask.size, color)
    d._image.paste(overlay, (int(x0), int(y0)), mask)


def north_arrow(d, xy, s=46):
    x, y = xy
    d.polygon([(x, y - s), (x - s * 0.35, y + s * 0.6), (x, y + s * 0.25), (x + s * 0.35, y + s * 0.6)],
              fill="#d93025", outline="black")
    text_c(d, (x, y + s + 14), "北", F(18, True))


def legend(items, x, y, d, font=None, dx=190, per_row=None):
    """items: list of (kind, label). kind: rect/warn/exit/ext/aid/power/arrow"""
    font = font or F(17)
    per_row = per_row or max(1, 920 // dx)
    for i, (kind, label) in enumerate(items):
        cx = x + (i % per_row) * dx
        cy = y + (i // per_row) * 34
        if kind == "rect":
            d.rectangle([cx, cy - 9, cx + 26, cy + 9], fill="#e8f0fe", outline="black", width=2)
        elif kind == "warn":
            d.rectangle([cx, cy - 9, cx + 26, cy + 9], fill="#fce8e6", outline="black", width=2)
            hatch(d, [cx, cy - 9, cx + 26, cy + 9], color="#d93025", spacing=6, width=1)
        elif kind == "exit":
            d.rectangle([cx, cy - 9, cx + 26, cy + 9], fill="#1e8e3e")
        elif kind == "ext":
            d.ellipse([cx + 4, cy - 9, cx + 30, cy + 13], fill="#d93025", outline="black")
            d.rectangle([cx + 13, cy - 6, cx + 21, cy + 6], fill="white")
        elif kind == "aid":
            d.rectangle([cx, cy - 9, cx + 26, cy + 9], fill="white", outline="#1e8e3e", width=3)
            d.rectangle([cx + 10, cy - 6, cx + 16, cy + 6], fill="#1e8e3e")
            d.rectangle([cx + 5, cy - 2, cx + 21, cy + 3], fill="#1e8e3e")
        elif kind == "power":
            d.polygon([(cx + 13, cy - 12), (cx + 8, cy + 2), (cx + 18, cy + 2)], fill="#f9ab00")
            d.line([(cx + 13, cy + 2), (cx + 13, cy + 10)], fill="#f9ab00", width=4)
            d.ellipse([cx + 1, cy - 11, cx + 25, cy + 13], outline="#f9ab00", width=3)
        elif kind == "arrow":
            arrow(d, (cx + 2, cy), (cx + 26, cy), color="#1e8e3e", width=4, head=10)
        text_c(d, (cx + 36, cy), label, font, anchor="lm")


def title_block(d, w, h, title, subtitle="", meta=""):
    d.rectangle([0, 0, w, 64], fill="#1a3a6b")
    text_c(d, (24, 32), title, F(30, True), fill="white", anchor="lm")
    if subtitle:
        text_c(d, (w - 24, 26), subtitle, F(18), fill="#cfe0ff", anchor="rm")
    if meta:
        text_c(d, (w - 24, 48), meta, F(14), fill="#cfe0ff", anchor="rm")


def info_card(d, x, y, w, lines, font=None, title=None):
    font = font or F(17)
    pad = 12
    th = 34 if title else 0
    h = th + pad * 2 + len(lines) * (font.size + 8)
    rrect(d, [x, y, x + w, y + h], r=10, fill="#f8fafc", outline="#5f6368", width=2)
    if title:
        text_c(d, (x + w // 2, y + th // 2), title, F(19, True), anchor="mm")
    cy = y + th + pad + font.size // 2
    for ln in lines:
        text_c(d, (x + pad, cy), ln, font, anchor="lm")
        cy += font.size + 8
    return h


def sign_extinguisher(d, xy, s=26):
    x, y = xy
    d.ellipse([x - s, y - s, x + s, y + s], fill="#d93025", outline="black", width=3)
    d.rectangle([x - s * 0.28, y - s * 0.55, x + s * 0.28, y + s * 0.7], fill="white")
    d.text((x, y - 2), "灭", font=F(int(s * 0.7), True), fill="#d93025", anchor="mm")


def sign_firstaid(d, xy, s=24):
    x, y = xy
    d.rectangle([x - s, y - s, x + s, y + s], fill="#1e8e3e", outline="black", width=3)
    t = s * 0.62
    d.rectangle([x - t * 0.3, y - t, x + t * 0.3, y + t], fill="white")
    d.rectangle([x - t, y - t * 0.3, x + t, y + t * 0.3], fill="white")


def sign_exit(d, xy, w=54, h=26, label="安全出口"):
    x, y = xy
    d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], radius=5, fill="#1e8e3e")
    d.text((x, y), label, font=F(16, True), fill="white", anchor="mm")


def door(d, box, orient="h", swing=40, color="#1a3a6b"):
    """画门（开口+门扇弧线）。box: 门所在墙上的开口位置(两点)"""
    (x0, y0), (x1, y1) = box
    d.line([(x0, y0), (x1, y1)], fill="white", width=10)
    d.line([(x0, y0), (x1, y1)], fill="#333333", width=3)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if orient == "h":
        d.arc([mx - swing, my - swing, mx + swing, my + swing], 180, 270, fill=color, width=3)
        d.line([(mx, my), (mx, my - swing)], fill=color, width=3)
    else:
        d.arc([mx - swing, my - swing, mx + swing, my + swing], 90, 180, fill=color, width=3)
        d.line([(mx, my), (mx - swing, my)], fill=color, width=3)


def window(d, box, color="#1a73e8"):
    (x0, y0), (x1, y1) = box
    if y0 == y1:
        d.line([(x0, y0), (x1, y1)], fill="white", width=10)
        d.line([(x0, y0), (x1, y1)], fill=color, width=5)
    else:
        d.line([(x0, y0), (x1, y1)], fill="white", width=10)
        d.line([(x0, y0), (x1, y1)], fill=color, width=5)


def server_rack(d, x, y, w=90, h=170, label="", n_units=8, color="#3c5064"):
    rrect(d, [x, y, x + w, y + h], r=4, fill="#eef2f6", outline=color, width=3)
    uh = (h - 20) / n_units
    for i in range(n_units):
        uy = y + 10 + i * uh
        d.rectangle([x + 8, uy + 2, x + w - 8, uy + uh - 3], fill=color)
        d.ellipse([x + w - 20, uy + uh / 2 - 3, x + w - 14, uy + uh / 2 + 3], fill="#34a853")
    if label:
        text_c(d, (x + w / 2, y + h + 14), label, F(15, True))


def workstation(d, x, y, s=70, label="", dual=False):
    rrect(d, [x, y, x + s, y + s * 0.62], r=4, fill="#e8f0fe", outline="#1a3a6b", width=3)
    d.rectangle([x + s * 0.42, y + s * 0.62, x + s * 0.58, y + s * 0.8], fill="#9aa0a6")
    d.rectangle([x + s * 0.2, y + s * 0.8, x + s * 0.8, y + s * 0.88], fill="#5f6368")
    if dual:
        rrect(d, [x + s * 1.05, y, x + s * 2.05, y + s * 0.62], r=4, fill="#e8f0fe", outline="#1a3a6b", width=3)
    if label:
        text_c(d, (x + s * (1.5 if dual else 0.5), y + s + 12), label, F(14, True))


def save_png(img, path):
    img.save(path)
    print("saved", path)
