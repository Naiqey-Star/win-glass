# -*- coding: utf-8 -*-
"""
win_glass 安装器 —— 由 PyInstaller 打包成 win_glass_setup_v<版本号>.exe

行为
  双击 / 无参数     安装（升级式覆盖），装到 %LOCALAPPDATA%\\Programs\\win_glass
  --uninstall       卸载（先优雅停掉正在跑的实例，再删文件与注册表）
  --dir <path>      指定安装目录
  --autostart       同时设置开机自启（登录时最小化启动）
  --no-autostart    移除开机自启
  --no-shortcut     不创建开始菜单快捷方式
  --quiet           少输出

设计取舍
  · 装到用户目录 ⇒ 不需要管理员权限、不弹 UAC
  · 主程序是窗口化（--noconsole）构建，没有任何控制台窗口，交互全在系统托盘上
  · 快捷方式直指 win_glass.exe；不再套 .vbs —— 有些机器 .vbs 关联被改成了记事本，
    点快捷方式会变成「用记事本打开脚本」，那是 v1.0.0 早期版本不可用的根因
  · 另装一份 win_glass-console.exe 作诊断用（--list / --verbose 需要看输出）
  · 卸载/升级前用 taskkill（不带 /F）向托盘的隐藏顶层窗口发 WM_CLOSE，
    程序收到后走正常退出流程把窗口透明度还原
"""
import argparse
import base64
import ctypes
import os
import shutil
import subprocess
import sys
import time
import winreg

# 中文输出保护：GBK 控制台需要同时把代码页切成 65001，否则中文显示成乱码
if sys.platform.startswith("win"):
    try:
        _k = ctypes.WinDLL("kernel32", use_last_error=True)
        _k.SetConsoleOutputCP(65001)
        _k.SetConsoleCP(65001)
    except Exception:
        pass
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

APP_NAME = "win_glass"
APP_VER = "1.7.1"
APP_DESC = "窗口聚焦透明度美化工具（聚焦/最大化/置顶走最高值，全屏固定 100%，悬停系数可调，层叠衰减按 Z 序递推；托盘菜单可右键绑定全局快捷键、自动适配 Win11 圆角、内置 13 种界面语言）"
PUBLISHER = "Naiqey.千鵺"
CLIENT_EXE = "win_glass.exe"                 # 窗口化主程序（无控制台，带系统托盘）
CONSOLE_EXE = "win_glass-console.exe"        # 控制台诊断版（--list / --verbose 等）
LNK_NAME = "win_glass 窗口透明效果.lnk"
RUN_VALUE = "win_glass"
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\win_glass"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

CREATE_NO_WINDOW = 0x08000000


