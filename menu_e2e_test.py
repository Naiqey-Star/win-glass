# -*- coding: utf-8 -*-
"""
menu_e2e_test.py — 托盘右键菜单滑块的实机验证

关键设计：**不启动引擎主循环**。只把 `TrayIcon` 挂在一个 GlassEngine 实例上
（引擎的 run() 不调用），所以整个测试不会去改桌面上任何真实窗口的透明度，
可以放心反复跑。

验证链路（每一条都是「真的做了这件事」，不是「函数返回了 True」）：
  1. 弹出真实菜单，截屏 → 肉眼可见两个滑块
  2. 用合成鼠标在滑块上按下-拖动-抬起 → 菜单**不关闭**（吞消息生效）、
     配置里的百分比按 x 坐标精确变化
  3. 滚轮 → ±1%
  4. 左右方向键 → ±1%（唯一能精确到 1% 的操作）
  5. 调完的值真的写进了 config.json
  6. 点菜单外部 → 菜单正常关闭（吞消息没有把菜单卡死）
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import tempfile
import time
from ctypes import byref

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win_glass as wg                                   # noqa: E402

u = wg.user32
k = wg.kernel32

u.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
u.FindWindowW.restype = wt.HWND
u.GetSystemMetrics.argtypes = [ctypes.c_int]
u.GetSystemMetrics.restype = ctypes.c_int
u.SetForegroundWindow.argtypes = [wt.HWND]
u.SetForegroundWindow.restype = wt.BOOL
u.mouse_event.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_void_p]
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_WHEEL = 0x0800
VK_LEFT, VK_RIGHT, KEYEVENTF_KEYUP = 0x25, 0x27, 0x0002
u.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wt.DWORD, ctypes.c_void_p]

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_out")

PASS, FAIL = [], []


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


def click(x, y, down_only=False):
    u.SetCursorPos(x, y)
    time.sleep(0.08)
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.06)
    if not down_only:
        u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
        time.sleep(0.06)


def expected_pct(x, rc, lo, hi):
    """独立算一遍期望值（不复用被测代码的映射函数）。"""
    x0 = rc.left + wg.SLIDER_PAD_X
    x1 = rc.right - wg.SLIDER_PAD_X - 1
    frac = (x - x0) / max(1, (x1 - x0))
    frac = 0.0 if frac < 0 else (1.0 if frac > 1 else frac)
    return max(lo, min(hi, lo + int(round(frac * (hi - lo)))))


def shot(path, rect=None):
    try:
        from PIL import ImageGrab
    except Exception as e:
        print("      (跳过截图：%s)" % e)
        return False
    img = ImageGrab.grab()
    if rect:
        x0, y0, x1, y1 = rect
        img = img.crop((max(0, x0), max(0, y0), x1, y1))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    print("      截图 -> %s  %s" % (path, img.size))
    return True


def main():
    tmp = tempfile.mkdtemp(prefix="winglass_e2e_")
    cfg_path = os.path.join(tmp, "config.json")
    print("=" * 74)
    print("托盘菜单滑块 · 实机验证")
    print("临时配置：%s" % cfg_path)
    print("=" * 74)

    cfg = wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00, cfg_path=cfg_path)
    eng = wg.GlassEngine(cfg)                 # 只用来承载配置，不跑 run()
    tray = wg.TrayIcon(eng)
    # 记下被调用的引擎动作，别让它真的去还原窗口
    acted = []
    eng.restore_now = lambda: acted.append("restore")
    eng.request_quit = lambda: acted.append("quit")
    eng.set_paused = lambda f: acted.append("paused=%s" % bool(f))

    if not tray.start():
        print("托盘窗口创建失败，无法继续。")
        return 1
    print("托盘窗口 hwnd = 0x%X" % tray.hwnd)

    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    anchor = (max(60, sw // 2 - 420), max(60, sh // 3))
    print("把光标放到 %r 后弹菜单（菜单会出现在这里）" % (anchor,))

    # ---------- 1) 弹出菜单 ----------
    u.SetCursorPos(*anchor)
    time.sleep(0.2)
    u.PostMessageW(tray.hwnd, wg.WM_TRAYICON, 1, wg.WM_RBUTTONUP)
    time.sleep(1.2)

    mhwnd = menu_hwnd()
    check("右键菜单已弹出（找到 #32768 菜单窗口）", bool(mhwnd), "#32768=0x%X" % mhwnd)
    if not mhwnd:
        print("\n菜单没出来，后续无法继续。")
        tray._uninstall_menu_hook()
        return 1

    sliders = tray._sliders
    check("菜单里有 2 个滑块", len(sliders) == 2,
          "实际 %d 个: %s" % (len(sliders), [s.label for s in sliders]))
    if len(sliders) != 2:
        return 1

    rects = []
    for sl in sliders:
        rc = item_rect(sl.hmenu, sl.pos, tray.hwnd)
        rects.append(rc)
        check("能取到「%s」的屏幕矩形" % sl.label, rc is not None,
              "(%d,%d)-(%d,%d)" % (rc.left, rc.top, rc.right, rc.bottom) if rc else "")
    if any(r is None for r in rects):
        return 1

    mrc = wt.RECT()
    u.GetWindowRect(mhwnd, byref(mrc))
    print("      菜单窗口 rect = (%d,%d)-(%d,%d)  宽 %d"
          % (mrc.left, mrc.top, mrc.right, mrc.bottom, mrc.right - mrc.left))
    # 宽度：系统会在 owner-draw 项请求的宽度上再加一段菜单留白（本机实测 +38px），
    # 所以断言是「不小于」，高度才是严格相等的。
    w0 = rects[0].right - rects[0].left
    check("菜单项宽度 >= SLIDER_ITEM_W", w0 >= wg.SLIDER_ITEM_W,
          "%d px（请求 %d，多出来的是菜单留白）" % (w0, wg.SLIDER_ITEM_W))
    check("菜单项高度 == SLIDER_ITEM_H", (rects[0].bottom - rects[0].top) == wg.SLIDER_ITEM_H,
          "%d px" % (rects[0].bottom - rects[0].top))

    pad = 14
    shot(os.path.join(OUT_DIR, "01_menu.png"),
         (mrc.left - pad, mrc.top - pad, mrc.right + pad, mrc.bottom + pad))
    shot(os.path.join(OUT_DIR, "01_menu_full.png"))

    # ---------- 2) 拖动第一个滑块 ----------
    rc, sl = rects[0], sliders[0]
    tx = rc.left + wg.SLIDER_PAD_X + int((rc.right - rc.left - 2 * wg.SLIDER_PAD_X) * 0.72)
    ty = (rc.top + rc.bottom) // 2
    want = expected_pct(tx, rc, sl.lo, sl.hi)
    before = cfg.inactive_pct
    print("\n  拖动「%s」到 x=%d（期望 %d%%，当前 %d%%）" % (sl.label, tx, want, before))

    u.SetCursorPos(rc.left + wg.SLIDER_PAD_X + 4, ty)
    time.sleep(0.1)
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.1)
    u.SetCursorPos(tx, ty)                     # 拖
    time.sleep(0.15)
    check("拖动后菜单仍然开着（点击被吞掉了）", menu_hwnd() == mhwnd,
          "菜单窗口 0x%X" % menu_hwnd())
    check("拖动过程中值已实时变化", cfg.inactive_pct != before,
          "%d%% -> %d%%" % (before, cfg.inactive_pct))
    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.2)
    check("松手后菜单仍然开着", menu_hwnd() == mhwnd)
    check("拖动落点 == 期望 %d%%" % want, cfg.inactive_pct == want,
          "实际 %d%%" % cfg.inactive_pct)

    shot(os.path.join(OUT_DIR, "02_after_drag.png"),
         (mrc.left - pad, mrc.top - pad, mrc.right + pad, mrc.bottom + pad))

    # ---------- 3) 滚轮 ±1%（信息项，不计入通过/失败） ----------
    # 说明：滚轮是否真能进到菜单里取决于系统的消息路由。合成滚轮在自动化里
    # 常常被投递到前台窗口而不是菜单的模态循环，所以这里只报告事实；
    # 处理逻辑本身（lParam 高 16 位才是增量）由 slider_test.py 直接喂消息验证。
    v0 = cfg.inactive_pct
    u.SetCursorPos(tx, ty)
    time.sleep(0.1)
    u.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, 120, None)      # 上滚 +1
    time.sleep(0.25)
    print("      [信息] 滚轮上滚：%d%% -> %d%%（期望 %d%%）"
          % (v0, cfg.inactive_pct, min(sl.hi, v0 + 1)))
    v1 = cfg.inactive_pct
    u.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, ctypes.c_ulong(-120).value, None)
    time.sleep(0.25)
    print("      [信息] 滚轮下滚：%d%% -> %d%%（期望 %d%%）"
          % (v1, cfg.inactive_pct, max(sl.lo, v1 - 1)))

    # ---------- 4) 方向键 ±1% ----------
    # 先用鼠标点一下滑块把它变成高亮项（点击被吞，但菜单会把光标位置当作高亮项）
    u.SetCursorPos(tx, ty)
    time.sleep(0.15)
    v2 = cfg.inactive_pct
    u.keybd_event(VK_RIGHT, 0, 0, None)
    u.keybd_event(VK_RIGHT, 0, KEYEVENTF_KEYUP, None)
    time.sleep(0.25)
    after_right = cfg.inactive_pct
    u.keybd_event(VK_LEFT, 0, 0, None)
    u.keybd_event(VK_LEFT, 0, KEYEVENTF_KEYUP, None)
    time.sleep(0.25)
    after_left = cfg.inactive_pct
    if after_right == min(sl.hi, v2 + 1) and after_left == after_right - 1:
        check("右方向键 +1%%、左方向键 -1%%", True,
              "%d%% -> %d%% -> %d%%" % (v2, after_right, after_left))
    else:
        check("右方向键 +1%%、左方向键 -1%%", False,
              "%d%% -> %d%% -> %d%%（该滑块此刻可能未被高亮，属可选增强）"
              % (v2, after_right, after_left))

    # ---------- 5) 拖动第二个滑块（聚焦最高透明度） ----------
    rc2, sl2 = rects[1], sliders[1]
    tx2 = rc2.left + wg.SLIDER_PAD_X + int((rc2.right - rc2.left - 2 * wg.SLIDER_PAD_X) * 0.45)
    ty2 = (rc2.top + rc2.bottom) // 2
    want2 = expected_pct(tx2, rc2, sl2.lo, sl2.hi)
    print("\n  拖动「%s」到 x=%d（期望 %d%%）" % (sl2.label, tx2, want2))
    click(tx2, ty2)
    time.sleep(0.3)
    check("聚焦滑块落点 == 期望 %d%%" % want2, cfg.active_pct == want2,
          "实际 %d%%" % cfg.active_pct)
    check("非聚焦滑块取值未被连带改掉",
          cfg.inactive_pct == after_left,
          "%d%% (期望 %d%%)" % (cfg.inactive_pct, after_left))

    shot(os.path.join(OUT_DIR, "03_both.png"),
         (mrc.left - pad, mrc.top - pad, mrc.right + pad, mrc.bottom + pad))

    # ---------- 6) 落盘 ----------
    tray.engine.save_cfg(force=True)
    time.sleep(0.4)
    saved = json.load(open(cfg_path, encoding="utf-8")) if os.path.isfile(cfg_path) else {}
    check("config.json 已写出", bool(saved), json.dumps(saved, ensure_ascii=False))
    check("落盘值与内存一致",
          saved.get("inactive_percent") == cfg.inactive_pct
          and saved.get("active_percent") == cfg.active_pct,
          "文件 %s / 内存 %d,%d" % (saved, cfg.inactive_pct, cfg.active_pct))
    check("落盘的是整数（无小数点）",
          isinstance(saved.get("inactive_percent"), int)
          and isinstance(saved.get("active_percent"), int))

    # ---------- 7) 点菜单外部应正常关闭 ----------
    u.SetCursorPos(30, sh - 40)
    time.sleep(0.2)
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.08)
    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.8)
    check("点菜单外部后菜单正常关闭", menu_hwnd() == 0, "菜单窗口 0x%X" % menu_hwnd())
    check("整场测试没有触发引擎还原/退出（未影响桌面窗口）",
          acted == [], repr(acted))

    # 收尾：清掉托盘图标
    u.PostMessageW(tray.hwnd, wg.WM_CLOSE, 0, 0)
    time.sleep(0.6)

    print("\n消息到达计数（诊断）：%r" % (tray.msg_counts,))
    print("探针明细 (kind, CtlType, itemID, w, h)：")
    for row in tray.msg_probe[:30]:
        print("   %r" % (row,))
    print("\n" + "=" * 74)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("  FAILED: %s" % f)
    print("截图目录：%s" % OUT_DIR)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
