# -*- coding: utf-8 -*-
"""
安装包验证：在沙盒目录完整走一遍 安装 -> 校验 -> 卸载 -> 校验清理。
不触碰真实的 %LOCALAPPDATA%\\Programs\\win_glass。

v2 变更：启动器 .vbs 已彻底移除（部分机器 .vbs 关联被改成记事本，
点快捷方式只会“用记事本打开脚本”）。现在快捷方式直指窗口化主程序，
主程序无控制台、靠系统托盘交互。
"""
import ctypes
import os
import subprocess
import sys
import time
import winreg

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
SETUP = os.path.join(DIST, "win_glass_setup_v1.0.1.exe")
CLIENT = os.path.join(DIST, "win_glass.exe")            # 窗口化 + 托盘
CONSOLE = os.path.join(DIST, "win_glass-console.exe")   # 控制台诊断版
SANDBOX = os.path.join(HERE, "_installtest")
LNK = os.path.join(os.environ.get("APPDATA", ""),
                   r"Microsoft\Windows\Start Menu\Programs",
                   "win_glass 窗口透明效果.lnk")
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\win_glass"
CREATE_NO_WINDOW = 0x08000000

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [PASS] %s %s" % (name, detail))
    else:
        FAIL += 1
        print("  [FAIL] %s %s" % (name, detail))


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def lnk_target(path):
    """读出快捷方式真实指向，确认没有中间层 .vbs。"""
    import base64
    ps = ("$ws = New-Object -ComObject WScript.Shell; "
          "$s = $ws.CreateShortcut('%s'); "
          "Write-Output $s.TargetPath" % path.replace("'", "''"))
    enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                        "-EncodedCommand", enc],
                       capture_output=True, text=True, timeout=60,
                       encoding="utf-8", errors="replace",
                       creationflags=CREATE_NO_WINDOW)
    return (r.stdout or "").strip()


def pe_subsystem(path):
    """读 PE 可选头的 Subsystem 字段。2=WINDOWS_GUI(无控制台)，3=WINDOWS_CUI(带控制台)。
    这是「主程序会不会弹黑窗口」最硬的证据，不依赖肉眼观察。"""
    import struct
    with open(path, "rb") as f:
        if f.read(2) != b"MZ":
            return None
        f.seek(0x3C)
        e_lfanew = struct.unpack("<I", f.read(4))[0]
        f.seek(e_lfanew)
        if f.read(4) != b"PE\0\0":
            return None
        f.seek(e_lfanew + 0x5C)
        return struct.unpack("<H", f.read(2))[0]


print("=" * 74)
print("A. 打包产物形态")
print("=" * 74)
check("窗口化主程序存在", os.path.isfile(CLIENT),
      "%.2f MB" % (os.path.getsize(CLIENT) / 1048576) if os.path.isfile(CLIENT) else "缺失")
check("控制台诊断版存在", os.path.isfile(CONSOLE),
      "%.2f MB" % (os.path.getsize(CONSOLE) / 1048576) if os.path.isfile(CONSOLE) else "缺失")
check("安装包存在", os.path.isfile(SETUP),
      "%.2f MB" % (os.path.getsize(SETUP) / 1048576) if os.path.isfile(SETUP) else "缺失")

if os.path.isfile(CLIENT):
    sub = pe_subsystem(CLIENT)
    check("主程序是 GUI 子系统（双击不会弹命令行窗口）", sub == 2,
          "Subsystem=%s" % sub)
if os.path.isfile(CONSOLE):
    sub = pe_subsystem(CONSOLE)
    check("诊断版是 CUI 子系统（能看输出）", sub == 3, "Subsystem=%s" % sub)

print()
print("=" * 74)
print("B. 打包后独立可用性（不装 Python 也能跑）")
print("=" * 74)
r = run([CONSOLE, "--list"])
check("--list 可运行", r.returncode == 0, "rc=%d" % r.returncode)
print("  " + "\n  ".join((r.stdout or "").strip().splitlines()[:6]))

r = run([CONSOLE, "--help"])
check("--help 正常", r.returncode == 0)

