# -*- coding: utf-8 -*-
"""
probe_map.py — 一条一条记录菜单相关消息的「消息号 + lParam 原始字节」。

要回答的唯一问题：哪个消息号拿到的是「待填宽高的 MEASUREITEMSTRUCT」，
哪个拿到的是「带 rcItem/hDC 的 DRAWITEMSTRUCT」。
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win_glass as wg                                   # noqa: E402

u = wg.user32
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u.GetSystemMetrics.argtypes = [ctypes.c_int]
u.GetSystemMetrics.restype = ctypes.c_int
u.mouse_event.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_void_p]

NAMES = {
    0x002B: "WM_MEASUREITEM",
    0x002C: "WM_DRAWITEM",
    0x0116: "WM_INITMENUPOPUP",
    0x0117: "WM_MENUSELECT",
    0x011F: "WM_MENUCHAR",
    0x0121: "WM_ENTERMENULOOP",
    0x0122: "WM_EXITMENULOOP",
    0x0123: "WM_CONTEXTMENU",
}
ROWS = []


class ProbeTray(wg.TrayIcon):
    def _on_msg(self, hwnd, msg, wp, lp):
        if msg in (0x002B, 0x002C) and len(ROWS) < 16:
            raw = ctypes.string_at(lp, 64) if lp else b""
            i32 = []
            for off in range(0, 32, 4):
                i32.append(int.from_bytes(raw[off:off + 4], "little",
                                          signed=True))
            ROWS.append((msg, NAMES.get(msg, hex(msg)), lp, i32,
                         " ".join("%02X" % b for b in raw[32:64])))
        return super()._on_msg(hwnd, msg, wp, lp)


def main():
    cfg = wg.GlassConfig(cfg_path="")
    eng = wg.GlassEngine(cfg)
    eng.restore_now = lambda: None
    eng.request_quit = lambda: None
    eng.set_paused = lambda f: None
    tray = ProbeTray(eng)
    if not tray.start():
        print("托盘创建失败")
        return 1
    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    u.SetCursorPos(max(60, sw // 2 - 420), max(60, sh // 3))
    time.sleep(0.3)
    u.PostMessageW(tray.hwnd, wg.WM_TRAYICON, 1, wg.WM_RBUTTONUP)
    time.sleep(1.4)
    u.SetCursorPos(30, sh - 40)
    u.mouse_event(0x0002, 0, 0, 0, None)
    time.sleep(0.05)
    u.mouse_event(0x0004, 0, 0, 0, None)
    time.sleep(0.8)
    u.PostMessageW(tray.hwnd, wg.WM_CLOSE, 0, 0)
    time.sleep(0.4)

    print("\n" + "=" * 78)
    print("消息号            lParam       前 8 个 int32                             后32字节")
    for msg, name, lp, i32, tail in ROWS:
        print("0x%04X %-16s 0x%X  %s   %s" % (msg, name, lp, i32, tail))
    print("=" * 78)
    print("计数: %r" % (tray.msg_counts,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
