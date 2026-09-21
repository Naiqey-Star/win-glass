# -*- coding: utf-8 -*-
"""
win_glass 健壮性 / 可用性验证

  A. 参数边界    —— 各种 --inactive-alpha / --fade-ms / 非法参数不崩
  B. 零窗口      —— 把所有窗口类都排除时，能正常起停
  C. 长跑稳定性  —— 30s 运行，采样内存/CPU，中途反复创建销毁窗口
  D. 强杀还原    —— 进程内直接调 _on_console_ctrl(CTRL_CLOSE)，验证还原且幂等
  E. 系统托盘    —— 窗口化打包后唯一的交互入口，能创建并正常起停
  F. 优雅退出    —— 托盘窗口是顶层窗口，收 WM_CLOSE 后还原并退出（卸载器 taskkill 路径）
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import subprocess
import sys
import time
from ctypes import byref, c_ssize_t

# 一律用「正在跑本脚本的解释器」和「本脚本所在目录」，任何机器 clone 下来直接可跑。
PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "win_glass.py")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

GP = user32.GetWindowLongPtrW
GP.restype = c_ssize_t
GP.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
psapi.GetProcessMemoryInfo.restype = wt.BOOL
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
# 必须声明 argtypes，否则 64 位句柄按 C int 传参被截断 -> GetProcessTimes 静默失败
kernel32.GetProcessTimes.argtypes = [wt.HANDLE, ctypes.POINTER(wt.FILETIME),
                                     ctypes.POINTER(wt.FILETIME),
                                     ctypes.POINTER(wt.FILETIME),
                                     ctypes.POINTER(wt.FILETIME)]
kernel32.GetProcessTimes.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL

PASS, FAIL = 0, 0
def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [PASS] %s %s" % (name, detail))
    else:
        FAIL += 1
        print("  [FAIL] %s %s" % (name, detail))


def find_hwnd(prefix):
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    @WNDENUMPROC
    def cb(h, l):
        h = int(h)
        if user32.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(h, b, 512)
            if b.value.startswith(prefix):
                found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def find_hwnd_by_class(cls):
    """按类名找顶层窗口。注意会命中隐藏窗口 —— taskkill 就是这么枚举的。"""
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    @WNDENUMPROC
    def cb(h, l):
        b = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(int(h), b, 256)
        if b.value == cls:
            found.append(int(h))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def exstyle(h):
    return GP(h, -20) if h else 0


def all_visible_classes():
    """枚举当前所有可见窗口的类名 —— 用它们构造排除表，才能保证真的接管 0 个。"""
    got = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    @WNDENUMPROC
    def cb(h, l):
        h = int(h)
        if user32.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, b, 256)
            if b.value:
                got.append(b.value)
        return True

    user32.EnumWindows(cb, 0)
    return sorted(set(got))


def mem_cpu(pid):
    h = kernel32.OpenProcess(0x0410, False, pid)   # QUERY_INFORMATION|VM_READ
    if not h:
        return None, None
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    rss = None
    if psapi.GetProcessMemoryInfo(h, byref(pmc), pmc.cb):
        rss = pmc.WorkingSetSize
    ct, et, kt, ut = (wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME())
    cpu = None
    if kernel32.GetProcessTimes(h, byref(ct), byref(et), byref(kt), byref(ut)):
        def f2i(f):
            return (f.dwHighDateTime << 32) | f.dwLowDateTime
        cpu = (f2i(kt) + f2i(ut)) / 1e7
    kernel32.CloseHandle(h)
    return rss, cpu


print("=" * 70)
print("A. 参数边界")
print("=" * 70)
cases = [
    (["--list", "--inactive-alpha", "0.05"], "下限 0.05"),
    (["--list", "--inactive-alpha", "1.0"], "上限 1.0"),
    (["--list", "--inactive-alpha", "9.9"], "越界 9.9（应被夹到 1.0）"),
    (["--list", "--fade-ms", "50"], "极短渐变 50ms"),
    (["--list", "--duration", "0"], "duration=0"),
]
for args, desc in cases:
    r = subprocess.run([PY, MAIN] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    check("参数 " + desc, r.returncode == 0,
          "rc=%d" % r.returncode if r.returncode else "")

r = subprocess.run([PY, MAIN, "--inactive-alpha", "abc"], capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=60)
check("非法参数优雅报错", r.returncode != 0 and "invalid" in (r.stderr or "").lower(),
      "rc=%d" % r.returncode)

print()
print("=" * 70)
print("B. 零窗口场景（动态排除当前所有窗口类）")
print("=" * 70)
_excl = ",".join(all_visible_classes())
r = subprocess.run([PY, MAIN, "--no-tray", "--duration", "4", "--exclude", _excl],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=60)
out = r.stdout or ""
print("  排除了 %d 个窗口类" % len(_excl.split(",")))
print("  " + "\n  ".join(out.strip().splitlines()[:5]))
check("零窗口可正常起停", r.returncode == 0 and "开始实时跟随" in out, "rc=%d" % r.returncode)
check("零窗口时接管数为 0", bool(re.search(r"首批接管 0 个", out)))

print()
print("=" * 70)
print("C. 长跑稳定性（30s，反复创建/销毁窗口 + 每 1.5s 置顶抖动以驱动动画）")
print("=" * 70)
eng = subprocess.Popen([PY, MAIN, "--no-tray", "--duration", "30", "--exclude",
                        "Chrome_WidgetWin_1"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding="utf-8", errors="replace")
time.sleep(2)
samples = []
vics = []
for i in range(6):
    # 第 5 参数 1.5 => 每 1.5s 翻转置顶，目标值反复 100%<->40%，逼出大量动画帧
    p = subprocess.Popen([PY, HERE + r"\victim_window.py",
                          "win_glass 稳态测试 %d" % i, str(120 + i * 40), "520", "12", "1.5"])
    vics.append(p)
    time.sleep(1.2)
    rss, cpu = mem_cpu(eng.pid)
    if rss:
        samples.append((rss, cpu))
    if i % 2 == 1:
        vics[-1].terminate()

while eng.poll() is None:
    rss, cpu = mem_cpu(eng.pid)
    if rss:
        samples.append((rss, cpu))
    time.sleep(1.5)

out, _ = eng.communicate()
alive = eng.returncode == 0
check("30s 长跑正常退出", alive, "rc=%s" % eng.returncode)
if samples:
    rss_mb = [s[0] / 1048576 for s in samples]
    first, last, peak = rss_mb[0], rss_mb[-1], max(rss_mb)
    cpu_first, cpu_last = samples[0][1], samples[-1][1]
    measured = cpu_first is not None and cpu_last is not None
    span = (cpu_last - cpu_first) if measured else None
    print("  内存采样 MB: " + " ".join("%.1f" % v for v in rss_mb))
    print("  首 %.1f / 末 %.1f / 峰 %.1f MB   期间累计 CPU %s"
          % (first, last, peak, ("%.3fs" % span) if measured else "测量失败"))
    check("无内存泄漏（末-首 < 5MB）", (last - first) < 5.0,
          "Δ=%.2f MB" % (last - first))
    # CPU 必须测到真实值，测不到就是 FAIL（避免静默假通过）
    check("CPU 采样有效", measured, "cpu_first=%s cpu_last=%s" % (cpu_first, cpu_last))
    if measured:
        check("CPU 占用极低（30s 内 < 5s）", span < 5.0, "%.3fs" % span)
print("  " + "\n  ".join(out.strip().splitlines()[-3:]))
for v in vics:
    try:
        v.terminate()
    except Exception:
        pass

print()
print("=" * 70)
print("D. 强杀还原路径（进程内调用 _on_console_ctrl(CTRL_CLOSE)）")
print("=" * 70)
sys.path.insert(0, HERE)
import win_glass as wg

cfg = wg.GlassConfig(extra_exclude=["Chrome_WidgetWin_1"], verbose=False)
engine = wg.GlassEngine(cfg)
engine._cb_ref = wg.WINEventProc(engine._hook_cb)

pv = subprocess.Popen([PY, HERE + r"\victim_window.py", "win_glass 强杀还原", "200", "560", "25"])
time.sleep(1.6)
hv = find_hwnd("win_glass 强杀还原")
check("测试窗口就绪", hv != 0, "hwnd=0x%08X" % hv)
base = exstyle(hv)

engine._refresh_window_list()
time.sleep(0.3)
after = exstyle(hv)
check("接管后挂上 LAYERED", bool(after & 0x80000), "exstyle 0x%08X -> 0x%08X" % (base, after))

handled = engine._on_console_ctrl(wg.CTRL_CLOSE_EVENT)
time.sleep(0.3)
restored = exstyle(hv)
check("CTRL_CLOSE 被处理", bool(handled))
check("窗口已还原（LAYERED 移除）", not (restored & 0x80000),
      "exstyle=0x%08X" % restored)
n2 = engine._restore_all()
check("还原幂等（二次调用返回 0）", n2 == 0, "n=%d" % n2)
try:
    pv.terminate()
except Exception:
    pass

print()
print("=" * 70)
print("E. 系统托盘（窗口化打包后唯一的交互入口）")
print("=" * 70)
r = subprocess.run([PY, MAIN, "--duration", "5", "--exclude", "Chrome_WidgetWin_1"],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=60)
eo = r.stdout or ""
check("托盘图标创建成功", "托盘图标已就位" in eo,
      "rc=%d" % r.returncode)
check("托盘模式下正常退出", r.returncode == 0, "rc=%d" % r.returncode)
print("  " + "\n  ".join(eo.strip().splitlines()[:3]))

print()
print("=" * 70)
print("F. 优雅退出通道（卸载器 taskkill 走的就是这条路）")
print("=" * 70)
pv2 = subprocess.Popen([PY, HERE + r"\victim_window.py", "win_glass 优雅退出", "260", "560", "40"])
time.sleep(1.8)
hv2 = find_hwnd("win_glass 优雅退出")
check("测试窗口就绪", hv2 != 0, "hwnd=0x%08X" % hv2)

p = subprocess.Popen([PY, MAIN, "--duration", "40", "--exclude", "Chrome_WidgetWin_1"],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True, encoding="utf-8", errors="replace")
cls = "WinGlassTrayWnd_%d" % p.pid
hwnd = 0
for _ in range(48):
    time.sleep(0.25)
    hwnd = find_hwnd_by_class(cls)
    if hwnd:
        break
check("托盘窗口是顶层窗口（taskkill 枚举得到）", hwnd != 0,
      "class=%s hwnd=0x%08X" % (cls, hwnd))
if hwnd:
    ex = exstyle(hwnd)
    check("托盘窗口带 WS_EX_TOOLWINDOW（不进任务栏/Alt+Tab）",
          bool(ex & 0x00000080), "exstyle=0x%08X" % ex)
    check("托盘窗口不可见（不抢焦点）", not user32.IsWindowVisible(hwnd))
    time.sleep(1.2)
    check("退出前窗口已被接管（挂上 LAYERED）", bool(exstyle(hv2) & 0x80000),
          "exstyle=0x%08X" % exstyle(hv2))
    user32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE，等价于 taskkill
    try:
        fout, _ = p.communicate(timeout=40)
    except subprocess.TimeoutExpired:
        p.kill()
        fout, _ = p.communicate()
    check("WM_CLOSE 触发优雅退出（未强杀）", p.returncode == 0, "rc=%s" % p.returncode)
    check("退出后窗口已还原（LAYERED 摘除）", not (exstyle(hv2) & 0x80000),
          "exstyle=0x%08X" % exstyle(hv2))
    check("退出日志写明已还原", "已还原" in (fout or ""))
    print("  " + "\n  ".join((fout or "").strip().splitlines()[-2:]))
else:
    p.kill()
try:
    pv2.terminate()
except Exception:
    pass

print()
print("=" * 70)
print("汇总：PASS=%d  FAIL=%d" % (PASS, FAIL))
print("=" * 70)
sys.exit(1 if FAIL else 0)
