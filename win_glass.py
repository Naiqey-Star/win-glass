# -*- coding: utf-8 -*-
"""
win_glass.py — Windows 窗口美化工具：透明度随「聚焦 / 置顶 / 未聚焦」实时变化

状态规则
    聚焦窗口  -> 100%
    置顶窗口  -> 100%
    其余窗口  -> 40%   （--inactive-alpha 可调）

特性
    * 实时   —— 焦点/置顶状态一变，立刻重新起动画
    * 平滑   —— 默认 500ms 缓动(smoothstep)，绝不突跳
    * 无依赖 —— 纯 ctypes 调用 user32/dwmapi，不需要 pywin32
    * 可还原 —— 退出时把透明度与窗口样式恢复原状

用法
    python win_glass.py                   常驻运行，Ctrl+C 退出
    python win_glass.py --list            只列出窗口与其目标透明度，不改动
    python win_glass.py --self-test       用自带测试窗口验证透明度链路
    python win_glass.py --fade-ms 500 --inactive-alpha 0.4
    python win_glass.py --duration 20     跑 20 秒后自动退出并还原

作者：月见八千代 (Yachiyo)
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
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
APP_VER = "1.0.1"
LOG_PATH = DEFAULT_LOG
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
# 配置
# --------------------------------------------------------------------------
class GlassConfig:
    def __init__(self, inactive_alpha=0.40, fade_ms=500, fps=60,
                 scan_interval=0.15, rescan_interval=0.50,
                 skip_fullscreen=True, skip_foreign_layered=False,
                 extra_exclude=(), verbose=False, restore_on_exit=True,
                 tray=True, log_path=""):
        self.inactive_alpha = min(max(float(inactive_alpha), 0.05), 1.0)
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


class TrayIcon:
    """系统托盘图标。左键单击=暂停/继续；右键菜单=暂停、恢复、打开日志、退出。"""

    def __init__(self, engine, tip="win_glass — 窗口聚焦透明"):
        self.engine = engine
        self.tip = tip[:127]
        self.hwnd = 0
        self._proc_ref = None
        self._ready = threading.Event()

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
        user32.AppendMenuW(m, MF_STRING, CMD_LOG, "打开日志")
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(m, MF_STRING, CMD_QUIT, "退出（还原全部窗口）")
        pt = wt.POINT()
        user32.GetCursorPos(byref(pt))
        # TrackPopupMenu 要求窗口在前台，否则点菜单外部不会关闭
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(m)
        if cmd:
            self._invoke(int(cmd))

    def _invoke(self, cid):
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
                    tgt = 1.0 if (hwnd == fg or top) else self.cfg.inactive_alpha
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
                tgt = 1.0 if (is_fg or top) else self.cfg.inactive_alpha
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

        print(f"[win_glass] v{APP_VER} 启动  未聚焦={int(self.cfg.inactive_alpha*100)}%  "
              f"聚焦/置顶=100%  渐变={self.cfg.fade_ms}ms  {self.cfg.fps}fps")
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
            tgt, why = 100, "聚焦"
        elif top:
            tgt, why = 100, "置顶"
        else:
            tgt, why = int(cfg.inactive_alpha * 100), "未聚焦"
        rows.append((hwnd, _class_name(hwnd), _window_text(hwnd), tgt, why))
    rows.sort(key=lambda r: (-r[3], r[1]))
    print(f"可管理窗口 {len(rows)} 个   未聚焦目标={int(cfg.inactive_alpha*100)}%   聚焦/置顶=100%")
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

    # 跑一段 100% -> 40% -> 100% 的缓动，并采样读回（单位统一为不透明度 0..1）
    print(f"[self-test] 播放 {cfg.fade_ms}ms 缓动   100% -> "
          f"{int(cfg.inactive_alpha*100)}% -> 100%")
    samples = []
    seq = [(1.0, cfg.inactive_alpha), (cfg.inactive_alpha, 1.0)]
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
        description="win_glass — 窗口透明度随聚焦状态动态变化（聚焦/置顶 100%，未聚焦 40%）")
    ap.add_argument("--inactive-alpha", type=float, default=0.40,
                    help="未聚焦窗口的不透明度，0.05~1.0，默认 0.40")
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

    cfg = GlassConfig(
        inactive_alpha=args.inactive_alpha,
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
