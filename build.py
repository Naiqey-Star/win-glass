# -*- coding: utf-8 -*-
"""
win_glass 打包脚本。

产物（均在 dist\\ 下）
  win_glass.exe                  主程序（单文件，无需 Python 环境）
  win_glass_setup_v<ver>.exe     安装包（内嵌主程序，双击即装/卸载）

目标平台：Windows x64（与本机一致）
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 用「当前正在跑本脚本的那个解释器」来执行 PyInstaller。
# 不要把某台机器的 Python 绝对路径写死 —— 否则换台机器就跑不了。
# 若确实想指定别的解释器，设环境变量 WIN_GLASS_PY 即可。
PY = os.environ.get("WIN_GLASS_PY") or sys.executable
ICON = os.path.join(HERE, "icon.ico")
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")
SPEC = os.path.join(BUILD, "spec")
VER = "1.1.0"
SETUP_NAME = "win_glass_setup_v%s" % VER

VERSION_FILE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 1, 0, 0),
    prodvers=(1, 1, 0, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404B0', [
        StringStruct('CompanyName', 'Yachiyo'),
        StringStruct('FileDescription', 'win_glass - window focus transparency'),
        StringStruct('FileVersion', '1.0.1.0'),
        StringStruct('InternalName', 'win_glass'),
        StringStruct('OriginalFilename', 'win_glass.exe'),
        StringStruct('ProductName', 'win_glass'),
        StringStruct('ProductVersion', '1.1.0.0'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def run(cmd, title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    t0 = time.time()
    r = subprocess.run(cmd, cwd=HERE)
    print("-> 退出码 %s  用时 %.1fs" % (r.returncode, time.time() - t0))
    return r.returncode


def build_client(name, windowed, work):
    mode = "--noconsole" if windowed else "--console"
    rc = run([
        PY, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", mode, "--noupx",
        "--name", name,
        "--icon", ICON,
        "--version-file", os.path.join(BUILD, "version_info.txt"),
        "--distpath", DIST,
        "--workpath", os.path.join(BUILD, work),
        "--specpath", SPEC,
        os.path.join(HERE, "win_glass.py"),
    ], "打包 %s（%s）" % (name, "窗口化+托盘" if windowed else "控制台诊断"))
    return rc


def main():
    for d in (DIST, BUILD):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(SPEC, exist_ok=True)

    vf = os.path.join(BUILD, "version_info.txt")
    with open(vf, "w", encoding="utf-8") as f:
        f.write(VERSION_FILE)

    # 1) 窗口化主程序：无控制台窗口，靠系统托盘交互
    if build_client("win_glass", True, "client") != 0:
        print("窗口化主程序打包失败。")
        return 1
    # 2) 控制台诊断版：--list / --verbose 等需要看输出的场合
    if build_client("win_glass-console", False, "client_console") != 0:
        print("控制台版打包失败。")
        return 1

    client = os.path.join(DIST, "win_glass.exe")
    console = os.path.join(DIST, "win_glass-console.exe")
    for p in (client, console):
        if not os.path.isfile(p):
            print("未找到 %s" % p)
            return 3

    # 3) 安装包（把两个 exe + 图标嵌进去）
    rc = run([
        PY, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--console", "--noupx",
        "--name", SETUP_NAME,
        "--icon", ICON,
        "--version-file", vf,
        "--add-data", client + os.pathsep + ".",
        "--add-data", console + os.pathsep + ".",
        "--add-data", ICON + os.pathsep + ".",
        "--distpath", DIST,
        "--workpath", os.path.join(BUILD, "setup"),
        "--specpath", SPEC,
        os.path.join(HERE, "installer.py"),
    ], "步骤 3/3：打包安装包 %s.exe" % SETUP_NAME)
    if rc != 0:
        print("安装包打包失败。")
        return rc

    setup = os.path.join(DIST, SETUP_NAME + ".exe")
    print("\n" + "=" * 70)
    print("打包完成（目标平台 Windows x64）")
    print("=" * 70)
    for p in (client, console, setup):
        if os.path.isfile(p):
            print("  %-40s %7.2f MB" % (os.path.basename(p), os.path.getsize(p) / 1048576.0))
            print("      %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
