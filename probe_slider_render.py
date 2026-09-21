# -*- coding: utf-8 -*-
"""probe_slider_render.py — 把音量条式滑块离屏渲染成 PNG，用眼睛确认观感。

不弹菜单、不动桌面窗口，纯离屏 DIB 绘制。
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win_glass as wg                                   # noqa: E402

g = wg.gdi32
u = wg.user32

W, H = wg.SLIDER_ITEM_W, wg.SLIDER_ITEM_H
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_out")


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


u.GetDC.argtypes = [wt.HWND]
u.GetDC.restype = wt.HDC
u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
g.CreateCompatibleDC.argtypes = [wt.HDC]
g.CreateCompatibleDC.restype = wt.HDC
g.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
g.CreateCompatibleBitmap.restype = wt.HBITMAP
g.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
                        ctypes.POINTER(BITMAPINFOHEADER), wt.UINT]
g.GetDIBits.restype = ctypes.c_int
g.DeleteDC.argtypes = [wt.HDC]
g.DeleteObject.argtypes = [wt.HGDIOBJ]

STATES = [
    ("常态 5%（最左端）", 0, 5, "非聚焦最低透明度", 5, 95, False),
    ("常态 40%（默认）", 0, 40, "非聚焦最低透明度", 5, 95, False),
    ("常态 95%（最右端）", 0, 95, "非聚焦最低透明度", 5, 95, False),
    ("聚焦滑块 100%", 0, 100, "聚焦最高透明度", 5, 100, False),
    ("悬停/拖动 60%（手柄放大）", 0, 60, "非聚焦最低透明度", 5, 95, True),
    ("选中行 60%（强调色背景）", wg.ODS_SELECTED, 60, "非聚焦最低透明度", 5, 95, True),
    ("禁用 40%", wg.ODS_DISABLED, 40, "非聚焦最低透明度", 5, 95, False),
]
LANE_H = H + 22          # 每条留出标题行


def render(state, pct, label, lo, hi, hot):
    screen = u.GetDC(None)
    dc = g.CreateCompatibleDC(screen)
    bmp = g.CreateCompatibleBitmap(screen, W, LANE_H)
    old = g.SelectObject(dc, bmp)
    try:
        bg = wg.COLOR_HIGHLIGHT if (state & wg.ODS_SELECTED) else wg.COLOR_MENU
        u.FillRect(dc, ctypes.byref(wt.RECT(0, 0, W, LANE_H)), u.GetSysColorBrush(bg))
        # 档位标题，方便对号入座
        r1 = wt.RECT(wg.SLIDER_PAD_X, 3, W - wg.SLIDER_PAD_X, 19)
        g.SetBkMode(dc, wg.TRANSPARENT)
        g.SetTextColor(dc, u.GetSysColor(wg.COLOR_MENUTEXT))
        g.SelectObject(dc, wg._menu_font())
        s = "state=0x%02X  hot=%s  pct=%d" % (state, hot, pct)
        u.DrawTextW(dc, s, -1, ctypes.byref(r1), wg.DT_LEFT | wg.DT_VCENTER | wg.DT_SINGLELINE)

        dis = wg.DRAWITEMSTRUCT()
        dis.CtlType = wg.ODT_MENU
        dis.itemID = wg.CMD_SLIDE_INACTIVE
        dis.itemState = state
        dis.hDC = dc
        dis.rcItem = wt.RECT(0, 20, W, 20 + H)
        wg.draw_menu_slider(dis, label, lo, hi, pct, hot=hot)

        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = W
        bi.biHeight = -LANE_H
        bi.biPlanes = 1
        bi.biBitCount = 32
        buf = ctypes.create_string_buffer(W * LANE_H * 4)
        g.GetDIBits(dc, bmp, 0, LANE_H, buf, ctypes.byref(bi), 0)
        return buf.raw
    finally:
        g.SelectObject(dc, old)
        g.DeleteObject(bmp)
        g.DeleteDC(dc)
        u.ReleaseDC(None, screen)


def main():
    raws = []
    for name, state, pct, label, lo, hi, hot in STATES:
        raws.append((name, render(state, pct, label, lo, hi, hot)))

    try:
        from PIL import Image
        imgs = [Image.frombuffer("RGB", (W, LANE_H), raw, "raw", "BGRX", 0, 1)
                for _, raw in raws]
        canvas = Image.new("RGB", (W, LANE_H * len(imgs)), (255, 255, 255))
        for i, im in enumerate(imgs):
            canvas.paste(im, (0, i * LANE_H))
        os.makedirs(OUT, exist_ok=True)
        p = os.path.join(OUT, "slider_render.png")
        canvas.resize((W * 2, LANE_H * len(imgs) * 2), Image.NEAREST).save(p)
        print("已保存: %s" % p)
        print("自上而下依次是：")
        for i, (name, _) in enumerate(raws):
            print("   第%d条  %s" % (i + 1, name))
    except Exception as e:
        print("存图失败:", e)

    rc = wt.RECT(0, 0, W, H)
    print("\n几何：轨道 %d..%d（厚 %d），圆心范围 %d..%d，半径 %d/%d" % (
        wg.SLIDER_PAD_X, W - wg.SLIDER_PAD_X, wg.SLIDER_TRACK_H,
        wg.SLIDER_PAD_X + wg.SLIDER_THUMB_INSET,
        W - wg.SLIDER_PAD_X - wg.SLIDER_THUMB_INSET,
        wg.SLIDER_THUMB_R, wg.SLIDER_THUMB_R_HOT))
    for p in (5, 40, 95):
        print("   pct=%3d -> 圆心 x=%d" % (p, wg.pct_to_thumb_x(p, 5, 95, rc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
