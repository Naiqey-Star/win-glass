# -*- coding: utf-8 -*-
"""复现 / 验证：最大化窗口被误判为「全屏」的矩形取证。

自建一个 tkinter 窗口，依次摆成三种状态，把「IsZoomed / 窗口矩形 / 监视器矩形」
三者摊开对比，并打印当前 `_is_fullscreen()` 与 `target_for()` 的结论。

只操作自己创建的窗口，不碰任何现有程序。
"""
import ctypes
import os
import sys
import time
from ctypes import byref

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win_glass as wg  # noqa: E402


def monitor_rects(hwnd):
    mon = wg.user32.MonitorFromWindow(hwnd, wg.MONITOR_DEFAULTTONEAREST)
    mi = wg.MONITORINFO()
    mi.cbSize = ctypes.sizeof(wg.MONITORINFO)
    if not mon or not wg.user32.GetMonitorInfoW(mon, byref(mi)):
        return None, None
    return mi.rcMonitor, mi.rcWork


def fmt_rect(r):
    return "(%6d,%6d,%6d,%6d) %4dx%-4d" % (
        r.left, r.top, r.right, r.bottom, r.right - r.left, r.bottom - r.top)


def frame_metrics():
    """缩放边框厚度 —— 最大化窗口越过屏幕边缘的那几像素就来自这里。"""
    u = wg.user32
    for name in ("GetSystemMetrics",):
        pass
    SM_CXSIZEFRAME, SM_CYSIZEFRAME = 32, 33
    SM_CXPADDEDBORDER = 92
    u.GetSystemMetrics.restype = ctypes.c_int
    cx = u.GetSystemMetrics(SM_CXSIZEFRAME)
    cy = u.GetSystemMetrics(SM_CYSIZEFRAME)
    pad = u.GetSystemMetrics(SM_CXPADDEDBORDER)
    return cx, cy, pad


def dump(root, label, cfg):
    hwnd = wg._h(wg.user32.GetAncestor(root.winfo_id(), wg.GA_ROOT)) or wg._h(root.winfo_id())
    rc = wg.wt.RECT()
    wg.user32.GetWindowRect(hwnd, byref(rc))
    mon, work = monitor_rects(hwnd)
    zoomed = bool(wg.user32.IsZoomed(hwnd))
    fs_old = wg._is_fullscreen(hwnd, rc)
    top, z2, fs2 = wg.read_window_state(hwnd)

    print("\n" + "-" * 78)
    print("[%s]  HWND=0x%X" % (label, hwnd))
    print("  IsZoomed            = %s" % zoomed)
    print("  窗口矩形            = %s" % fmt_rect(rc))
    if mon:
        print("  监视器 rcMonitor    = %s" % fmt_rect(mon))
        print("  监视器 rcWork       = %s" % fmt_rect(work))
        print("  窗口 - rcMonitor    = L%+d T%+d R%+d B%+d   (正数=越出屏幕)"
              % (rc.left - mon.left, rc.top - mon.top,
                 rc.right - mon.right, rc.bottom - mon.bottom))
        print("  窗口 - rcWork       = L%+d T%+d R%+d B%+d"
              % (rc.left - work.left, rc.top - work.top,
                 rc.right - work.right, rc.bottom - work.bottom))
    print("  _is_fullscreen()    = %s      <-- 当前实现" % fs_old)
    print("  read_window_state() = top=%s zoomed=%s fullscreen=%s" % (top, z2, fs2))

    dst, why, _ = wg.target_for(cfg, hwnd, is_fg=False, top=top, zoomed=z2, fullscreen=fs2)
    print("  → target_for 结论   = %.0f%%  理由=%s" % (dst * 100, why))
    return dict(hwnd=hwnd, rc=rc, mon=mon, zoomed=zoomed, fs_old=fs_old, fs=fs2, why=why, dst=dst)


def settle(root, sec=0.45):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def main():
    try:
        import tkinter as tk
    except Exception as e:
        print("需要 tkinter：%s" % e)
        return 1

    cx, cy, pad = frame_metrics()
    print("=" * 78)
    print("缩放边框度量：SM_CXSIZEFRAME=%d  SM_CYSIZEFRAME=%d  SM_CXPADDEDBORDER=%d"
          % (cx, cy, pad))
    print("（最大化时窗口矩形会越过屏幕边缘约 %d px —— 这就是嫌疑所在）" % (cx + pad))
    print("=" * 78)

    cfg = wg.GlassConfig(active_alpha=0.80, inactive_alpha=0.40)
    print("测试配置：最高（聚焦/最大化/置顶）= %.0f%%   最低 = %.0f%%   全屏恒 = %.0f%%"
          % (cfg.active_alpha * 100, cfg.inactive_alpha * 100, cfg.fullscreen_alpha * 100))

    root = tk.Tk()
    root.title("win_glass fs probe")
    root.geometry("520x320+120+120")
    tk.Label(root, text="fs_probe", font=("Microsoft YaHei", 16)).pack(expand=True)
    settle(root)

    r_normal = dump(root, "A. 普通窗口", cfg)

    root.state("zoomed")
    settle(root)
    r_max = dump(root, "B. 最大化（用户按了最大化按钮）", cfg)

    root.state("normal")
    settle(root, 0.3)
    root.attributes("-fullscreen", True)
    settle(root)
    r_fs = dump(root, "C. 真正的全屏（-fullscreen，等价 F11）", cfg)

    root.attributes("-fullscreen", False)
    settle(root, 0.3)
    root.destroy()

    print("\n" + "=" * 78)
    print("判定")
    print("=" * 78)
    ok = True

    if r_max["zoomed"]:
        bad = r_max["fs_old"]
        print("  [%s] 最大化窗口的 _is_fullscreen() = %s（期望 False）" %
              ("FAIL" if bad else "PASS", r_max["fs_old"]))
        ok &= not bad
        exp = cfg.active_alpha * 100
        got = r_max["dst"] * 100
        print("  [%s] 最大化窗口目标 = %.0f%%（期望 %.0f%% = 用户设定的最高透明度）" %
              ("FAIL" if abs(got - exp) > 0.5 else "PASS", got, exp))
        ok &= abs(got - exp) <= 0.5
    else:
        print("  [SKIP] 本机 tk 最大化没触发 IsZoomed，无法复现（少见）")

    fs_ok = r_fs["fs"]
    print("  [%s] 真全屏窗口的 fullscreen = %s（期望 True）" %
          ("PASS" if fs_ok else "FAIL", fs_ok))
    ok &= fs_ok
    got = r_fs["dst"] * 100
    print("  [%s] 真全屏窗口目标 = %.0f%%（期望 100%%）" %
          ("PASS" if abs(got - 100) < 0.5 else "FAIL", got))
    ok &= abs(got - 100) < 0.5

    print("\n结论：%s" % ("全部符合预期 ✅" if ok else "存在不符合项 ❌"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
