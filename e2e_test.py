# -*- coding: utf-8 -*-
"""
端到端验证 win_glass（确定性版）。

关键点：Windows 前台锁会拒绝后台进程抢焦点，所以由**编排器**用
AttachThreadInput + AllowSetForegroundWindow + Alt 敲击 主动切换前台窗口，
每一步都断言 GetForegroundWindow() 确实生效，避免测试 flaky。

流程
  1) 起测试窗 A，编排器把 A 设为前台  -> 引擎应接管 A 为 100%
  2) 起测试窗 B，编排器把 B 设为前台  -> A 应变 100% -> 40%
  3) 编排器把 A 再设回前台            -> A 应变 40% -> 100%，B 变 40%
  4) 引擎退出                        -> A 的 WS_EX_LAYERED 应被移除

为保护本机正在使用的窗口，引擎带 --exclude Chrome_WidgetWin_1；
并且带 --no-config + 显式 --inactive-alpha/--active-alpha：
既能保证期望值确定（不受用户自己拖过的配置文件影响），也不会写坏真实配置。
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import subprocess
import sys
import time
from ctypes import c_ssize_t

# 一律用「正在跑本脚本的解释器」和「本脚本所在目录」，任何机器 clone 下来直接可跑。
PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))

# 本测试使用的两个目标透明度（显式传给引擎，不依赖配置文件）
INACT_PCT, ACT_PCT = 40, 100

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GP = user32.GetWindowLongPtrW
GP.restype = c_ssize_t
GP.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetForegroundWindow.restype = wt.HWND
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.AllowSetForegroundWindow.argtypes = [wt.DWORD]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.c_void_p]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL
user32.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.c_void_p]
kernel32.GetCurrentThreadId.restype = wt.DWORD

ASFW_ANY = 0xFFFFFFFF
VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002


def force_foreground(hwnd) -> bool:
    """把指定窗口强行推到前台（绕过 Windows 前台锁），并确认真的生效。"""
    if not hwnd:
        return False
    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
        # Alt 敲击：解除前台锁
        user32.keybd_event(VK_MENU, 0, 0, None)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, None)
        cur = kernel32.GetCurrentThreadId()
        fg = int(user32.GetForegroundWindow() or 0)
        t_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = False
        if t_fg and t_fg != cur:
            attached = bool(user32.AttachThreadInput(cur, t_fg, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if attached:
            user32.AttachThreadInput(cur, t_fg, False)
        time.sleep(0.3)
        return int(user32.GetForegroundWindow() or 0) == hwnd
    except Exception:
        return False


def find_hwnd(title_part):
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    @WNDENUMPROC
    def cb(h, l):
        h = int(h)
        if user32.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(h, b, 512)
            if b.value.startswith(title_part):
                found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def exstyle(h):
    return GP(h, -20) if h else 0


log = []


def say(s):
    print(s, flush=True)
    log.append(s)


def spawn_victim(title, x, y, life):
    return subprocess.Popen([PY, HERE + r"\victim_window.py", title,
                             str(x), str(y), str(life)])


say("=== win_glass 端到端验证（确定性前台切换）===")

# 1) 测试窗 A + 设为前台
pa = spawn_victim("win_glass e2e A", 160, 160, 60)
time.sleep(1.6)
ha = find_hwnd("win_glass e2e A")
if not ha:
    say("[FAIL] 未找到测试窗口 A")
    pa.kill()
    sys.exit(1)
base_ex = exstyle(ha)
ok_fg = force_foreground(ha)
say("A 就绪 HWND=0x%08X exstyle=0x%08X  设前台成功=%s  当前前台=0x%08X"
    % (ha, base_ex, ok_fg, int(user32.GetForegroundWindow() or 0)))

# 2) 引擎
eng = subprocess.Popen(
    [PY, HERE + r"\win_glass.py", "--no-tray", "--duration", "20", "--verbose",
     "--no-config",
     "--inactive-alpha", str(INACT_PCT), "--active-alpha", str(ACT_PCT),
     "--exclude", "Chrome_WidgetWin_1"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    encoding="utf-8", errors="replace")
time.sleep(3.0)
ex_now = exstyle(ha)
say("引擎跑 3s：A exstyle=0x%08X (LAYERED=%s)  << 应已挂上 LAYERED"
    % (ex_now, bool(ex_now & 0x80000)))

# 3) 起 B 并设为前台 -> A 应失焦变 40%
pb = spawn_victim("win_glass e2e B", 640, 160, 60)
time.sleep(1.2)
hb = find_hwnd("win_glass e2e B")
ok_b = force_foreground(hb)
say("B 就绪 HWND=0x%08X  设前台成功=%s  当前前台=0x%08X"
    % (hb, ok_b, int(user32.GetForegroundWindow() or 0)))
time.sleep(3.0)

# 4) 把前台切回 A -> A 应回焦变 100%
ok_a2 = force_foreground(ha)
say("切回 A 成功=%s  当前前台=0x%08X" % (ok_a2, int(user32.GetForegroundWindow() or 0)))
time.sleep(3.0)

# 5) 收尾
try:
    pb.kill()
except Exception:
    pass
try:
    out, _ = eng.communicate(timeout=30)
except subprocess.TimeoutExpired:
    eng.kill()
    out, _ = eng.communicate()
say("\n--- 引擎输出 ---")
for line in (out or "").splitlines():
    say(line)

time.sleep(1.0)
ha2 = find_hwnd("win_glass e2e A")
ex2 = 0
if ha2:
    ex2 = exstyle(ha2)
    say("\n--- 还原检查 ---")
    say("A 还原后 exstyle=0x%08X (LAYERED=%s)  原始=0x%08X"
        % (ex2, bool(ex2 & 0x80000), base_ex))

say("\n--- 关键断言 ---")
joined = "\n".join(log) + (out or "")
# 期望值来自上面显式传给引擎的那两个数，不写死 —— 否则用户一拖滑块就假失败
n40 = len(re.findall(r"%d%% -> %d%%" % (ACT_PCT, INACT_PCT), joined))
n100 = len(re.findall(r"%d%% -> %d%%" % (INACT_PCT, ACT_PCT), joined))
fg_ok = ok_fg and ok_b and ok_a2
restored = bool(ha2) and not (ex2 & 0x80000)
say("前台切换确实生效        = %-3s %s" % (fg_ok, "PASS" if fg_ok else "FAIL"))
say("失焦 %d%%->%d%% 记录数  = %-3d %s"
    % (ACT_PCT, INACT_PCT, n40, "PASS" if n40 else "FAIL"))
say("回焦 %d%%->%d%% 记录数  = %-3d %s"
    % (INACT_PCT, ACT_PCT, n100, "PASS" if n100 else "FAIL"))
say("退出后 LAYERED 已移除    = %-3s %s" % (restored, "PASS" if restored else "FAIL"))
for p in (pa, pb):
    try:
        p.kill()
    except Exception:
        pass
say("=== 结束 ===")
sys.exit(0 if (fg_ok and n40 and n100 and restored) else 1)
