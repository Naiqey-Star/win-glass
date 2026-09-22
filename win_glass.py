# -*- coding: utf-8 -*-
"""
win_glass.py — Windows 窗口美化工具：透明度随「全屏 / 聚焦 / 最大化 / 置顶 / 悬停 / 未聚焦」实时变化

状态规则（**按优先级从上到下，先命中先返回**）
    ① 全屏窗口  -> 100%   **恒定 100%，完全不受「聚焦最高透明度」设置影响** ——
                          全屏基本等于游戏/视频/演示，被压暗就没法看了
    ② 聚焦窗口  -> 最大   （托盘菜单「聚焦最高透明度」可调，5~100%）
    ③ 最大化窗口-> 最大   （同上。最大化与置顶都**视为聚焦**：它们同样占满
    ④ 置顶窗口  -> 最大     视觉主导权，只是没有键盘焦点）
    ⑤ 悬停窗口  -> 70%    （v1.3.0：未聚焦窗口被鼠标压住时提亮到「最大/最低」
                           之间的插值点；默认 100%/40% ⇒ 70%）
    ⑥ 其余窗口  -> 40%    （托盘菜单「非聚焦最低透明度」可调，5~95%）

    ⇒ ②③④ 是同一组、⑤ 是另一组：悬停**只作用于"本应被压暗"的窗口**，
      全屏/聚焦/最大化/置顶都不参与悬停（它们当前都是或应当是最高透明度，
      按插值算只会把它们压暗）。

特性
    * 实时   —— 焦点/最大化/置顶/全屏/悬停状态一变，立刻重新起动画
    * 平滑   —— 默认 500ms 缓动(smoothstep)，绝不突跳
    * 无依赖 —— 纯 ctypes 调用 user32/dwmapi，不需要 pywin32
    * 可还原 —— 退出时把透明度与窗口样式恢复原状
    * 可调   —— 托盘右键菜单里有三个滑块：两个透明度（步进 1%）+
               悬停插值系数（步进 0.1），取值全部持久化

用法
    python win_glass.py                   常驻运行，Ctrl+C 退出
    python win_glass.py --list            只列出窗口与其目标透明度，不改动
    python win_glass.py --self-test       用自带测试窗口验证透明度链路
    python win_glass.py --fade-ms 500 --inactive-alpha 0.4
    python win_glass.py --no-hover        关掉「悬停半透明」
    python win_glass.py --hover-ratio 0.8 悬停值取「最低→最高」的 80%（默认）
    python win_glass.py --skip-fullscreen 全屏窗口完全不接管（给全屏游戏留退路）
    python win_glass.py --duration 20     跑 20 秒后自动退出并还原

托盘右键菜单（每项右键可绑全局快捷键，v1.7.0）
    暂停 / [悬停半透明] / [全屏窗口固定 100%] / [层叠衰减] /
    [非聚焦最低透明度] / [聚焦最高透明度] / [悬停插值系数] / [层衰减系数] /
    渐隐时间… / 语言 / 打开日志 / 退出
    滑块：两个透明度 5~95% 与 5~100%（步进 1%、显示整数百分比），
    另有「悬停插值系数」0.0~1.0 与「层衰减系数」0.1~1.0（步进 0.1、一位小数）。
    拖动、鼠标滚轮、左右方向键都能调；调完写入
    %LOCALAPPDATA%\\win_glass\\config.json，下次启动自动生效。

悬停半透明（v1.3.0；v1.7.1 起带「联动压暗」）
    * 被悬停窗口的值 = 最低 + (最高 − 最低) × hover_ratio，系数**由菜单里的
      「悬停插值系数」滑块实时调节**（0.0~1.0，步进 0.1，默认 0.8）：
      默认 100%/40% ⇒ 88%；拖到 0.5 ⇒ 70%；拖到 0 ⇒ 等于最低值（等于没开）。
    * 「提亮」只作用于**本应被压暗的窗口**：全屏/聚焦/最大化/置顶本就在最高值，
      按同一个比例算反而会压暗它们 ⇒ 它们不参与提亮。
    * ⭐ v1.7.1 **联动压暗**：悬停某个窗口时，**其余所有受规则影响的窗口（无论
      是否聚焦）**一起压暗到「基准值 × 压暗比例」，制造焦点对比：
          压暗比例 = 悬停插值系数 − 0.3，下限 0.1
      例：系数 0.7 ⇒ 比例 0.4 ⇒ 一个 100% 的窗口被压到 40%；压暗后绝对下限 5%。
      全屏窗口恒 100%、不参与；被悬停的那个窗口自身只提亮、不压暗。
    * 全局同时最多只有一个「悬停窗口」（鼠标只有一个点），取 WindowFromPoint
      真正会收到鼠标的那个窗口。
    * 悬停目标变了不改动别的东西：新目标从**当前透明度**起缓动，所以鼠标快速
      在多个窗口之间划过时，是一条连续曲线上的折线，不会突跳、也不会互相干扰。

全屏窗口（v1.4.0）—— 为什么要单独定一条 100%
    * 「全屏」= **不是最大化** 且 窗口矩形完整覆盖所在显示器的 rcMonitor
      （见 `_is_fullscreen`）：有边框的全屏、无边框全屏（游戏常见的 borderless）、
      F11 全屏都算。
    * ⚠️ **最大化 ≠ 全屏**：两者是独立状态。最大化窗口的矩形因为那圈看不见的缩放
      边框会**越出屏幕 8px**，光按矩形判会把它误判成全屏；所以 `IsZoomed()` 是
      一票否决 —— 最大化窗口走「最高透明度」，不受本段影响。
    * 全屏时目标值**写死 1.0**，不走「聚焦最高透明度」—— 用户把最高值调到
      60% 是为了看清背景窗口，不是为了把全屏视频压暗。
    * ⚠️ 但**不会白白给它加 WS_EX_LAYERED**：本来没分层的窗口加层会丢掉 DWM
      的独立翻转/硬件叠加优化（全屏游戏可能掉帧），而 100% 的观感与非分层完全
      一致 ⇒ "目标 100% 且我们没占过它"时一个字都不改。
    * 想彻底不管全屏窗口（例如玩游戏时连判定都省掉）：托盘菜单里把
      「全屏窗口固定 100%」取消勾选，或命令行 `--skip-fullscreen`。

作者：Naiqey.千鵺 <1609458331@qq.com>
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

try:
    # 多语言文案与快捷键的「纯逻辑」层，见 win_glass_i18n.py 的说明。
    # 单独成模块是为了能脱离 GUI 单测（它不碰 ctypes、不碰窗口）。
    import win_glass_i18n as i18n
except ImportError:                                   # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import win_glass_i18n as i18n

# --------------------------------------------------------------------------
# 输出环境：既要中文不乱码，也要兼容「窗口化(--noconsole)打包」时没有控制台的情况
# --------------------------------------------------------------------------
DEFAULT_LOG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                           "win_glass", "win_glass.log")
DEFAULT_CFG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                           "win_glass", "config.json")
APP_VER = "1.7.1"
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
GW_HWNDNEXT = 2          # GetWindow：同层的下一个窗口（沿它走就是 Z 序往下一层）
MONITOR_DEFAULTTONEAREST = 2
DWMWA_CLOAKED = 14
WM_QUIT = 0x0012
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

# ---- 悬停半透明（v1.3.0）----
# 悬停值 = 最低 + (最高 − 最低) × HOVER_RATIO。0.8 = 偏向最高值一侧。
HOVER_RATIO_MIN, HOVER_RATIO_MAX = 0.0, 1.0
DEFAULT_HOVER_RATIO = 0.8
# 托盘滑块是**整数**滑块（1 档 = 1 单位），而系数是 0.0~1.0 的一位小数，
# 所以统一按「单位」来走：0.1 → 1 单位，范围 0~10，除以 HOVER_RATIO_UNITS 还原。
# 这样取值精度天然是 0.1，也不会引入浮点步进误差。
HOVER_RATIO_UNITS = 10
# 鼠标位置的轮询间隔（秒）。50ms 足够跟手，又几乎不占 CPU：
# 光标没动的那一轮直接返回，连 WindowFromPoint 都不做。
DEFAULT_HOVER_INTERVAL = 0.05

# ---- 悬停联动压暗（v1.7.1）----
# 悬停某个窗口时，除了把被悬停的窗口按系数提亮，还要把**其余**「受透明度规则
# 影响」的窗口一起压暗，制造焦点对比：
#     其余窗口目标 = max( 基准值 × HOVER_DIM_RATIO , LAYER_MIN_PCT/100 )
#     HOVER_DIM_RATIO = 悬停插值系数 − HOVER_DIM_OFFSET，下限 HOVER_DIM_MIN_RATIO
# 参与范围：「无论是否聚焦」——聚焦 / 最大化 / 置顶 / 未聚焦都算；
# 唯二例外：全屏窗口恒 100% 不受规则影响，被悬停的那个窗口自己只提亮、
# 绝不进这条压暗分支。
HOVER_DIM_OFFSET = 0.3
HOVER_DIM_MIN_RATIO = 0.1

# ---- 全屏锁定 100%（v1.4.0）----
# 全屏窗口的目标透明度写死这个值，**不读 active_pct**：
# 用户调「聚焦最高透明度」是为了看清背景，不是为了压暗全屏视频/游戏。
FULLSCREEN_ALPHA = 1.0

# ---- 层叠衰减（v1.6.0）----
# 普通非聚焦窗口按**它在这个堆叠栈里的位置**递减：
#   第 1 层（栈里最靠上的普通非聚焦窗口）= inactive_pct
#   之后每层 = 上一层**已取整的显示值** × LAYER_DECAY_RATIO，四舍五入
#   低于 LAYER_MIN_PCT 就直接封底
# 「视作聚焦」的窗口（最大化 / 置顶）和全屏窗口**不参与层级编号** ——
# 它们各自有更高的优先级，不会因为排在下面而被压暗。
LAYER_DECAY_MIN, LAYER_DECAY_MAX = 0.10, 1.00
DEFAULT_LAYER_DECAY = 0.70
# 和悬停系数一样：滑块是整数档，1 档 = 0.1 ⇒ 范围 1~10。
LAYER_DECAY_UNITS = 10
# 逐层递推的透明度下限（%）。算到就等于它，再往下不再继续乘。
LAYER_MIN_PCT = 5

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
# 菜单里的三个滑块（owner-draw，不走 WM_COMMAND 业务逻辑）
CMD_SLIDE_INACTIVE, CMD_SLIDE_ACTIVE = 10, 11
# 「渐隐时间…」：普通菜单项，点开弹一个数值输入框
CMD_FADE_MS = 12
# 「悬停半透明」：普通菜单项，勾选式开关（v1.3.0）
CMD_HOVER = 13
# 「全屏窗口固定 100%」：勾选式开关（v1.4.0）
CMD_FULLSCREEN = 14
# 「悬停插值系数」：owner-draw 滑块，0.0~1.0、0.1 一档（v1.5.0）
CMD_SLIDE_HOVER = 15
# 「层叠衰减」：勾选式开关，按窗口在堆叠栈里的位置逐层递减（v1.6.0）
CMD_LAYER = 16
# 「层衰减系数」：owner-draw 滑块，0.1~1.0、0.1 一档（v1.6.0）
CMD_SLIDE_DECAY = 17

# 滑块外观：整条菜单的宽度由最宽的 owner-draw 项决定。
# 观感对齐 **Windows 任务栏音量条**：细轨道 + 强调色填充 + 圆形手柄。
SLIDER_ITEM_W = 300        # 菜单项宽度(px)
SLIDER_ITEM_H = 46         # 两行：标题+数值 / 轨道+手柄
SLIDER_PAD_X = 15          # 左右留白，贴近普通菜单项的文字缩进
SLIDER_TITLE_H = 18        # 第一行文字高度
SLIDER_TRACK_H = 4         # 轨道厚度（音量条那种细条）
SLIDER_THUMB_R = 7         # 手柄半径：常态（直径 14）
SLIDER_THUMB_R_HOT = 9     # 手柄半径：悬停/拖动时放大（直径 18）
# 手柄圆心可移动范围相对轨道两端的缩进。
# ⚠️ 取值映射（x→百分比）与绘制（百分比→圆心）**共用**这个常量，
# 这样「点哪里手柄就停在哪儿」，而且两端能精确取到 5% / 100%。
SLIDER_THUMB_INSET = SLIDER_THUMB_R_HOT


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
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
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

# 弹出菜单窗口的窗口类名。Win32 的菜单不是控件，它就是一类叫 "#32768" 的窗口；
# 想让它重绘，必须把 InvalidateRect 打在这个窗口上。
MENU_CLASS = "#32768"
# RedrawWindow 标志：立刻失效并同步重画（不等消息队列里的 WM_PAINT）
RDW_INVALIDATE, RDW_UPDATENOW, RDW_ERASE = 0x0001, 0x0100, 0x0004

# ---------------------------------------------------------------------------
# 全局快捷键（v1.7.0）
# ---------------------------------------------------------------------------
# 菜单项上绑的快捷键靠 RegisterHotKey 走全局热键：托盘那个隐藏窗口本身就有
# 消息循环，WM_HOTKEY 直接落到它的窗口过程里，不需要额外的线程或钩子。
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000            # 按住不放不重复触发（否则按住会刷屏）
VK_BACK, VK_DELETE, VK_ESCAPE = 0x08, 0x2E, 0x1B
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_SPACE = 0x20

# 低级别键盘钩子：录制快捷键时用它把按键**整个吞掉**，否则菜单会把这些键
# 当成助记符/方向键自己处理掉，根本录不到。WH_KEYBOARD_LL 不需要注入 DLL。
WH_KEYBOARD_LL = 13
LLKHF_UP = 0x80                  # KBDLLHOOKSTRUCT.flags 的「松开」位


# ---------------------------------------------------------------------------
# 菜单圆角（v1.7.0）：对齐 Windows 11 的视觉风格
# ---------------------------------------------------------------------------
# DWMWA_WINDOW_CORNER_PREFERENCE 在 Win11(22000+) 上能把任意顶层窗口（包括菜单
# 窗口 #32768）的四角设成圆角；Win10 及更早会直接失败，失败就退回方角，无害。
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DEFAULT, DWMWCP_DONOTROUND, DWMWCP_ROUND, DWMWCP_ROUNDSMALL = 0, 1, 2, 3

try:                                   # 非 Windows 上跑测试时 sys 里没有这项
    _WIN_BUILD = sys.getwindowsversion()[2]
except Exception:                      # pragma: no cover
    _WIN_BUILD = 0
IS_WIN11 = _WIN_BUILD >= 22000         # Win11 首版内部版本是 22000

# owner-draw 菜单项的圆角：Win11 用 6px，Win10 保持 0（直角）以免显得格格不入
MENU_CORNER_R = 6 if IS_WIN11 else 0
# 选中态高亮块相对菜单项内缩一点，圆角才看得出是「一块」而不是半屏色块
MENU_HILITE_INSET = 2

# 两行的普通菜单项（标题 + 灰色快捷键提示）比滑块矮一些
TOGGLE_ITEM_H = 40
TOGGLE_HINT_H = 15                # 第二行（灰色小字）的高度
TOGGLE_PAD_X = 15                 # 和滑块的 SLIDER_PAD_X 对齐，视觉才不歪

# 语言子菜单的命令 ID：从 100 起，一段连续区间，避免和上面的 CMD_* 撞车
CMD_LANG_BASE = 100
CMD_LANG_MENU = 90                # 「语言…」这一项本身（它带子菜单）

# 重绘链路诊断：设 WIN_GLASS_DEBUG_REDRAW=1 后，每次 _redraw_item 都会打印
# 目标窗口、窗口类名、各 API 返回值与 WM_DRAWITEM 计数。排查「拖了不刷新」用这个。
DBG_REDRAW = os.environ.get("WIN_GLASS_DEBUG_REDRAW") == "1"


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
user32.GetUpdateRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), wt.BOOL]
user32.GetUpdateRect.restype = wt.BOOL
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
# ⚠️ Z 序遍历（v1.6.0 层叠衰减）要用这两个，**必须声明 argtypes** ——
# 不声明时 64 位 HWND 会被当 c_int 截断，返回的句柄值错了也不报错，
# 只是静默地走不到底 / 认错窗口（和 IsZoomed 那次是同一类坑）。
user32.GetTopWindow.argtypes = [wt.HWND]
user32.GetTopWindow.restype = wt.HWND
user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
user32.GetWindow.restype = wt.HWND

# ---- 全局热键（v1.7.0）----
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.RegisterHotKey.restype = wt.BOOL
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wt.BOOL
# 录制快捷键时用它读「当前按住的修饰键」——比在 LL 钩子里自己记账更可靠：
# 用户可能在我们开始录制**之前**就按住了 Ctrl，那种情况记账会漏。
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetUserDefaultUILanguage.restype = wt.LANGID
kernel32.GetUserDefaultUILanguage.argtypes = []

# ---- 低级别键盘钩子（录制快捷键用）----
user32.SetWindowsHookExW.restype = wt.HHOOK

# ---- DWM 圆角（Win11）----
if dwmapi is not None:
    dwmapi.DwmSetWindowAttribute.argtypes = [wt.HWND, wt.DWORD,
                                             ctypes.c_void_p, wt.DWORD]
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """WH_KEYBOARD_LL 回调拿到的键盘事件。

    ⚠️ 字段顺序不能改：这是系统填充的二进制结构，改了就会把 scanCode
    当成 vkCode 之类的错位（症状：录到的键永远不对）。
    """
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD),
                ("flags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


def _win_class(hwnd) -> str:
    """取窗口类名（诊断用）。"""
    try:
        buf = ctypes.create_unicode_buffer(256)
        n = user32.GetClassNameW(hwnd, buf, 255)
        return buf.value if n else "?"
    except Exception:
        return "?"
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
# 画圆角轨道 / 圆形手柄要用；配 NULL_PEN 可以只填充不描边，省掉自建画笔
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.GetStockObject.restype = wt.HGDIOBJ
gdi32.RoundRect.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.RoundRect.restype = wt.BOOL
gdi32.Ellipse.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.Ellipse.restype = wt.BOOL
NULL_PEN = 8

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
user32.SetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p]
user32.SetWindowTextW.restype = wt.BOOL
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
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
# v1.4.0：最大化判定。⚠️ 必须显式声明 argtypes —— 不给的话 ctypes 会把 HWND
# 当 c_int 传（32 位截断），在句柄值大的机器上会静默判错窗口。
user32.IsZoomed.argtypes = [wt.HWND]
user32.IsZoomed.restype = wt.BOOL
user32.RedrawWindow.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), wt.HANDLE, wt.UINT]
user32.RedrawWindow.restype = wt.BOOL
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetClientRect.restype = wt.BOOL
if dwmapi is not None:
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
    try:
        dwmapi.DwmGetColorizationColor.argtypes = [ctypes.POINTER(wt.DWORD),
                                                   ctypes.POINTER(wt.BOOL)]
        dwmapi.DwmGetColorizationColor.restype = ctypes.c_long
    except Exception:
        pass


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


# ⚠️ 全屏判定的矩形容差（像素）。真全屏窗口的矩形理论上正好等于 rcMonitor，
# 但不同 DPI 缩放 / 进程 DPI 感知级别下会有一两像素的取整误差；而"窗口比屏幕
# 小 1px"显然不该被踢出全屏。只朝"略小"方向放宽，不朝"略大"方向放宽。
FS_SLACK = 2


def rect_covers_monitor(rc, m, slack: int = FS_SLACK) -> bool:
    """纯几何判定：窗口矩形是否覆盖整个监视器（允许 slack 像素的内缩误差）。

    抽成纯函数是为了可测 —— 不碰任何 Win32 调用，测试里直接喂合成矩形。
    """
    return (rc.left <= m.left + slack and rc.top <= m.top + slack
            and rc.right >= m.right - slack and rc.bottom >= m.bottom - slack)


def _is_fullscreen(hwnd: int, rc: wt.RECT, *, zoomed: bool = None) -> bool:
    """窗口是否处于**真正的全屏**状态。

    ⭐ 关键：**最大化窗口永远不是全屏**（这是 v1.4.0 的一个真 bug 的修复点）。

    为什么必须显式排除最大化：
      Windows 在窗口最大化时，会让窗口矩形**越过屏幕边缘**——那圈看不见的
      缩放边框（`SM_CXSIZEFRAME` + `SM_CXPADDEDBORDER`，本机 = 4+4）会朝左右下
      （新系统上下都算）各外扩 8px。于是本机实测最大化窗口矩形 =
      (-8,-8,1928,1088)，而屏幕是 (0,0,1920,1080)：

          rc.left(-8) <= m.left(0)    ✓
          rc.right(1928) >= m.right(1920)  ✓     →  包含判定"成立"
                                                  →  最大化被误判成全屏
                                                  →  target = FULLSCREEN_ALPHA = 1.0
                                                  →  用户设的「最高透明度」失效

      所以不能只做"矩形包含"判断：`IsZoomed()` 才是 Windows 对"用户按了最大化"
      的权威认定，必须作为**一票否决**挡在前面。

    ⚠️ 也别指望用 rcWork ≠ rcMonitor 来区分两者：任务栏设为自动隐藏时
    rcWork 与 rcMonitor **完全相等**（本机就是这样），那条思路直接失效。

    反过来，"真全屏"的 `IsZoomed()` 是 **False**（F11、无边框全屏、游戏全屏
    都只是把矩形撑满，不走 SW_MAXIMIZE）—— 这正是两者可以干净分开的原因。

    传了 `zoomed` 就复用调用方已经取到的值，省一次 Win32 调用。
    """
    if zoomed is None:
        zoomed = bool(user32.IsZoomed(hwnd))
    if zoomed:
        return False
    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not mon:
        return False
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(mon, byref(mi)):
        return False
    return rect_covers_monitor(rc, mi.rcMonitor)


def read_window_state(hwnd: int, st=None):
    """一次读出判定所需的全部窗口属性：置顶 / 最大化 / 全屏。

    返回 (top, zoomed, fullscreen)；传了 st 就顺手写回它的缓存字段，
    省得调用方再赋值一遍。

    ⚠️ 「最大化」用 IsZoomed，「全屏」必须靠**矩形覆盖整个监视器 + 不是最大化** ——
    这两者是**互相独立**的状态，不能用一个去解释另一个：
      · 「最大化」IsZoomed()==True，矩形往往**越出屏幕 8px**（那圈看不见的缩放边框）
      · 「全屏」（F11 / 无边框 / 游戏）IsZoomed()==False，矩形正好铺满

    只按矩形判会把最大化误判成全屏（进而锁定 100%，用户设的最高透明度失效），
    所以 `_is_fullscreen()` 里 IsZoomed 是一票否决。判定全屏必须排在最大化前面，
    见 target_for()。
    """
    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
    top = bool(ex & WS_EX_TOPMOST)
    zoomed = bool(user32.IsZoomed(hwnd))
    fs = False
    rc = wt.RECT()
    if user32.GetWindowRect(hwnd, byref(rc)):
        fs = _is_fullscreen(hwnd, rc, zoomed=zoomed)
    if st is not None:
        st.topmost, st.zoomed, st.fullscreen = top, zoomed, fs
    return top, zoomed, fs


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


def _detect_sys_lang() -> str:
    """读系统 UI 语言，映射成我们的语言 code；拿不到就回退英文。"""
    try:
        langid = int(kernel32.GetUserDefaultUILanguage())
    except Exception:
        return i18n.FALLBACK_LANG
    return i18n.detect_sys_lang(langid)


def _sanitize_shortcuts(raw) -> dict:
    """把配置里读到的 shortcuts 洗成干净的 {int cid: "Ctrl+Alt+P"}。

    为什么要洗：这个文件用户可能会手改，也可能被旧版本写成别的形状。
    任何一条不合法就**整条丢弃**（而不是抛异常）——少一个快捷键只是没绑上，
    抛异常会让整个程序起不来，代价完全不对等。
    """
    out = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            cid = int(k)
        except Exception:
            continue
        parsed = i18n.parse_combo(v) if isinstance(v, str) else None
        if parsed is None:
            continue
        mods, vk = parsed
        norm = i18n.normalize_combo(mods, vk)
        if norm is None:
            continue
        out[cid] = i18n.format_combo(*norm)
    return out


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
    # 渐隐时长（ms）：菜单里「渐隐时间…」可输入，配置文件也能存
    FADE_MIN_MS, FADE_MAX_MS = 1, 5000
    DEFAULT_FADE_MS = 500
    # 悬停插值比例：0=等于最低透明度（等于没开），1=等于最高透明度，0.8=偏向最高值
    DEFAULT_HOVER_RATIO = DEFAULT_HOVER_RATIO          # 见模块顶部常量
    DEFAULT_HOVER = True
    # 悬停插值系数滑块的档位数：0~HOVER_RATIO_UNITS（即 0.0~1.0，1 档 = 0.1）
    HOVER_RATIO_UNITS = HOVER_RATIO_UNITS              # 见模块顶部常量
    # 全屏窗口默认「接管并锁定 100%」——见模块顶部「全屏窗口（v1.4.0）」说明
    DEFAULT_FULLSCREEN_LOCK = True
    # 层叠衰减（v1.6.0）：普通非聚焦窗口按堆叠层级递减 —— 见模块顶部常量块。
    DEFAULT_LAYER_DECAY_ON = True
    DEFAULT_LAYER_DECAY = DEFAULT_LAYER_DECAY          # 见模块顶部常量
    # 层衰减系数滑块的档位数（1 档 = 0.1 ⇒ 1~10 即 0.1~1.0）
    LAYER_DECAY_UNITS = LAYER_DECAY_UNITS              # 见模块顶部常量
    # 语言（v1.7.0）："auto" = 跟随系统 UI 语言，具体语言写 zh_CN / en_US …
    DEFAULT_LANG = i18n.DEFAULT_LANG
    # 可以给「菜单项命令」绑全局快捷键的那些命令 ID。
    # 滑块不给绑：它本身是靠鼠标拖的，绑热键没有意义，还会让人误会。
    BINDABLE_CMDS = (CMD_TOGGLE, CMD_HOVER, CMD_FULLSCREEN,
                     CMD_LAYER, CMD_FADE_MS, CMD_LOG, CMD_QUIT)

    def __init__(self, inactive_alpha=0.40, active_alpha=1.00, fade_ms=500, fps=60,
                 scan_interval=0.15, rescan_interval=0.50,
                 fullscreen_lock=None, skip_foreign_layered=False,
                 extra_exclude=(), verbose=False, restore_on_exit=True,
                 tray=True, log_path="", cfg_path=None,
                 hover=None, hover_ratio=None, hover_interval=None,
                 layer_decay=None, layer_decay_ratio=None,
                 language=None, shortcuts=None):
        # cfg_path=None → 用默认路径；cfg_path="" → 明确关闭持久化
        self.cfg_path = CFG_PATH if cfg_path is None else cfg_path
        # None 视为「没指定」，落到内置默认；否则 _to_pct(None) 会直接 TypeError
        self.inactive_pct = (self.DEFAULT_INACTIVE_PCT if inactive_alpha is None
                             else _to_pct(inactive_alpha))
        self.active_pct = (self.DEFAULT_ACTIVE_PCT if active_alpha is None
                           else _to_pct(active_alpha))
        # None 视为「没指定」，落到内置默认；否则 int(None) 会直接 TypeError
        self.fade_ms = (self.DEFAULT_FADE_MS if fade_ms is None else fade_ms)
        self.fps = max(int(fps), 10)
        self.scan_interval = max(float(scan_interval), 0.02)
        self.rescan_interval = max(float(rescan_interval), 0.05)
        # 全屏窗口：True（默认）= 接管并**锁定 100%**；False = 完全不接管。
        # None 视为「没指定」→ 内置默认，首次运行 / --no-config 都要能用。
        self.fullscreen_lock = (self.DEFAULT_FULLSCREEN_LOCK
                                if fullscreen_lock is None else bool(fullscreen_lock))
        # Chromium/Electron 系应用会自行使用 WS_EX_LAYERED(alpha 常非 255)。
        # 本工具会记录并原样还原；若仍不放心，可开启此开关直接跳过这类窗口。
        self.skip_foreign_layered = bool(skip_foreign_layered)
        self.extra_exclude = set(extra_exclude or ())
        self.verbose = bool(verbose)
        self.restore_on_exit = bool(restore_on_exit)
        self.tray = bool(tray)
        self.log_path = log_path or ""
        # 悬停半透明：None 一律回落到内置默认（首次运行 / --no-config 都要能用）
        self.hover = self.DEFAULT_HOVER if hover is None else bool(hover)
        self.hover_ratio = (self.DEFAULT_HOVER_RATIO if hover_ratio is None
                            else hover_ratio)
        self.hover_interval = (DEFAULT_HOVER_INTERVAL if hover_interval is None
                               else hover_interval)
        # 层叠衰减：None 一律回落到内置默认（首次运行 / --no-config 都要能用）
        self.layer_decay = (self.DEFAULT_LAYER_DECAY_ON if layer_decay is None
                            else bool(layer_decay))
        self.layer_decay_ratio = (self.DEFAULT_LAYER_DECAY
                                  if layer_decay_ratio is None
                                  else layer_decay_ratio)
        # ---- 语言与快捷键（v1.7.0）----
        # 语言单独一个 I18N 实例持有：改语言只需要换实例，不用到处传参数。
        self._sys_lang = _detect_sys_lang()
        self.i18n = i18n.I18N(language or self.DEFAULT_LANG, self._sys_lang)
        # 快捷键：{命令ID(int): "Ctrl+Alt+P"}。键是 int，落盘时才转成 str。
        self.shortcuts = _sanitize_shortcuts(shortcuts)
        # 语言一旦切换，菜单上的按钮文案（确定/取消）也要跟着走，
        # 所以这里把常用按钮文案暴露成属性，供对话框取用。

    # ---- 语言（v1.7.0）----
    @property
    def language(self) -> str:
        """配置里存的那个值（可能是 "auto"）。"""
        return self.i18n.requested

    @language.setter
    def language(self, code: str):
        self.i18n.set(str(code) if code else self.DEFAULT_LANG)

    @property
    def lang_effective(self) -> str:
        """实际生效的语言（"auto" 已解析成具体语言）。"""
        return self.i18n.effective

    def t(self, key: str, **kw) -> str:
        """取当前语言的文案——菜单/对话框一律走这里，不要直接写字面量。"""
        return self.i18n.t(key, **kw)

    # ---- 快捷键（v1.7.0）----
    def shortcut_of(self, cid: int) -> str:
        """该命令当前绑定的快捷键文本；没绑就返回空串。"""
        return self.shortcuts.get(int(cid), "")

    def combos_of(self, cid: int):
        """(mods, vk) 或 None。解析失败（坏数据/被手改过）当作没绑。"""
        return i18n.parse_combo(self.shortcut_of(cid))

    def owner_of_combo(self, text: str, exclude_cid: int = None):
        """这个组合已经被谁占了？返回命令 ID 或 None（冲突检测用）。"""
        for cid, s in self.shortcuts.items():
            if int(cid) == int(exclude_cid or -1):
                continue
            if s and s.lower() == str(text).lower():
                return int(cid)
        return None

    def set_shortcut(self, cid: int, text: str) -> bool:
        """绑定/解绑一个快捷键。text 为空串即解绑。返回是否有变化。"""
        cid = int(cid)
        text = "" if text is None else str(text)
        if text:
            parsed = i18n.parse_combo(text)
            if parsed is None:
                return False
            mods, vk = parsed
            if not i18n.is_bindable_vk(vk):
                return False
            text = i18n.format_combo(mods, vk)      # 归一化后再存
        if self.shortcuts.get(cid, "") == text:
            return False
        if text:
            self.shortcuts[cid] = text
        else:
            self.shortcuts.pop(cid, None)
        return True

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

    # ---- 渐隐时长（FADE_MIN_MS ~ FADE_MAX_MS）----
    @property
    def fade_ms(self) -> int:
        return self._fade_ms

    @fade_ms.setter
    def fade_ms(self, v):
        self._fade_ms = max(self.FADE_MIN_MS,
                            min(self.FADE_MAX_MS, int(round(float(v)))))

    # ---- 悬停半透明 ----
    @property
    def hover(self) -> bool:
        return self._hover

    @hover.setter
    def hover(self, v):
        self._hover = bool(v)

    @property
    def hover_ratio(self) -> float:
        return self._hover_ratio

    @hover_ratio.setter
    def hover_ratio(self, v):
        # 夹到 [0,1]：这保证悬停值**恒在**最低值与最高值之间，不会跑到范围外。
        # （ratio=0 → 悬停无效果；ratio=1 → 悬停即最高透明度）
        self._hover_ratio = max(HOVER_RATIO_MIN,
                                min(HOVER_RATIO_MAX, float(v)))

    @property
    def hover_interval(self) -> float:
        return self._hover_interval

    @hover_interval.setter
    def hover_interval(self, v):
        # 下限 0.02s：再快也只是白烧 CPU —— 60fps 主循环本来就会节流
        self._hover_interval = max(0.02, float(v))

    @property
    def hover_pct(self) -> int:
        """悬停目标（整数百分比）：最低 → 最高 之间按 hover_ratio 插值。

        用户例子：最高 100% / 最低 50% ⇒ 90%。默认 100%/40% ⇒ 88%。

        最后的 max(…, 最低值) 是**结构性保证「悬停永远不压暗」**：
        ratio 已被夹到 [0,1]，所以常规配置（最高 ≥ 最低）下这个 max 恒等于
        插值公式本身、等于没写；只有用户把最高值调到比最低值还低（反向配置，
        滑块允许）时，插值结果才会低于最低值 —— 那种情况下悬停退化为"不改变"，
        而不是把窗口进一步压暗。
        """
        lo, hi = self._inactive_pct, self._active_pct
        mid = int(round(lo + (hi - lo) * self._hover_ratio))
        return max(mid, lo)

    @property
    def hover_alpha(self) -> float:
        return self.hover_pct / 100.0

    # ---- 悬停联动压暗（v1.7.1）----
    @property
    def hover_dim_ratio(self) -> float:
        """悬停联动时「其余窗口」的压暗比例（**乘数**）：

            其余窗口目标 = max(基准值 × hover_dim_ratio, 5%)

        比例 = 悬停插值系数 − HOVER_DIM_OFFSET(0.3)，下限 HOVER_DIM_MIN_RATIO(0.1)。
        例：悬停系数 0.7 ⇒ 比例 0.4 ⇒ 一个 100% 的窗口被压到 40%。

        ⚠️ 这里夹下限**只夹比例本身**；乘上去之后的绝对下限（5%）由 target_for
        在算目标值时再封一次。两者不能合并：比例下限保证「至少压一点点」，
        绝对下限保证「别把窗口压到看不见」。
        """
        return max(HOVER_DIM_MIN_RATIO, self._hover_ratio - HOVER_DIM_OFFSET)

    # ---- 全屏锁定（v1.4.0）----
    @property
    def fullscreen_lock(self) -> bool:
        """True = 接管全屏窗口并把透明度**锁死在 100%**（默认）。

        False = 完全不接管全屏窗口（v1.3.0 及以前的行为，给全屏游戏留退路）。
        """
        return self._fullscreen_lock

    @fullscreen_lock.setter
    def fullscreen_lock(self, v):
        self._fullscreen_lock = bool(v)

    @property
    def fullscreen_alpha(self) -> float:
        """全屏窗口的目标透明度：**恒定 100%，不读 active_pct**。"""
        return FULLSCREEN_ALPHA

    # ---- 层叠衰减（v1.6.0）----
    @property
    def layer_decay(self) -> bool:
        """True = 普通非聚焦窗口按堆叠层级逐层递减（默认开）。

        False = v1.5.0 及以前的行为：所有普通非聚焦窗口统一 inactive_pct。
        注意参与递减的**只有**普通非聚焦窗口 —— 聚焦 / 最大化 / 置顶 / 全屏
        各有更高优先级，不占层级号。
        """
        return self._layer_decay

    @layer_decay.setter
    def layer_decay(self, v):
        self._layer_decay = bool(v)

    @property
    def layer_decay_ratio(self) -> float:
        """层衰减系数：每一层 = 上一层（已取整的显示值）× 它。

        夹到 [0.1, 1.0]：上限 1.0 = 完全不衰减（所有层同值），
        下限 0.1 而不是 0 —— 0 会让第 2 层直接砸到下限，链条失去意义。
        """
        return self._layer_decay_ratio

    @layer_decay_ratio.setter
    def layer_decay_ratio(self, v):
        self._layer_decay_ratio = max(LAYER_DECAY_MIN,
                                      min(LAYER_DECAY_MAX, float(v)))

    def layer_alpha(self, depth: int) -> float:
        """第 depth 层「普通非聚焦」窗口的目标透明度（0..1）。"""
        return layer_pct(self._inactive_pct, depth,
                         self._layer_decay_ratio) / 100.0

    # ---- 持久化 ----
    def as_dict(self) -> dict:
        return {"version": 1,
                "inactive_percent": self._inactive_pct,
                "active_percent": self._active_pct,
                "fade_ms": self._fade_ms,
                "hover_enabled": bool(self._hover),
                "hover_ratio": round(float(self._hover_ratio), 3),
                "fullscreen_lock": bool(self._fullscreen_lock),
                "layer_decay": bool(self._layer_decay),
                "layer_decay_ratio": round(float(self._layer_decay_ratio), 3),
                # v1.7.0：语言与快捷键。shortcuts 的键必须是 str（JSON 要求）
                "language": self.language,
                "shortcuts": {str(k): v for k, v in sorted(self.shortcuts.items())}}

    @classmethod
    def apply_saved_lang(cls, saved: dict, language, shortcuts=None):
        """语言 / 快捷键的「命令行 > 配置文件 > 内置默认」三级优先。

        和 apply_saved 系列一样单独一个方法：不破坏既有调用方的返回值形状。
        """
        if language is None:
            language = (saved or {}).get("language", i18n.DEFAULT_LANG)
        if not language:
            language = i18n.DEFAULT_LANG
        if shortcuts is None:
            shortcuts = _sanitize_shortcuts((saved or {}).get("shortcuts"))
        return language, shortcuts

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

    @classmethod
    def apply_saved_fade(cls, saved: dict, fade_ms):
        """渐隐时间：命令行没给就用配置文件里的，再不行落内置默认。

        单独一个方法、而不是塞进 apply_saved 的返回值，是为了不破坏既有调用方
        （slider_test.py 按 (inactive, active) 二元组断言过）。
        """
        if fade_ms is None:
            fade_ms = (saved or {}).get("fade_ms", cls.DEFAULT_FADE_MS)
        return fade_ms

    @classmethod
    def apply_saved_hover(cls, saved: dict, hover, hover_ratio):
        """悬停开关与插值比例：命令行 > 配置文件 > 内置默认。

        返回 (hover, hover_ratio)；同样单独一个方法，避免动到 apply_saved 的
        二元组契约。
        """
        if hover is None:
            hv = (saved or {}).get("hover_enabled", cls.DEFAULT_HOVER)
            hover = cls.DEFAULT_HOVER if hv is None else bool(hv)
        if hover_ratio is None:
            hover_ratio = (saved or {}).get("hover_ratio", cls.DEFAULT_HOVER_RATIO)
        return hover, hover_ratio

    @classmethod
    def apply_saved_fs(cls, saved: dict, fullscreen_lock):
        """全屏锁定开关：命令行 > 配置文件 > 内置默认。

        返回 None 表示"都没指定，用内置默认"（构造函数的 None 语义），
        这样调用方不用重复写一遍默认值。
        """
        if fullscreen_lock is not None:
            return bool(fullscreen_lock)
        v = (saved or {}).get("fullscreen_lock", None)
        return None if v is None else bool(v)

    @classmethod
    def apply_saved_layer(cls, saved: dict, layer_decay, layer_decay_ratio):
        """层叠衰减开关与系数：命令行 > 配置文件 > 内置默认。

        返回 (layer_decay, layer_decay_ratio)；和 apply_saved_hover 一样单独一个
        classmethod，避免动到 apply_saved 的二元组契约。
        """
        if layer_decay is None:
            v = (saved or {}).get("layer_decay", cls.DEFAULT_LAYER_DECAY_ON)
            layer_decay = cls.DEFAULT_LAYER_DECAY_ON if v is None else bool(v)
        if layer_decay_ratio is None:
            layer_decay_ratio = (saved or {}).get("layer_decay_ratio",
                                                  cls.DEFAULT_LAYER_DECAY)
        return layer_decay, layer_decay_ratio


# --------------------------------------------------------------------------
# 单窗口状态
# --------------------------------------------------------------------------
class WinState:
    __slots__ = ("hwnd", "cur", "src", "dst", "t0", "dur",
                 "layered_owned", "framechanged", "orig_alpha",
                 "applied", "failed", "title", "cls",
                 "topmost", "is_fg", "zoomed", "fullscreen", "hover")

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
        self.zoomed = False     # 最大化（IsZoomed）
        self.fullscreen = False # 矩形铺满所在显示器（含无边框全屏）
        self.hover = False      # 本轮鼠标是否压在这个窗口上


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
    if not cfg.fullscreen_lock and _is_fullscreen(hwnd, rc):
        # 只有显式关掉「全屏锁定」时才整窗排除（v1.3.0 及以前的默认行为）。
        # 默认不排除：全屏窗口要留在受管集合里，才能被锁定到 100%
        # —— 因为 rescan 会漏掉"刚变成全屏"的那一帧，被排除就等于没人管它。
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


def cursor_pos():
    """当前光标坐标 (x, y)；取不到返回 None。

    单独抽一层是为了可测：_poll_hover 的全部判定都基于它返回的坐标，
    测试里把它换掉就能在**不真的移动用户鼠标**的前提下驱动悬停逻辑。
    """
    pt = wt.POINT()
    if not user32.GetCursorPos(byref(pt)):
        return None
    return int(pt.x), int(pt.y)


def cursor_root_window() -> int:
    """鼠标此刻压在哪个**顶层**窗口上（取不到返回 0）。

    * WindowFromPoint 返回的是「真正会收到这个鼠标消息的那个窗口」，
      可能是个子控件（编辑框、面板…），所以必须 GetAncestor(GA_ROOT) 归一
      到顶层 —— 否则永远匹配不上我们接管的那些顶层 HWND。
    * 顺便天然处理了层叠顺序：取到的就是视觉上最上层的那一个，
      上下叠了多少个窗口都不影响判定。
    """
    pos = cursor_pos()
    if pos is None:
        return 0
    pt = wt.POINT(pos[0], pos[1])
    hwnd = _h(user32.WindowFromPoint(pt))
    if not hwnd:
        return 0
    return _h(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd


def round_half_up(x: float) -> int:
    """四舍五入取整。

    ⚠️ 不能用内建 round()：它是**银行家舍入**（round(24.5) == 24），
    而层叠衰减明确要求四舍五入 —— 24.5 必须是 25，否则用户按
    「50 → 35 → 25」心算就对不上了。
    """
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def layer_pct(base_pct: int, depth: int, ratio: float,
              floor_pct: int = LAYER_MIN_PCT) -> int:
    """第 depth 层「普通非聚焦」窗口的不透明度（%，整数）。

    输入
      base_pct  : 第 1 层的值，即 cfg.inactive_pct（非聚焦设定值）
      depth     : 层级，**从 1 开始**（1 = 堆叠栈里最靠上的普通非聚焦窗口）
      ratio     : 层衰减系数（0.1~1.0），默认 0.70
      floor_pct : 下限，默认 LAYER_MIN_PCT(5)

    递推
      depth = 1 → base_pct
      depth = n → round_half_up(第 n-1 层的**已取整显示值** × ratio)

    ⚠️ 用「已取整的上一层」而不是 base × ratio^(n-1)：这样每一层的数字都能
    拿屏幕上看到的上一层直接心算验证（25% × 0.7 = 17.5 → 18%）。
    代价是舍入误差顺着层数累加 —— 这是**有意**的取舍：链内自洽、肉眼可验，
    比「绝对精确但和屏幕对不上」更符合这个工具的定位。

    例（base=50, ratio=0.7）：
      第1层 50 · 第2层 35 · 第3层 25(24.5→25) · 第4层 18(17.5→18)
      · 第5层 13(12.6→13) · 第6层 9 · 第7层 6 · 第8层起 5（封底）
    """
    v = max(int(base_pct), int(floor_pct))
    n = int(depth)
    if n <= 1:
        return v
    for _ in range(n - 1):
        if v <= floor_pct:
            break               # 已经封底，不必再乘（结果不会变）
        v = round_half_up(v * ratio)
    return max(v, int(floor_pct))


def z_order_windows(limit: int = 4000):
    """按 **Z 序从上到下**列出顶层窗口（最顶的在前），不做任何过滤。

    EnumWindows 的回调顺序其实也是 Z 序，但要跑完整回调；层叠衰减每一轮
    都要拿一次顺序，所以用 GetTopWindow + GW_HWNDNEXT 这条链只读顺序，
    开销更低（一次 GetWindow / 窗口）。

    limit 是防呆上限：万一窗口链被某个驱动弄成环，不至于把主循环挂死。
    """
    out = []
    h = user32.GetTopWindow(None)
    while h and len(out) < limit:
        out.append(_h(h))
        h = user32.GetWindow(h, GW_HWNDNEXT)
    return out


def assign_depths(z_order, participants):
    """给「参与层叠编号的窗口」按 Z 序编号，返回 {hwnd: depth}，depth 从 1 起。

    participants 只应包含**普通非聚焦窗口**：聚焦 / 最大化 / 置顶 / 全屏
    各有更高的优先级，既不占层级号，也不会把后面的窗口挤下一层。
    结果完全由 z_order 决定 ⇒ 同一个 z_order 必得同一个结果（纯函数，可测）。
    """
    depths = {}
    d = 0
    for h in z_order:
        if h in participants:
            d += 1
            depths[h] = d
    return depths


def target_for(cfg: "GlassConfig", hwnd: int, *, is_fg: bool = False,
               top: bool = False, zoomed: bool = False, fullscreen: bool = False,
               hover_hwnd: int = 0, depth: int = 0):
    """唯一的「目标透明度判定」出口。返回 (目标不透明度, 理由, 是否悬停中)。

    放在模块级、而不是 GlassEngine 的方法，是为了让 `--list` 体检打印的结果
    与引擎实际会做的事**共用同一份逻辑** —— 分两处写早晚会不一致。

    优先级（先命中先返回）：
      ① 全屏窗口   —— **恒定 100%（cfg.fullscreen_alpha），完全不读 active_pct**。
                      全屏基本就是游戏/视频/演示，用户调「聚焦最高透明度」
                      是为了看清背景窗口，不是为了把全屏画面压暗。
                      必须排在聚焦前面：全屏窗口几乎总是同时"聚焦"的。
      ② 聚焦窗口   —— active_pct（滑块可调）
      ③ 最大化窗口 —— active_pct（**视为聚焦**：占满屏幕，视觉主导权等价）
      ④ 置顶窗口   —— active_pct（**视为聚焦**：虽然没键盘焦点，但压在所有窗口
                      之上，压暗它反而更看不清）
      ⑤ 悬停窗口   —— 插值点值（最低 + (最高−最低) × hover_ratio），
                      **只对"本应被压暗"的窗口生效**
      ⑥ 普通非聚焦 —— **层叠衰减**（v1.6.0，`cfg.layer_decay` 默认开）：
                      depth=1 用 inactive_pct，depth=n 用
                      round_half_up(上一层已取整显示值 × cfg.layer_decay_ratio)，
                      下限 LAYER_MIN_PCT(5%)。关掉就退回「统一 inactive_pct」。

    ⑤ 与 ①~④ 的区分：被悬停的那个窗口，若它本应是最高透明度（全屏/聚焦/最大化/
    置顶），按插值算只会把它压暗 ⇒ 一律不参与"提亮"，保证**提亮永不压暗**。

    ⑦ 是 v1.7.1 新增的**后处理**：先按 ①~⑥ 算出「基准值」，再在悬停生效时把
    **非悬停窗口**整体乘一个压暗比例。它与 ⑤ 是互补的两件事——⑤ 只提亮"被悬停
    的那一个"，⑦ 则压暗"其余所有受规则影响的窗口"（无论是否聚焦），制造焦点
    对比。全屏恒 100% 不参与 ⑦；绝对下限 5% 在 ⑦ 里再封一次。

    ⚠️ 参数全部强制关键字（`*`）：以前是位置参数 (is_fg, top, hover_hwnd)，
    现在中间插进了 zoomed/fullscreen —— 保持位置传递会让老调用悄悄错位，
    所以宁可让它直接 TypeError。
    """
    if fullscreen:
        base, reason, hv = cfg.fullscreen_alpha, "全屏", False
    elif is_fg:
        base, reason, hv = cfg.active_alpha, "聚焦", False
    elif zoomed:
        base, reason, hv = cfg.active_alpha, "最大化", False
    elif top:
        base, reason, hv = cfg.active_alpha, "置顶", False
    elif cfg.hover and hover_hwnd and hover_hwnd == hwnd:
        base, reason, hv = cfg.hover_alpha, "悬停", True
    elif cfg.layer_decay and depth >= 1:
        base = layer_pct(cfg.inactive_pct, depth, cfg.layer_decay_ratio) / 100.0
        reason, hv = "第%d层" % depth, False
    else:
        base, reason, hv = cfg.inactive_alpha, "未聚焦", False

    # ⑦ 悬停联动压暗（v1.7.1）：悬停某个窗口时，**其余**「受透明度规则影响」的
    #    窗口（无论是否聚焦：聚焦 / 最大化 / 置顶 / 未聚焦）一起压暗到
    #    base × hover_dim_ratio，绝对下限 LAYER_MIN_PCT(5%)。
    #    两个例外：① 全屏恒 100%、不参与任何规则；② 被悬停的窗口本身（hv=True）
    #    只提亮，绝不压暗自己 —— 所以这里显式排除。dimmed < base 才改，避免
    #    用户把系数调得极低时反而把窗口"提"上去。
    if (cfg.hover and hover_hwnd and hwnd != hover_hwnd and not fullscreen):
        dimmed = max(LAYER_MIN_PCT / 100.0, base * cfg.hover_dim_ratio)
        if dimmed < base:
            return dimmed, reason + "·悬停压暗", hv
    return base, reason, hv


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


_ACCENT_CACHE = None


def _luma(color: int) -> float:
    r, g, b = color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF
    return 0.299 * r + 0.587 * g + 0.114 * b


def _accent_color() -> int:
    """系统强调色（COLORREF）。取不到、或与菜单底色对比度太低时退回默认蓝。

    任务栏音量条的填充色用的就是系统强调色，这里跟随同一个来源。
    取值优先级：
      1) HKCU\\...\\DWM\\AccentColor            —— 权威的强调色（ABGR，低 24 位即 COLORREF）
      2) HKCU\\...\\Explorer\\Accent\\AccentColorMenu
      3) DwmGetColorizationColor                —— 取不到注册表时的近似值
      4) 内置默认蓝 #2F6FE4
    强调色被设成接近菜单底色的颜色时会「看不见」，所以最后还有一道对比度检查。
    """
    global _ACCENT_CACHE
    if _ACCENT_CACHE is not None:
        return _ACCENT_CACHE
    default = 0xE46F2F                     # COLORREF 是 BGR：#2F6FE4（Windows 默认蓝）
    c = 0
    try:
        import winreg
        for path, name in ((r"Software\Microsoft\Windows\DWM", "AccentColor"),
                           (r"Software\Microsoft\Windows\CurrentVersion"
                            r"\Explorer\Accent", "AccentColorMenu")):
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
                try:
                    v, _t = winreg.QueryValueEx(k, name)
                finally:
                    winreg.CloseKey(k)
                if int(v) & 0xFFFFFF:
                    c = int(v) & 0xFFFFFF     # 低位起就是 R,G,B，正好是 COLORREF
                    break
            except OSError:
                continue
    except Exception:
        pass
    if not c:
        try:
            if dwmapi is not None:
                argb = wt.DWORD(0)
                opaque = wt.BOOL(0)
                if dwmapi.DwmGetColorizationColor(byref(argb), byref(opaque)) == 0:
                    v = int(argb.value)    # 0xAARRGGBB
                    c = ((v & 0xFF) << 16) | ((v >> 8) & 0xFF00) | ((v >> 16) & 0xFF)
        except Exception:
            c = 0
    if not c:
        c = default
    if abs(_luma(c) - _luma(int(user32.GetSysColor(COLOR_MENU)))) < 40:
        c = default
    _ACCENT_CACHE = c
    return c


def _slider_colors(selected: bool, disabled: bool):
    """返回 (已填充色, 轨道底色, 手柄色, 手柄外圈色)。跟随系统主题与选中态。"""
    menu_bg = int(user32.GetSysColor(COLOR_MENU))
    dark = _menu_is_dark()
    if disabled:
        edge = int(user32.GetSysColor(COLOR_GRAYTEXT))
        return (_mix(menu_bg, edge, 0.35), _mix(menu_bg, edge, 0.16),
                _mix(menu_bg, edge, 0.35), _mix(menu_bg, edge, 0.30))
    if selected:
        # 选中时整行是强调色背景：手柄与填充改用高亮文字色才看得见
        bg = int(user32.GetSysColor(COLOR_HIGHLIGHT))
        ht = int(user32.GetSysColor(COLOR_HIGHLIGHTTEXT))
        return ht, _mix(bg, menu_bg, 0.45), ht, _mix(bg, menu_bg, 0.62)
    accent = _accent_color()
    track = 0x4A4A4A if dark else 0xC9C9C9
    ring = _mix(accent, 0x000000, 0.28) if not dark else _mix(accent, 0xFFFFFF, 0.18)
    return accent, track, accent, ring


def _track_geom(rc):
    """轨道两端、以及手柄圆心可移动的范围。

    ⚠️ 绘制（百分比→圆心）与命中判定（x→百分比）**共用**这一组坐标，
    否则「点了这里、手柄却停在那里」，两端也取不满。
    """
    left = rc.left + SLIDER_PAD_X
    right = rc.right - SLIDER_PAD_X
    cx0 = left + SLIDER_THUMB_INSET
    cx1 = right - SLIDER_THUMB_INSET
    if cx1 <= cx0:
        cx1 = cx0 + 1
    return left, right, cx0, cx1


def _track_center_y(rc) -> int:
    """轨道的垂直中线（相对菜单项矩形）。

    绘制和自动化测试**共用**这一个公式：测试要沿这一行逐像素扫描来反查
    填充边界，公式一旦不一致，测试就会去扫一条根本没画东西的线。
    """
    r1_bottom = rc.top + 3 + SLIDER_TITLE_H      # 第一行(标题/数值)的底
    row_top = r1_bottom + 2
    row_bot = rc.bottom - 3
    if row_bot <= row_top:
        row_bot = row_top + 1
    return (row_top + row_bot) // 2


def pct_to_thumb_x(pct: int, lo: int, hi: int, rc) -> int:
    """百分比 → 手柄圆心 x。"""
    _, _, cx0, cx1 = _track_geom(rc)
    frac = 0.0 if hi <= lo else (int(pct) - lo) / float(hi - lo)
    frac = max(0.0, min(1.0, frac))
    return int(round(cx0 + frac * (cx1 - cx0)))


def x_to_pct(x: int, lo: int, hi: int, rc) -> int:
    """鼠标 x → 1% 步进的整数值。"""
    _, _, cx0, cx1 = _track_geom(rc)
    frac = (x - cx0) / float(max(1, cx1 - cx0))
    frac = max(0.0, min(1.0, frac))
    return max(lo, min(hi, lo + int(round(frac * (hi - lo)))))


def _fill_capsule(hdc, l, t, r, b, color):
    """圆头胶囊（轨道 / 已填充部分）。用 NULL_PEN 只填充不描边。"""
    h = max(2, b - t)
    if (r - l) < h:
        r = l + h
    ob = gdi32.SelectObject(hdc, _brush(color))
    op = gdi32.SelectObject(hdc, gdi32.GetStockObject(NULL_PEN))
    gdi32.RoundRect(hdc, l, t, r, b, h, h)
    gdi32.SelectObject(hdc, op)
    gdi32.SelectObject(hdc, ob)


def _fill_circle(hdc, cx, cy, rad, color):
    ob = gdi32.SelectObject(hdc, _brush(color))
    op = gdi32.SelectObject(hdc, gdi32.GetStockObject(NULL_PEN))
    gdi32.Ellipse(hdc, cx - rad, cy - rad, cx + rad, cy + rad)
    gdi32.SelectObject(hdc, op)
    gdi32.SelectObject(hdc, ob)


def fmt_pct(v) -> str:
    """滑块数值 → 显示文本：百分数（非聚焦/聚焦那两个滑块）。"""
    return "%d%%" % int(v)


def fmt_ratio_units(v) -> str:
    """滑块数值 → 显示文本：一位小数（悬停插值系数，单位 0.1）。"""
    return "%.1f" % (int(v) / float(HOVER_RATIO_UNITS))


def draw_menu_slider(dis, label: str, lo: int, hi: int, pct: int,
                     hot: bool = False, text: str = None):
    """把一个 owner-draw 菜单项画成**音量条式**滑块。

    布局（两行）：
        非聚焦最低透明度                      40%     <- 左标题 / 右数值
        ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━         <- 细轨道 + 圆形手柄

    与 v1.1.0 的「分段条（每段 1%）」相比，形状 / 比例 / 手柄反馈都对齐
    Windows 任务栏音量条；取值精度不变 —— 仍是 1 档步进。

    `text` 是右下角那个数值的显示文本；不传就按百分比显示。
    悬停插值系数滑块传 "0.8" 这种一位小数（它的内部单位是 0.1）。
    """
    hdc = dis.hDC
    rc = dis.rcItem
    selected = bool(dis.itemState & ODS_SELECTED)
    disabled = bool(dis.itemState & (ODS_GRAYED | ODS_DISABLED))
    pct = max(lo, min(hi, int(pct)))
    if text is None:
        text = fmt_pct(pct)
    fill_c, track_c, thumb_c, ring_c = _slider_colors(selected, disabled)

    # 背景必须自己刷：owner-draw 项不会被系统自动填充
    # v1.7.0：Win11 下高亮块改画**圆角**，和新增的两行菜单项观感一致。
    # Win10（MENU_CORNER_R=0）自动退化成整行填充，零成本、零差异。
    if selected and MENU_CORNER_R > 0:
        user32.FillRect(hdc, byref(rc), user32.GetSysColorBrush(COLOR_MENU))
        fill_round_rect(hdc, rc.left + MENU_HILITE_INSET, rc.top + MENU_HILITE_INSET,
                        rc.right - MENU_HILITE_INSET, rc.bottom - MENU_HILITE_INSET,
                        int(user32.GetSysColor(COLOR_HIGHLIGHT)), MENU_CORNER_R)
    else:
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

    # ---- 第一行：标题 + 当前值（百分比 或 一位小数）----
    r1 = wt.RECT(left, rc.top + 3, right, rc.top + 3 + SLIDER_TITLE_H)
    gdi32.SetTextColor(hdc, text_c)
    user32.DrawTextW(hdc, label, -1, byref(r1), DT_LEFT | DT_VCENTER | DT_SINGLELINE)
    user32.DrawTextW(hdc, text, -1, byref(r1),
                     DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

    # ---- 第二行：细轨道 + 圆形手柄 ----
    cy = _track_center_y(rc)

    t_left, t_right, _, _ = _track_geom(rc)
    th = SLIDER_TRACK_H
    t_top = cy - th // 2
    t_bot = t_top + th

    # 手柄：悬停/按下时放大一圈，和音量条一样有反馈
    rad = SLIDER_THUMB_R_HOT if (hot or selected) else SLIDER_THUMB_R
    cx = pct_to_thumb_x(pct, lo, hi, rc)
    # 取到两端时手柄会略微探出轨道，别让它被菜单项边缘裁掉
    cx = max(rc.left + rad + 1, min(rc.right - rad - 1, cx))

    # 1) 整条轨道（底色）
    _fill_capsule(hdc, t_left, t_top, t_right, t_bot, track_c)
    # 2) 已填充部分：从左端一直连到手柄圆心
    if cx > t_left:
        _fill_capsule(hdc, t_left, t_top, cx, t_bot, fill_c)
    # 3) 手柄：先画稍大一圈的外圈做出描边感，再叠上本体
    _fill_circle(hdc, cx, cy, rad, ring_c)
    _fill_circle(hdc, cx, cy, max(1, rad - 1), thumb_c)

    gdi32.SelectObject(hdc, old_font)
    gdi32.SetBkMode(hdc, old_mode)
    gdi32.SetTextColor(hdc, int(user32.GetSysColor(COLOR_MENUTEXT)))


# --------------------------------------------------------------------------
# v1.7.0：Windows 11 圆角菜单
# --------------------------------------------------------------------------
def fill_round_rect(hdc, left, top, right, bottom, color, radius=0):
    """画一个填充矩形；radius>0 时走 RoundRect（Win11 的圆角高亮块）。

    ⚠️ 不能直接改用具名 Adams 的 CreateRoundRectRgn + FillRgn：那样边缘没有
    GDI 的路径抗锯齿，小块高亮会毛边。RoundRect 走的是当前笔+刷路径，观感
    和系统菜单一致。Win10（radius=0）自动退化成普通 FillRect，零成本。
    """
    if right <= left or bottom <= top:
        return
    brush = gdi32.CreateSolidBrush(int(color))
    if not brush:
        if radius <= 0:
            user32.FillRect(hdc, byref(wt.RECT(left, top, right, bottom)),
                            user32.GetSysColorBrush(COLOR_MENU))
        return
    try:
        if radius <= 0:
            rc = wt.RECT(left, top, right, bottom)
            user32.FillRect(hdc, byref(rc), brush)
            return
        # RoundRect 用当前笔描边：把笔设成和刷同色且宽度为 1，
        # 避免描边用默认的黑笔画出一圈脏边。
        pen = gdi32.CreatePen(0, 1, int(color))       # PS_SOLID
        old_pen = old_brush = 0
        if pen:
            old_pen = gdi32.SelectObject(hdc, pen)
        old_brush = gdi32.SelectObject(hdc, brush)
        gdi32.RoundRect(hdc, left, top, right, bottom, radius * 2, radius * 2)
        if old_brush:
            gdi32.SelectObject(hdc, old_brush)
        if pen:
            if old_pen:
                gdi32.SelectObject(hdc, old_pen)
            gdi32.DeleteObject(pen)
    finally:
        gdi32.DeleteObject(brush)


def set_menu_corner_preference(hwnd: int, enable: bool = True) -> bool:
    """给菜单窗口套上 Win11 的圆角偏好。

    Windows 11 会把顶层窗口（包括 #32768 菜单窗口）的四角按这个属性渲染成圆角；
    Win10 及更早版本没有这个属性，调用会失败 —— 失败就保持方角，无害。

    ⚠️ 必须在菜单窗口**已经创建之后**调用（TrackPopupMenu 期间拿到句柄），
    提前对 0 句柄调用会直接返回失败。
    """
    if not hwnd or dwmapi is None or not enable:
        return False
    if not IS_WIN11:
        return False
    try:
        val = ctypes.c_int(DWMWCP_ROUND)
        hr = dwmapi.DwmSetWindowAttribute(
            wt.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE,
            byref(val), ctypes.sizeof(val))
        return hr == 0
    except Exception:
        return False


def draw_menu_toggle(dis, label: str, hint: str, checked: bool = False,
                     hint_alert: bool = False):
    """把一个 owner-draw 菜单项画成「标题 + 灰色小字」两行。

        暂停（所有窗口恢复 100%）          <- 第一行：正式标题（可带勾选标记）
        右键设置快捷键                     <- 第二行：灰色小字（快捷键/提示）

    `hint_alert=True` 时第二行用强调色画（冲突/错误提示），让「这条要注意」
    一眼能看出来，而不是混在普通灰色里被忽略。

    ⚠️ owner-draw 项**必须自己刷背景**：系统不会替我们填，不刷就会留下残影。
    """
    hdc = dis.hDC
    rc = dis.rcItem
    selected = bool(dis.itemState & ODS_SELECTED)
    disabled = bool(dis.itemState & (ODS_GRAYED | ODS_DISABLED))

    menu_bg = int(user32.GetSysColor(COLOR_MENU))
    # 1) 整个项刷菜单底色（清残影）
    user32.FillRect(hdc, byref(rc), user32.GetSysColorBrush(COLOR_MENU))
    # 2) 选中态：画一块**圆角**高亮块（Win11 观感的关键）
    if selected and MENU_CORNER_R > 0:
        fill_round_rect(hdc, rc.left + MENU_HILITE_INSET,
                        rc.top + MENU_HILITE_INSET,
                        rc.right - MENU_HILITE_INSET,
                        rc.bottom - MENU_HILITE_INSET,
                        int(user32.GetSysColor(COLOR_HIGHLIGHT)), MENU_CORNER_R)
    elif selected:
        inner = wt.RECT(rc.left + MENU_HILITE_INSET, rc.top + MENU_HILITE_INSET,
                        rc.right - MENU_HILITE_INSET, rc.bottom - MENU_HILITE_INSET)
        user32.FillRect(hdc, byref(inner), user32.GetSysColorBrush(COLOR_HIGHLIGHT))

    old_mode = gdi32.SetBkMode(hdc, TRANSPARENT)
    left = rc.left + TOGGLE_PAD_X
    right = rc.right - TOGGLE_PAD_X
    # 勾选标记占 14px，标题要给它让位，否则会被压在钩下面
    mark_w = 14 if checked else 0

    # ---- 第一行：标题 ----
    title_c = int(user32.GetSysColor(
        COLOR_GRAYTEXT if disabled else
        (COLOR_HIGHLIGHTTEXT if selected else COLOR_MENUTEXT)))
    r1 = wt.RECT(left + mark_w, rc.top + 2, right, rc.top + 2 + TOGGLE_ITEM_H // 2)
    gdi32.SelectObject(hdc, _menu_font())
    gdi32.SetTextColor(hdc, title_c)
    if checked:
        # 手画一个对钩（两条 LineTo）：MFT_OWNERDRAW 下系统不会替你画勾
        mark_c = int(user32.GetSysColor(
            COLOR_HIGHLIGHTTEXT if selected else COLOR_MENUTEXT))
        gdi32.SetTextColor(hdc, mark_c)
        mr = wt.RECT(left, rc.top + 2, left + mark_w, rc.top + 2 + TOGGLE_ITEM_H // 2)
        user32.DrawTextW(hdc, "✓", -1, byref(mr),
                         DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        gdi32.SetTextColor(hdc, title_c)
    user32.DrawTextW(hdc, label, -1, byref(r1),
                     DT_LEFT | DT_VCENTER | DT_SINGLELINE)

    # ---- 第二行：灰色小字（快捷键 / 提示）----
    if hint:
        if disabled:
            hint_c = int(user32.GetSysColor(COLOR_GRAYTEXT))
        elif hint_alert:
            hint_c = _accent_color()
        elif selected:
            hint_c = int(user32.GetSysColor(COLOR_HIGHLIGHTTEXT))
        else:
            hint_c = _mix(int(user32.GetSysColor(COLOR_MENUTEXT)), menu_bg, 0.42)
        r2 = wt.RECT(left + mark_w, rc.top + TOGGLE_ITEM_H // 2, right,
                     rc.bottom - 2)
        gdi32.SetTextColor(hdc, hint_c)
        user32.DrawTextW(hdc, hint, -1, byref(r2),
                         DT_LEFT | DT_VCENTER | DT_SINGLELINE)

    gdi32.SetBkMode(hdc, old_mode)


class MenuSlider:
    """托盘菜单里的一个 owner-draw 滑块。"""

    __slots__ = ("cid", "label", "lo", "hi", "get", "set", "fmt", "pos", "hmenu")

    def __init__(self, cid, label, lo, hi, getter, setter, fmt=None):
        self.cid = int(cid)
        self.label = label
        self.lo = int(lo)
        self.hi = int(hi)
        self.get = getter            # () -> int  当前档位
        self.set = setter            # (int) -> None
        self.fmt = fmt or fmt_pct    # (int) -> str  右下角数值怎么显示
        self.pos = -1                # 菜单里的位置（0 基）
        self.hmenu = None

    def text(self) -> str:
        """当前值在菜单里显示的文本（百分比 / 一位小数）。"""
        return self.fmt(int(self.get()))

    def hit_frac_to_pct(self, x: int, rc) -> int:
        """把鼠标 x 换算成 1% 步进的整数值。

        必须和绘制共用同一套坐标（二者都基于 _track_geom），
        否则会出现「点在这里、手柄却停在那里」。
        """
        return x_to_pct(x, self.lo, self.hi, rc)


# --------------------------------------------------------------------------
# 数值输入框（托盘菜单里「渐隐时间…」点开后弹出）
#
# 为什么手搓而不用 DialogBoxIndirectParam：这里只需要「一个编辑框 + 确定/取消」，
# 而内存里拼 DLGTEMPLATE（可变长数组 + 对齐）比直接建窗口更难维护。
# Enter / Esc / Tab 交给 IsDialogMessage 处理，行为与系统对话框一致。
# --------------------------------------------------------------------------
WM_NCDESTROY = 0x0082
WM_SETFONT = 0x0030
EM_SETSEL = 0x00B1
SW_SHOW = 5
WS_POPUP, WS_CAPTION, WS_SYSMENU = 0x80000000, 0x00C00000, 0x00080000
WS_CHILD, WS_VISIBLE, WS_BORDER, WS_TABSTOP = 0x40000000, 0x10000000, 0x00800000, 0x00010000
WS_EX_CLIENTEDGE, WS_EX_CONTROLPARENT = 0x00000200, 0x00010000
ES_NUMBER, ES_AUTOHSCROLL = 0x2000, 0x0080
BS_DEFPUSHBUTTON, BS_PUSHBUTTON = 0x00000001, 0x00000000
SS_LEFT = 0x00000000
IDC_NUM_EDIT, IDC_NUM_OK, IDC_NUM_CANCEL = 1001, 1002, 1003
ERROR_CLASS_ALREADY_EXISTS = 1410

user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = c_ssize_t
user32.SetFocus.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wt.HWND]
user32.DestroyWindow.restype = wt.BOOL
user32.IsDialogMessageW.argtypes = [wt.HWND, ctypes.POINTER(wt.MSG)]
user32.IsDialogMessageW.restype = wt.BOOL
user32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
user32.GetDlgItem.restype = wt.HWND
kernel32.GetLastError.restype = wt.DWORD


class NumberInputBox:
    """一个小巧的模态数值输入框：说明 + 编辑框 + 单位 + 确定/取消。

        v = NumberInputBox(parent_hwnd, "渐隐时间", "渐隐时长（毫秒）：", "ms",
                           500, 1, 5000).show()
        # 点「确定」-> int（已夹紧）；「取消」/ 关窗 -> None
    """

    _cls_name = None
    _proc_ref = None
    _by_hwnd = {}

    def __init__(self, parent, title, prompt, unit, value, lo, hi):
        self.parent = parent
        self.title = title
        self.prompt = prompt
        self.unit = unit
        self.value = int(value)
        self.lo, self.hi = int(lo), int(hi)
        self.hwnd = 0
        self.edit = 0
        self.result = None

    # ---- 窗口类只注册一次 ----
    @classmethod
    def _ensure_class(cls):
        if cls._cls_name:
            return cls._cls_name
        cls._proc_ref = WNDPROC(NumberInputBox._wndproc)   # 必须留引用
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = ctypes.cast(cls._proc_ref, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.hbrBackground = user32.GetSysColorBrush(COLOR_MENU)
        wc.lpszClassName = "WinGlassNumberInput"
        if not user32.RegisterClassW(byref(wc)):
            if kernel32.GetLastError() != ERROR_CLASS_ALREADY_EXISTS:
                return None
        cls._cls_name = "WinGlassNumberInput"
        return cls._cls_name

    # ---- 窗口过程 ----
    @staticmethod
    def _wndproc(hwnd, msg, wparam, lparam):
        try:
            me = NumberInputBox._by_hwnd.get(_h(hwnd))
            if me is not None:
                if msg == WM_COMMAND:
                    cid = int(wparam) & 0xFFFF
                    if cid == IDC_NUM_OK:
                        me._accept()
                        return 0
                    if cid == IDC_NUM_CANCEL:
                        me._finish()
                        return 0
                elif msg == WM_CLOSE:
                    me._finish()
                    return 0
                elif msg in (WM_DESTROY, WM_NCDESTROY):
                    NumberInputBox._by_hwnd.pop(_h(hwnd), None)
                    # 唤醒外层那个嵌套消息循环（它正阻塞在 GetMessage 上）
                    user32.PostMessageW(me.parent, WM_NULL, 0, 0)
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _accept(self):
        raw = _window_text(self.edit) if self.edit else ""
        digits = "".join(ch for ch in raw if ch.isdigit())
        try:
            v = int(digits) if digits else self.value
        except Exception:
            v = self.value
        self.result = max(self.lo, min(self.hi, v))     # 越界一律夹紧，不报错打断
        self._finish()

    def _finish(self):
        h = self.hwnd
        self.hwnd = 0
        if h:
            user32.DestroyWindow(h)

    def show(self):
        cls = self._ensure_class()
        if not cls:
            return None
        hinst = kernel32.GetModuleHandleW(None)
        w, h = 268, 132

        # 放到光标所在显示器的正中
        pt = wt.POINT()
        user32.GetCursorPos(byref(pt))
        x, y = pt.x - w // 2, pt.y - h // 2
        try:
            mon = user32.MonitorFromWindow(self.parent or None, MONITOR_DEFAULTTONEAREST)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if mon and user32.GetMonitorInfoW(mon, byref(mi)):
                x = mi.rcWork.left + ((mi.rcWork.right - mi.rcWork.left) - w) // 2
                y = mi.rcWork.top + ((mi.rcWork.bottom - mi.rcWork.top) - h) // 2
        except Exception:
            pass

        self.hwnd = _h(user32.CreateWindowExW(
            WS_EX_CONTROLPARENT, cls, self.title,
            WS_POPUP | WS_CAPTION | WS_SYSMENU, x, y, w, h,
            self.parent, None, hinst, None))
        if not self.hwnd:
            return None
        NumberInputBox._by_hwnd[self.hwnd] = self

        def mk(kind, text, style, cx, cy, cw, ch, cid):
            return _h(user32.CreateWindowExW(0, kind, text, style, cx, cy, cw, ch,
                                             self.hwnd, cid, hinst, None))

        mk("STATIC", self.prompt, SS_LEFT | WS_CHILD | WS_VISIBLE,
           16, 14, w - 32, 18, 0)
        self.edit = mk("EDIT", "%d" % self.value,
                       WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_NUMBER | ES_AUTOHSCROLL,
                       16, 40, 150, 24, IDC_NUM_EDIT)
        mk("STATIC", self.unit, SS_LEFT | WS_CHILD | WS_VISIBLE,
           176, 44, 68, 18, 0)
        mk("BUTTON", "确定", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
           w - 172, 82, 76, 28, IDC_NUM_OK)
        mk("BUTTON", "取消", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
           w - 88, 82, 76, 28, IDC_NUM_CANCEL)

        # 用系统菜单字体，别落回默认的宋体
        hf = _menu_font()
        for cid in (IDC_NUM_EDIT, IDC_NUM_OK, IDC_NUM_CANCEL):
            h = user32.GetDlgItem(self.hwnd, cid)
            if h:
                user32.SendMessageW(h, WM_SETFONT, hf, True)
        if self.edit:
            user32.SendMessageW(self.edit, EM_SETSEL, 0, -1)   # 全选，直接改数字
            user32.SetFocus(self.edit)
        user32.ShowWindow(self.hwnd, SW_SHOW)

        # 嵌套消息循环：靠 IsDialogMessage 把 Enter/Esc/Tab 当对话框处理。
        # ⚠️ 不能 PostQuitMessage —— 这条线程还跑着托盘的 GetMessage 循环，
        #    会把整个程序一起退掉。
        msg = wt.MSG()
        while self.hwnd and user32.IsWindow(self.hwnd):
            if user32.GetMessageW(byref(msg), None, 0, 0) <= 0:
                break
            if not user32.IsDialogMessageW(self.hwnd, byref(msg)):
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
        NumberInputBox._by_hwnd.pop(self.hwnd, None)
        return self.result


class _ToggleItem:
    """托盘菜单里一个 owner-draw 的「两行」菜单项（标题 + 灰色快捷键提示）。

    刻意做成只有字段的轻结构：`hmenu` / `pos` 是为了复用 `_item_rect()` 取
    屏幕矩形（它原本只认滑块，两者都有这两个字段就能共用一套几何逻辑）。
    """

    __slots__ = ("cid", "label", "checked", "hmenu", "pos")

    def __init__(self, cid, label, checked=False):
        self.cid = int(cid)
        self.label = label
        self.checked = bool(checked)
        self.hmenu = 0
        self.pos = 0


class TrayIcon:
    """系统托盘图标。左键单击=暂停/继续；右键菜单=各项开关、滑块、快捷键绑定、语言。"""

    def __init__(self, engine, tip="win_glass — 窗口聚焦透明"):
        self.engine = engine
        self.tip = tip[:127]
        self.hwnd = 0
        self._proc_ref = None
        self._ready = threading.Event()
        # ---- 菜单滑块状态 ----
        self._sliders = []          # 当前菜单里的 MenuSlider 列表
        self._items = []            # 当前菜单里的 _ToggleItem 列表（v1.7.0）
        self._hook = 0              # WH_MSGFILTER 钩子
        self._hook_ref = None       # 钩子回调引用（不放会被 GC，随即崩溃）
        self._menu_hwnd = 0         # 正在显示的菜单窗口（给坐标换算用）
        self._dragging = False      # 是否正在拖动滑块
        # ---- 快捷键录制（v1.7.0）----
        self._recording = 0         # 正在录制的命令 ID（0=没在录）
        self._rec_pending = None    # 已按下、等松手的那次组合 (mods, vk)
        self._kb_hook = 0           # WH_KEYBOARD_LL 钩子（只在录制期间挂）
        self._kb_hook_ref = None    # 同上，必须留引用
        self._alerts = {}           # {cid: 提示文案} 冲突/失败之类的一次性提示
        self._hotkeys = {}          # 已成功注册的热键 {cid: True}
        self._rounded = False       # 菜单窗口是否已成功套上 Win11 圆角
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
            # v1.7.0：窗口一就绪就把配置里存的快捷键注册成全局热键
            self._register_hotkeys()
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
            if msg == WM_HOTKEY:
                # v1.7.0 全局快捷键：RegisterHotKey 的 id 就是命令 ID，
                # wParam 直接拿来用，不需要查表。
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

    def _build_menu(self):
        """只负责「拼菜单」，不负责「弹菜单」。

        拆出来是为了让菜单内容可测：TrackPopupMenu 会阻塞，弹出去就没法在
        同一个线程里断言菜单里到底有哪些项、文字是什么。现在测试可以直接
        调这个函数，再拿 GetMenuStringW 把每一项读回来核对。
        返回菜单句柄；调用方负责 DestroyMenu。
        """
        m = user32.CreatePopupMenu()
        if not m:
            return 0
        cfg = self.engine.cfg
        # 每次重新弹菜单都清掉上一轮的告警（「冲突」提示不该跨菜单留着）
        self._alerts = {}
        self._items = []
        # ① 上面一排开关（两行：标题 + 灰色快捷键提示）
        self._append_toggle(m, CMD_TOGGLE, *self._spec(CMD_TOGGLE))
        self._append_toggle(m, CMD_HOVER, *self._spec(CMD_HOVER))
        self._append_toggle(m, CMD_FULLSCREEN, *self._spec(CMD_FULLSCREEN))
        self._append_toggle(m, CMD_LAYER, *self._spec(CMD_LAYER))
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        # ② 滑块
        self._append_sliders(m)
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        # ③ 渐隐时间（也是两行，可绑快捷键）
        self._append_toggle(m, CMD_FADE_MS,
                            "%s\t%d ms" % (cfg.t("fade"), cfg.fade_ms), False)
        # ④ 语言子菜单（普通项 + 打勾，不涉及快捷键）
        self._append_language_menu(m)
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        self._append_toggle(m, CMD_LOG, *self._spec(CMD_LOG))
        self._append_toggle(m, CMD_QUIT, *self._spec(CMD_QUIT))
        return m

    # ---------------- 菜单项：内容 ----------------
    def _spec(self, cid):
        """某个命令 ID 当前的 (标题, 是否勾选)。

        标题依赖实时状态（比如「已暂停」和「暂停」是同一项的两幅面孔），
        所以每次弹菜单都要重算，不能在启动时算一次存着。
        """
        cfg = self.engine.cfg
        t = cfg.t
        if cid == CMD_TOGGLE:
            paused = self.engine.paused
            return (t("resume") if paused else t("pause"), paused)
        if cid == CMD_RESTORE:
            return (t("restore"), False)
        if cid == CMD_HOVER:
            return (t("hover", pct=cfg.hover_pct), bool(cfg.hover))
        if cid == CMD_FULLSCREEN:
            return ((t("fullscreen_on") if cfg.fullscreen_lock
                     else t("fullscreen_off")), bool(cfg.fullscreen_lock))
        if cid == CMD_LAYER:
            # 勾选时把前几层的**实际算出来的值**直接写进菜单文字 ——
            # 省得用户自己去心算「50% × 0.7 × 0.7 是多少」。
            if cfg.layer_decay:
                txt = t("layer_on", vals=" / ".join(
                    "%d%%" % layer_pct(cfg.inactive_pct, d, cfg.layer_decay_ratio)
                    for d in range(1, 4)))
            else:
                txt = t("layer_off", pct=cfg.inactive_pct)
            return (txt, bool(cfg.layer_decay))
        if cid == CMD_LOG:
            return (t("log"), False)
        if cid == CMD_QUIT:
            return (t("quit"), False)
        return ("", False)

    def _hint_for(self, cid) -> str:
        """第二行那行灰色小字该显示什么。"""
        cfg = self.engine.cfg
        if self._recording == cid:
            return cfg.t("shortcut_rec")           # 正在录制：提示按键
        alert = self._alerts.get(cid)
        if alert:
            return alert                            # 冲突 / 注册失败
        combo = cfg.shortcut_of(cid)
        if combo:
            return combo + "    " + cfg.t("shortcut_clear")
        return cfg.t("shortcut_unset")

    def _is_alert_hint(self, cid) -> bool:
        """告警文案用强调色画，普通提示用灰色。"""
        return bool(self._alerts.get(cid)) or self._recording == cid

    def _append_toggle(self, m, cid, label, checked):
        """把一个命令项作为 owner-draw（两行）插进菜单。"""
        it = _ToggleItem(cid, label, checked)
        it.hmenu = m
        it.pos = max(0, user32.GetMenuItemCount(m))
        mii = MENUITEMINFOW()
        mii.cbSize = ctypes.sizeof(MENUITEMINFOW)
        mii.fMask = MIIM_ID | MIIM_FTYPE | MIIM_DATA
        mii.fType = MFT_OWNERDRAW
        mii.wID = cid
        mii.dwItemData = cid
        if not user32.InsertMenuItemW(m, it.pos, True, byref(mii)):
            # 建不出来就退回普通文字项：菜单少一行提示，但功能不能丢
            user32.AppendMenuW(m, MF_STRING | (MF_CHECKED if checked else 0),
                               cid, label)
            return None
        self._items.append(it)
        return it

    def _append_language_menu(self, m):
        """语言子菜单：列出所有语言，当前生效的那个打勾。"""
        cfg = self.engine.cfg
        sub = user32.CreatePopupMenu()
        if not sub:
            return
        cur = cfg.language
        for i, d in enumerate(i18n.LANGS):
            flags = MF_STRING
            if d["code"] == cur:
                flags |= MF_CHECKED
            user32.AppendMenuW(sub, flags, CMD_LANG_BASE + i, d["native"])
        mii = MENUITEMINFOW()
        mii.cbSize = ctypes.sizeof(MENUITEMINFOW)
        mii.fMask = MIIM_SUBMENU | MIIM_STRING | MIIM_ID | MIIM_FTYPE
        mii.fType = MF_STRING
        mii.wID = CMD_LANG_MENU
        mii.hSubMenu = sub
        mii.dwTypeData = cfg.t("language")
        user32.InsertMenuItemW(m, max(0, user32.GetMenuItemCount(m)), True,
                               byref(mii))

    def _toggle_by_id(self, item_id):
        for it in self._items:
            if it.cid == int(item_id):
                return it
        return None

    def _hit_toggle(self, pt):
        """光标落在哪个可绑快捷键的菜单项上？"""
        for it in self._items:
            if it.cid not in GlassConfig.BINDABLE_CMDS:
                continue
            rc = self._item_rect(it)
            if rc is None:
                continue
            if rc.left <= pt.x < rc.right and rc.top <= pt.y < rc.bottom:
                return it, rc
        return None

    def _spec_label(self, cid):
        """冲突提示里要显示「被谁占了」，得拿到那一项的标题。"""
        label, _checked = self._spec(cid)
        return label

    # ---------------- 快捷键：全局热键 ----------------
    def _register_hotkeys(self) -> dict:
        """把配置里所有已存的快捷键注册成全局热键。

        RegisterHotKey 的 id 直接用**命令 ID**：WM_HOTKEY 的 wParam 就是它，
        收到后直接丢给 _invoke，不需要再查表。
        返回 {cid: 是否注册成功} —— 失败的大多是「被系统或其他程序占了」，
        起程序时静默跳过即可（用户去菜单里重绑会看到提示）。
        """
        self._unregister_hotkeys()
        result = {}
        if not self.hwnd:
            return result
        for cid, text in sorted(self.engine.cfg.shortcuts.items()):
            parsed = i18n.parse_combo(text)
            if parsed is None:
                continue
            mods, vk = parsed
            ok = bool(user32.RegisterHotKey(
                wt.HWND(self.hwnd), int(cid), int(mods) | MOD_NOREPEAT, int(vk)))
            result[int(cid)] = ok
            if ok:
                self._hotkeys[int(cid)] = True
        return result

    def _unregister_hotkeys(self):
        for cid in list(self._hotkeys):
            try:
                user32.UnregisterHotKey(wt.HWND(self.hwnd), int(cid))
            except Exception:
                pass
        self._hotkeys = {}

    def _register_one(self, cid, mods, vk) -> bool:
        """只注册一个（录制完成时用）。会先解绑这个 cid 上的旧绑定。"""
        if not self.hwnd:
            return False
        try:
            user32.UnregisterHotKey(wt.HWND(self.hwnd), int(cid))
        except Exception:
            pass
        self._hotkeys.pop(int(cid), None)
        ok = bool(user32.RegisterHotKey(
            wt.HWND(self.hwnd), int(cid), int(mods) | MOD_NOREPEAT, int(vk)))
        if ok:
            self._hotkeys[int(cid)] = True
        return ok

    def _unbind(self, cid):
        """解绑一个命令的快捷键（录制时按 Delete 走这里）。"""
        try:
            user32.UnregisterHotKey(wt.HWND(self.hwnd), int(cid))
        except Exception:
            pass
        self._hotkeys.pop(int(cid), None)
        self.engine.cfg.set_shortcut(cid, "")
        self.engine.save_cfg(force=True)

    # ---------------- 快捷键：录制 ----------------
    def _start_recording(self, cid, rc=None):
        """右键某个菜单项 → 进入录制状态。"""
        if int(cid) not in GlassConfig.BINDABLE_CMDS:
            return
        if self._recording:
            self._stop_recording()
        self._recording = int(cid)
        self._rec_pending = None
        self._alerts.pop(int(cid), None)
        self._install_kb_hook()
        self._redraw_cid(int(cid))

    def _stop_recording(self):
        cid = self._recording
        self._recording = 0
        self._rec_pending = None
        self._uninstall_kb_hook()
        if cid:
            self._redraw_cid(cid)

    def _install_kb_hook(self):
        """挂上低级别键盘钩子。

        WH_KEYBOARD_LL 是**全局**钩子但不需要注入 DLL —— 回调在安装的那个线程
        里跑，所以只要该线程有消息循环（托盘线程有）就能收到。
        这也是唯一能在菜单开着时把按键抢过来的办法：菜单的模态循环会把
        普通按键当成助记符/方向键自己吃掉，根本轮不到我们。
        """
        try:
            self._kb_hook_ref = HOOKPROC(self._kb_proc)
            self._kb_hook = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._kb_hook_ref, None, 0) or 0
        except Exception:
            self._kb_hook = 0

    def _uninstall_kb_hook(self):
        if self._kb_hook:
            try:
                user32.UnhookWindowsHookEx(self._kb_hook)
            except Exception:
                pass
            self._kb_hook = 0
        self._kb_hook_ref = None        # 先摘钩子再丢引用

    def _kb_proc(self, nCode, wParam, lParam):
        """录制期间的键盘钩子回调：全部吞掉，只把结果交给录制状态机。"""
        try:
            if nCode >= 0 and lParam and self._recording:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = int(kb.vkCode)
                if int(kb.flags) & LLKHF_UP:
                    self._on_rec_keyup(vk)
                else:
                    self._on_rec_keydown(vk)
                # 返回非 0 = 吞掉这条按键：菜单/Open 对话框都不该再看到它
                return 1
        except Exception:
            pass
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _mods_down(self) -> int:
        """当前物理按住的修饰键位掩码。

        用 GetAsyncKeyState 读**物理状态**，而不是在钩子里自己记账 ——
        用户很可能在我们开始录制**之前**就按住了 Ctrl，那种情况记账会漏。
        """
        m = 0
        try:
            if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
                m |= i18n.MOD_CTRL
            if user32.GetAsyncKeyState(VK_MENU) & 0x8000:
                m |= i18n.MOD_ALT
            if user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
                m |= i18n.MOD_SHIFT
            if (user32.GetAsyncKeyState(VK_LWIN) & 0x8000
                    or user32.GetAsyncKeyState(VK_RWIN) & 0x8000):
                m |= i18n.MOD_WIN
        except Exception:
            pass
        return m

    def _on_rec_keydown(self, vk):
        cid = self._recording
        if not cid:
            return
        if vk == VK_ESCAPE:                      # Esc = 取消录制
            self._stop_recording()
            return
        mods = self._mods_down()
        if vk in (VK_DELETE, VK_BACK) and not mods:
            self._unbind(cid)                    # 单按 Delete/Backspace = 解绑
            self._stop_recording()
            return
        if i18n.is_bindable_vk(vk):
            # 记下候选，等**松手**才最终确认（用户要的是「按下并松开后完成」）
            self._rec_pending = (mods, vk)

    def _on_rec_keyup(self, vk):
        cid = self._recording
        pending = self._rec_pending
        if not cid or not pending:
            return
        mods, p_vk = pending
        if int(vk) != int(p_vk):
            return                                # 松的是别的键，继续等
        self._finish_bind(cid, mods, p_vk)

    def _finish_bind(self, cid, mods, vk):
        """录制完成：校验 → 查冲突 → 真注册一次 → 落盘。"""
        cfg = self.engine.cfg
        combo = i18n.format_combo(mods, vk)
        # ① 键本身能不能当主键（修饰键 / Esc / 鼠标键都不行）
        if not i18n.is_bindable_vk(vk):
            self._set_alert(cid, cfg.t("shortcut_invalid"))
            self._stop_recording()
            return
        # ② 是不是已经被别的菜单项占了
        owner = cfg.owner_of_combo(combo, exclude_cid=cid)
        if owner is not None:
            self._set_alert(cid, cfg.t("shortcut_conflict",
                                       name=self._spec_label(owner)))
            self._stop_recording()
            return
        # ③ 真去注册一次：注册不上的（被系统/其它程序占用）就别存，
        #    否则菜单上显示着一个「绑好了」却按不动的键，比不绑更糟。
        if not self.hwnd:
            # 没有托盘窗口（--no-tray）时无法注册，但仍然存下来，
            # 下次带托盘启动时会自动生效。
            cfg.set_shortcut(cid, combo)
            self.engine.save_cfg(force=True)
            self._stop_recording()
            return
        if not self._register_one(cid, mods, vk):
            self._set_alert(cid, cfg.t("shortcut_failed"))
            self._stop_recording()
            return
        cfg.set_shortcut(cid, combo)
        self.engine.save_cfg(force=True)
        self._stop_recording()

    def _set_alert(self, cid, text):
        """在那一项的灰色小字位置显示一次提示（冲突/失败），并立即重绘。"""
        self._alerts[int(cid)] = text
        self._redraw_cid(int(cid))

    def _redraw_cid(self, cid):
        it = self._toggle_by_id(cid)
        if it is None:
            return
        rc = self._item_rect(it)
        if rc is not None:
            self._redraw_item(rc)

    def _popup(self):
        m = self._build_menu()
        if not m:
            return
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
            # 录制中菜单被关掉（点了别处 / Esc）→ 必须把键盘钩子摘掉，
            # 否则会一直吞按键，整个系统的键盘都失灵。这是本功能最危险的一处泄漏。
            self._stop_recording()
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
        """把四个滑块作为 owner-draw 菜单项插进菜单。"""
        cfg = self.engine.cfg
        sliders = [
            MenuSlider(CMD_SLIDE_INACTIVE, cfg.t("inactive"),
                       cfg.INACTIVE_MIN_PCT, cfg.INACTIVE_MAX_PCT,
                       lambda: self.engine.cfg.inactive_pct,
                       lambda v: self.engine.set_alpha_targets(inactive_pct=v)),
            MenuSlider(CMD_SLIDE_ACTIVE, cfg.t("active"),
                       cfg.ACTIVE_MIN_PCT, cfg.ACTIVE_MAX_PCT,
                       lambda: self.engine.cfg.active_pct,
                       lambda v: self.engine.set_alpha_targets(active_pct=v)),
            # 悬停插值系数（v1.5.0）：内部档位 0~10，显示成 0.0~1.0。
            # 悬停值 = 最低 + (最高 − 最低) × 系数，所以拖它就能实时看到
            # 上面那行「悬停半透明（未聚焦窗口 → xx%）」跟着变。
            MenuSlider(CMD_SLIDE_HOVER, cfg.t("hover_ratio"),
                       0, cfg.HOVER_RATIO_UNITS,
                       lambda: int(round(
                           self.engine.cfg.hover_ratio * cfg.HOVER_RATIO_UNITS)),
                       lambda v: self.engine.set_hover_ratio(
                           v / float(cfg.HOVER_RATIO_UNITS)),
                       fmt_ratio_units),
            # 层衰减系数（v1.6.0）：同样是内部 0~10 档、显示成 0.0~1.0。
            # 普通非聚焦窗口每往下一层就乘一次它，拖动时上面那行
            # 「层叠衰减（第 1 层 xx%，之后每层 ×0.7，下限 5%）」会立刻跟着变。
            MenuSlider(CMD_SLIDE_DECAY, cfg.t("decay"),
                       0, cfg.LAYER_DECAY_UNITS,
                       lambda: int(round(
                           self.engine.cfg.layer_decay_ratio
                           * cfg.LAYER_DECAY_UNITS)),
                       lambda v: self.engine.set_layer_decay_ratio(
                           v / float(cfg.LAYER_DECAY_UNITS)),
                       fmt_ratio_units),
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
            # 滑块 vs 两行菜单项：谁命中就按谁的尺寸回。两者都走这一条
            # WM_MEASUREITEM 通道，靠 itemID 区分。
            if self._slider_by_id(mis.itemID) is not None:
                mis.itemWidth = SLIDER_ITEM_W
                mis.itemHeight = SLIDER_ITEM_H
            elif self._toggle_by_id(mis.itemID) is not None:
                mis.itemWidth = SLIDER_ITEM_W
                mis.itemHeight = TOGGLE_ITEM_H
            else:
                return
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
            if sl is not None:
                # hot：悬停（选中）或正在拖动时，手柄放大一圈，与音量条一致
                hot = bool(self._dragging) or bool(dis.itemState & ODS_SELECTED)
                draw_menu_slider(dis, sl.label, sl.lo, sl.hi, int(sl.get()), hot,
                                 sl.text())
                return
            it = self._toggle_by_id(dis.itemID)
            if it is not None:
                draw_menu_toggle(dis, it.label, self._hint_for(it.cid),
                                 it.checked, self._is_alert_hint(it.cid))
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
                # ⚠️ 只认真正的菜单窗口（#32768）。MSGF_MENU 回调里的 msg.hwnd 可能是
                # 本线程正在处理的**任意**窗口 —— 踩过：钩子看到的头一条消息，hwnd 是
                # shell 的 SystemUserAdapterWindowClass，把它当成菜单窗口缓存下来之后，
                # InvalidateRect 全打在无关窗口上，菜单永远不会重绘。
                # 症状就是「拖动时数值和进度条怎么都不刷新，指针一移出去才刷新」。
                # v1.7.0：菜单窗口一出现就给它套上 Win11 的圆角偏好。
                # 必须**在这里**做 —— 只有此刻才拿得到真实的 #32768 句柄。
                if not self._menu_hwnd and msg.hwnd and _win_class(msg.hwnd) == MENU_CLASS:
                    self._menu_hwnd = _h(msg.hwnd)
                    self._rounded = set_menu_corner_preference(self._menu_hwnd)
                    if DBG_REDRAW:
                        print("[dbg] captured _menu_hwnd=0x%X class=%s (msg=0x%04X)"
                              % (self._menu_hwnd, _win_class(msg.hwnd), int(msg.message)))
                mtype = int(msg.message)
                if mtype in (WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP,
                             WM_MOUSEWHEEL, WM_KEYDOWN,
                             # v1.7.0：右键菜单项 = 进入快捷键录制
                             WM_RBUTTONDOWN, WM_RBUTTONUP):
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
            # 录制中：所有按键都归录制状态机，滑块的方向键微调让路
            if self._recording:
                return True
            return self._handle_slider_key(int(msg.wParam))
        pt = wt.POINT(int(msg.pt.x), int(msg.pt.y))
        if mtype in (WM_RBUTTONDOWN, WM_RBUTTONUP):
            # v1.7.0 右键某项 = 录快捷键。两个消息都要吞掉：
            # 吞 RBUTTONUP 是为了不让 Windows 把它当成「选中并关闭菜单」。
            if mtype == WM_RBUTTONUP:
                if self._recording:
                    self._stop_recording()      # 右键空白处 = 取消录制
                else:
                    hit = self._hit_toggle(pt)
                    if hit:
                        self._start_recording(hit[0].cid, hit[1])
            return True
        hit = self._hit_slider(pt)
        if hit is None:
            if mtype == WM_LBUTTONUP:
                self._dragging = False
            return False
        sl, rc = hit
        if DBG_REDRAW:
            print("[dbg] click mtype=0x%04X pt=(%d,%d) rc=(%d,%d)-(%d,%d) "
                  "-> pct=%d dragging=%s"
                  % (mtype, pt.x, pt.y, rc.left, rc.top, rc.right, rc.bottom,
                     sl.hit_frac_to_pct(pt.x, rc), self._dragging))
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
        """夹紧到合法范围后写回配置；值没变就不重绘，避免无谓闪烁。

        这里传进来的都是**档位**（整数），不是显示值：两个透明度滑块是
        「1 档 = 1%」，悬停插值系数是「1 档 = 0.1」。
        """
        pct = max(sl.lo, min(sl.hi, int(pct)))      # 取整 + 夹紧 → 步进恒定
        if pct == int(sl.get()):
            return
        sl.set(pct)
        if DBG_REDRAW:
            print("[dbg] apply %s -> %s" % (sl.label, sl.fmt(pct)))
        self._redraw_item(rc)

    def _resolve_menu_hwnd(self, rc=None):
        """定位真正的菜单窗口（窗口类 #32768）。

        不能只信钩子里缓存的那个句柄：MSGF_MENU 回调的 msg.hwnd 可能是线程里任意窗口。
        这里逐级校验并回填缓存——缓存 → FindWindowW → 按菜单项中心点取窗口。
        """
        for cand in (self._menu_hwnd, _h(user32.FindWindowW(MENU_CLASS, None))):
            if cand and user32.IsWindow(cand) and _win_class(cand) == MENU_CLASS:
                self._menu_hwnd = cand
                return cand
        if rc is not None:
            pt = wt.POINT((rc.left + rc.right) // 2, (rc.top + rc.bottom) // 2)
            cand = _h(user32.WindowFromPoint(pt))
            if cand and _win_class(cand) == MENU_CLASS:
                self._menu_hwnd = cand
                return cand
        self._menu_hwnd = 0
        return 0

    def _redraw_item(self, rc):
        """就地重绘某个菜单项，让滑块与数值实时跟手。

        ⚠️ 必须打在**菜单窗口**（#32768）上。打在别的窗口上不会报任何错，
        但菜单永远不会重绘 —— 这正是「拖动时数值/进度条不刷新」的根因。
        """
        hwnd = self._resolve_menu_hwnd(rc)
        if not hwnd:
            if DBG_REDRAW:
                print("[dbg] redraw SKIP: 找不到菜单窗口")
            return
        local = wt.RECT(rc.left, rc.top, rc.right, rc.bottom)
        n = user32.MapWindowPoints(None, hwnd,
                                   ctypes.cast(byref(local), ctypes.POINTER(wt.POINT)), 2)
        # RedrawWindow(RDW_UPDATENOW) 比 InvalidateRect+UpdateWindow 更可靠：
        # 菜单窗口的 WM_PAINT 有自己的节奏，RDW_UPDATENOW 会强制立刻同步画一遍。
        ok = user32.RedrawWindow(hwnd, byref(local), None,
                                 RDW_INVALIDATE | RDW_UPDATENOW)
        if DBG_REDRAW:
            print("[dbg] redraw hwnd=0x%X class=%s map=%d rw=%s "
                  "local=(%d,%d)-(%d,%d) draw_total=%d"
                  % (hwnd, _win_class(hwnd), n, bool(ok),
                     local.left, local.top, local.right, local.bottom,
                     self.msg_counts["draw"]))

    def _invoke(self, cid):
        if cid in (CMD_SLIDE_INACTIVE, CMD_SLIDE_ACTIVE,
                   CMD_SLIDE_HOVER, CMD_SLIDE_DECAY):
            return                       # 滑块靠钩子拖动，不走命令逻辑
        if CMD_LANG_BASE <= cid < CMD_LANG_BASE + len(i18n.LANGS):
            # v1.7.0 语言子菜单：每一项的 ID 是 CMD_LANG_BASE + 序号
            self.engine.set_language(i18n.LANGS[cid - CMD_LANG_BASE]["code"])
            return
        if cid == CMD_LANG_MENU:
            return                       # 只是个子菜单的父项，点了没动作
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
        elif cid == CMD_HOVER:
            self.engine.set_hover(not self.engine.cfg.hover)
        elif cid == CMD_FULLSCREEN:
            self.engine.set_fullscreen_lock(not self.engine.cfg.fullscreen_lock)
        elif cid == CMD_LAYER:
            self.engine.set_layer_decay(not self.engine.cfg.layer_decay)
        elif cid == CMD_FADE_MS:
            self._ask_fade_ms()

    def _ask_fade_ms(self):
        """弹数值输入框改渐隐时长（ms）。取消（返回 None）就什么都不做。"""
        cfg = self.engine.cfg
        v = NumberInputBox(self.hwnd, "渐隐时间", "渐隐时长（毫秒）：", "ms",
                           cfg.fade_ms, cfg.FADE_MIN_MS, cfg.FADE_MAX_MS).show()
        if v is not None:
            self.engine.set_fade_ms(v)


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
        # ---- 悬停状态 ----
        self._hover_hwnd = 0            # 此刻被鼠标压住的、已接管的顶层窗口
        self._hover_cursor = None       # 上次采样到的光标坐标（没动就跳过判定）
        self._hover_at = 0.0            # 上次轮询时刻（节流用）

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

    def set_fade_ms(self, fade_ms):
        """托盘菜单改渐隐时长后调用。

        除了写配置，还要把**正在进行的缓动**按新时长重排时间轴：
        否则改完要等下一次切换才生效，用户会以为没生效。做法是保持「已完成
        进度」不变，只把 t0 往回推到与新时长匹配的位置。
        """
        old_ms = self.cfg.fade_ms
        with self.lock:
            self.cfg.fade_ms = fade_ms
            new_dur = self.cfg.fade_ms / 1000.0
            now = time.perf_counter()
            for st in self.states.values():
                if st.dur <= 0.0 or st.t0 <= 0.0:
                    continue
                prog = (now - st.t0) / st.dur
                if prog >= 1.0:
                    continue
                st.dur = new_dur
                st.t0 = now - prog * new_dur
        self._dirty.set()
        self.save_cfg(force=True)
        if self.cfg.verbose and self.cfg.fade_ms != old_ms:
            print(f"[win_glass] 渐隐时长 {old_ms}ms -> {self.cfg.fade_ms}ms")

    def set_hover(self, flag):
        """开关「悬停半透明」（托盘菜单 / 测试用）。

        关掉时顺手把 _hover_cursor 清空 —— 再打开时立刻重新判定一次光标下的
        窗口，否则要到用户下次动鼠标才会生效，看起来像"开了没反应"。
        """
        with self.lock:
            self.cfg.hover = bool(flag)
            self._hover_cursor = None
            if not self.cfg.hover:
                # 别让已经压暗/提亮的窗口停在悬停值上：下一次 _update_targets
                # 会把它们拉回各自的基础目标
                self._hover_hwnd = 0
        self._dirty.set()
        self.save_cfg(force=True)
        print("[win_glass] 悬停半透明：%s（未聚焦窗口 %s → %d%%，其余窗口 ×%.1f）"
              % ("开" if self.cfg.hover else "关",
                 self.cfg.inactive_pct, self.cfg.hover_pct,
                 self.cfg.hover_dim_ratio))

    def set_hover_ratio(self, ratio):
        """改悬停插值比例（0=等于最低，0.8=默认偏向最高，1=等于最高）。"""
        with self.lock:
            self.cfg.hover_ratio = ratio
        self._dirty.set()
        self.save_cfg(force=True)
        if self.cfg.verbose:
            print("[win_glass] 悬停比例 %.2f → 悬停值 %d%%"
                  % (self.cfg.hover_ratio, self.cfg.hover_pct))

    def set_fullscreen_lock(self, flag):
        """开关「全屏窗口固定 100%」（托盘菜单 / 测试用）。

        关掉 = 全屏窗口完全不接管（v1.3.0 及以前的行为）。这个开关会改变
        **可管理集合**（见 is_manageable），所以不在这里手工增删窗口 —— 交给
        下一次 `_refresh_window_list()` 全量重扫：新放开的会被接管、被排除的会
        走 `_restore()` 还原。代价是最多 `rescan_interval`（默认 0.5s）的延迟，
        换来的是只有一条代码路径负责"集合变了怎么办"。
        """
        with self.lock:
            self.cfg.fullscreen_lock = bool(flag)
        self._dirty.set()
        self.save_cfg(force=True)
        print("[win_glass] 全屏窗口：%s"
              % ("接管并固定在 100%（不受最高值设置影响）"
                 if self.cfg.fullscreen_lock else "完全不接管（原样保留）"))

    def set_layer_decay(self, flag):
        """开关「层叠衰减」（托盘菜单 / 测试用，v1.6.0）。

        关掉 = 退回 v1.5.0 行为（所有普通非聚焦窗口统一 inactive_pct）。
        不用手工重算：`_dirty` 会让下一轮 `_update_targets()` 重算全部目标值 ——
        层级号、颜色、理由文本会一起更新。
        """
        with self.lock:
            self.cfg.layer_decay = bool(flag)
        self._dirty.set()
        self.save_cfg(force=True)
        print("[win_glass] 层叠衰减：%s"
              % ("开（第 1 层 %d%%，之后每层 ×%.1f，下限 %d%%）"
                 % (self.cfg.inactive_pct, self.cfg.layer_decay_ratio,
                    LAYER_MIN_PCT)
                 if self.cfg.layer_decay
                 else "关（所有非聚焦窗口统一 %d%%）" % self.cfg.inactive_pct))

    def set_layer_decay_ratio(self, ratio):
        """改层衰减系数（0.1~1.0，默认 0.70）。"""
        with self.lock:
            self.cfg.layer_decay_ratio = ratio
        self._dirty.set()
        self.save_cfg(force=True)
        if self.cfg.verbose:
            print("[win_glass] 层衰减系数 %.2f → 第 1~4 层 %s"
                  % (self.cfg.layer_decay_ratio,
                     " / ".join("%d%%" % layer_pct(self.cfg.inactive_pct, d,
                                                   self.cfg.layer_decay_ratio)
                                for d in range(1, 5))))

    def set_language(self, code: str):
        """切换界面语言并立即落盘。

        这里**不需要**重算透明度（语言只影响菜单文字），所以不像别的 set_*
        那样置 _dirty —— 改语言不该让整屏窗口抖一下。
        """
        if not code:
            return
        with self.lock:
            self.cfg.language = code
        self.save_cfg(force=True)
        print("[win_glass] 界面语言 → %s（%s）"
              % (i18n.lang_name(code), self.cfg.lang_effective))

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
        # ---- 全屏锁 100% 的快捷路径：本来没分层就一个字都不改 ----
        # 给一个非分层窗口硬加 WS_EX_LAYERED 会丢掉 DWM 的独立翻转/硬件叠加
        # 优化（全屏游戏可能掉帧），而 alpha=255 的观感与非分层窗口完全一致
        # —— 也就是说"加"这个动作除了副作用没有任何收益。
        # 反过来：我们自己之前给它分过层（先前是非全屏、被压暗过），或者它
        # 本来就带 LAYERED（应用自己的分层），那就必须真的把 alpha 顶到 255。
        if (alpha == 255 and st.fullscreen and not st.layered_owned
                and not (_GetWindowLong(hwnd, GWL_EXSTYLE) & WS_EX_LAYERED)):
            st.applied = alpha
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

    # ---------------- 悬停 ----------------
    def _poll_hover(self, now: float):
        """轮询鼠标，更新「此刻被压住的窗口」self._hover_hwnd。

        为什么是轮询而不是事件：Win32 根本没有「鼠标进入/离开任意窗口」的全局
        事件。TrackMouseEvent 只对自己窗口有效；WH_MOUSE_LL 要多一个低级钩子，
        还会把鼠标消息拉进本进程的消息路径 —— 为了一个视觉效果不值得。

        开销：50ms 一次 GetCursorPos，几十微秒；**光标没动的那一轮直接返回**，
        连 WindowFromPoint 都不做。常驻运行实测 CPU 占用无可测变化。
        """
        if not self.cfg.hover:
            if self._hover_hwnd:
                self._hover_hwnd = 0
                self._dirty.set()
            return
        if (now - self._hover_at) < self.cfg.hover_interval:
            return
        self._hover_at = now
        cur = cursor_pos()
        if cur is None:
            return
        if cur == self._hover_cursor:
            return                     # 光标没动 → 悬停目标不可能变
        self._hover_cursor = cur
        cand = cursor_root_window()
        with self.lock:
            # 只管我们已接管的窗口：桌面、任务栏、别人窗口一律视作「没有悬停」
            known = cand in self.states
        cand = cand if known else 0
        if cand != self._hover_hwnd:
            old, self._hover_hwnd = self._hover_hwnd, cand
            self._dirty.set()          # 交给主循环统一重算，回调里不做重活
            if self.cfg.verbose:
                print("[win_glass] 悬停 %s -> %s"
                      % ("0x%X" % old if old else "无",
                         "0x%X" % cand if cand else "无"))

    def _target_for(self, hwnd: int, *, is_fg=False, top=False, zoomed=False,
                    fullscreen=False, hover_hwnd=0, depth=0):
        """见模块级 target_for()——这里只是把 cfg 填进去，保证两边同一份逻辑。"""
        return target_for(self.cfg, hwnd, is_fg=is_fg, top=top, zoomed=zoomed,
                          fullscreen=fullscreen, hover_hwnd=hover_hwnd,
                          depth=depth)

    def _layer_depths(self, want):
        """给 want 里的**普通非聚焦窗口**按 Z 序编号，返回 {hwnd: depth}。

        只编号「普通非聚焦」：聚焦 / 最大化 / 置顶 / 全屏各有更高优先级，不占
        层级号。尤其是**置顶窗口**——它物理上总在很靠上的位置，若让它占号会把
        它下面所有窗口整体推低一层，而它自己又不参与递减 ⇒ 层级就没法解释了。

        返回的字典只包含确实算普通非聚焦的窗口；调用方拿不到键就传 depth=0，
        target_for 会走 active/inactive 分支。关掉层叠衰减时直接返回空字典。

        ⚠️ 这里是**独立重读一遍**窗口状态（不复用 _update_targets 的结果），
        所以只在"新窗口接管"这种低频路径上调用。
        """
        if not self.cfg.layer_decay:
            return {}
        fg = _h(user32.GetForegroundWindow())
        plain = set()
        for hwnd in want:
            if hwnd == fg:
                continue
            top, zoomed, fs = read_window_state(hwnd)
            if not (top or zoomed or fs):
                plain.add(hwnd)
        if not plain:
            return {}
        return assign_depths(z_order_windows(), plain)

    def _refresh_window_list(self):
        """全量枚举：发现新窗口、清理已消失的窗口。"""
        alive = set(scan_windows(self.cfg, self.self_pid))
        fg = _h(user32.GetForegroundWindow())
        # 窗口可能正好在光标下面冒出来/消失（而光标没动）。清掉坐标缓存，
        # 逼 _poll_hover 下次重新判定，不然悬停状态会一直停在旧结论上。
        self._hover_cursor = None
        with self.lock:
            fresh = [h for h in alive if h not in self.states]
            # 新窗口一开始就要落在它该有的层级上：否则会先按「未聚焦」接管、
            # 下一轮再淡到层值，肉眼能看到一次多余的跳变。
            depths = self._layer_depths(alive) if fresh else {}
            for hwnd in fresh:
                top, zoomed, fs = read_window_state(hwnd)
                tgt, _why, _hv = self._target_for(
                    hwnd, is_fg=(hwnd == fg), top=top, zoomed=zoomed,
                    fullscreen=fs, hover_hwnd=self._hover_hwnd,
                    depth=depths.get(hwnd, 0))
                self._adopt(hwnd, tgt)
            for hwnd in list(self.states):
                if hwnd not in alive:
                    st = self.states.pop(hwnd)
                    self._restore(st)

    def _update_targets(self):
        """只读式重算目标（全屏/最大化/置顶/悬停检测 + 层叠层级编号）。

        每轮每个窗口多花 3 次 user32 调用（GetWindowRect + MonitorFromWindow +
        GetMonitorInfoW）判断全屏；层叠衰减再走一次 Z 序链（GetTopWindow +
        每窗口一次 GetWindow）。默认 7 次/秒、窗口数十几，实测可忽略。

        必须分两遍：**先把这一轮所有窗口的状态判定完**，才知道谁算「普通非
        聚焦」，才能按 Z 序给它们编号；而编号又决定每个窗口的目标值 ——
        一遍算不出来（先算的窗口不知道后面还有几个普通非聚焦排在它下面）。
        """
        if self.paused:
            return
        fg = _h(user32.GetForegroundWindow())
        with self.lock:
            hover_hwnd = self._hover_hwnd
            # 第一遍：判定状态，顺便收集「普通非聚焦」（层叠编号的候选）
            info = {}
            plain = set()
            for hwnd, st in self.states.items():
                if not user32.IsWindow(hwnd):
                    continue
                top, zoomed, fs = read_window_state(hwnd, st)
                is_fg = (hwnd == fg)
                st.is_fg = is_fg
                info[hwnd] = (is_fg, top, zoomed, fs)
                if not (is_fg or top or zoomed or fs):
                    plain.add(hwnd)
            # 第二遍：按 Z 序编号（层叠关掉、或没有普通非聚焦窗口 → 空字典）
            depths = (assign_depths(z_order_windows(), plain)
                      if (self.cfg.layer_decay and plain) else {})
            # 第三遍：算目标值
            for hwnd, (is_fg, top, zoomed, fs) in info.items():
                st = self.states.get(hwnd)
                if st is None:
                    continue        # 上面 _restore 掉的不再管
                tgt, reason, hv = self._target_for(
                    hwnd, is_fg=is_fg, top=top, zoomed=zoomed,
                    fullscreen=fs, hover_hwnd=hover_hwnd,
                    depth=depths.get(hwnd, 0))
                st.hover = hv
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
                self.tray = TrayIcon(self, tip=self.cfg.t("tip"))
                if self.tray.start():
                    print("[win_glass] 托盘图标已就位（左键暂停/继续，右键菜单可退出）")
                else:
                    print("[win_glass] 托盘图标创建失败，改用控制台交互。")
                    self.tray = None
            except Exception as e:
                print("[win_glass] 托盘创建异常：%s" % e)
                self.tray = None

        print(f"[win_glass] v{APP_VER} 启动  未聚焦={self.cfg.inactive_pct}%  "
              f"聚焦/最大化/置顶={self.cfg.active_pct}%  "
              f"全屏=100%(固定)  渐变={self.cfg.fade_ms}ms  "
              f"{self.cfg.fps}fps  配置={self.cfg.cfg_path}")
        print("[win_glass] 全屏窗口：%s"
              % ("接管并固定在 100%（不受最高值设置影响）"
                 if self.cfg.fullscreen_lock else "完全不接管（原样保留）"))
        if self.cfg.hover:
            print(f"[win_glass] 悬停半透明：开   未聚焦窗口被鼠标压住时 "
                  f"{self.cfg.inactive_pct}% -> {self.cfg.hover_pct}% "
                  f"(最高/最低插值 {self.cfg.hover_ratio:.2f})；"
                  f"其余窗口联动 ×{self.cfg.hover_dim_ratio:.1f}  "
                  f"轮询={self.cfg.hover_interval * 1000:.0f}ms")
        else:
            print("[win_glass] 悬停半透明：关")
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
                # 悬停：自带节流；光标没动时是零成本空转，也不动 _dirty
                self._poll_hover(now)
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
    hwnds = scan_windows(cfg, self_pid)
    # 悬停候选：光标压着的那个顶层窗口，且必须在可管理集合里
    hover_hwnd = cursor_root_window() if cfg.hover else 0
    if hover_hwnd and hover_hwnd not in hwnds:
        hover_hwnd = 0
    # 层叠编号：与引擎共用 assign_depths，保证 --list 打印的就是引擎
    # 实际会算出来的层级（只统计「普通非聚焦」窗口）。
    plain = set()
    for hwnd in hwnds:
        if hwnd == fg:
            continue
        _t, _z, _f = read_window_state(hwnd)
        if not (_t or _z or _f):
            plain.add(hwnd)
    depths = (assign_depths(z_order_windows(), plain)
              if (cfg.layer_decay and plain) else {})
    rows = []
    for hwnd in hwnds:
        top, zoomed, fs = read_window_state(hwnd)
        alpha, why, _hv = target_for(cfg, hwnd, is_fg=(hwnd == fg), top=top,
                                     zoomed=zoomed, fullscreen=fs,
                                     hover_hwnd=hover_hwnd,
                                     depth=depths.get(hwnd, 0))
        flags = "".join(("F" if fs else "-", "Z" if zoomed else "-",
                         "T" if top else "-"))
        rows.append((hwnd, _class_name(hwnd), _window_text(hwnd),
                     int(round(alpha * 100)), why, flags,
                     depths.get(hwnd, 0)))
    rows.sort(key=lambda r: (-r[3], r[1]))
    print(f"可管理窗口 {len(rows)} 个   未聚焦目标={cfg.inactive_pct}%   "
          f"聚焦/最大化/置顶目标={cfg.active_pct}%   全屏固定=100%   "
          f"渐隐={cfg.fade_ms}ms")
    print("判定优先级: 全屏(恒 100%，不受最高值设置影响) > 聚焦 > 最大化 > "
          "置顶 > 悬停 > 普通非聚焦(层叠衰减)")
    print("标记 F=全屏 Z=最大化 T=置顶   层=层叠层级(1 起，0=不参与层叠)")
    if cfg.layer_decay:
        print("层叠衰减：开   第 1~5 层 = %s（系数 %.2f，下限 %d%%）"
              % (" / ".join("%d%%" % layer_pct(cfg.inactive_pct, d,
                                               cfg.layer_decay_ratio)
                            for d in range(1, 6)),
                 cfg.layer_decay_ratio, LAYER_MIN_PCT))
    else:
        print("层叠衰减：关（所有非聚焦窗口统一 %d%%）" % cfg.inactive_pct)
    if not cfg.fullscreen_lock:
        print("⚠️ 全屏锁定：关 —— 全屏窗口完全不接管（--skip-fullscreen）")
    if cfg.hover:
        print("悬停半透明：开   未聚焦窗口 → %d%%（插值 %.2f）   "
              "联动压暗：其余窗口 ×%.1f（下限 %d%%）   此刻悬停=%s"
              % (cfg.hover_pct, cfg.hover_ratio, cfg.hover_dim_ratio,
                 LAYER_MIN_PCT,
                 ("0x%08X" % hover_hwnd) if hover_hwnd else "无"))
    else:
        print("悬停半透明：关")
    print("-" * 96)
    print(f"{'HWND':>10}  {'目标':>5}  {'层':>3}  {'原因':<8} {'FZT':<4} "
          f"{'类名':<28} 标题")
    print("-" * 96)
    for hwnd, cls, title, tgt, why, flags, depth in rows:
        print(f"0x{hwnd:08X}  {tgt:>4}%  {depth:>3}  {why:<8} {flags:<4} "
              f"{cls[:28]:<28} {title[:34]}")
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

    # 跑一段 聚焦% -> 非聚焦% -> 悬停% -> 非聚焦% -> 全屏% -> 非聚焦% -> 聚焦%
    # 的缓动，并采样读回（单位统一为不透明度 0..1）
    hi, lo = cfg.active_alpha, cfg.inactive_alpha
    fsa = cfg.fullscreen_alpha                       # 恒定 1.0
    hv = cfg.hover_alpha if cfg.hover else lo
    print(f"[self-test] 滑块取值：非聚焦={cfg.inactive_pct}%  "
          f"聚焦/最大化/置顶={cfg.active_pct}%  （均为整数百分比）")
    print(f"[self-test] 全屏取值：{int(round(fsa * 100))}%"
          f"（恒定，不受聚焦最高透明度 {cfg.active_pct}% 影响）"
          + ("" if hi != fsa else "  ⚠️ 本次最高值也是 100%，该段与聚焦段数值相同"))
    if cfg.hover:
        print(f"[self-test] 悬停取值：{cfg.hover_pct}%"
              f"（最高/最低插值 {cfg.hover_ratio:.2f}）")
    else:
        print("[self-test] 悬停半透明：关（该段退化为非聚焦值）")
    print(f"[self-test] 播放 {cfg.fade_ms}ms 缓动   {cfg.active_pct}% -> "
          f"{cfg.inactive_pct}% -> {cfg.hover_pct}% -> {cfg.inactive_pct}% -> "
          f"{int(round(fsa * 100))}% -> {cfg.inactive_pct}% -> {cfg.active_pct}%")
    samples = []
    seq = [(hi, lo), (lo, hv), (hv, lo), (lo, fsa), (fsa, lo), (lo, hi)]
    step_ms = 50

    def play(leg_idx, elapsed):
        if leg_idx >= len(seq):
            print("[self-test] 采样读回（每段内部应平滑单调，段间瞬间即续，无突跳）：")
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
        description="win_glass — 窗口透明度随全屏/聚焦/最大化/置顶/悬停状态动态变化"
                    "（全屏恒定 100%，聚焦/最大化/置顶 5~100%，未聚焦 5~95%，"
                    "悬停取最高/最低中间值，托盘菜单可调）")
    ap.add_argument("--inactive-alpha", type=float, default=None,
                    help="未聚焦窗口的不透明度，0.05~0.95（也接受 5~95），"
                         "默认取配置文件，否则 0.40")
    ap.add_argument("--active-alpha", type=float, default=None,
                    help="聚焦 / 最大化 / 置顶窗口的不透明度，0.05~1.00"
                         "（也接受 5~100），默认取配置文件，否则 1.00；"
                         "全屏窗口不受它影响，恒为 100%%")
    ap.add_argument("--no-config", action="store_true",
                    help="既不读取也不写入配置文件（滑块改动只在本次运行有效）")
    ap.add_argument("--save-config", action="store_true",
                    help="把本次命令行参数写入配置文件后继续运行")
    ap.add_argument("--fade-ms", type=int, default=None,
                    help="渐变时长(ms)，1~5000；不给则用配置文件里的，默认 500")
    ap.add_argument("--no-hover", action="store_true",
                    help="关闭「悬停半透明」（鼠标压住未聚焦窗口时不再提亮）")
    ap.add_argument("--hover-ratio", type=float, default=None,
                    help="悬停值在「最低→最高」之间的插值，0~1，默认 0.8")
    ap.add_argument("--hover-interval", type=float, default=None,
                    help="鼠标位置轮询间隔(秒)，默认 0.05；越小越跟手也越费 CPU")
    ap.add_argument("--no-layer-decay", action="store_true",
                    help="关闭「层叠衰减」：所有非聚焦窗口统一用最低透明度"
                         "（v1.5.0 及以前的行为）")
    ap.add_argument("--layer-decay-ratio", type=float, default=None,
                    help="层衰减系数 0.1~1.0，默认 0.70：普通非聚焦窗口每往下"
                         "一层就乘一次它（上一层取整后的显示值），下限 5%%")
    ap.add_argument("--lang", default=None,
                    help="界面语言，如 zh_CN / en_US / ja_JP / de_DE …；"
                         "auto = 跟随系统；默认 en_US。可用值见 --list-langs")
    ap.add_argument("--list-langs", action="store_true",
                    help="列出所有可用语言后退出")
    ap.add_argument("--reset-shortcuts", action="store_true",
                    help="清空所有已绑定的菜单快捷键后退出")
    ap.add_argument("--fps", type=int, default=60, help="动画帧率，默认 60")
    ap.add_argument("--scan", type=float, default=0.15, help="目标重算间隔(秒)，默认 0.15")
    ap.add_argument("--rescan", type=float, default=0.50, help="窗口全量枚举间隔(秒)，默认 0.50")
    ap.add_argument("--exclude", default="", help="额外排除的窗口类名，逗号分隔")
    ap.add_argument("--skip-fullscreen", action="store_true",
                    help="完全不管全屏窗口（默认接管并锁定 100%%；"
                         "玩游戏怕掉帧时用这个退回 v1.3 行为）")
    ap.add_argument("--no-skip-fullscreen", action="store_true",
                    help="已废弃（v1.4.0 起默认就接管全屏窗口，此选项无作用）")
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
    fade = GlassConfig.apply_saved_fade(saved, args.fade_ms)
    hover, hover_ratio = GlassConfig.apply_saved_hover(
        saved, False if args.no_hover else None, args.hover_ratio)
    # 层叠衰减：--no-layer-decay（关）> 配置文件 > 内置默认（开）
    layer_decay, layer_ratio = GlassConfig.apply_saved_layer(
        saved, False if args.no_layer_decay else None, args.layer_decay_ratio)
    # 全屏锁定：--skip-fullscreen（关）> 配置文件 > 内置默认（开）
    fs_lock = GlassConfig.apply_saved_fs(
        saved, False if args.skip_fullscreen else None)
    # 语言 / 快捷键：命令行 > 配置文件 > 内置默认（v1.7.0）
    lang, shortcuts = GlassConfig.apply_saved_lang(
        saved, args.lang,
        {} if args.reset_shortcuts else None)
    cfg = GlassConfig(
        inactive_alpha=inactive,
        active_alpha=active,
        cfg_path="" if args.no_config else None,
        fade_ms=fade,
        fps=args.fps,
        scan_interval=args.scan,
        rescan_interval=args.rescan,
        fullscreen_lock=fs_lock,
        skip_foreign_layered=args.skip_foreign_layered,
        extra_exclude=[c.strip() for c in args.exclude.split(",") if c.strip()],
        verbose=args.verbose,
        restore_on_exit=not args.no_restore,
        tray=not args.no_tray,
        log_path=args.log,
        hover=hover,
        hover_ratio=hover_ratio,
        hover_interval=args.hover_interval,
        layer_decay=layer_decay,
        layer_decay_ratio=layer_ratio,
        language=lang,
        shortcuts=shortcuts,
    )
    if args.list_langs:
        print("可用语言（--lang 取值）：")
        for d in i18n.LANGS:
            mark = " *" if d["code"] == cfg.language else ""
            print("  %-8s %-22s %s%s"
                  % (d["code"], d["native"], d["english"], mark))
        return 0
    if args.reset_shortcuts:
        n = len(cfg.shortcuts)
        cfg.shortcuts = {}
        print("[win_glass] 已清空 %d 个快捷键绑定%s"
              % (n, "（写入配置文件）" if cfg.save() else "（配置文件写入失败，"
                 "本次仅内存生效）"))
        return 0
    if args.save_config and not args.no_config:
        if cfg.save():
            print("[win_glass] 已写入配置 %s：非聚焦=%d%%  聚焦/最大化/置顶=%d%%"
                  "  全屏=%s  渐隐=%dms  悬停=%s/%d%%"
                  % (CFG_PATH, cfg.inactive_pct, cfg.active_pct,
                     "固定100%" if cfg.fullscreen_lock else "不接管",
                     cfg.fade_ms, "开" if cfg.hover else "关", cfg.hover_pct))
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