# --------------------------------------------------------------------------
def res_path(name: str) -> str:
    """打包后从 _MEIPASS 取内嵌文件，未打包时取脚本同目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def default_install_dir() -> str:
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    return os.path.join(root, "Programs", APP_NAME)


def start_menu_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")


def ps(script: str):
    """用 -EncodedCommand 跑 PowerShell，彻底规避引号转义问题。

    ⚠️ 必须带 errors="replace"：PowerShell 输出走的是控制台代码页，
    中文环境下可能是 GBK 字节，strict UTF-8 解码会在读取线程里抛
    UnicodeDecodeError（表现是 make_shortcut 拿不到 stdout，静默失败）。
    """
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                           "-EncodedCommand", enc],
                          capture_output=True, text=True, timeout=60,
                          encoding="utf-8", errors="replace",
                          creationflags=CREATE_NO_WINDOW)


def make_shortcut(lnk: str, target: str, args: str = "", workdir: str = "",
                  icon: str = "", desc: str = ""):
    def q(s):
        return s.replace("'", "''")

    lines = [
        "$ws = New-Object -ComObject WScript.Shell",
        "$s = $ws.CreateShortcut('%s')" % q(lnk),
        "$s.TargetPath = '%s'" % q(target),
    ]
    if args:
        lines.append("$s.Arguments = '%s'" % q(args))
    if workdir:
        lines.append("$s.WorkingDirectory = '%s'" % q(workdir))
    if icon:
        lines.append("$s.IconLocation = '%s'" % q(icon))
    if desc:
        lines.append("$s.Description = '%s'" % q(desc))
    lines.append("$s.Save()")
    r = ps("\n".join(lines))
    return r.returncode == 0 and os.path.exists(lnk)


def stop_running(quiet=False):
    """优雅停掉正在运行的 win_glass。

    两个版本都接得住 taskkill（不带 /F）发的 WM_CLOSE：
      · 窗口化版：托盘的隐藏顶层窗口收到 WM_CLOSE → 还原窗口并退出
      · 控制台版：控制台窗口收到 CTRL_CLOSE → 还原窗口并退出
    所以先不带 /F 请求退出，超时未退再强杀兜底。
    """
    def _out(s):
        if not quiet:
            print(s)

    def _running(name):
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/NH"],
                           capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        return name.lower() in (r.stdout or "").lower()

    found = False
    try:
        for name in (CLIENT_EXE, CONSOLE_EXE):
            if not _running(name):
                continue
            found = True
            _out("  · 检测到正在运行的 %s，先请它退出（会自动还原窗口）…" % name)
            subprocess.run(["taskkill", "/IM", name], capture_output=True,
                           creationflags=CREATE_NO_WINDOW)
            for _ in range(12):
                time.sleep(0.25)
                if not _running(name):
                    break
            if _running(name):
                _out("  · %s 未能优雅退出，强制结束。" % name)
                subprocess.run(["taskkill", "/IM", name, "/F"], capture_output=True,
                               creationflags=CREATE_NO_WINDOW)
                time.sleep(0.4)
        if found:
            _out("  · 运行中的实例已停止。")
        return found
    except Exception as e:
        _out("  · 停止实例时出错：%s" % e)
        return False


def set_autostart(enable: bool, exe: str):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
    with key:
        if enable:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, '"%s"' % exe)
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def reg_uninstall(install_dir: str, uninst_exe: str, exe: str, icon: str):
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINST_KEY)
    with key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "win_glass 窗口透明度")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VER)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, icon)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, '"%s" --uninstall' % uninst_exe)
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ,
                          '"%s" --uninstall --quiet' % uninst_exe)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, 0)


def remove_reg_uninstall():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINST_KEY)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def pause_if_tty():
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n按回车关闭…")
    except Exception:
        pass


# --------------------------------------------------------------------------
def do_install(args) -> int:
    install_dir = os.path.abspath(args.dir or default_install_dir())
    print("=" * 66)
    print(" win_glass %s 安装程序" % APP_VER)
    print("=" * 66)
    print("目标平台 : Windows x64")
    print("安装目录 : %s" % install_dir)
    print()

    src = res_path(CLIENT_EXE)
    if not os.path.isfile(src):
        print("[错误] 安装包内未找到 %s（打包时漏了 --add-data？）" % CLIENT_EXE)
        return 2

    stop_running(args.quiet)

    os.makedirs(install_dir, exist_ok=True)

    # 主程序 = 窗口化（无控制台）+ 系统托盘；这是日常用的那个
    dst_exe = os.path.join(install_dir, CLIENT_EXE)
    shutil.copy2(src, dst_exe)
    print("  · 已写入 %s (%.1f MB)  [窗口化 + 托盘]" % (dst_exe, os.path.getsize(dst_exe) / 1048576.0))

    # 控制台诊断版：需要看 --list / --verbose 输出时用
    dst_console = os.path.join(install_dir, CONSOLE_EXE)
    cs = res_path(CONSOLE_EXE)
    if os.path.isfile(cs):
        shutil.copy2(cs, dst_console)
        print("  · 已写入 %s (%.1f MB)  [控制台诊断版]"
              % (dst_console, os.path.getsize(dst_console) / 1048576.0))

    # 图标随程序目录留一份，供快捷方式与卸载项引用
    icon_src = res_path("icon.ico")
    dst_icon = os.path.join(install_dir, "icon.ico")
    if os.path.isfile(icon_src):
        shutil.copy2(icon_src, dst_icon)
    else:
        dst_icon = dst_exe

    # 卸载器 = 安装包自身的一份副本
    uninst_exe = os.path.join(install_dir, "uninstall.exe")
    try:
        shutil.copy2(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__),
                     uninst_exe)
    except Exception:
        shutil.copy2(res_path(CLIENT_EXE), uninst_exe)   # 兜底：至少放个可执行文件
    print("  · 已生成卸载程序 uninstall.exe")

    # 清理旧版本遗留：v1.0.0 早期版本用 .vbs 当启动器，而这台机器 .vbs 关联被改成了
    # 记事本，点快捷方式只会“用记事本打开脚本”。新版本已彻底不用它，升级时顺手删掉。
    for name in os.listdir(install_dir):
        if name.lower().endswith(".vbs"):
            try:
                os.remove(os.path.join(install_dir, name))
                print("  · 已清理旧版启动器 %s（新版不再需要）" % name)
            except OSError:
                pass

    lnk_path = ""
    if not args.no_shortcut:
        # 直接指向 exe —— 不要再套 .vbs：很多机器上 .vbs 关联被改成了记事本，
        # 点快捷方式会变成「用记事本打开脚本」而不是运行它。
        lnk_path = os.path.join(start_menu_dir(), LNK_NAME)
        ok = make_shortcut(lnk_path, dst_exe, workdir=install_dir, icon=dst_icon,
                           desc=APP_DESC)
        print("  · 开始菜单快捷方式：%s" % ("已创建" if ok else "创建失败"))
        if not ok:
            lnk_path = ""

    reg_uninstall(install_dir, uninst_exe, dst_exe, dst_icon)
    print("  · 已注册卸载项（控制面板「程序和功能」可见）")

    if args.autostart:
        set_autostart(True, dst_exe)
        print("  · 已设置开机自启（登录时静默启动到托盘）")
    elif args.no_autostart:
        set_autostart(False, dst_exe)
        print("  · 已移除开机自启")

    print()
    print("-" * 66)
    print("安装完成。")
    print("  启动方式：开始菜单搜索 “win_glass”%s" % ("" if lnk_path else "，或直接双击：" + dst_exe))
    print("  运行表现：无控制台窗口；托盘会出现一个图标")
    print("            · 左键单击 = 暂停 / 继续（暂停时所有窗口恢复 100%）")
    print("            · 右键     = 暂停、立即恢复、打开日志、退出")
    print("  退出方式：托盘右键 → 退出（会自动把所有窗口透明度还原）")
    print("  诊断查看：%s --list   （控制台版，能直接看窗口状态表）" % CONSOLE_EXE)
    print("  卸载方式：控制面板「程序和功能」→ win_glass 窗口透明度")
    print("-" * 66)
    return 0


def do_uninstall(args) -> int:
    install_dir = os.path.abspath(args.dir or default_install_dir())
    print("=" * 66)
    print(" win_glass 卸载程序")
    print("=" * 66)
    print("安装目录 : %s" % install_dir)
    print()

    stop_running(args.quiet)

    lnk = os.path.join(start_menu_dir(), LNK_NAME)
    if os.path.isfile(lnk):
        try:
            os.remove(lnk)
            print("  · 已删除开始菜单快捷方式")
        except OSError as e:
            print("  · 快捷方式删除失败：%s" % e)

    set_autostart(False, "")
    print("  · 已移除开机自启")

    if remove_reg_uninstall():
        print("  · 已移除卸载注册项")

    # 目录内含正在运行的 uninstall.exe，延迟自删
    if os.path.isdir(install_dir):
        try:
            for name in os.listdir(install_dir):
                if name.lower() == "uninstall.exe":
                    continue
                p = os.path.join(install_dir, name)
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            print("  · 已删除安装文件（卸载器本体稍后自动清理）")
        except Exception as e:
            print("  · 删除文件时出错：%s" % e)
        subprocess.Popen('cmd /c ping -n 3 127.0.0.1 >nul & rmdir /s /q "%s"' % install_dir,
                         shell=True, creationflags=CREATE_NO_WINDOW)

    print()
    print("卸载完成。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True,
                                 description="win_glass %s 安装/卸载程序" % APP_VER)
    ap.add_argument("--uninstall", action="store_true", help="卸载 win_glass")
    ap.add_argument("--dir", default="", help="指定安装目录")
    ap.add_argument("--autostart", action="store_true", help="设置开机自启")
    ap.add_argument("--no-autostart", action="store_true", help="移除开机自启")
    ap.add_argument("--no-shortcut", action="store_true", help="不创建开始菜单快捷方式")
    ap.add_argument("--quiet", action="store_true", help="少输出")
    args = ap.parse_args()

    try:
        rc = do_uninstall(args) if args.uninstall else do_install(args)
    except Exception as e:
        print("\n[错误] %s" % e)
        rc = 1
    if not args.quiet:
        pause_if_tty()
    return rc


if __name__ == "__main__":
    sys.exit(main())
