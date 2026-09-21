# -*- coding: utf-8 -*-
"""
hover_live_test.py — 「悬停半透明」在**真实桌面 + 真实光标**上的验证（零副作用）

为什么单独写这么一个：
  e2e_test.py 会真的去改窗口透明度，而本机可能已经在跑一个 win_glass 实例
  （托盘那个）。两个引擎同时管理同一批窗口会互相抢写，测出来必然抖。
  悬停逻辑里真正"新"的部分是**判定**：光标底下是哪个窗口、该给什么值。
  判定层完全不碰 Win32 的写接口，所以可以在真实桌面上安全地跑：

      scan_windows()        真实枚举受管窗口
      cursor_root_window()  真实光标位置 → 顶层窗口
      _poll_hover()         真实轮询 + 节流 + 光标缓存
      _update_targets()     真实目标判定（只写内存里的 dst / src / t0）

  ⚠️ 关键隔离：**动画（_tick）只在假 HWND 上跑**。
  _tick 会为每个 cur≠dst 的窗口调 _apply_alpha —— 若把它跑在真实窗口上，
  就会真的改用户窗口的透明度。所以这里用第二个引擎，states 里只放假句柄
  （IsWindow() 返回 false → _apply_alpha 提前退出，一个 API 都不调），
  但 cur 照样按 smoothstep 推进，曲线形状可以照量。

  最后由一个「写接口计数器」兜底证明：整轮跑下来
  SetLayeredWindowAttributes / SetWindowLongPtr 的调用次数必须为 0。

覆盖（v1.4.0）
  A  真实光标 → 顶层窗口（cursor_pos / cursor_root_window 可复现）
  B  悬停判定：谁参与、谁不参与
  B2 真实窗口 + 真实光标：未聚焦被悬停 / 移出回落 / 焦点优先
  C  --move-cursor：临时把光标挪到未聚焦窗口中心（跑完精确还原）
  D  缓动曲线（假 HWND，零 API 写入）
  E  快速切换悬停目标不跳变
  G  真实窗口的状态判定链：全屏 > 聚焦 > 最大化 > 置顶 > 悬停 > 未聚焦
  H  零副作用兜底（写接口调用次数必须为 0）

用法
  python hover_live_test.py                只读光标（不动它）
  python hover_live_test.py --move-cursor  临时把光标移到某个未聚焦窗口中心，
                                           跑完精确还原（用来验证"悬停进去 → 提亮"）
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win_glass as wg                                     # noqa: E402

PASS, FAIL, SKIP = [], [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("   " + detail if detail else ""))


def skip(name, why=""):
    SKIP.append(name)
    print("  [SKIP] " + name + ("   " + why if why else ""))


INACT, ACT = 40, 100
HOVER = 70                       # (40+100)/2


def new_cfg():
    return wg.GlassConfig(inactive_alpha=INACT / 100.0, active_alpha=ACT / 100.0,
                          cfg_path="")


def real_engine(cfg):
    """只判不改的引擎：states 手工填真实窗口，绝不调 _refresh_window_list。

    _refresh_window_list / _adopt 会真的写 alpha（新窗口直接设为目标值），
    而这里要的是零副作用，所以自己用 WinState 铺状态。
    """
    eng = wg.GlassEngine(cfg)
    for hwnd in wg.scan_windows(cfg, os.getpid()):
        st = wg.WinState(hwnd)
        st.title = wg._window_text(hwnd)
        st.cls = wg._class_name(hwnd)
        st.cur = st.src = st.dst = cfg.inactive_alpha
        eng.states[hwnd] = st
    return eng


def fake_engine(cfg, handles):
    """动画专用引擎：states 里只有假句柄，_tick 绝不可能碰到真实窗口。"""
    eng = wg.GlassEngine(cfg)
    for h in handles:
        st = wg.WinState(h)
        st.title, st.cls = "fake", "fake"
        st.cur = st.src = st.dst = cfg.inactive_alpha
        eng.states[h] = st
    return eng


print("=" * 74)
print("悬停半透明 · 真实桌面判定层验证（不写任何窗口透明度）")
print("=" * 74)

MOVE = "--move-cursor" in sys.argv
real_setalpha = wg.user32.SetLayeredWindowAttributes
real_setlong = wg._SetWindowLong
writes = {"alpha": 0, "exstyle": 0}


def guard_alpha(*a, **k):
    writes["alpha"] += 1
    return real_setalpha(*a, **k)


def guard_long(*a, **k):
    writes["exstyle"] += 1
    return real_setlong(*a, **k)


wg.user32.SetLayeredWindowAttributes = guard_alpha
wg._SetWindowLong = guard_long

orig_pos = wg.cursor_pos()
print("\n起始光标 = %s" % (orig_pos,))

try:
    cfg = new_cfg()
    eng = real_engine(cfg)
    print("受管窗口 %d 个：悬停值 = %d%%（最高 %d%% / 最低 %d%% 的中点）"
          % (len(eng.states), cfg.hover_pct, cfg.active_pct, cfg.inactive_pct))
    for hwnd, st in eng.states.items():
        print("   0x%08X  %-30s %s" % (hwnd, st.cls[:30], st.title[:40]))

    # ---------------- 1. 真实光标下的窗口 ----------------
    print("\nA. 真实光标 → 顶层窗口（cursor_pos / cursor_root_window）")
    eng._poll_hover(time.perf_counter())
    print("   光标=%s  悬停目标=0x%08X" % (wg.cursor_pos(), eng._hover_hwnd))
    root_direct = wg.cursor_root_window()
    check("cursor_root_window() 与轮询结果一致（判定可复现）",
          root_direct == eng._hover_hwnd
          or (root_direct not in eng.states and eng._hover_hwnd == 0),
          "direct=0x%08X polled=0x%08X" % (root_direct, eng._hover_hwnd))

    # ---------------- 2. 目标判定（只写内存） ----------------
    print("\nB. 目标判定：谁被悬停、谁不参与")
    eng._update_targets()
    fg = wg._h(wg.user32.GetForegroundWindow())
    hovered = [h for h, st in eng.states.items() if st.hover]
    check("同一时刻最多一个窗口处于悬停态（鼠标只有一个点）",
          len(hovered) <= 1, "实际 %d 个" % len(hovered))

    if eng._hover_hwnd and eng._hover_hwnd in eng.states:
        h = eng._hover_hwnd
        st = eng.states[h]
        if h == fg:
            # 光标正好压在焦点窗口上：这是"焦点窗口不受影响"的现成样本
            check("光标压在**焦点**窗口上 → 仍是最高值（焦点不受悬停影响）",
                  abs(st.dst - ACT / 100.0) < 1e-9 and not st.hover,
                  "dst=%.0f%% hover=%s" % (st.dst * 100, st.hover))
            skip("未聚焦窗口被悬停 → 提亮到 %d%%" % HOVER,
                 "光标此刻压在焦点窗口上；见下方 B2（会强制覆盖这一分支）")
        else:
            check("未聚焦窗口被悬停 → 目标值 = 中点 %d%%" % HOVER,
                  abs(st.dst - HOVER / 100.0) < 1e-9 and st.hover,
                  "0x%08X dst=%.0f%% hover=%s" % (h, st.dst * 100, st.hover))
            check("被悬停窗口必定不是焦点/置顶（优先级正确）",
                  not (st.is_fg or st.topmost))
    else:
        skip("光标所在窗口的悬停判定", "光标不在任何受管窗口上")

    others = [h for h, st in eng.states.items()
              if not st.hover and not st.is_fg and not st.topmost]
    bad = [(hex(h), round(eng.states[h].dst * 100)) for h in others]
    check("其余未聚焦窗口保持最低值 %d%%（悬停不波及别的窗口）" % INACT,
          all(v == INACT for _h, v in bad), "异常 %r" % [b for b in bad if b[1] != INACT][:3])
    bad2 = [(hex(h), round(st.dst * 100)) for h, st in eng.states.items()
            if (st.is_fg or st.topmost)]
    check("焦点/置顶窗口恒为最高值（悬停绝不压暗它们）",
          all(v == ACT for _h, v in bad2),
          "异常 %r" % [b for b in bad2 if b[1] != ACT][:3])

    # ---------------- 2b. 真实窗口 + 真实光标：补齐剩下两个分支 ----------------
    # 上一步受限于"光标此刻正好压在焦点窗口上"，拿不到「未聚焦被悬停」的真实样本。
    # 这里**只把焦点来源 / 悬停来源打桩**，窗口与光标都是真的：
    #   · 假装没有焦点窗口 → 光标下那个真实窗口就成了"未聚焦"
    #   · 假装光标移开       → 悬停清空
    # 全程仍然一个 alpha 都不写（F 段有计数器兜底）。
    print("\nB2. 真实窗口 + 真实光标：未聚焦被悬停 / 移出回落（只打桩来源）")
    hover_hwnd = eng._hover_hwnd
    if hover_hwnd and hover_hwnd in eng.states:
        real_fg = wg.user32.GetForegroundWindow
        real_root = wg.cursor_root_window

        def probe():
            """绕过 50ms 节流强制采一次，避免"打了桩却没被采样到"。"""
            eng._hover_cursor = None
            eng._hover_at = 0.0
            eng._poll_hover(time.perf_counter())
            eng._update_targets()

        try:
            wg.user32.GetForegroundWindow = lambda: 0        # 假装"没有焦点窗口"
            probe()
            st = eng.states[hover_hwnd]
            check("真实窗口 + 真实光标：未聚焦窗口被悬停 → 目标 = 中点 %d%%" % HOVER,
                  eng._hover_hwnd == hover_hwnd
                  and abs(st.dst - HOVER / 100.0) < 1e-9 and st.hover,
                  "0x%08X dst=%.0f%% hover=%s" % (hover_hwnd, st.dst * 100, st.hover))
            check("  其余未聚焦窗口仍是 %d%%（悬停只作用于光标下那一个）" % INACT,
                  all(abs(s.dst - INACT / 100.0) < 1e-9
                      for h, s in eng.states.items()
                      if h != hover_hwnd and not s.topmost))
            # 假装光标移开 → 悬停清空 → 回落
            wg.cursor_root_window = lambda: 0
            probe()
            check("  悬停来源消失（光标移出）→ 该窗口回落最低值 %d%%" % INACT,
                  eng._hover_hwnd == 0
                  and abs(eng.states[hover_hwnd].dst - INACT / 100.0) < 1e-9
                  and not eng.states[hover_hwnd].hover,
                  "dst=%.0f%%" % (eng.states[hover_hwnd].dst * 100))
        finally:
            wg.user32.GetForegroundWindow = real_fg
            wg.cursor_root_window = real_root
        # 恢复真实来源后，它应当立刻回到"焦点窗口 = 最高值"
        probe()
        st = eng.states[hover_hwnd]
        check("恢复真实焦点来源后回到最高值 %d%%（焦点优先于悬停）" % ACT,
              abs(st.dst - ACT / 100.0) < 1e-9 and not st.hover,
              "dst=%.0f%%" % (st.dst * 100))
    else:
        skip("真实窗口上的「未聚焦被悬停」分支", "光标不在任何受管窗口上")

    # ---------------- 3. --move-cursor：真的把光标挪过去 ----------------
    if MOVE and eng.states and orig_pos is not None:
        print("\nC. 移动光标到未聚焦窗口中心（跑完精确还原）")
        target = next((h for h, st in eng.states.items()
                       if h != fg and not st.topmost), None)
        if target is None:
            skip("光标移入未聚焦窗口 → 目标变 %d%%" % HOVER, "没有可用的未聚焦窗口")
        else:
            rc = wt.RECT()
            wg.user32.GetWindowRect(target, ctypes.byref(rc))
            cx, cy = (rc.left + rc.right) // 2, (rc.top + rc.bottom) // 2
            print("   目标 0x%08X「%s」→ 光标移到 (%d,%d)"
                  % (target, eng.states[target].title[:30], cx, cy))
            wg.user32.SetCursorPos(cx, cy)
            time.sleep(0.12)
            eng._hover_cursor = None
            eng._poll_hover(time.perf_counter())
            eng._update_targets()
            st = eng.states[target]
            check("光标移入未聚焦窗口 → 该窗口目标变为 %d%%" % HOVER,
                  eng._hover_hwnd == target and abs(st.dst - HOVER / 100.0) < 1e-9,
                  "hover=0x%08X dst=%.0f%%" % (eng._hover_hwnd, st.dst * 100))
            check("  该窗口被标记为悬停态", st.hover)
            check("  其它未聚焦窗口不受影响",
                  all(abs(s.dst - INACT / 100.0) < 1e-9
                      for h, s in eng.states.items()
                      if h != target and not s.is_fg and not s.topmost))
            check("  焦点/置顶窗口仍不受影响",
                  all(abs(s.dst - ACT / 100.0) < 1e-9
                      for s in eng.states.values() if s.is_fg or s.topmost))

            wg.user32.SetCursorPos(orig_pos[0], orig_pos[1])
            time.sleep(0.12)
            eng._hover_cursor = None
            eng._poll_hover(time.perf_counter())
            eng._update_targets()
            check("光标移出后回落最低值 %d%%（移入/移出都走同一套平滑过渡）" % INACT,
                  abs(eng.states[target].dst - INACT / 100.0) < 1e-9
                  and not eng.states[target].hover,
                  "dst=%.0f%%" % (eng.states[target].dst * 100))

    # ---------------- 4. 缓动曲线（假 HWND，纯内存） ----------------
    print("\nD. 缓动：从当前值平滑过渡到悬停值（**只在假 HWND 上跑**，零 API 写入）")
    fake = 0xDEAD0001
    fe = fake_engine(cfg, [fake])
    fe.cfg.fade_ms = 300
    fst = fe.states[fake]
    fe._set_target(fst, HOVER / 100.0, "悬停")
    check("起终点正确（40% → 70%）",
          abs(fst.src - 0.40) < 1e-9 and abs(fst.dst - 0.70) < 1e-9,
          "%.2f -> %.2f" % (fst.src, fst.dst))
    samples = []
    for i in range(1, 16):
        fe._tick(fst.t0 + i * 0.02)
        samples.append(round(fst.cur * 100, 1))
    print("   cur 采样（每 20ms，共 300ms）：%s" % samples)
    check("过程单调递增、无跳变",
          all(samples[i] <= samples[i + 1] + 1e-9 for i in range(len(samples) - 1)),
          str(samples))
    check("确实经过了中间值（不是一步到位）",
          any(41.0 < s < 69.0 for s in samples), str(samples))
    check("到达 70% 并在之后保持", abs(fst.cur - 0.70) < 1e-6, "%.4f" % fst.cur)
    if len(samples) >= 12:
        head = [round(samples[i + 1] - samples[i], 1) for i in range(2)]
        mid = [round(samples[i + 1] - samples[i], 1)
               for i in range(6, 8)]
        check("两端步长小于中段（smoothstep 的 ease-in-out 特征）",
              max(head) <= max(mid) + 1e-9,
              "起始步长=%s  中段步长=%s" % (head, mid))

    # ---------------- 5. 快速切换悬停目标 ----------------
    print("\nE. 快速在多窗口之间切换悬停目标（动画中途改目标不跳回）")
    fa, fb = 0xDEAD0002, 0xDEAD0003
    fe2 = fake_engine(cfg, [fa, fb])
    fe2.cfg.fade_ms = 300
    jumps, ok_src = [], True
    # 悬停 A → 走了 1/3 就切到 B → 再切回 A → 最后离开（目标清空）
    plan = [fa, fb, fa, 0]
    for tgt_hwnd in plan:
        for h in (fa, fb):
            s = fe2.states[h]
            tgt, _why, _hv = wg.target_for(cfg, h, hover_hwnd=tgt_hwnd)
            before, old_dst = s.cur, s.dst
            fe2._set_target(s, tgt, "悬停")
            # 只有**确实起了新一段动画**时才要求 src == 当前值。
            # 目标没变时 _set_target 会提前返回，此时 src 是上一段的旧值，
            # 拿它跟 cur 比会假失败 —— 第一版测试就踩了这个。
            if abs(s.dst - old_dst) > 1e-9 and abs(s.src - before) > 1e-9:
                ok_src = False
                jumps.append((hex(h), round(before, 3), round(s.src, 3)))
        fe2._tick(fe2.states[fa].t0 + 0.1)          # 推进 100ms（时长 300ms）
        for h in (fa, fb):
            fe2.states[h].t0 -= 0.1                 # 让下一轮仍处于"动画中途"
    check("每次改目标都以**当前值**为新起点（不跳回旧起点/旧终点）", ok_src,
          "异常 %r" % jumps[:3])
    check("A、B 最终都回到基础值 40%（离开后不留残留）",
          all(abs(fe2.states[h].dst - INACT / 100.0) < 1e-9 for h in (fa, fb)),
          "A=%.0f%% B=%.0f%%" % (fe2.states[fa].dst * 100, fe2.states[fb].dst * 100))
    curv = fe2.states[fa].cur
    check("A 的当前值仍是动画中的中间态（说明是连续曲线而非瞬跳）",
          INACT / 100.0 - 1e-9 <= curv <= HOVER / 100.0 + 1e-9,
          "cur=%.1f%%" % (curv * 100))

    # ---------------- 6. 状态判定表（真实窗口，v1.4.0） ----------------
    # 直接在**真实窗口**上核对「全屏恒定 100% / 最大化+置顶=聚焦值 / 悬停 / 未聚焦」
    # 这条优先级链。期望值用独立算式算（不复用 target_for），避免同义反复。
    print("\nG. 真实窗口的状态判定链（全屏 > 聚焦 > 最大化 > 置顶 > 悬停 > 未聚焦）")
    print("   %-10s %-4s %-9s %-8s %s" % ("HWND", "FZT", "实际目标", "理由", "标题"))
    bad = []
    nz = nf = 0
    seen_flags = []
    for hwnd in wg.scan_windows(cfg, os.getpid()):
        hst = wg.WinState(hwnd)
        hst.title, hst.cls = wg._window_text(hwnd), wg._class_name(hwnd)
        hst.cur = hst.src = hst.dst = cfg.inactive_alpha
        eng.states.setdefault(hwnd, hst)
        top, zoomed, fs = wg.read_window_state(hwnd, hst)
        is_fg = (hwnd == fg)
        alpha, why, _hv = wg.target_for(cfg, hwnd, is_fg=is_fg, top=top,
                                        zoomed=zoomed, fullscreen=fs,
                                        hover_hwnd=eng._hover_hwnd)
        # 独立期望值（不复用被测函数的分支顺序，只按文档表格手算）
        if fs:
            exp, exp_why = 1.0, "全屏"
        elif is_fg:
            exp, exp_why = ACT / 100.0, "聚焦"
        elif zoomed:
            exp, exp_why = ACT / 100.0, "最大化"
        elif top:
            exp, exp_why = ACT / 100.0, "置顶"
        elif eng._hover_hwnd == hwnd:
            exp, exp_why = cfg.hover_alpha, "悬停"
        else:
            exp, exp_why = INACT / 100.0, "未聚焦"
        flags = "".join(("F" if fs else "-", "Z" if zoomed else "-",
                         "T" if top else "-"))
        seen_flags.append((flags, why, round(alpha * 100)))
        nz += 1 if zoomed else 0
        nf += 1 if fs else 0
        print("   %-10s %-4s %-9s %-8s %s"
              % ("0x%08X" % hwnd, flags, "%.0f%%" % (alpha * 100), why,
                 hst.title[:34]))
        if abs(alpha - exp) > 1e-9 or why != exp_why:
            bad.append((hex(hwnd), flags, round(alpha * 100), why,
                        round(exp * 100), exp_why))
    check("每个真实窗口的目标值/理由都与规则表一致", not bad, "异常 %r" % bad[:4])
    # ⭐ v1.4.1 回归：最大化与全屏是**互斥**的两个状态。
    #   病根——最大化窗口矩形会越出屏幕 8px，零容差的"矩形包含"判定于是恒成立，
    #   最大化被误判成全屏 → 锁定 100%，用户设的最高透明度失效。实测证据见 fs_probe.py。
    check("⭐ 没有任何窗口同时被判为「最大化」和「全屏」（F 与 Z 互斥）",
          not any((f[0] == "F" and f[1] == "Z") for f in seen_flags),
          "本机 最大化=%d 全屏=%d 个窗口" % (nz, nf))
    check("⭐ 被判为最大化的窗口目标是**用户设的最高值** %d%%（不是写死的 100%%）" % ACT,
          all(pct == ACT for _f, why, pct in seen_flags if why == "最大化"),
          "（本机无最大化窗口时本条为空真）")
    check("全屏窗口（若有）目标恒为 100%，与「最高值设置」无关",
          all(abs(wg.target_for(cfg, h, fullscreen=True)[0] - 1.0) < 1e-9
              for h in eng.states))
    # 用"把最高值压到 50%"再算一遍：全屏仍是 100%，最大化/置顶/聚焦跟着变 50%
    lo_cfg = wg.GlassConfig(inactive_alpha=INACT / 100.0, active_alpha=0.50,
                            cfg_path="")
    check("最高值=50% 时：全屏仍 100%，而最大化/置顶/聚焦都变 50%",
          wg.target_for(lo_cfg, 1, fullscreen=True)[0] == 1.0
          and wg.target_for(lo_cfg, 1, zoomed=True)[0] == 0.50
          and wg.target_for(lo_cfg, 1, top=True)[0] == 0.50
          and wg.target_for(lo_cfg, 1, is_fg=True)[0] == 0.50)

    # ---------------- 7. 零副作用兜底 ----------------
    print("\nH. 零副作用兜底")
    check("整轮验证中 SetLayeredWindowAttributes 调用次数 = 0",
          writes["alpha"] == 0, "实际 %d 次" % writes["alpha"])
    check("整轮验证中 SetWindowLongPtr(GWL_EXSTYLE) 调用次数 = 0",
          writes["exstyle"] == 0, "实际 %d 次" % writes["exstyle"])
finally:
    wg.user32.SetLayeredWindowAttributes = real_setalpha
    wg._SetWindowLong = real_setlong
    if MOVE and orig_pos is not None:
        wg.user32.SetCursorPos(orig_pos[0], orig_pos[1])
        print("\n光标已还原：目标 %s / 当前 %s" % (orig_pos, wg.cursor_pos()))

print("\n" + "=" * 74)
print("通过 %d 项，失败 %d 项，跳过 %d 项" % (len(PASS), len(FAIL), len(SKIP)))
for f in FAIL:
    print("  FAILED: %s" % f)
for s in SKIP:
    print("  SKIPPED: %s" % s)
print("=" * 74)
sys.exit(1 if FAIL else 0)