r = run([CONSOLE, "--self-test"], timeout=90)
out = (r.stdout or "")
has_tk = "透明度设置与读回链路可用" in out or "已完成" in out
check("打包内含 tkinter（--self-test 可用）", has_tk, "rc=%d" % r.returncode)

r = run([CLIENT, "--no-tray", "--duration", "3"])
check("窗口化主程序实际运行 3s 正常退出", r.returncode == 0, "rc=%d" % r.returncode)

print()
print("=" * 74)
print("C. 安装到沙盒目录 %s" % SANDBOX)
print("=" * 74)
r = run([SETUP, "--dir", SANDBOX, "--quiet"])
out = (r.stdout or "") + (r.stderr or "")
check("安装器返回 0", r.returncode == 0, "rc=%d" % r.returncode)
print("  " + "\n  ".join(out.strip().splitlines()[:12]))

exe = os.path.join(SANDBOX, "win_glass.exe")
console = os.path.join(SANDBOX, "win_glass-console.exe")
uninst = os.path.join(SANDBOX, "uninstall.exe")
icon = os.path.join(SANDBOX, "icon.ico")
files = os.listdir(SANDBOX) if os.path.isdir(SANDBOX) else []
vbs_left = [n for n in files if n.lower().endswith(".vbs")]

check("窗口化主程序已安装", os.path.isfile(exe),
      "%.2f MB" % (os.path.getsize(exe) / 1048576) if os.path.isfile(exe) else "缺失")
check("控制台诊断版已安装", os.path.isfile(console))
check("已无 .vbs 启动器（关键修复）", not vbs_left,
      "残留: %s" % vbs_left if vbs_left else "干净")
check("卸载程序已生成", os.path.isfile(uninst))
check("图标已随装", os.path.isfile(icon))
check("开始菜单快捷方式已创建", os.path.isfile(LNK))

tgt = lnk_target(LNK) if os.path.isfile(LNK) else ""
check("快捷方式直指 win_glass.exe（不经 VBS）",
      tgt.lower().endswith("win_glass.exe") and os.path.normcase(SANDBOX) in os.path.normcase(tgt),
      tgt or "未读到")

try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINST_KEY) as k:
        dn = winreg.QueryValueEx(k, "DisplayName")[0]
        dv = winreg.QueryValueEx(k, "DisplayVersion")[0]
        us = winreg.QueryValueEx(k, "UninstallString")[0]
    check("卸载注册项已写入", True, "%s v%s" % (dn, dv))
    check("UninstallString 指向安装目录",
          os.path.normcase(SANDBOX) in os.path.normcase(us), us)
except FileNotFoundError:
    check("卸载注册项已写入", False, "未找到注册表键")

print()
print("=" * 74)
print("D. 已安装的程序能否启动")
print("=" * 74)
r = run([console, "--list"])
check("已安装的控制台版可运行", r.returncode == 0, "rc=%d" % r.returncode)
r = run([exe, "--no-tray", "--duration", "3"])
check("已安装的窗口化版可运行", r.returncode == 0, "rc=%d" % r.returncode)

print()
print("=" * 74)
print("E. 卸载")
print("=" * 74)
r = run([uninst, "--uninstall", "--quiet", "--dir", SANDBOX], timeout=120)
out = (r.stdout or "") + (r.stderr or "")
check("卸载程序返回 0", r.returncode == 0, "rc=%d" % r.returncode)
print("  " + "\n  ".join(out.strip().splitlines()[:12]))

time.sleep(4)   # 等延迟自删完成

left = os.listdir(SANDBOX) if os.path.isdir(SANDBOX) else []
check("安装目录已清理", not left, "残留: %s" % left if left else "已空/已删除")
check("开始菜单快捷方式已删除", not os.path.isfile(LNK))
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINST_KEY):
        check("卸载注册项已移除", False, "注册表键仍在")
except FileNotFoundError:
    check("卸载注册项已移除", True)

print()
print("=" * 74)
print("汇总：PASS=%d  FAIL=%d" % (PASS, FAIL))
print("=" * 74)
sys.exit(1 if FAIL else 0)
