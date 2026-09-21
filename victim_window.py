# -*- coding: utf-8 -*-
"""
测试窗口（win_glass 验证用）。

用法: victim_window.py <标题> <x> <y> <存活秒数> [置顶抖动间隔秒] [退出时交还焦点的标题前缀]
  · 第 5 参数 >0  : 周期性切换 -topmost，压测「置顶状态轮询」路径
  · 第 6 参数非空: 存活结束时显式把前台焦点交还给该前缀的窗口
                   （Windows 前台锁会拒绝后台进程抢焦点，必须 AllowSetForegroundWindow）
"""
import ctypes
import ctypes.wintypes as wt
import sys
import tkinter as tk

title = sys.argv[1]
x, y = int(sys.argv[2]), int(sys.argv[3])
life = float(sys.argv[4])
churn = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
handoff = sys.argv[6] if len(sys.argv) > 6 else ""

root = tk.Tk()
root.title(title)
root.geometry("380x150+%d+%d" % (x, y))
label = tk.Label(root, text=title, font=("Microsoft YaHei", 15))
label.pack(expand=True)
root.attributes("-topmost", False)

state = {"top": False, "n": 0}


def _unlock_foreground():
    """解除 Windows 前台锁：AllowSetForegroundWindow(ASFW_ANY) + 模拟一次 Alt 敲击。
    否则后台启动的进程调 SetForegroundWindow/focus_force 会被系统直接忽略。"""
    try:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.AllowSetForegroundWindow.argtypes = [wt.DWORD]
        u.AllowSetForegroundWindow(0xFFFFFFFF)          # ASFW_ANY
        VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
        u.keybd_event(VK_MENU, 0, 0, 0)
        u.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    except Exception:
        pass


def grab():
    _unlock_foreground()
    try:
        root.deiconify()
        root.lift()
        root.focus_force()
    except Exception:
        pass


def toggle_top():
    state["top"] = not state["top"]
    state["n"] += 1
    try:
        root.attributes("-topmost", state["top"])
        label.config(text="%s\n置顶=%s (第%d次翻转)"
                     % (title, "是" if state["top"] else "否", state["n"]))
    except Exception:
        pass
    root.after(int(churn * 1000), toggle_top)





def handoff_and_die():
    """把前台焦点交还指定窗口，重试几次后再关闭自己。
    窗口正在销毁时调 SetForegroundWindow 往往不生效，所以要「先交还、稳住、再销毁」。"""
    if not handoff:
        root.destroy()
        return
    if hand_tries["n"] >= 4:
        root.destroy()
        return
    hand_tries["n"] += 1
    _unlock_foreground()
    try:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
        u.SetForegroundWindow.argtypes = [wt.HWND]
        found = []
        CB = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        @CB
        def cb(h, l):
            b = ctypes.create_unicode_buffer(512)
            u.GetWindowTextW(int(h), b, 512)
            if b.value.startswith(handoff):
                found.append(int(h))
            return True

        u.EnumWindows(cb, 0)
        if found:
            u.SetForegroundWindow(found[0])
    except Exception:
        pass
    root.after(300, handoff_and_die)



hand_tries = {"n": 0}
root.after(250, grab)
if churn > 0:
    root.after(int(churn * 1000), toggle_top)
root.after(int(life * 1000), handoff_and_die)
root.mainloop()
