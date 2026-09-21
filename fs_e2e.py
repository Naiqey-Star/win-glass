# -*- coding: utf-8 -*-
"""端到端取证：让**打包好的** win_glass-console.exe 去给真实窗口分类。

自建一个 tkinter 窗口，先最大化再全屏，每种状态下调用打包产物 `--list`，
从它的输出里找出这个窗口那一行，核对标记（F/Z）与目标值。

这是对"判定层真的修好了"最直接的证据 —— 走的是发布出去的那个 exe。
"""
import ctypes
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dist", "win_glass-console.exe")
GA_ROOT = 2


def settle(root, sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def list_windows(active="80", inactive="40"):
    cmd = [EXE, "--list", "--no-config",
           "--active-alpha", active, "--inactive-alpha", inactive]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    out = r.stdout.decode("utf-8", "replace")
    return r.returncode, out


def find_line(out, hwnd):
    """从 --list 的表里挑出指定 HWND 那一行。"""
    pat = re.compile(r"^0x%08X\s+(.*)$" % hwnd, re.M)
    m = pat.search(out)
    return m.group(1).strip() if m else None


def main():
    if not os.path.isfile(EXE):
        print("找不到 %s，先跑 build.py" % EXE)
        return 1
    try:
        import tkinter as tk
    except Exception as e:
        print("需要 tkinter：%s" % e)
        return 1

    root = tk.Tk()
    root.title("win_glass fs e2e")
    root.geometry("520x320+140+140")
    tk.Label(root, text="fs_e2e", font=("Microsoft YaHei", 16)).pack(expand=True)
    settle(root)

    hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), GA_ROOT)
    print("=" * 78)
    print("受测 exe : %s" % EXE)
    print("测试窗口 : HWND=0x%08X" % hwnd)
    print("配置     : 最高（聚焦/最大化/置顶）=80%  最低=40%  全屏恒=100%")
    print("=" * 78)

    results = []

    def current_hwnd():
        # ⚠️ Tk 切到 -fullscreen 时会**重建顶层窗口**（HWND 变了），
        #    所以每一段都必须重新取一次，不能用开头那个句柄去找行。
        return ctypes.windll.user32.GetAncestor(root.winfo_id(), GA_ROOT)

    def stage(label, setup):
        setup()
        settle(root)
        h = current_hwnd()
        rc, out = list_windows()
        line = find_line(out, h)
        results.append((label, rc, line, h))
        print("\n[%s]  HWND=0x%08X" % (label, h))
        print("  返回码 %d" % rc)
        for ln in out.splitlines():
            if ln.startswith("判定优先级") or ln.startswith("可管理窗口") \
                    or ln.startswith("标记 F="):
                print("  | %s" % ln)
        print("  → 本窗口那一行: %s" % line)

    stage("A. 普通窗口", lambda: None)
    stage("B. 最大化", lambda: root.state("zoomed"))
    stage("C. 真全屏", lambda: (root.state("normal"), settle(root, 0.3),
                             root.attributes("-fullscreen", True)))
    stage("D. 全屏退回普通", lambda: root.attributes("-fullscreen", False))

    root.destroy()

    print("\n" + "=" * 78)
    print("判定")
    print("=" * 78)
    # 说明：这个测试窗口自己是焦点窗口，所以「聚焦」会盖过「最大化」——
    # 两者都用同一个「最高透明度」80%，所以**不影响**对 80% 的断言，
    # 而"绝不能是 100%"这条正是用户看到的现象，与焦点无关。
    ok = True

    def expect(label, *, has=(), not_has=(), pcts=(), none_ok=False):
        nonlocal ok
        row = dict((l, (rc, ln)) for l, rc, ln, _h in results)[label]
        rc, ln = row
        if ln is None:
            good = none_ok
        else:
            good = (rc == 0
                    and all(t in ln for t in has)
                    and not any(t in ln for t in not_has)
                    and any(p in ln for p in pcts))
        print("  [%s] %-16s → %s" % ("PASS" if good else "FAIL", label, ln))
        if not good:
            print("         期望：含 %r，不含 %r，百分比 ∈ %r" % (has, not_has, pcts))
            ok = False

    def flags_of(label):
        """从 --list 的表行里把 FZT 标记列抠出来。

        行格式：`<目标>  <理由>  <FZT>  <类名>  <标题>`
        —— 按位置切容易错，改成"找类名前面那个 token"，最稳。
        （踩过：用 `(\\S{3})\\s+\\S` 会先匹到 `80%`，把百分比当成标记列。）
        """
        ln = dict((l, ln) for l, _rc, ln, _h in results)[label] or ""
        toks = ln.split()
        for i, t in enumerate(toks):
            if t == "TkTopLevel":
                return toks[i - 1] if i else ""
        return "?"

    expect("A. 普通窗口", has=["%"], not_has=["F", "100%"], pcts=["80%", "40%"])
    # ⭐ 核心回归：最大化窗口标记 Z、**不是** F、目标是用户设的 80% 而不是 100%
    expect("B. 最大化", has=["80%", "Z"], not_has=["100%"], pcts=["80%"])
    expect("C. 真全屏", has=["100%", "F"], pcts=["100%"])
    expect("D. 全屏退回普通", not_has=["F", "100%"], pcts=["80%", "40%"])

    fa = flags_of("A. 普通窗口")
    fb = flags_of("B. 最大化")
    fc = flags_of("C. 真全屏")
    fd = flags_of("D. 全屏退回普通")
    print("\n  标记链：普通=%s  最大化=%s  全屏=%s  退回=%s" % (fa, fb, fc, fd))

    def chk(name, cond, detail=""):
        nonlocal ok
        print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                              ("   " + detail) if detail else ""))
        if not cond:
            ok = False

    chk("⭐ 最大化时 Z 置位、F 不置位（两个状态确实独立）",
        "Z" in fb and "F" not in fb, "maximize flags=%r" % fb)
    chk("⭐ 全屏时 F 置位、Z 不置位",
        "F" in fc and "Z" not in fc, "fullscreen flags=%r" % fc)
    chk("⭐ 任何一段都不会 F 与 Z 同时出现", not any("F" in f and "Z" in f
                                                for f in (fa, fb, fc, fd)))
    chk("退回普通后 Z/F 都不再置位", "Z" not in fd and "F" not in fd)

    print("\n结论：%s" % ("打包产物判定正确 ✅" if ok else "存在不符合项 ❌"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
