# -*- coding: utf-8 -*-
"""
menu_live_test.py — 「指针停在菜单项上拖动时，滑块是否**实时重绘**」的回归测试

为什么单独一个文件：
    这是曾经真实出现过的 bug —— 拖动时配置里的值确实在变（透明度真的跟着改），
    但**菜单项上的数值与进度条始终不刷新**，只有指针移出该项后菜单因高亮变化
    重绘一次，显示才「追上」。
    根因：WH_MSGFILTER 回调里拿到的 msg.hwnd 不一定是菜单窗口，
    代码把 shell 的 SystemUserAdapterWindowClass 当成菜单窗口缓存了，
    于是 InvalidateRect/RedrawWindow 全打在无关窗口上，真正的 #32768 从未被失效。
    menu_e2e_test.py 只校验「配置值变了」，所以当时**没能发现**这个渲染问题。
    本文件补上渲染层面的断言。

抓屏为什么用 ctypes 而不是 PIL：
    PIL 的 ImageGrab 会扰动这条本来就敏感的合成鼠标序列（会让菜单提前关闭、
    或让后续 SetCursorPos 的坐标系对不上），实测同一份代码两次运行结果完全不同。
    这里改用 GetDC + BitBlt + GetDIBits 直接读屏幕像素：纯读操作、无副作用、
    单次 <5ms，而且顺带去掉了对 Pillow 的依赖，任何 Python 都能跑。

判定方式（只看屏幕像素，不依赖内部实现）：
    1. 光标停在滑块上按下并保持按住 → 截图 A
    2. 保持按住、把光标移到同一项内的另一处（**指针始终不离开该项**）→ 截图 B
    3. A 与 B 必须有明显像素差异 —— 差异只能来自数值与进度条的重绘
       （两张图都是「高亮 + 指针在项内 + 按键按住」，排除了高亮变化造成的假阳性）
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import tempfile
import time
from ctypes import byref

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win_glass as wg                                   # noqa: E402

u = wg.user32
g = wg.gdi32

u.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
u.FindWindowW.restype = wt.HWND
u.GetSystemMetrics.argtypes = [ctypes.c_int]
u.GetSystemMetrics.restype = ctypes.c_int
u.mouse_event.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_void_p]
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004

# --- 抓屏绑定 ---
SRCCOPY, DIB_RGB_COLORS = 0x00CC0020, 0
u.GetDC.argtypes = [wt.HWND]
u.GetDC.restype = wt.HDC
u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
u.ReleaseDC.restype = ctypes.c_int
g.CreateCompatibleDC.argtypes = [wt.HDC]
g.CreateCompatibleDC.restype = wt.HDC
g.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
g.CreateCompatibleBitmap.restype = wt.HBITMAP
g.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                     wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
g.BitBlt.restype = wt.BOOL
g.DeleteDC.argtypes = [wt.HDC]
g.DeleteObject.argtypes = [wt.HGDIOBJ]
g.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
                        ctypes.c_void_p, wt.UINT]
g.GetDIBits.restype = ctypes.c_int


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_out")
PASS, FAIL = [], []

# 判定阈值：单像素 R/G/B 三通道绝对差之和超过它才算「真的变了」。
# 取 30 是为了滤掉字体抗锯齿带来的 1~2 级抖动。
PIXEL_EPS = 30
# 至少这么多像素发生变化才算「重绘了」。改 1% 就有十几像素。
MIN_CHANGED = 8


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("   " + detail if detail else ""))


def menu_hwnd():
    return int(u.FindWindowW("#32768", None) or 0)


def item_rect(hmenu, pos, owner):
    rc = wt.RECT()
    for wnd in (menu_hwnd() or None, owner, None):
        if u.GetMenuItemRect(wnd, hmenu, pos, byref(rc)):
            return rc
    return None


def rstr(r):
    return "None" if r is None else "(%d,%d)-(%d,%d) w=%d h=%d" % (
        r.left, r.top, r.right, r.bottom, r.right - r.left, r.bottom - r.top)


def sub(rc, top_off, bot_off):
    r = wt.RECT()
    r.left, r.right = rc.left, rc.right
    r.top, r.bottom = rc.top + top_off, rc.top + bot_off
    return r


def capture(rc):
    """BitBlt 抓屏，返回 (w, h, bytes)。像素为 BGRA、自上而下。"""
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w <= 0 or h <= 0:
        return 0, 0, b""
    hdc = u.GetDC(None)
    mem = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    old = g.SelectObject(mem, bmp)
    try:
        g.BitBlt(mem, 0, 0, w, h, hdc, rc.left, rc.top, SRCCOPY)
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = w
        bi.biHeight = -h                 # 负数 = 自上而下，省一次翻转
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0             # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        g.GetDIBits(mem, bmp, 0, h, buf, byref(bi), DIB_RGB_COLORS)
        return w, h, buf.raw
    finally:
        g.SelectObject(mem, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mem)
        u.ReleaseDC(None, hdc)


def changed_pixels(a, b):
    """两张 BGRA 抓屏里「肉眼可见地变了」的像素数。a/b 为 (w,h,bytes)。"""
    wa, ha, ba = a
    wb, hb, bb = b
    if wa != wb or ha != hb or not ba:
        return -1
    n = 0
    for i in range(0, wa * ha * 4, 4):
        if (abs(ba[i] - bb[i]) + abs(ba[i + 1] - bb[i + 1]) + abs(ba[i + 2] - bb[i + 2])) > PIXEL_EPS:
            n += 1
    return n


def save_raw(path, cap):
    """存成 PNG（有 Pillow 就存，没有就跳过）。"""
    try:
        from PIL import Image
    except Exception:
        return False
    w, h, raw = cap
    if not raw:
        return False
    img = Image.frombuffer("RGB", (w, h), raw, "raw", "BGRX", 0, 1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return True


def main():
    tmp = tempfile.mkdtemp(prefix="winglass_live_")
    cfg_path = os.path.join(tmp, "config.json")
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 74)
    print("滑块实时重绘 · 回归测试（指针停在菜单项上拖动）")
    print("=" * 74)

    cfg = wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00, cfg_path=cfg_path)
    eng = wg.GlassEngine(cfg)
    tray = wg.TrayIcon(eng)
    eng.restore_now = lambda: None
    eng.request_quit = lambda: None
    eng.set_paused = lambda f: None

    if not tray.start():
        print("托盘窗口创建失败。")
        return 1

    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    anchor = (max(60, sw // 2 - 420), max(60, sh // 3))
    u.SetCursorPos(*anchor)
    time.sleep(0.2)
    u.PostMessageW(tray.hwnd, wg.WM_TRAYICON, 1, wg.WM_RBUTTONUP)

    # 轮询等菜单，别用固定 sleep：桌面一忙 1.2s 就不够了（踩过这个 flake）
    got = 0
    for _ in range(120):                     # 最多等 6s
        got = menu_hwnd()
        if got:
            break
        time.sleep(0.05)
    if got:
        time.sleep(0.4)

    if not menu_hwnd():
        print("菜单没弹出来，无法继续。")
        tray._uninstall_menu_hook()
        return 1

    sliders = tray._sliders
    if not sliders:
        print("菜单里没有滑块，无法继续。")
        return 1
    sl = sliders[0]
    rc = item_rect(sl.hmenu, sl.pos, tray.hwnd)
    if rc is None:
        print("取不到滑块矩形，无法继续。")
        return 1

    mrc = wt.RECT()
    u.GetWindowRect(menu_hwnd(), byref(mrc))
    app_rc = tray._item_rect(sl)
    print("  菜单窗口 = 0x%X  菜单矩形 = %s" % (menu_hwnd(), rstr(mrc)))
    print("  测试取的项矩形 = %s" % rstr(rc))
    print("  程序取的项矩形 = %s" % rstr(app_rc))
    check("测试与程序取到同一个菜单项矩形",
          app_rc is not None and app_rc.left == rc.left and app_rc.right == rc.right,
          "" if app_rc else "程序未取到")

    # 项内两个子区域：数值行（顶部）、进度条行（底部）
    ih = rc.bottom - rc.top
    title_rc = sub(rc, 3, 20)
    bar_rc = sub(rc, ih - 24, ih)

    # 手柄行程两端内缩 SLIDER_THUMB_INSET（圆形手柄不越界），期望值要跟着走
    inset = wg.SLIDER_THUMB_INSET
    x0 = rc.left + wg.SLIDER_PAD_X + inset
    x1 = rc.right - wg.SLIDER_PAD_X - inset
    span = max(1, x1 - x0)
    ty = (rc.top + rc.bottom) // 2
    xa = x0 + int(span * 0.15)
    xb = x0 + int(span * 0.80)

    def pct_at(x):
        frac = max(0.0, min(1.0, (x - x0) / span))
        return max(sl.lo, min(sl.hi, sl.lo + int(round(frac * (sl.hi - sl.lo)))))

    # ---------- 1) 悬停（不按下） ----------
    u.SetCursorPos(xa, ty)
    time.sleep(0.35)
    a_title, a_bar = capture(title_rc), capture(bar_rc)
    print("  悬停于 x=%d（值 %d%%）" % (xa, int(sl.get())))

    # ---------- 2) 按下并保持按住（指针仍在项内） ----------
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.3)
    press_val = int(sl.get())
    b_title, b_bar = capture(title_rc), capture(bar_rc)
    check("按下即跳到光标位置（点击即定位）", press_val == pct_at(xa),
          "%d%% (期望 %d%%)" % (press_val, pct_at(xa)))

    # ---------- 3) 保持按住、移到同项内另一处；指针不离开该项 ----------
    u.SetCursorPos(xb, ty)
    time.sleep(0.35)
    drag_val = int(sl.get())
    c_title, c_bar = capture(title_rc), capture(bar_rc)
    check("按住拖动时值实时变化", drag_val == pct_at(xb) and drag_val != press_val,
          "%d%% -> %d%% (期望 %d%%)" % (press_val, drag_val, pct_at(xb)))

    # ---------- 4) 关键断言：画面必须跟着重绘 ----------
    n_title = changed_pixels(b_title, c_title)
    n_bar = changed_pixels(b_bar, c_bar)
    check("按住拖动时【数值文字】实时重绘（指针未离开该项）", n_title >= MIN_CHANGED,
          "变化像素 %d（阈值 %d）" % (n_title, MIN_CHANGED))
    check("按住拖动时【进度条】实时重绘（指针未离开该项）", n_bar >= MIN_CHANGED,
          "变化像素 %d（阈值 %d）" % (n_bar, MIN_CHANGED))
    check("整场拖动菜单始终开着", menu_hwnd() != 0)

    save_raw(os.path.join(OUT_DIR, "live_press_title.png"), b_title)
    save_raw(os.path.join(OUT_DIR, "live_drag_title.png"), c_title)
    save_raw(os.path.join(OUT_DIR, "live_press_bar.png"), b_bar)
    save_raw(os.path.join(OUT_DIR, "live_drag_bar.png"), c_bar)

    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.2)

    # ---------- 5) 收尾：点菜单外部应正常关闭 ----------
    u.SetCursorPos(30, sh - 40)
    time.sleep(0.2)
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.08)
    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.8)
    check("点菜单外部后正常关闭", menu_hwnd() == 0)

    u.PostMessageW(tray.hwnd, wg.WM_CLOSE, 0, 0)
    time.sleep(0.5)

    print("\n" + "=" * 74)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("  FAILED: %s" % f)
    print("证据图目录：%s" % OUT_DIR)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
