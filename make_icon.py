# -*- coding: utf-8 -*-
"""生成 win_glass 图标（月牙 + 半透明窗口），输出 icon.ico。"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icon.ico")

S = 1024
BG = (27, 33, 56, 255)          # 深靛蓝
WIN_SOLID = (255, 255, 255, 235)
WIN_FAINT = (255, 255, 255, 90)
MOON = (255, 232, 160, 255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角底板
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=BG)

# 两个叠放的"窗口"：下面那个是未聚焦的半透明窗口，上面那个是聚焦的实心窗口
def win_box(x, y, w, h, fill, bar):
    d.rounded_rectangle([x, y, x + w, y + h], radius=int(S * 0.045), fill=fill)
    # 标题栏
    d.rounded_rectangle([x, y, x + w, y + int(h * 0.22)], radius=int(S * 0.045), fill=bar)

k = S * 0.055
win_box(S * 0.30 + k, S * 0.34 + k, S * 0.42, S * 0.34, WIN_FAINT, (255, 255, 255, 120))
win_box(S * 0.30, S * 0.30, S * 0.42, S * 0.34, WIN_SOLID, (205, 214, 240, 255))

# 月牙（用两圆相减）
mx, my, r = S * 0.745, S * 0.275, S * 0.135
moon_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
md = ImageDraw.Draw(moon_layer)
md.ellipse([mx - r, my - r, mx + r, my + r], fill=MOON)
cut = S * 0.062
md.ellipse([mx - r + cut, my - r - cut * 0.35, mx + r + cut, my + r - cut * 0.35],
           fill=(0, 0, 0, 0))
img = Image.alpha_composite(img, moon_layer)

# 导出多尺寸 ico
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(OUT, format="ICO", sizes=sizes)
print("已生成:", OUT)
for s in sizes:
    print("   %dx%d" % s)
