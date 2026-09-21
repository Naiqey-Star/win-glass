# -*- coding: utf-8 -*-
"""
win_glass.py — Windows 窗口美化工具：透明度随「聚焦 / 置顶 / 未聚焦」实时变化

状态规则
    聚焦窗口  -> 100%   （托盘菜单「聚焦最高透明度」可调，5~100%）
    置顶窗口  -> 100%   （同上，跟随「聚焦最高透明度」）
    其余窗口  -> 40%    （托盘菜单「非聚焦最低透明度」可调，5~95%）

特性
    * 实时   —— 焦点/置顶状态一变，立刻重新起动画
    * 平滑   —— 默认 500ms 缓动(smoothstep)，绝不突跳
    * 无依赖 —— 纯 ctypes 调用 user32/dwmapi，不需要 pywin32
    * 可还原 —— 退出时把透明度与窗口样式恢复原状
    * 可调   —— 托盘右键菜单里有两个分段式滑块，步进 1%，取值持久化

用法
    python win_glass.py                   常驻运行，Ctrl+C 退出
    python win_glass.py --list            只列出窗口与其目标透明度，不改动
    python win_glass.py --self-test       用自带测试窗口验证透明度链路
    python win_glass.py --fade-ms 500 --inactive-alpha 0.4
    python win_glass.py --duration 20     跑 20 秒后自动退出并还原

托盘右键菜单
    暂停 / 立即恢复 / [非聚焦最低透明度] / [聚焦最高透明度] / 打开日志 / 退出
    两个滑块：范围 5~95% 与 5~100%，步进 1%，显示为整数百分比。
    拖动、鼠标滚轮、左右方向键都能调；调完写入
    %LOCALAPPDATA%\\win_glass\\config.json，下次启动自动生效。

作者：月见八千代 (Yachiyo)
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import threading
import time
from ctypes import byref, c_ssize_t, c_ubyte

# --------------------------------------------------------------------------
# 输出环境：既要中文不乱码，也要兼容「窗口化(--noconsole)打包」时没有控制台的情况
# --------------------------------------------------------------------------
DEFAULT_LOG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                           "win_glass", "win_glass.log")
DEFAULT_CFG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                           "win_glass", "config.json")
APP_VER = "1.1.0"
LOG_PATH = DEFAULT_LOG
CFG_PATH = DEFAULT_CFG
_IO_LOG_FH = None          # 当前接管的日志文件句柄（用于 --log 覆盖时重开）


class _NullIO:
    def write(self, *_a):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False

    def reconfigure(self, **_k):
        pass

    def close(self):
        pass


def _setup_io(log_path=None):
    """统一处理输出目标，三种情形：
    1) 有控制台(脚本/控制台版 exe) —— 切代码页 65001 + utf-8，中文正常
    2) 窗口化 exe 从 cmd 启动 —— AttachConsole 挂到父进程控制台，输出可见
    3) 窗口化 exe 双击/托盘启动 —— 落到日志文件，托盘菜单可打开

    注意：本函数在 import 时先跑一次（窗口化场景此时 stdout 已是 None），
    main() 解析出 --log 后可能再跑一次；若目标日志换了，必须重开文件句柄，
    否则 --log 会被 import 期的默认日志悄悄顶掉。
    """
    global LOG_PATH, _IO_LOG_FH
    target = log_path or DEFAULT_LOG
    LOG_PATH = target
    if _IO_LOG_FH is not None and not log_path:
        return                      # 已经接管到默认日志，且没人要求改
    if (_IO_LOG_FH is not None
            and os.path.abspath(target) == os.path.abspath(_IO_LOG_FH.name)):
        return                      # 目标没变，不必重开
    if sys.platform.startswith("win"):
        try:
            _k = ctypes.WinDLL("kernel32", use_last_error=True)
            _k.SetConsoleOutputCP(65001)
            _k.SetConsoleCP(65001)
        except Exception:
            pass
    if sys.stdout is None or sys.stderr is None:
        attached = False
        try:
            _k = ctypes.WinDLL("kernel32", use_last_error=True)
            _k.AttachConsole.argtypes = [wt.DWORD]
            attached = bool(_k.AttachConsole(0xFFFFFFFF))   # ATTACH_PARENT_PROCESS
        except Exception:
            attached = False
        if attached:
            try:
                fh = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
                sys.stdout = fh
                sys.stderr = fh
            except Exception:
                pass
    if sys.stdout is None or sys.stderr is None:
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            fh = open(LOG_PATH, "w", encoding="utf-8", errors="replace", buffering=1)
            _IO_LOG_FH = fh
            sys.stdout = fh
            sys.stderr = fh
        except Exception:
            sink = _NullIO()
            sys.stdout = sink
            sys.stderr = sink
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_setup_io()

if not sys.platform.startswith("win"):
    print("[win_glass] 仅支持 Windows。")
    sys.exit(1)

# --------------------------------------------------------------------------
# Win32 绑定
# --------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
except OSError:                                     # pragma: no cover
    dwmapi = None

# 窗口样式
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000

# 分层窗口属性
LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002

# 杂项
GA_ROOT = 2
GW_OWNER = 4
MONITOR_DEFAULTTONEAREST = 2
DWMWA_CLOAKED = 14
WM_QUIT = 0x0012
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

# WinEvent
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_SYSTEM_MINIMIZESTART = 0x0016
EVENT_SYSTEM_MINIMIZEEND = 0x0017
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_DESTROY = 0x8001
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_HIDE = 0x8003
EVENT_OBJECT_STATECHANGE = 0x800A
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD),
                ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD)]


WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
WINEventProc = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND,
                                  wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)
PHANDLER_ROUTINE = ctypes.WINFUNCTYPE(wt.BOOL, wt.DWORD)

# 控制台控制事件：关闭控制台窗口/注销/关机时必须抢在进程死前还原
CTRL_C_EVENT = 0
CTRL_BREAK_EVENT = 1
CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6

kernel32.SetConsoleCtrlHandler.argtypes = [PHANDLER_ROUTINE, wt.BOOL]
kernel32.SetConsoleCtrlHandler.restype = wt.BOOL

# ---- 托盘图标 (Shell_NotifyIcon) ----
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x01, 0x02, 0x04
IMAGE_ICON = 1
LR_LOADFROMFILE, LR_DEFAULTSIZE = 0x0010, 0x0020
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_COMMAND = 0x0111
WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0202, 0x0203, 0x0205
MF_STRING, MF_SEPARATOR, MF_CHECKED, MF_GRAYED = 0x0000, 0x0800, 0x0008, 0x0001
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
HWND_MESSAGE = -3
IDI_APPLICATION = 32512

# 托盘菜单项
CMD_TOGGLE, CMD_RESTORE, CMD_LOG, CMD_QUIT = 1, 2, 3, 4
# 菜单里的两个滑块（owner-draw，不走 WM_COMMAND 业务逻辑）
CMD_SLIDE_INACTIVE, CMD_SLIDE_ACTIVE = 10, 11

# 滑块外观：整条菜单的宽度由最宽的 owner-draw 项决定
SLIDER_ITEM_W = 300        # 菜单项宽度(px)
SLIDER_ITEM_H = 42         # 两行：标题+数值 / 分段条
SLIDER_PAD_X = 15          # 左右留白，贴近普通菜单项的文字缩进
SLIDER_TITLE_H = 17        # 第一行文字高度
SLIDER_BAR_H = 13          # 分段条高度
SLIDER_SEG_GAP = 1         # 相邻分段之间的缝隙(px)


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
        ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT), ("hIcon", wt.HANDLE),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT),                 # 联合体位（uTimeout/uVersion）
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwInfoFlags", wt.DWORD),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE),
        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
    ]


WNDPROC = ctypes.WINFUNCTYPE(c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


def _signed_word(v, shift: int) -> int:
    """取 32 位消息参数的某 16 位并按有符号解释（滚轮增量、坐标都能用）。"""
    return ctypes.c_short((int(v) >> shift) & 0xFFFF).value


# --------------------------------------------------------------------------
# 菜单滑块（owner-draw）所需的 Win32 声明
#
# 为什么必须 owner-draw：Win32 的弹出菜单本身没有滑块控件，TrackPopupMenu 期间
# 菜单会跑自己的模态循环，普通子窗口控件（msctls_trackbar32）放不进去。
# 唯一可行的做法是「自绘菜单项 + 消息钩子」：
#   WM_MEASUREITEM / WM_DRAWITEM  → 自己画分段条
#   WH_MSGFILTER (MSGF_MENU)      → 在菜单模态循环里截获鼠标，实现拖动
# --------------------------------------------------------------------------
WM_DRAWITEM, WM_MEASUREITEM = 0x002B, 0x002C
# ！！踩过的坑，别改回去 ！！
# 这两个常量特别容易记反：WM_DRAWITEM 是 0x2B、WM_MEASUREITEM 是 0x2C。
# 写反了不会报错、消息照样收得到，只是「拿到的是另一个结构体」：
#   WM_DRAWITEM 的 lParam 是 DRAWITEMSTRUCT（hDC / rcItem 可用）
#   WM_MEASUREITEM 的 lParam 是 MEASUREITEMSTRUCT（要填 itemWidth / itemHeight）
# 于是滑块会表现成「尺寸怎么设都不生效、菜单项是空白的」——
# 因为宽高被写进了 DRAWITEMSTRUCT 的 itemAction/itemState，而绘制时读到的
# rcItem 其实是 MEASUREITEMSTRUCT 里的垃圾值。定位过程见 probe_map.py。
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
VK_LEFT, VK_RIGHT = 0x25, 0x27

ODT_MENU = 1
ODS_SELECTED, ODS_GRAYED, ODS_DISABLED = 0x0001, 0x0002, 0x0004
MIIM_STATE, MIIM_ID, MIIM_SUBMENU, MIIM_DATA, MIIM_STRING, MIIM_FTYPE = (
    0x0001, 0x0002, 0x0004, 0x0020, 0x0040, 0x0100)
MFT_OWNERDRAW = 0x00000100       # 注意：不是 0x1000，写错会得到 ERROR_INVALID_PARAMETER(87)
MFS_HILITE = 0x00000080

COLOR_MENU, COLOR_MENUTEXT, COLOR_HIGHLIGHT, COLOR_HIGHLIGHTTEXT = 4, 7, 13, 14
COLOR_GRAYTEXT = 17
SPI_GETNONCLIENTMETRICS = 0x0029
DT_LEFT, DT_RIGHT, DT_VCENTER, DT_SINGLELINE = 0x0, 0x2, 0x4, 0x20
TRANSPARENT = 1

WH_MSGFILTER = -1
MSGF_MENU = 2
PROBE_MAX = 64                  # 诊断明细最多留这么多条，常驻进程里不会无限涨


class LOGFONTW(ctypes.Structure):
    _fields_ = [("lfHeight", ctypes.c_int), ("lfWidth", ctypes.c_int),
                ("lfEscapement", ctypes.c_int), ("lfOrientation", ctypes.c_int),
                ("lfWeight", ctypes.c_int),
                ("lfItalic", ctypes.c_byte), ("lfUnderline", ctypes.c_byte),
                ("lfStrikeOut", ctypes.c_byte), ("lfCharSet", ctypes.c_byte),
                ("lfOutPrecision", ctypes.c_byte),
                ("lfClipPrecision", ctypes.c_byte),
                ("lfQuality", ctypes.c_byte), ("lfPitchAndFamily", ctypes.c_byte),
                ("lfFaceName", wt.WCHAR * 32)]


class NONCLIENTMETRICSW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("iBorderWidth", ctypes.c_int),
                ("iScrollWidth", ctypes.c_int), ("iScrollHeight", ctypes.c_int),
                ("iCaptionWidth", ctypes.c_int), ("iCaptionHeight", ctypes.c_int),
                ("lfCaptionFont", LOGFONTW),
                ("iSmCaptionWidth", ctypes.c_int), ("iSmCaptionHeight", ctypes.c_int),
                ("lfSmCaptionFont", LOGFONTW),
                ("iMenuWidth", ctypes.c_int), ("iMenuHeight", ctypes.c_int),
                ("lfMenuFont", LOGFONTW), ("lfStatusFont", LOGFONTW),
                ("lfMessageFont", LOGFONTW), ("iPaddedBorderWidth", ctypes.c_int)]


class MENUITEMINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("fMask", wt.UINT), ("fType", wt.UINT),
                ("fState", wt.UINT), ("wID", wt.UINT), ("hSubMenu", wt.HMENU),
                ("hbmpChecked", wt.HBITMAP), ("hbmpUnchecked", wt.HBITMAP),
                ("dwItemData", ctypes.c_void_p), ("dwTypeData", wt.LPWSTR),
                ("cch", wt.UINT), ("hbmpItem", wt.HBITMAP)]


class MEASUREITEMSTRUCT(ctypes.Structure):
    _fields_ = [("CtlType", wt.UINT), ("CtlID", wt.UINT), ("itemID", wt.UINT),
                ("itemWidth", wt.UINT), ("itemHeight", wt.UINT),
                ("itemData", ctypes.c_void_p)]


class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [("CtlType", wt.UINT), ("CtlID", wt.UINT), ("itemID", wt.UINT),
                ("itemAction", wt.UINT), ("itemState", wt.UINT),
                ("hwndItem", wt.HWND), ("hDC", wt.HDC),
                ("rcItem", wt.RECT), ("itemData", ctypes.c_void_p)]


class MENUMSG(ctypes.Structure):
    """WH_MSGFILTER 回调拿到的 MSG；pt 是屏幕坐标，且结构可写（用于吞掉鼠标点击）。"""
    _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT),
                ("wParam", wt.WPARAM), ("lParam", wt.LPARAM),
                ("time", wt.DWORD), ("pt", wt.POINT)]


HOOKPROC = ctypes.WINFUNCTYPE(c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)

user32.InsertMenuItemW.argtypes = [wt.HMENU, wt.UINT, wt.BOOL,
                                   ctypes.POINTER(MENUITEMINFOW)]
user32.InsertMenuItemW.restype = wt.BOOL
user32.GetMenuItemInfoW.argtypes = [wt.HMENU, wt.UINT, wt.BOOL,
                                    ctypes.POINTER(MENUITEMINFOW)]
user32.GetMenuItemInfoW.restype = wt.BOOL
user32.GetMenuItemCount.argtypes = [wt.HMENU]
user32.GetMenuItemCount.restype = ctypes.c_int
user32.GetMenuItemID.argtypes = [wt.HMENU, ctypes.c_int]
user32.GetMenuItemID.restype = ctypes.c_int
user32.GetMenuItemRect.argtypes = [wt.HWND, wt.HMENU, wt.UINT, ctypes.POINTER(wt.RECT)]
user32.GetMenuItemRect.restype = wt.BOOL
user32.MapWindowPoints.argtypes = [wt.HWND, wt.HWND, ctypes.POINTER(wt.POINT), wt.UINT]
user32.MapWindowPoints.restype = ctypes.c_int
user32.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), wt.BOOL]
user32.UpdateWindow.argtypes = [wt.HWND]
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HANDLE
user32.UnhookWindowsHookEx.argtypes = [wt.HANDLE]
user32.CallNextHookEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = c_ssize_t
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]
user32.GetSysColor.argtypes = [ctypes.c_int]
user32.GetSysColor.restype = wt.DWORD
user32.GetSysColorBrush.argtypes = [ctypes.c_int]
user32.GetSysColorBrush.restype = wt.HBRUSH
user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int,
                             ctypes.POINTER(wt.RECT), wt.UINT]
user32.DrawTextW.restype = ctypes.c_int
user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]
user32.FillRect.restype = ctypes.c_int
gdi32.SetTextColor.argtypes = [wt.HDC, wt.DWORD]
gdi32.SetTextColor.restype = wt.DWORD
gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.SetBkMode.restype = ctypes.c_int
gdi32.CreateFontIndirectW.argtypes = [ctypes.POINTER(LOGFONTW)]
gdi32.CreateFontIndirectW.restype = wt.HFONT
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.CreateSolidBrush.argtypes = [wt.DWORD]
gdi32.CreateSolidBrush.restype = wt.HBRUSH

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p]
user32.CreateWindowExW.restype = wt.HWND
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = c_ssize_t
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wt.BOOL
shell32.ExtractIconExW.argtypes = [wt.LPCWSTR, ctypes.c_int,
                                   ctypes.POINTER(wt.HANDLE), ctypes.POINTER(wt.HANDLE),
                                   wt.UINT]
shell32.ExtractIconExW.restype = wt.UINT
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wt.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = wt.BOOL
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                              ctypes.c_int, ctypes.c_int, wt.UINT]
user32.LoadImageW.restype = wt.HANDLE
user32.LoadIconW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]   # 第二参可能是 MAKEINTRESOURCE
user32.LoadIconW.restype = wt.HANDLE
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE

# 64 位下必须走 LongPtr，否则句柄被截断
if hasattr(user32, "GetWindowLongPtrW"):
    _GetWindowLong = user32.GetWindowLongPtrW
    _SetWindowLong = user32.SetWindowLongPtrW
    _GetWindowLong.restype = c_ssize_t
    _SetWindowLong.restype = c_ssize_t
    _SetWindowLong.argtypes = [wt.HWND, ctypes.c_int, c_ssize_t]
else:                                               # pragma: no cover
    _GetWindowLong = user32.GetWindowLongW
    _SetWindowLong = user32.SetWindowLongW
    _GetWindowLong.restype = wt.LONG
    _SetWindowLong.restype = wt.LONG
    _SetWindowLong.argtypes = [wt.HWND, ctypes.c_int, wt.LONG]
_GetWindowLong.argtypes = [wt.HWND, ctypes.c_int]

user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
user32.GetWindow.restype = wt.HWND
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.MonitorFromWindow.restype = wt.HANDLE
user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.DWORD, wt.DWORD, wt.DWORD]
user32.SetLayeredWindowAttributes.restype = wt.BOOL
user32.GetLayeredWindowAttributes.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD),
                                              ctypes.POINTER(c_ubyte),
                                              ctypes.POINTER(wt.DWORD)]
user32.GetLayeredWindowAttributes.restype = wt.BOOL
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWinEventHook.argtypes = [wt.UINT, wt.UINT, wt.HMODULE, WINEventProc,
                                   wt.DWORD, wt.DWORD, wt.UINT]
user32.SetWinEventHook.restype = wt.HANDLE
user32.UnhookWinEvent.argtypes = [wt.HANDLE]
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
if dwmapi is not None:
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------
def _h(v) -> int:
    """句柄归一化为 int（ctypes 可能给 None）。"""
    return int(v) if v else 0


def _window_text(hwnd: int, n: int = 512) -> str:
    buf = ctypes.create_unicode_buffer(n)
    user32.GetWindowTextW(hwnd, buf, n)
    return buf.value


def _class_name(hwnd: int, n: int = 256) -> str:
    buf = ctypes.create_unicode_buffer(n)
    user32.GetClassNameW(hwnd, buf, n)
    return buf.value


def _is_cloaked(hwnd: int) -> bool:
    """UWP/虚拟桌面隐藏窗口（看不见但 IsWindowVisible 为真）。"""
    if dwmapi is None:
        return False
    val = wt.DWORD(0)
    try:
        hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, byref(val), 4)
        return hr == 0 and val.value != 0
    except Exception:
        return False


def _is_fullscreen(hwnd: int, rc: wt.RECT) -> bool:
    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not mon:
        return False
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(mon, byref(mi)):
        return False
    m = mi.rcMonitor
    return (rc.left <= m.left and rc.top <= m.top
            and rc.right >= m.right and rc.bottom >= m.bottom)


def smoothstep(t: float) -> float:
    """ease-in-out 缓动曲线：两端导数为 0，起步与收尾都不生硬。"""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


# 默认排除的窗口类：桌面外壳、IME、UWP 容器等（给它们加分层会出怪象）
EXCLUDE_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "SysShadow", "ForegroundStaging", "MultitaskingViewFrame",
    "XamlExplorerHostIslandWindow", "Windows.UI.Core.CoreWindow",
    "Windows.Internal.Shell.TabProxyWindow", "ApplicationFrameWindow",
    "TaskListThumbnailWnd", "DV2ControlHost", "tooltips_class32",
    "MsgrIMEWindowClass", "Default IME", "IME", "NarratorHelperWindow",
    "Windows.UI.Composition.DesktopWindowContentBridge",
}


# --------------------------------------------------------------------------
# 配置：命令行参数 / 配置文件 / 托盘滑块 三者共用同一份取值
# --------------------------------------------------------------------------
def _to_pct(v) -> float:
    """把「0..1 的不透明度」和「0..100 的百分数」都归一化成百分数。

    两种写法都接受：--inactive-alpha 0.4 与 --inactive-alpha 40 等价。
    """
    f = float(v)
    return f * 100.0 if f <= 1.0 else f


def load_cfg_file(path=None) -> dict:
    """读配置文件；任何异常（不存在/坏 JSON/权限）都静默退化成空配置。

    path=None → 默认位置；path="" → 明确不读（配合 --no-config）。
    """
    p = CFG_PATH if path is None else path
    if not p:
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_cfg_file(d: dict, path=None) -> bool:
    """原子写配置文件（先写 .tmp 再 replace），失败不影响运行。

    path=None → 默认位置；path="" → 明确不写，直接返回 False。
    """
    p = CFG_PATH if path is None else path
    if not p:
        return False
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


class GlassConfig:
    """运行配置。

    两个透明度阈值都**以整数百分比存储**（内部 _inactive_pct / _active_pct），
    这样「步进 1%、永不出现小数点」是结构性保证，而不是靠显示层四舍五入。
    `inactive_alpha` / `active_alpha` 两个 0..1 的属性读写是给旧代码用的兼容层。
    """

    # 滑块范围（含两端）
    INACTIVE_MIN_PCT, INACTIVE_MAX_PCT = 5, 95
    ACTIVE_MIN_PCT, ACTIVE_MAX_PCT = 5, 100
    # 内置默认值（既没有命令行参数、也没有配置文件时用）
    DEFAULT_INACTIVE_PCT, DEFAULT_ACTIVE_PCT = 40, 100

    def __init__(self, inactive_alpha=0.40, active_alpha=1.00, fade_ms=500, fps=60,
                 scan_interval=0.15, rescan_interval=0.50,
                 skip_fullscreen=True, skip_foreign_layered=False,
                 extra_exclude=(), verbose=False, restore_on_exit=True,
                 tray=True, log_path="", cfg_path=None):
        # cfg_path=None → 用默认路径；cfg_path="" → 明确关闭持久化
        self.cfg_path = CFG_PATH if cfg_path is None else cfg_path
        # None 视为「没指定」，落到内置默认；否则 _to_pct(None) 会直接 TypeError
        self.inactive_pct = (self.DEFAULT_INACTIVE_PCT if inactive_alpha is None
                             else _to_pct(inactive_alpha))
        self.active_pct = (self.DEFAULT_ACTIVE_PCT if active_alpha is None
                           else _to_pct(active_alpha))
        self.fade_ms = max(int(fade_ms), 1)
        self.fps = max(int(fps), 10)
        self.scan_interval = max(float(scan_interval), 0.02)
        self.rescan_interval = max(float(rescan_interval), 0.05)
        self.skip_fullscreen = bool(skip_fullscreen)
        # Chromium/Electron 系应用会自行使用 WS_EX_LAYERED(alpha 常非 255)。
        # 本工具会记录并原样还原；若仍不放心，可开启此开关直接跳过这类窗口。
        self.skip_foreign_layered = bool(skip_foreign_layered)
        self.extra_exclude = set(extra_exclude or ())
        self.verbose = bool(verbose)
        self.restore_on_exit = bool(restore_on_exit)
        self.tray = bool(tray)
        self.log_path = log_path or ""

    # ---- 非聚焦最低透明度（5~95%）----
    @property
    def inactive_pct(self) -> int:
        return self._inactive_pct

    @inactive_pct.setter
    def inactive_pct(self, v):
        self._inactive_pct = max(self.INACTIVE_MIN_PCT,
                                 min(self.INACTIVE_MAX_PCT, int(round(float(v)))))

    @property
    def inactive_alpha(self) -> float:
        return self._inactive_pct / 100.0

    @inactive_alpha.setter
    def inactive_alpha(self, v):
        self.inactive_pct = _to_pct(v)

    # ---- 聚焦/置顶最高透明度（5~100%）----
    @property
    def active_pct(self) -> int:
        return self._active_pct

    @active_pct.setter
    def active_pct(self, v):
        self._active_pct = max(self.ACTIVE_MIN_PCT,
                               min(self.ACTIVE_MAX_PCT, int(round(float(v)))))

    @property
    def active_alpha(self) -> float:
        return self._active_pct / 100.0

    @active_alpha.setter
    def active_alpha(self, v):
        self.active_pct = _to_pct(v)

    # ---- 持久化 ----
    def as_dict(self) -> dict:
        return {"version": 1,
                "inactive_percent": self._inactive_pct,
                "active_percent": self._active_pct}

    def save(self) -> bool:
        return save_cfg_file(self.as_dict(), self.cfg_path)

    @classmethod
    def apply_saved(cls, saved: dict, inactive, active):
        """把配置文件里的值填到命令行缺省的位置（命令行显式给了就用命令行的）。

        返回 (inactive, active) 供构造使用；配置文件里的键名是 *_percent。
        """
        # 无论有没有配置文件，都必须返回两个可用的数字：
        # 早先写成「saved 为空就原样返回」，于是 --no-config / 首次运行拿到的是
        # (None, None)，进构造函数 float(None) 直接崩 —— 已由 slider_test.py 的
        # 「空配置 + 无参数」用例与「--no-config 起得来」用例守住。
        if inactive is None:
            inactive = (saved or {}).get("inactive_percent",
                                         cls.DEFAULT_INACTIVE_PCT)
        if active is None:
            active = (saved or {}).get("active_percent",
                                       cls.DEFAULT_ACTIVE_PCT)
        return inactive, active


# --------------------------------------------------------------------------
# 单窗口状态
# --------------------------------------------------------------------------
class WinState:
    __slots__ = ("hwnd", "cur", "src", "dst", "t0", "dur",
                 "layered_owned", "framechanged", "orig_alpha",
                 "applied", "failed", "title", "cls", "topmost", "is_fg")

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.cur = 1.0          # 当前不透明度 0..1
        self.src = 1.0          # 本段动画起点
        self.dst = 1.0          # 本段动画终点
        self.t0 = time.perf_counter()
        self.dur = 0.0
        self.layered_owned = False
        self.framechanged = False
        self.orig_alpha = 255
        self.applied = -1
        self.failed = False
        self.title = ""
        self.cls = ""
        self.topmost = False
        self.is_fg = False


def is_manageable(hwnd: int, cfg: GlassConfig, self_pid: int) -> bool:
    if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return False
    if _is_cloaked(hwnd):
        return False
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, byref(pid))
    if pid.value == self_pid:
        return False
    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW or ex & WS_EX_NOACTIVATE:
        return False
    if cfg.skip_foreign_layered and (ex & WS_EX_LAYERED):
        return False
    owner = _h(user32.GetWindow(hwnd, GW_OWNER))
    if owner and not (ex & WS_EX_APPWINDOW):
        return False
    cls = _class_name(hwnd)
    if cls in EXCLUDE_CLASSES or cls in cfg.extra_exclude:
        return False
    rc = wt.RECT()
    if not user32.GetWindowRect(hwnd, byref(rc)):
        return False
    if (rc.right - rc.left) < 80 or (rc.bottom - rc.top) < 60:
        return False
    if not _window_text(hwnd) and not (ex & WS_EX_APPWINDOW):
        return False
    if cfg.skip_fullscreen and _is_fullscreen(hwnd, rc):
        return False
    return True


def scan_windows(cfg: GlassConfig, self_pid: int):
    found = []

    @WNDENUMPROC
    def _cb(hwnd, _lparam):
        try:
            if is_manageable(_h(hwnd), cfg, self_pid):
                found.append(_h(hwnd))
        except Exception:
            pass
        return True

    user32.EnumWindows(_cb, 0)
    return found


# --------------------------------------------------------------------------
# 托盘图标（纯 ctypes；窗口化打包时用来替代控制台交互）
# --------------------------------------------------------------------------
def _res_dir() -> str:
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------
# 菜单滑块的绘制
# --------------------------------------------------------------------------
_FONT_CACHE = {}
_BRUSH_CACHE = {}


def _menu_font() -> int:
    """取系统菜单字体并缓存 HFONT（HFONT 在菜单存活期内不能释放）。"""
    h = _FONT_CACHE.get("menu")
    if h:
        return h
    ncm = NONCLIENTMETRICSW()
    ncm.cbSize = ctypes.sizeof(NONCLIENTMETRICSW)
    ok = user32.SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, ncm.cbSize,
                                      byref(ncm), 0)
    if ok:
        lf = ncm.lfMenuFont
    else:
        lf = LOGFONTW()
        lf.lfHeight = -12
        lf.lfCharSet = 1                       # DEFAULT_CHARSET
        lf.lfWeight = 400
        lf.lfFaceName = "Segoe UI"
    h = gdi32.CreateFontIndirectW(byref(lf))
    _FONT_CACHE["menu"] = h
    return h


def _brush(color: int) -> int:
    """按 COLORREF 缓存画刷。滑块只用几种固定颜色，缓存不会无限增长。"""
    key = int(color) & 0xFFFFFF
    b = _BRUSH_CACHE.get(key)
    if b is None:
        b = gdi32.CreateSolidBrush(key)
        _BRUSH_CACHE[key] = b
    return b


def _menu_is_dark() -> bool:
    """按菜单背景色的亮度判断当前是浅色还是深色主题。"""
    c = int(user32.GetSysColor(COLOR_MENU))
    r, g, b = c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128.0


def _mix(c1: int, c2: int, t: float) -> int:
    """按比例混合两个 COLORREF。"""
    out = 0
    for i in range(3):
        a = (c1 >> (8 * i)) & 0xFF
        b = (c2 >> (8 * i)) & 0xFF
        out |= int(round(a + (b - a) * t)) << (8 * i)
    return out


def _slider_colors(selected: bool, disabled: bool):
    """返回 (已填充色, 未填充色, 边框色)。跟随系统主题与选中态。"""
    menu_bg = int(user32.GetSysColor(COLOR_MENU))
    dark = _menu_is_dark()
    if disabled:
        edge = int(user32.GetSysColor(COLOR_GRAYTEXT))
        return _mix(menu_bg, edge, 0.35), _mix(menu_bg, edge, 0.16), \
            _mix(menu_bg, edge, 0.30)
    if selected:
        bg = int(user32.GetSysColor(COLOR_HIGHLIGHT))
        # 选中时整行是强调色背景：已填充段用高亮文字色，未填充段压在背景上
        return int(user32.GetSysColor(COLOR_HIGHLIGHTTEXT)), _mix(bg, menu_bg, 0.45), \
            _mix(bg, menu_bg, 0.70)
    accent = 0xE46F2F if dark else 0xE46F2F          # COLORREF 是 BGR：蓝调 #2F6FE4
    empty = 0x4A4A4A if dark else 0xC9C9C9
    return accent, empty, (0x6E6E6E if dark else 0x9A9A9A)


def draw_menu_slider(dis, label: str, lo: int, hi: int, pct: int):
    """把一个 owner-draw 菜单项画成分段式滑块。

    布局（两行）：
        非聚焦最低透明度                      40%     <- 左标题 / 右数值
        ▮▮▮▮▮▮▮▮▮▮▮▮▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯     <- 分段条，每段 = 1%
    """
    hdc = dis.hDC
    rc = dis.rcItem
    selected = bool(dis.itemState & ODS_SELECTED)
    disabled = bool(dis.itemState & (ODS_GRAYED | ODS_DISABLED))
    pct = max(lo, min(hi, int(pct)))
    fill_c, empty_c, edge_c = _slider_colors(selected, disabled)

    # 背景必须自己刷：owner-draw 项不会被系统自动填充
    user32.FillRect(hdc, byref(rc), user32.GetSysColorBrush(
        COLOR_HIGHLIGHT if selected else COLOR_MENU))

    old_font = gdi32.SelectObject(hdc, _menu_font())
    old_mode = gdi32.SetBkMode(hdc, TRANSPARENT)
    if disabled:
        text_c = int(user32.GetSysColor(COLOR_GRAYTEXT))
    else:
        text_c = int(user32.GetSysColor(
            COLOR_HIGHLIGHTTEXT if selected else COLOR_MENUTEXT))

    left = rc.left + SLIDER_PAD_X
    right = rc.right - SLIDER_PAD_X

    # ---- 第一行：标题 + 整数百分比 ----
    r1 = wt.RECT(left, rc.top + 3, right, rc.top + 3 + SLIDER_TITLE_H)
    gdi32.SetTextColor(hdc, text_c)
    user32.DrawTextW(hdc, label, -1, byref(r1), DT_LEFT | DT_VCENTER | DT_SINGLELINE)
    user32.DrawTextW(hdc, "%d%%" % pct, -1, byref(r1),
                     DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

    # ---- 第二行：分段条 ----
    bar = wt.RECT(left, r1.bottom + 3, right, r1.bottom + 3 + SLIDER_BAR_H)
    if bar.bottom > rc.bottom - 2:
        bar.bottom = rc.bottom - 2
    if bar.bottom <= bar.top:
        bar.bottom = bar.top + 1

    # 底槽
    user32.FillRect(hdc, byref(bar), _brush(empty_c))

    n = hi - lo + 1                          # 段数 = 可取值的个数，每段正好 1%
    span = bar.right - bar.left
    filled = pct - lo + 1
    for i in range(n):
        x0 = bar.left + (i * span) // n
        x1 = bar.left + ((i + 1) * span) // n - SLIDER_SEG_GAP
        if x1 <= x0:
            x1 = x0 + 1
        seg = wt.RECT(x0, bar.top, x1, bar.bottom)
        if i < filled:
            user32.FillRect(hdc, byref(seg), _brush(fill_c))

    # 外描边（1px，用 FillRect 画四条边，避免额外 GDI 对象）
    user32.FillRect(hdc, byref(wt.RECT(bar.left, bar.top, bar.right, bar.top + 1)),
                   _brush(edge_c))
    user32.FillRect(hdc, byref(wt.RECT(bar.left, bar.bottom - 1, bar.right, bar.bottom)),
                   _brush(edge_c))

    gdi32.SelectObject(hdc, old_font)
    gdi32.SetBkMode(hdc, old_mode)
    gdi32.SetTextColor(hdc, int(user32.GetSysColor(COLOR_MENUTEXT)))


class MenuSlider:
    """托盘菜单里的一个 owner-draw 滑块。"""

    __slots__ = ("cid", "label", "lo", "hi", "get", "set", "pos", "hmenu")

    def __init__(self, cid, label, lo, hi, getter, setter):
        self.cid = int(cid)
        self.label = label
        self.lo = int(lo)
        self.hi = int(hi)
        self.get = getter            # () -> int  当前百分比
        self.set = setter            # (int) -> None
        self.pos = -1                # 菜单里的位置（0 基）
        self.hmenu = None

    def hit_frac_to_pct(self, x: int, rc) -> int:
        """把鼠标 x 换算成 1% 步进的整数值。"""
        x0 = rc.left + SLIDER_PAD_X
        x1 = rc.right - SLIDER_PAD_X - 1
        span = max(1, x1 - x0)
        frac = (x - x0) / span
        if frac < 0.0:
            frac = 0.0
        elif frac > 1.0:
            frac = 1.0
        return max(self.lo, min(self.hi, self.lo + int(round(frac * (self.hi - self.lo)))))


class TrayIcon:
    """系统托盘图标。左键单击=暂停/继续；右键菜单=暂停、两个透明度滑块、日志、退出。"""

    def __init__(self, engine, tip="win_glass — 窗口聚焦透明"):
        self.engine = engine
        self.tip = tip[:127]
        self.hwnd = 0
        self._proc_ref = None
        self._ready = threading.Event()
        # ---- 菜单滑块状态 ----
        self._sliders = []          # 当前菜单里的 MenuSlider 列表
        self._hook = 0              # WH_MSGFILTER 钩子
        self._hook_ref = None       # 钩子回调引用（不放会被 GC，随即崩溃）
        self._menu_hwnd = 0         # 正在显示的菜单窗口（给坐标换算用）
        self._dragging = False      # 是否正在拖动滑块
        # 诊断用：菜单相关消息的到达计数（滑块出问题时看这个最快）
        self.msg_counts = {"measure": 0, "draw": 0, "initmenu": 0, "select": 0,
                           "mouse": 0, "key": 0, "wheel": 0}
        self.msg_probe = []         # (kind, CtlType, itemID, w, h) 诊断明细

    def _probe(self, row):
        """记一条诊断明细。常驻进程里菜单会被弹很多次，必须封顶，否则一直涨。"""
        self.msg_probe.append(row)
        if len(self.msg_probe) > PROBE_MAX:
            del self.msg_probe[:-PROBE_MAX]

    def _load_icon(self):
        # 1) 从自身 exe 抽图标（PyInstaller --icon 打进去的那个）
        try:
            if getattr(sys, "frozen", False):
                big, small = wt.HANDLE(), wt.HANDLE()
                n = shell32.ExtractIconExW(sys.executable, 0, byref(big), byref(small), 1)
                if n and big.value:
                    return big
        except Exception:
            pass
        # 2) 同目录 icon.ico
        try:
            ico = os.path.join(_res_dir(), "icon.ico")
            if os.path.isfile(ico):
                h = user32.LoadImageW(None, ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                if not h:
                    h = user32.LoadImageW(None, ico, IMAGE_ICON, 0, 0,
                                          LR_LOADFROMFILE | LR_DEFAULTSIZE)
                if h:
                    return h
        except Exception:
            pass
        # 3) 系统默认
        try:
            return user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        except Exception:
            return None

    def start(self) -> bool:
        threading.Thread(target=self._run, name="winglass-tray", daemon=True).start()
        self._ready.wait(6.0)
        return self.hwnd != 0

    def _run(self):
        nid = None
        try:
            self._proc_ref = WNDPROC(self._on_msg)      # 必须留引用，否则回调被 GC 后崩溃
            hinst = kernel32.GetModuleHandleW(None)
            cls = "WinGlassTrayWnd_%d" % os.getpid()
            wc = WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = ctypes.cast(self._proc_ref, ctypes.c_void_p)
            wc.hInstance = hinst
            wc.lpszClassName = cls
            user32.RegisterClassW(byref(wc))
            # 刻意用「隐藏的顶层窗口」而不是 HWND_MESSAGE 消息窗口：
            # 卸载器/升级遇到正在运行的实例时会 taskkill（不带 /F）请求优雅退出，
            # 而 taskkill 只枚举顶层窗口 —— 消息窗口收不到 WM_CLOSE，会被降级成
            # /F 强杀，窗口就卡在 40% 透明度了。顶层 + WS_EX_TOOLWINDOW 既收得到
            # WM_CLOSE，又不会出现在任务栏/Alt+Tab 里。
            self.hwnd = _h(user32.CreateWindowExW(WS_EX_TOOLWINDOW, cls, "win_glass", 0,
                                                  0, 0, 0, 0, None, None, hinst, None))
            if not self.hwnd:
                return
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAYICON
            nid.hIcon = self._load_icon()
            nid.szTip = self.tip
            if not shell32.Shell_NotifyIconW(NIM_ADD, byref(nid)):
                self.hwnd = 0
                return
        except Exception as e:
            print("[win_glass] 托盘创建异常：%r" % (e,))
            self.hwnd = 0
            return
        finally:
            self._ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
        try:
            shell32.Shell_NotifyIconW(NIM_DELETE, byref(nid))
        except Exception:
            pass

    def _on_msg(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAYICON:
                ev = int(lparam) & 0xFFFF
                if ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.engine.set_paused(not self.engine.paused)
                elif ev == WM_RBUTTONUP:
                    self._popup()
                return 0
            if msg == WM_COMMAND:
                self._invoke(int(wparam) & 0xFFFF)
                return 0
            if msg == WM_MEASUREITEM:
                # 菜单第一次弹出时问 owner-draw 项要多大；返回 TRUE 表示已处理
                self.msg_counts["measure"] += 1
                self._on_measureitem(lparam)
                return 1
            if msg == WM_DRAWITEM:
                self.msg_counts["draw"] += 1
                self._on_drawitem(lparam)
                return 1
            if msg == WM_MOUSEWHEEL and self._sliders:
                # 兜底：菜单开着时滚轮未必经过菜单的模态循环，WH_MSGFILTER 就看不到它，
                # 而是直接投给 owner 窗口。这里再接一次，光标压在滑块上就 ±1%。
                # （wm_mousewheel: wParam 低 16 位 = x、高 16 位 = y，lParam 高 16 位 = 增量）
                self.msg_counts["wheel"] += 1
                hit = self._hit_slider(wt.POINT(_signed_word(wparam, 0),
                                                _signed_word(wparam, 16)))
                if hit:
                    sl, rc = hit
                    delta = _signed_word(lparam, 16)
                    if delta:
                        self._apply_slider(
                            sl, rc, int(sl.get()) + (1 if delta > 0 else -1))
                    return 0
            if msg == WM_CLOSE:
                # 卸载/升级/外部请求关闭：走正常退出流程，shutdown() 会还原所有窗口。
                # 不 DestroyWindow，让主循环收尾。
                self.engine.request_quit()
                return 0
            if msg == WM_QUERYENDSESSION:
                return 1                    # 允许注销/关机
            if msg == WM_ENDSESSION:
                if wparam:                  # TRUE = 会话真的要结束了，没时间了，立刻还原
                    try:
                        self.engine.restore_now()
                    except Exception:
                        pass
                    self.engine.request_quit()
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _popup(self):
        m = user32.CreatePopupMenu()
        if not m:
            return
        paused = self.engine.paused
        user32.AppendMenuW(m, MF_STRING | (MF_CHECKED if paused else 0), CMD_TOGGLE,
                           "已暂停（点击继续）" if paused else "暂停（所有窗口恢复 100%）")
        user32.AppendMenuW(m, MF_STRING, CMD_RESTORE, "立即把所有窗口恢复 100%")
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        self._append_sliders(m)
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(m, MF_STRING, CMD_LOG, "打开日志")
        user32.AppendMenuW(m, MF_STRING, CMD_QUIT, "退出（还原全部窗口）")

        pt = wt.POINT()
        user32.GetCursorPos(byref(pt))
        self._menu_hwnd = 0
        self._dragging = False
        # TrackPopupMenu 会自己跑一套模态消息循环，普通子控件塞不进菜单里；
        # 只有 WH_MSGFILTER 能在那个循环里截到鼠标消息，滑块才拖得动。
        self._install_menu_hook()
        # TrackPopupMenu 要求窗口在前台，否则点菜单外部不会关闭
        user32.SetForegroundWindow(self.hwnd)
        try:
            cmd = user32.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                        pt.x, pt.y, 0, self.hwnd, None)
        finally:
            self._uninstall_menu_hook()
            self._menu_hwnd = 0
            self._dragging = False
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(m)
        self._sliders = []
        self.engine.save_cfg(force=True)      # 最后一次拖动可能还在节流窗口里
        if cmd:
            self._invoke(int(cmd))

    # ---------------- 滑块：建项 / 测量 / 绘制 ----------------
    def _append_sliders(self, m):
        """把两个滑块作为 owner-draw 菜单项插进菜单。"""
        cfg = self.engine.cfg
        sliders = [
            MenuSlider(CMD_SLIDE_INACTIVE, "非聚焦最低透明度",
                       cfg.INACTIVE_MIN_PCT, cfg.INACTIVE_MAX_PCT,
                       lambda: self.engine.cfg.inactive_pct,
                       lambda v: self.engine.set_alpha_targets(inactive_pct=v)),
            MenuSlider(CMD_SLIDE_ACTIVE, "聚焦最高透明度",
                       cfg.ACTIVE_MIN_PCT, cfg.ACTIVE_MAX_PCT,
                       lambda: self.engine.cfg.active_pct,
                       lambda v: self.engine.set_alpha_targets(active_pct=v)),
        ]
        self._sliders = []
        for sl in sliders:
            sl.hmenu = m
            sl.pos = max(0, user32.GetMenuItemCount(m))
            mii = MENUITEMINFOW()
            mii.cbSize = ctypes.sizeof(MENUITEMINFOW)
            mii.fMask = MIIM_ID | MIIM_FTYPE | MIIM_DATA
            mii.fType = MFT_OWNERDRAW
            mii.wID = sl.cid
            mii.dwItemData = sl.cid          # MFT_OWNERDRAW 要求带上应用自定义值
            if not user32.InsertMenuItemW(m, sl.pos, True, byref(mii)):
                print("[win_glass] 警告：滑块菜单项创建失败，"
                      "请改用命令行 --inactive-alpha / --active-alpha 调节。")
                self._sliders = []
                return
            self._sliders.append(sl)
        if not self._sliders:
            print("[win_glass] 警告：本次菜单没有可用的滑块。")

    def _slider_by_id(self, item_id):
        for sl in self._sliders:
            if sl.cid == int(item_id):
                return sl
        return None

    def _on_measureitem(self, lparam):
        try:
            mis = ctypes.cast(lparam, ctypes.POINTER(MEASUREITEMSTRUCT)).contents
            self._probe(("measure", int(mis.CtlType), int(mis.itemID),
                         int(mis.itemWidth), int(mis.itemHeight)))
            if int(mis.CtlType) != ODT_MENU:
                return
            if self._slider_by_id(mis.itemID) is None:
                return
            mis.itemWidth = SLIDER_ITEM_W
            mis.itemHeight = SLIDER_ITEM_H
            self._probe(("measure-set", 0, int(mis.itemID),
                         int(mis.itemWidth), int(mis.itemHeight)))
        except Exception:
            pass

    def _on_drawitem(self, lparam):
        try:
            dis = ctypes.cast(lparam, ctypes.POINTER(DRAWITEMSTRUCT)).contents
            self._probe(("draw", int(dis.CtlType), int(dis.itemID),
                         dis.rcItem.right - dis.rcItem.left,
                         dis.rcItem.bottom - dis.rcItem.top))
            if int(dis.CtlType) != ODT_MENU:
                return
            sl = self._slider_by_id(dis.itemID)
            if sl is None:
                return
            draw_menu_slider(dis, sl.label, sl.lo, sl.hi, int(sl.get()))
        except Exception as e:
            if self.engine.cfg.verbose:
                print("[win_glass] 绘制滑块失败：%r" % (e,))

    # ---------------- 滑块：菜单内的鼠标 / 键盘 ----------------
    def _install_menu_hook(self):
        self._hook_ref = HOOKPROC(self._menu_msgfilter)
        self._hook = user32.SetWindowsHookExW(
            WH_MSGFILTER, self._hook_ref, None, kernel32.GetCurrentThreadId()) or 0

    def _uninstall_menu_hook(self):
        if self._hook:
            try:
                user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = 0
        self._hook_ref = None            # 先摘钩子再丢引用，否则回调可能被提前回收

    def _menu_msgfilter(self, nCode, wParam, lParam):
        """菜单模态循环里的消息钩子——滑块能拖动的关键。

        注意：这里跑在 Windows 的消息循环里，任何异常都不能外泄，
        否则会打断菜单，所以整体包了 try/except。
        """
        try:
            if nCode == MSGF_MENU and lParam and self._hook:
                msg = ctypes.cast(lParam, ctypes.POINTER(MENUMSG)).contents
                if not self._menu_hwnd and msg.hwnd:
                    self._menu_hwnd = _h(msg.hwnd)
                mtype = int(msg.message)
                if mtype in (WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP,
                             WM_MOUSEWHEEL, WM_KEYDOWN):
                    if mtype == WM_MOUSEMOVE:
                        self.msg_counts["mouse"] += 1
                    elif mtype == WM_MOUSEWHEEL:
                        self.msg_counts["wheel"] += 1
                    elif mtype == WM_KEYDOWN:
                        self.msg_counts["key"] += 1
                    if self._handle_menu_input(msg, mtype):
                        # 双保险：既改写消息本身，也让钩子链把它吞掉。
                        # 少了这步，点一下滑块菜单就关了，根本没法拖动。
                        msg.message = WM_NULL
                        return 1
        except Exception:
            pass
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _handle_menu_input(self, msg, mtype) -> bool:
        """返回 True 表示这条输入已被滑块消费，不该再交给菜单。

        WM_MOUSEMOVE 是**故意不吞**的：菜单要靠它把光标下的项高亮起来，
        吞了就永远看不到滑块被选中，而且方向键微调也就没机会生效。
        """
        if mtype == WM_MOUSEMOVE:
            if self._dragging:
                pt = wt.POINT(int(msg.pt.x), int(msg.pt.y))
                hit = self._hit_slider(pt)
                if hit:
                    sl, rc = hit
                    self._apply_slider(sl, rc, sl.hit_frac_to_pct(pt.x, rc))
            return False
        if mtype == WM_KEYDOWN:
            return self._handle_slider_key(int(msg.wParam))
        pt = wt.POINT(int(msg.pt.x), int(msg.pt.y))
        hit = self._hit_slider(pt)
        if hit is None:
            if mtype == WM_LBUTTONUP:
                self._dragging = False
            return False
        sl, rc = hit
        if mtype == WM_MOUSEWHEEL:
            # 滚轮增量在 lParam 的高 16 位！wParam 装的是光标坐标（低=x 高=y），
            # 从 wParam 取增量会拿到 y 坐标，滚多少都不动。
            delta = _signed_word(msg.lParam, 16)
            if delta:
                self._apply_slider(sl, rc, int(sl.get()) + (1 if delta > 0 else -1))
            return True
        if mtype == WM_LBUTTONDOWN:
            self._dragging = True
            self._apply_slider(sl, rc, sl.hit_frac_to_pct(pt.x, rc))
        elif mtype == WM_LBUTTONUP:
            if self._dragging:
                self._apply_slider(sl, rc, sl.hit_frac_to_pct(pt.x, rc))
            self._dragging = False
        return True

    def _handle_slider_key(self, vk) -> bool:
        """左右方向键在滑块上以 1% 微调——想精确到某个值时用这个。"""
        if vk not in (VK_LEFT, VK_RIGHT):
            return False
        sl = self._hilited_slider()
        if sl is None:
            return False
        rc = self._item_rect(sl)
        if rc is None:
            return False
        self._apply_slider(sl, rc, int(sl.get()) + (1 if vk == VK_RIGHT else -1))
        return True

    def _hilited_slider(self):
        """当前高亮的菜单项是不是滑块？是就返回它。"""
        for sl in self._sliders:
            mii = MENUITEMINFOW()
            mii.cbSize = ctypes.sizeof(MENUITEMINFOW)
            mii.fMask = MIIM_STATE
            try:
                if user32.GetMenuItemInfoW(sl.hmenu, sl.pos, True, byref(mii)) \
                        and (int(mii.fState) & MFS_HILITE):
                    return sl
            except Exception:
                pass
        return None

    def _hit_slider(self, pt):
        for sl in self._sliders:
            rc = self._item_rect(sl)
            if rc is None:
                continue
            if rc.left <= pt.x < rc.right and rc.top <= pt.y < rc.bottom:
                return sl, rc
        return None

    def _item_rect(self, sl):
        """取菜单项在屏幕上的矩形。uWnd 传菜单窗口最准，不行再退到别的句柄。"""
        rc = wt.RECT()
        seen = []
        for wnd in (self._menu_hwnd, self.hwnd, None):
            if wnd in seen:
                continue
            seen.append(wnd)
            try:
                if user32.GetMenuItemRect(wnd, sl.hmenu, sl.pos, byref(rc)):
                    return rc
            except Exception:
                pass
        return None

    def _apply_slider(self, sl, rc, pct):
        """夹紧到合法范围后写回配置；值没变就不重绘，避免无谓闪烁。"""
        pct = max(sl.lo, min(sl.hi, int(pct)))      # 取整 + 夹紧 → 步进恒为 1%
        if pct == int(sl.get()):
            return
        sl.set(pct)
        self._redraw_item(rc)

    def _redraw_item(self, rc):
        """就地重绘某个菜单项，让分段条与数值实时跟手。"""
        hwnd = self._menu_hwnd
        if not hwnd:
            return
        local = wt.RECT(rc.left, rc.top, rc.right, rc.bottom)
        user32.MapWindowPoints(None, hwnd,
                               ctypes.cast(byref(local), ctypes.POINTER(wt.POINT)), 2)
        user32.InvalidateRect(hwnd, byref(local), False)
        user32.UpdateWindow(hwnd)

    def _invoke(self, cid):
        if cid in (CMD_SLIDE_INACTIVE, CMD_SLIDE_ACTIVE):
            return                       # 滑块靠钩子拖动，不走命令逻辑
        if cid == CMD_TOGGLE:
            self.engine.set_paused(not self.engine.paused)
        elif cid == CMD_RESTORE:
            self.engine.restore_now()
        elif cid == CMD_LOG:
            try:
                if os.path.isfile(LOG_PATH):
                    os.startfile(LOG_PATH)
                else:
                    os.startfile(os.path.dirname(LOG_PATH))
            except Exception:
                pass
        elif cid == CMD_QUIT:
            self.engine.request_quit()


# --------------------------------------------------------------------------
# 引擎
# --------------------------------------------------------------------------
class GlassEngine:
    def __init__(self, cfg: GlassConfig):
        self.cfg = cfg
        self.self_pid = os.getpid()
        self.lock = threading.RLock()
        self.states = {}                      # hwnd -> WinState
        self._hooks = []
        self._hook_tid = 0
        self._stop = threading.Event()
        self._dirty = threading.Event()
        self._cb_ref = None                   # 防止回调被 GC
        self._ctrl_ref = None
        self._restored = False
        # 幂等守卫必须与 _stop 分开：托盘退出/卸载器 WM_CLOSE 都是先把 _stop 置上，
        # 再靠主循环退出走到 shutdown()。若 shutdown() 用 _stop 判幂等，就会直接
        # return，窗口全部卡在半透明 —— 这是实测抓到的真 bug。
        self._shutdown_done = False
        self.paused = False
        self.tray = None
        self.stats = {"adopted": 0, "transitions": 0, "failed": 0}
        self._cfg_lock = threading.Lock()
        self._cfg_saved_at = 0.0
        self._cfg_dirty = False

    # ---------------- 滑块取值 ----------------
    def set_alpha_targets(self, inactive_pct=None, active_pct=None):
        """托盘滑块改值时调用：更新配置 + 立刻重算目标 + 落盘（带节流）。

        只改内存不重算的话，焦点没变时窗口不会刷新，拖动就不是实时的。
        """
        with self.lock:
            if inactive_pct is not None:
                self.cfg.inactive_pct = inactive_pct
            if active_pct is not None:
                self.cfg.active_pct = active_pct
        self._dirty.set()
        self.save_cfg()

    def save_cfg(self, force: bool = False):
        """写配置文件。拖动滑块时会频繁触发，所以节流到 0.3s 一次；
        菜单关闭 / 退出时用 force=True 保证最后一次一定落盘。"""
        now = time.monotonic()
        with self._cfg_lock:
            if not self.cfg.cfg_path:        # --no-config：明确不落盘
                self._cfg_dirty = False
                return
            if not force and (now - self._cfg_saved_at) < 0.3:
                self._cfg_dirty = True
                return
            self._cfg_saved_at = now
            self._cfg_dirty = False
            snapshot = self.cfg.as_dict()
            path = self.cfg.cfg_path
        if save_cfg_file(snapshot, path) and self.cfg.verbose:
            print(f"[win_glass] 配置已保存：{path}")

    # ---------------- 透明度 ----------------
    def _ensure_layered(self, st: WinState) -> bool:
        """给窗口挂上 WS_EX_LAYERED（只挂一次）。"""
        hwnd = st.hwnd
        ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
        if ex & WS_EX_LAYERED:
            return True
        _SetWindowLong(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
        err = ctypes.get_last_error()
        ex2 = _GetWindowLong(hwnd, GWL_EXSTYLE)
        if not (ex2 & WS_EX_LAYERED):
            return False
        st.layered_owned = True
        if not st.framechanged:
            # MSDN：动态改扩展样式后需要一次 FRAMECHANGED 让变更生效
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER |
                                SWP_NOACTIVATE | SWP_FRAMECHANGED)
            st.framechanged = True
        return True

    def _apply_alpha(self, st: WinState) -> bool:
        if st.failed:
            return False
        hwnd = st.hwnd
        if not user32.IsWindow(hwnd):
            return False
        alpha = int(round(st.cur * 255.0))
        alpha = 0 if alpha < 0 else (255 if alpha > 255 else alpha)
        if alpha == st.applied:
            return True
        try:
            if not self._ensure_layered(st):
                st.failed = True
                self.stats["failed"] += 1
                if self.cfg.verbose:
                    print(f"  [跳过] 0x{hwnd:X} 无法挂 LAYERED  ({st.cls})")
                return False
            ok = user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
            if not ok:
                st.failed = True
                self.stats["failed"] += 1
                if self.cfg.verbose:
                    print(f"  [跳过] 0x{hwnd:X} SetLayeredWindowAttributes 失败 ({st.cls})")
                return False
            st.applied = alpha
            return True
        except Exception:
            st.failed = True
            self.stats["failed"] += 1
            return False

    def _restore(self, st: WinState):
        """还原透明度与窗口样式。"""
        hwnd = st.hwnd
        try:
            if not user32.IsWindow(hwnd):
                return
            if st.layered_owned:
                ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
                if ex & WS_EX_LAYERED:
                    user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
                    _SetWindowLong(hwnd, GWL_EXSTYLE, ex & ~WS_EX_LAYERED)
                    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER |
                                        SWP_NOACTIVATE | SWP_FRAMECHANGED)
            else:
                user32.SetLayeredWindowAttributes(hwnd, 0, st.orig_alpha, LWA_ALPHA)
        except Exception:
            pass

    # ---------------- 目标计算 ----------------
    def _set_target(self, st: WinState, target: float, reason: str):
        if abs(st.dst - target) < 0.0005:
            return
        old = st.dst
        st.src = st.cur
        st.dst = target
        st.t0 = time.perf_counter()
        st.dur = self.cfg.fade_ms / 1000.0
        self.stats["transitions"] += 1
        if self.cfg.verbose:
            print(f"  [{time.strftime('%H:%M:%S')}] 0x{st.hwnd:X} "
                  f"{int(old*100)}% -> {int(target*100)}%  ({reason})  {st.title[:40]}")

    def _adopt(self, hwnd: int, target: float):
        """新接管的窗口：直接设为目标值，不做淡入（窗口刚出现，没有跳变感）。"""
        st = WinState(hwnd)
        st.title = _window_text(hwnd)
        st.cls = _class_name(hwnd)
        st.cur = st.src = st.dst = target
        st.dur = 0.0
        # 记录原始 alpha，退出时好还原
        key = wt.DWORD(0)
        a = c_ubyte(255)
        fl = wt.DWORD(0)
        if user32.GetLayeredWindowAttributes(hwnd, byref(key), byref(a), byref(fl)):
            st.orig_alpha = a.value
        else:
            st.orig_alpha = 255
        with self.lock:
            self.states[hwnd] = st
        self._apply_alpha(st)
        self.stats["adopted"] += 1
        if self.cfg.verbose:
            print(f"  [接管] 0x{hwnd:X} {int(target*100)}%  ({st.cls})  {st.title[:40]}")

    def _refresh_window_list(self):
        """全量枚举：发现新窗口、清理已消失的窗口。"""
        alive = set(scan_windows(self.cfg, self.self_pid))
        fg = _h(user32.GetForegroundWindow())
        with self.lock:
            for hwnd in alive:
                if hwnd not in self.states:
                    st_tmp = WinState(hwnd)
                    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
                    top = bool(ex & WS_EX_TOPMOST)
                    tgt = self.cfg.active_alpha if (hwnd == fg or top) \
                        else self.cfg.inactive_alpha
                    self._adopt(hwnd, tgt)
            for hwnd in list(self.states):
                if hwnd not in alive:
                    st = self.states.pop(hwnd)
                    self._restore(st)

    def _update_targets(self):
        """只读式重算目标（含置顶检测），很轻。暂停时不做任何改动。"""
        if self.paused:
            return
        fg = _h(user32.GetForegroundWindow())
        with self.lock:
            for hwnd, st in self.states.items():
                if not user32.IsWindow(hwnd):
                    continue
                ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
                top = bool(ex & WS_EX_TOPMOST)
                is_fg = (hwnd == fg)
                reason = "聚焦" if is_fg else ("置顶" if top else "未聚焦")
                st.topmost, st.is_fg = top, is_fg
                tgt = self.cfg.active_alpha if (is_fg or top) \
                    else self.cfg.inactive_alpha
                self._set_target(st, tgt, reason)

    # ---------------- 动画 ----------------
    def _tick(self, now: float):
        with self.lock:
            for st in list(self.states.values()):
                if st.cur == st.dst:
                    continue
                if st.dur <= 0.0:
                    st.cur = st.dst
                else:
                    t = (now - st.t0) / st.dur
                    if t >= 1.0:
                        st.cur = st.dst
                    else:
                        st.cur = st.src + (st.dst - st.src) * smoothstep(t)
                self._apply_alpha(st)

    # ---------------- 事件钩子 ----------------
    def _hook_cb(self, _hook, event, hwnd, _idobj, _idchild, _tid, _time):
        self._dirty.set()

    def _restore_all(self) -> int:
        """幂等还原：把所有接管窗口恢复原状。Ctrl+C / 关控制台 / 注销 / 关机都会走这里。"""
        with self.lock:
            if self._restored:
                return 0
            self._restored = True
            n = len(self.states)
            for st in self.states.values():
                self._restore(st)
            self.states.clear()
        return n

    def _on_console_ctrl(self, ctrl_type):
        """控制台控制事件处理。CTRL_CLOSE/LOGOFF/SHUTDOWN 时抢时间还原，否则窗口会卡在半透明。"""
        if ctrl_type in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
            if self.cfg.restore_on_exit:
                n = self._restore_all()
                print(f"[win_glass] 用户结束会话，已还原 {n} 个窗口。", flush=True)
            self._stop.set()
            return True          # 已处理，进程随后即终止
        return False             # Ctrl+C 交给 Python 的 KeyboardInterrupt 正常走 finally

    # ---------------- 托盘动作 ----------------
    def set_paused(self, flag):
        self.paused = bool(flag)
        if self.paused:
            with self.lock:
                for st in self.states.values():
                    st.cur = st.src = st.dst = 1.0
                    self._apply_alpha(st)
            print("[win_glass] 已暂停：所有窗口恢复 100%")
        else:
            print("[win_glass] 已继续")
        self._dirty.set()

    def restore_now(self):
        with self.lock:
            for st in self.states.values():
                st.cur = st.src = st.dst = 1.0
                self._apply_alpha(st)
        print("[win_glass] 已把所有窗口恢复为 100%")

    def request_quit(self):
        print("[win_glass] 收到退出请求，正在还原并退出…")
        self._stop.set()

    def _hook_loop(self):
        self._hook_tid = kernel32.GetCurrentThreadId()
        ranges = [
            (EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND),
            (EVENT_SYSTEM_MINIMIZESTART, EVENT_SYSTEM_MINIMIZEEND),
            (EVENT_OBJECT_CREATE, EVENT_OBJECT_HIDE),
            (EVENT_OBJECT_STATECHANGE, EVENT_OBJECT_STATECHANGE),
        ]
        flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
        for lo, hi in ranges:
            h = user32.SetWinEventHook(lo, hi, None, self._cb_ref, 0, 0, flags)
            if h:
                self._hooks.append(h)
        if not self._hooks:
            print("[win_glass] 警告：事件钩子注册失败，将退化为纯轮询模式。")
        msg = wt.MSG()
        while True:
            r = user32.GetMessageW(byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

    # ---------------- 主循环 ----------------
    def run(self, duration: float = 0.0):
        self._cb_ref = WINEventProc(self._hook_cb)
        # 关控制台窗口 / 注销 / 关机时抢时间还原，避免窗口卡在半透明
        if sys.platform.startswith("win"):
            self._ctrl_ref = PHANDLER_ROUTINE(self._on_console_ctrl)
            try:
                kernel32.SetConsoleCtrlHandler(self._ctrl_ref, True)
            except Exception:
                pass
        t_hook = threading.Thread(target=self._hook_loop, name="winglass-hook", daemon=True)
        t_hook.start()
        time.sleep(0.25)                     # 等钩子就位

        if self.cfg.tray:
            try:
                self.tray = TrayIcon(self)
                if self.tray.start():
                    print("[win_glass] 托盘图标已就位（左键暂停/继续，右键菜单可退出）")
                else:
                    print("[win_glass] 托盘图标创建失败，改用控制台交互。")
                    self.tray = None
            except Exception as e:
                print("[win_glass] 托盘创建异常：%s" % e)
                self.tray = None

        print(f"[win_glass] v{APP_VER} 启动  未聚焦={self.cfg.inactive_pct}%  "
              f"聚焦/置顶={self.cfg.active_pct}%  渐变={self.cfg.fade_ms}ms  "
              f"{self.cfg.fps}fps  配置={self.cfg.cfg_path}")
        self._refresh_window_list()
        hint = "托盘右键退出" if self.tray else "Ctrl+C 退出"
        print(f"[win_glass] 首批接管 {len(self.states)} 个窗口，开始实时跟随。（{hint}）")

        frame = 1.0 / self.cfg.fps
        next_t = time.perf_counter()
        last_scan = 0.0
        last_rescan = 0.0
        t_start = time.perf_counter()
        try:
            while not self._stop.is_set():
                now = time.perf_counter()
                if self._dirty.is_set() or (now - last_scan) >= self.cfg.scan_interval:
                    self._dirty.clear()
                    last_scan = now
                    self._update_targets()
                if (now - last_rescan) >= self.cfg.rescan_interval:
                    last_rescan = now
                    self._refresh_window_list()
                self._tick(now)
                if duration and (now - t_start) >= duration:
                    break
                next_t += frame
                d = next_t - time.perf_counter()
                if d > 0:
                    time.sleep(d)
                else:
                    next_t = time.perf_counter()
        except KeyboardInterrupt:
            print("\n[win_glass] 收到中断。")
        finally:
            self.shutdown()

    def shutdown(self):
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._stop.set()
        self.save_cfg(force=True)          # 滑块的最后一次拖动可能还在节流窗口里
        for h in self._hooks:
            try:
                user32.UnhookWinEvent(h)
            except Exception:
                pass
        self._hooks.clear()
        if self._hook_tid:
            try:
                user32.PostThreadMessageW(self._hook_tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        if self.cfg.restore_on_exit:
            n = self._restore_all()
            print(f"[win_glass] 已还原 {n} 个窗口。接管 {self.stats['adopted']} 个 / "
                  f"状态切换 {self.stats['transitions']} 次 / 跳过 {self.stats['failed']} 个。")


# --------------------------------------------------------------------------
# --list ：只读体检
# --------------------------------------------------------------------------
def list_windows(cfg: GlassConfig):
    self_pid = os.getpid()
    fg = _h(user32.GetForegroundWindow())
    rows = []
    for hwnd in scan_windows(cfg, self_pid):
        ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
        top = bool(ex & WS_EX_TOPMOST)
        is_fg = (hwnd == fg)
        if is_fg:
            tgt, why = cfg.active_pct, "聚焦"
        elif top:
            tgt, why = cfg.active_pct, "置顶"
        else:
            tgt, why = cfg.inactive_pct, "未聚焦"
        rows.append((hwnd, _class_name(hwnd), _window_text(hwnd), tgt, why))
    rows.sort(key=lambda r: (-r[3], r[1]))
    print(f"可管理窗口 {len(rows)} 个   未聚焦目标={cfg.inactive_pct}%   "
          f"聚焦/置顶目标={cfg.active_pct}%")
    print("-" * 96)
    print(f"{'HWND':>10}  {'目标':>5}  {'原因':<7} {'类名':<28} 标题")
    print("-" * 96)
    for hwnd, cls, title, tgt, why in rows:
        print(f"0x{hwnd:08X}  {tgt:>4}%  {why:<7} {cls[:28]:<28} {title[:34]}")
    print("-" * 96)


# --------------------------------------------------------------------------
# --self-test ：用自带测试窗口验证透明度链路（只影响自己的窗口）
# --------------------------------------------------------------------------
def self_test(cfg: GlassConfig):
    try:
        import tkinter as tk
    except Exception as e:
        print(f"[self-test] 需要 tkinter，当前解释器没有：{e}")
        print("           请换用一个自带 tkinter 的 Python 发行版"
              "（官方 python.org 的 Windows 安装包默认就带）。")
        return 1

    alpha_out = c_ubyte(255)
    key_out = wt.DWORD(0)
    flag_out = wt.DWORD(0)

    def read_alpha(hwnd):
        if user32.GetLayeredWindowAttributes(hwnd, byref(key_out), byref(alpha_out), byref(flag_out)):
            return alpha_out.value
        return None

    def set_alpha(hwnd, v):
        user32.SetLayeredWindowAttributes(hwnd, 0, max(0, min(255, int(v))), LWA_ALPHA)

    root = tk.Tk()
    root.title("win_glass self-test")
    root.geometry("460x200+140+140")
    tk.Label(root, text="透明度链路自检\n(仅作用于本测试窗口)",
             font=("Microsoft YaHei", 14)).pack(expand=True)
    root.update()

    hwnd = _h(user32.GetAncestor(root.winfo_id(), GA_ROOT)) or _h(root.winfo_id())
    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
    _SetWindowLong(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    print(f"[self-test] 测试窗口 HWND=0x{hwnd:X}  已挂 WS_EX_LAYERED")

    ok = user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
    print(f"[self-test] SetLayeredWindowAttributes 返回 {bool(ok)}，读回 alpha={read_alpha(hwnd)}")
    if not ok:
        root.destroy()
        return 1

    # 跑一段 聚焦% -> 非聚焦% -> 聚焦% 的缓动，并采样读回（单位统一为不透明度 0..1）
    hi, lo = cfg.active_alpha, cfg.inactive_alpha
    print(f"[self-test] 滑块取值：非聚焦={cfg.inactive_pct}%  聚焦={cfg.active_pct}%"
          f"（均为整数百分比）")
    print(f"[self-test] 播放 {cfg.fade_ms}ms 缓动   {cfg.active_pct}% -> "
          f"{cfg.inactive_pct}% -> {cfg.active_pct}%")
    samples = []
    seq = [(hi, lo), (lo, hi)]
    step_ms = 50

    def play(leg_idx, elapsed):
        if leg_idx >= len(seq):
            print("[self-test] 采样读回（应为平滑单调变化，无突跳）：")
            print("           " + " ".join(str(s) for s in samples))
            root.after(400, root.destroy)
            return
        start, end = seq[leg_idx]
        if elapsed >= cfg.fade_ms:
            set_alpha(hwnd, round(end * 255))
            play(leg_idx + 1, 0)
            return
        t = elapsed / cfg.fade_ms
        v = start + (end - start) * smoothstep(t)
        set_alpha(hwnd, round(v * 255))
        got = read_alpha(hwnd)
        samples.append(got)
        root.after(step_ms, lambda: play(leg_idx, elapsed + step_ms))

    root.after(200, lambda: play(0, 0))
    root.mainloop()
    print("[self-test] 完成：透明度设置与读回链路可用。")
    return 0


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="win_glass — 窗口透明度随聚焦状态动态变化"
                    "（未聚焦 5~95%，聚焦/置顶 5~100%，托盘菜单可调）")
    ap.add_argument("--inactive-alpha", type=float, default=None,
                    help="未聚焦窗口的不透明度，0.05~0.95（也接受 5~95），"
                         "默认取配置文件，否则 0.40")
    ap.add_argument("--active-alpha", type=float, default=None,
                    help="聚焦 / 置顶窗口的不透明度，0.05~1.00（也接受 5~100），"
                         "默认取配置文件，否则 1.00")
    ap.add_argument("--no-config", action="store_true",
                    help="既不读取也不写入配置文件（滑块改动只在本次运行有效）")
    ap.add_argument("--save-config", action="store_true",
                    help="把本次命令行参数写入配置文件后继续运行")
    ap.add_argument("--fade-ms", type=int, default=500, help="渐变时长(ms)，默认 500")
    ap.add_argument("--fps", type=int, default=60, help="动画帧率，默认 60")
    ap.add_argument("--scan", type=float, default=0.15, help="目标重算间隔(秒)，默认 0.15")
    ap.add_argument("--rescan", type=float, default=0.50, help="窗口全量枚举间隔(秒)，默认 0.50")
    ap.add_argument("--exclude", default="", help="额外排除的窗口类名，逗号分隔")
    ap.add_argument("--no-skip-fullscreen", action="store_true",
                    help="不排除全屏窗口（默认排除，避免游戏/视频被透明化）")
    ap.add_argument("--skip-foreign-layered", action="store_true",
                    help="跳过已自带 WS_EX_LAYERED 的窗口（Chromium/Electron 系，最保守）")
    ap.add_argument("--no-restore", action="store_true", help="退出时不还原透明度")
    ap.add_argument("--no-tray", action="store_true", help="不创建系统托盘图标")
    ap.add_argument("--log", default="", help="日志文件路径（无控制台时使用）")
    ap.add_argument("--duration", type=float, default=0.0, help="运行指定秒数后自动退出")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印每次状态变化")
    ap.add_argument("--list", action="store_true", help="只列出窗口与目标透明度，不做修改")
    ap.add_argument("--self-test", action="store_true", help="用自带测试窗口验证透明度链路")
    ap.add_argument("--version", action="version", version="win_glass %s" % APP_VER)
    args = ap.parse_args()
    _setup_io(args.log or None)      # --log 可覆盖默认日志位置

    # 命令行显式值 > 配置文件 > 内置默认
    saved = {} if args.no_config else load_cfg_file()
    inactive, active = GlassConfig.apply_saved(saved, args.inactive_alpha,
                                               args.active_alpha)
    cfg = GlassConfig(
        inactive_alpha=inactive,
        active_alpha=active,
        cfg_path="" if args.no_config else None,
        fade_ms=args.fade_ms,
        fps=args.fps,
        scan_interval=args.scan,
        rescan_interval=args.rescan,
        skip_fullscreen=not args.no_skip_fullscreen,
        skip_foreign_layered=args.skip_foreign_layered,
        extra_exclude=[c.strip() for c in args.exclude.split(",") if c.strip()],
        verbose=args.verbose,
        restore_on_exit=not args.no_restore,
        tray=not args.no_tray,
        log_path=args.log,
    )
    if args.save_config and not args.no_config:
        if cfg.save():
            print("[win_glass] 已写入配置 %s：非聚焦=%d%%  聚焦=%d%%"
                  % (CFG_PATH, cfg.inactive_pct, cfg.active_pct))
        else:
            print("[win_glass] 配置写入失败，本次改动仅内存生效。")

    if args.list:
        list_windows(cfg)
        return 0
    if args.self_test:
        return self_test(cfg)

    engine = GlassEngine(cfg)
    engine.run(duration=args.duration)
    return 0


if __name__ == "__main__":
    sys.exit(main())
