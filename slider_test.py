# -*- coding: utf-8 -*-
"""
slider_test.py — win_glass 托盘菜单滑块的自动化测试

覆盖四层：
  A. 取值层   —— 量化/夹紧：永远是整数百分比，永远不会出现小数点
  B. 映射层   —— 鼠标 x 坐标 -> 百分比，1% 步进、两端可达
  C. 绘制层   —— 真画一遍，再用 GetPixel 反查填充边界是否等于设定值
  D. 持久层   —— config.json 往返，以及 --no-config 真的不落盘

绘制层是关键：它验证的不是「函数没抛异常」，而是「画出来的东西对不对」。
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import tempfile
from ctypes import byref

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win_glass as wg                                    # noqa: E402

gdi32 = wg.gdi32

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.GetPixel.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = wt.DWORD
gdi32.DeleteDC.argtypes = [wt.HDC]
wg.user32.GetDC.argtypes = [wt.HWND]
wg.user32.GetDC.restype = wt.HDC
wg.user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
wg.user32.ReleaseDC.restype = ctypes.c_int

W, H = wg.SLIDER_ITEM_W, wg.SLIDER_ITEM_H

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("   " + detail if detail else ""))


# ---------------------------------------------------------------- A. 取值层
def test_quantize():
    print("\nA. 取值层：整数百分比 + 范围夹紧")
    for raw, exp in [(0.40, 40), (0.4, 40), (40, 40), (0.05, 5), (1.00, 95),
                     (0.0, 5), (-3, 5)]:
        c = wg.GlassConfig(inactive_alpha=raw)
        check("非聚焦 %r -> %d%%" % (raw, exp), c.inactive_pct == exp,
              "实际 %d%%" % c.inactive_pct)

    # 非聚焦上限是 95%
    c = wg.GlassConfig(inactive_alpha=1.00)
    check("非聚焦 100% 被夹到 95%", c.inactive_pct == 95, "实际 %d%%" % c.inactive_pct)
    c = wg.GlassConfig(inactive_alpha=0.956)
    check("非聚焦 95.6% 被夹到 95%", c.inactive_pct == 95, "实际 %d%%" % c.inactive_pct)
    c.inactive_pct = 99
    check("非聚焦赋值 99 -> 95", c.inactive_pct == 95)

    # 聚焦上限是 100%
    for raw, exp in [(1.00, 100), (0.95, 95), (0.5, 50), (100, 100), (0, 5)]:
        c = wg.GlassConfig(active_alpha=raw)
        check("聚焦 %r -> %d%%" % (raw, exp), c.active_pct == exp,
              "实际 %d%%" % c.active_pct)
    c = wg.GlassConfig()
    c.active_pct = 250
    check("聚焦赋值 250 -> 100", c.active_pct == 100)

    # 整数性：随机扫一遍，断言 str() 里没有小数点
    bad = []
    c = wg.GlassConfig()
    for i in range(-20, 140):
        c.inactive_pct = i
        if "." in str(c.inactive_pct):
            bad.append(("inactive", i, c.inactive_pct))
        c.active_pct = i
        if "." in str(c.active_pct):
            bad.append(("active", i, c.active_pct))
    check("扫 -20..139 全程无小数", not bad, repr(bad[:4]))

    # alpha 属性是 0..1 的精确两位小数
    c = wg.GlassConfig(inactive_alpha=0.37, active_alpha=0.82)
    check("alpha 精度 inactive=0.37", abs(c.inactive_alpha - 0.37) < 1e-9)
    check("alpha 精度 active=0.82", abs(c.active_alpha - 0.82) < 1e-9)

    # 默认值
    c = wg.GlassConfig()
    check("默认 非聚焦=40% 聚焦=100%",
          c.inactive_pct == 40 and c.active_pct == 100,
          "实际 %d%% / %d%%" % (c.inactive_pct, c.active_pct))


# ---------------------------------------------------------------- B. 映射层
def test_mapping():
    print("\nB. 映射层：鼠标 x -> 百分比（1% 步进、两端可达）")
    rc = wt.RECT(0, 0, W, H)
    x0 = SL = wg.SLIDER_PAD_X
    x1 = W - wg.SLIDER_PAD_X - 1

    sl = wg.MenuSlider(1, "t", 5, 95, lambda: 40, lambda v: None)
    check("最左 -> 5%", sl.hit_frac_to_pct(x0, rc) == 5,
          str(sl.hit_frac_to_pct(x0, rc)))
    check("最右 -> 95%", sl.hit_frac_to_pct(x1, rc) == 95,
          str(sl.hit_frac_to_pct(x1, rc)))
    check("超出左边界仍夹到 5%", sl.hit_frac_to_pct(-999, rc) == 5)
    check("超出右边界仍夹到 95%", sl.hit_frac_to_pct(99999, rc) == 95)

    # 单调不减 & 覆盖全部取值 & 相邻 x 之间步进不超过 1%
    vals = [sl.hit_frac_to_pct(x, rc) for x in range(x0, x1 + 1)]
    check("单调不减", all(b >= a for a, b in zip(vals, vals[1:])))
    check("覆盖 5..95 全部取值", set(vals) == set(range(5, 96)),
          "缺 %s" % sorted(set(range(5, 96)) - set(vals))[:8])
    jumps = {b - a for a, b in zip(vals, vals[1:])}
    check("相邻采样步进 <= 1%", jumps <= {0, 1}, "出现步进 %s" % sorted(jumps))

    sl2 = wg.MenuSlider(1, "t", 5, 100, lambda: 100, lambda v: None)
    check("聚焦滑块 最右 -> 100%", sl2.hit_frac_to_pct(x1, rc) == 100,
          str(sl2.hit_frac_to_pct(x1, rc)))
    vals2 = [sl2.hit_frac_to_pct(x, rc) for x in range(x0, x1 + 1)]
    check("聚焦滑块 覆盖 5..100", set(vals2) == set(range(5, 101)))


# ---------------------------------------------------------------- C. 绘制层
def make_dc():
    """建一个屏幕兼容(32bpp)的离屏位图。

    坑：CreateCompatibleDC(NULL) 里默认是 1x1 的**单色**位图，
    再对它调 CreateCompatibleBitmap 会继承成 1bpp —— 于是所有颜色都塌成黑白，
    GetPixel 只能读回 0x000000/0xFFFFFF，看起来像「没画上去」。
    必须拿屏幕 DC 作为样板去建位图。
    """
    screen = wg.user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, W, H)
    wg.user32.ReleaseDC(None, screen)
    gdi32.SelectObject(dc, bmp)
    return dc, bmp


def draw_to(dc, label, lo, hi, pct, state=0):
    dis = wg.DRAWITEMSTRUCT()
    dis.CtlType = wg.ODT_MENU
    dis.CtlID = 0
    dis.itemID = wg.CMD_SLIDE_INACTIVE
    dis.itemAction = 0
    dis.itemState = state
    dis.hwndItem = None
    dis.hDC = dc
    dis.rcItem = wt.RECT(0, 0, W, H)
    dis.itemData = None
    wg.draw_menu_slider(dis, label, lo, hi, pct)


def sample_bar_y():
    """分段条的垂直中线。"""
    return 3 + wg.SLIDER_TITLE_H + 3 + wg.SLIDER_BAR_H // 2


def scan_bar(dc):
    """扫描分段条，返回 (每像素颜色列表, 起点 x, 宽度)。"""
    y = sample_bar_y()
    x0 = wg.SLIDER_PAD_X
    x1 = W - wg.SLIDER_PAD_X
    return [gdi32.GetPixel(dc, x, y) for x in range(x0, x1)], x0, x1 - x0


def runs_of(cols, color):
    """某颜色出现了几段（用来看是不是「分段」而不是一整条）。"""
    n, prev = 0, False
    for c in cols:
        cur = (c == color)
        if cur and not prev:
            n += 1
        prev = cur
    return n


def test_draw():
    print("\nC. 绘制层：真画一遍，再用 GetPixel 反查填充占比与分段数")
    y = sample_bar_y()
    check("采样行在条内", 0 < y < H, "y=%d" % y)

    dc, _ = make_dc()
    check("离屏位图是彩色(非单色)", gdi32.GetPixel(dc, 0, 0) != 0xFFFFFFFF)

    counts = []
    for pct in (5, 20, 40, 50, 67, 95):
        draw_to(dc, "非聚焦最低透明度", 5, 95, pct)
        cols, x0, span = scan_bar(dc)
        uniq = set(cols)
        check("pct=%d 至少画出两种颜色" % pct, len(uniq) >= 2,
              "颜色数=%d %s" % (len(uniq), [hex(c & 0xFFFFFF) for c in list(uniq)[:3]]))
        if len(uniq) < 2:
            continue
        # 核心不变量：亮起来的段数 == 该值对应的段数（每段正好 1%）
        nruns = runs_of(cols, cols[0])
        counts.append((pct, nruns))
        check("pct=%d 亮起段数 == %d" % (pct, pct - 5 + 1), nruns == pct - 5 + 1,
              "实测 %d 段" % nruns)

    check("亮起段数随数值单调增",
          all(a[1] <= b[1] for a, b in zip(counts, counts[1:])),
          str([c[1] for c in counts]))

    # 段总数必须等于可取值的个数——这就是「分段 = 步进 1%」的直接证据
    draw_to(dc, "非聚焦最低透明度", 5, 95, 95)
    cols, _, span = scan_bar(dc)
    check("非聚焦条共 91 段（= 95-5+1）", runs_of(cols, cols[0]) == 91,
          "实测 %d 段" % runs_of(cols, cols[0]))

    draw_to(dc, "聚焦最高透明度", 5, 100, 100)
    cols, _, span = scan_bar(dc)
    check("聚焦条共 96 段（= 100-5+1）", runs_of(cols, cols[0]) == 96,
          "实测 %d 段" % runs_of(cols, cols[0]))

    draw_to(dc, "聚焦最高透明度", 5, 100, 5)
    cols, _, span = scan_bar(dc)
    check("聚焦滑块 pct=5 只亮 1 段", runs_of(cols, cols[0]) == 1,
          "实测 %d 段" % runs_of(cols, cols[0]))
    n_fill = sum(1 for c in cols if c == cols[0])
    check("聚焦滑块 pct=5 填充像素很少", n_fill <= 6, "填充 %d 像素 / %d" % (n_fill, span))

    # 相邻段之间必须有 1px 分隔，否则就不是「段落式」而是一整条实心条
    draw_to(dc, "非聚焦最低透明度", 5, 95, 95)
    cols, _, _ = scan_bar(dc)
    gaps = sum(1 for a, b in zip(cols, cols[1:]) if a == cols[0] and a != b)
    check("pct=95 时 91 段各带 1px 分隔（共 91 处缝隙）", gaps == 91,
          "实测 %d 处 | 段数=%d" % (gaps, runs_of(cols, cols[0])))
    solid = sum(1 for i in range(len(cols) - 12)
                if len(set(cols[i:i + 12])) == 1)
    check("不存在长度 >= 12px 的实心段（确认是分段而非整条）", solid == 0,
          "发现 %d 处实心段" % solid)

    # 选中态 / 禁用态都要能画
    for state, name in ((wg.ODS_SELECTED, "选中态"), (wg.ODS_GRAYED, "禁用态")):
        try:
            draw_to(dc, "非聚焦最低透明度", 5, 95, 40, state)
            cols, _, _ = scan_bar(dc)
            check("%s 可绘制且有两种颜色" % name, len(set(cols)) >= 2)
        except Exception as e:
            check("%s 可绘制" % name, False, repr(e))

    gdi32.DeleteDC(dc)


# ---------------------------------------------------------------- D. 持久层
def test_persist():
    print("\nD. 持久层：config.json 往返 / --no-config 关闭")
    d = tempfile.mkdtemp(prefix="winglass_cfg_")
    p = os.path.join(d, "config.json")

    c = wg.GlassConfig(inactive_alpha=0.33, active_alpha=0.88, cfg_path=p)
    check("保存成功", c.save())
    check("文件已生成", os.path.isfile(p))
    raw = json.load(open(p, encoding="utf-8"))
    check("落盘的是整数百分比",
          raw.get("inactive_percent") == 33 and raw.get("active_percent") == 88,
          json.dumps(raw, ensure_ascii=False))

    loaded = wg.load_cfg_file(p)
    inactive, active = wg.GlassConfig.apply_saved(loaded, None, None)
    c2 = wg.GlassConfig(inactive_alpha=inactive, active_alpha=active, cfg_path=p)
    check("读回后取值一致 33/88",
          c2.inactive_pct == 33 and c2.active_pct == 88,
          "%d/%d" % (c2.inactive_pct, c2.active_pct))
    check("alpha 读回 0.33", abs(c2.inactive_alpha - 0.33) < 1e-9)

    # 命令行显式值优先于配置文件
    inactive, active = wg.GlassConfig.apply_saved(loaded, 0.5, None)
    check("命令行 0.5 覆盖配置 0.33，未给的沿用配置", inactive == 0.5 and active == 88,
          "%r/%r" % (inactive, active))
    c3 = wg.GlassConfig(inactive_alpha=inactive, active_alpha=active)
    check("合并后 50%/88%", c3.inactive_pct == 50 and c3.active_pct == 88,
          "%d/%d" % (c3.inactive_pct, c3.active_pct))

    # 坏文件 / 缺文件都退化
    open(p, "w").write("{ this is not json")
    check("坏 JSON 退化为空配置", wg.load_cfg_file(p) == {})
    check("不存在的文件退化为空配置", wg.load_cfg_file(os.path.join(d, "nope.json")) == {})
    check("path=None 走默认位置（不是空字典也不是崩）",
          isinstance(wg.load_cfg_file(None), dict))

    # ---- --no-config：把 CFG_PATH 指向临时文件，确认一个字都不写 ----
    real_cfg_path = wg.CFG_PATH
    probe = os.path.join(d, "should_not_exist.json")
    try:
        wg.CFG_PATH = probe
        c4 = wg.GlassConfig(cfg_path="")            # 等价于 --no-config
        check("cfg_path='' 时 save() 返回 False", c4.save() is False)
        eng = wg.GlassEngine(c4)
        eng.set_alpha_targets(inactive_pct=70)
        eng.save_cfg(force=True)
        check("--no-config 下改动仍在内存生效", c4.inactive_pct == 70)
        check("--no-config 下真的没写文件", not os.path.isfile(probe))
        check("--no-config 下 load_cfg_file('') 返回空", wg.load_cfg_file("") == {})

        # 反证：不关持久化时必须写
        c5 = wg.GlassConfig(cfg_path=None)          # None → 默认位置(=probe)
        eng5 = wg.GlassEngine(c5)
        eng5.set_alpha_targets(active_pct=77)
        eng5.save_cfg(force=True)
        check("开启持久化时会写出文件", os.path.isfile(probe))
        check("写出的值正确 40/77",
              wg.load_cfg_file(probe) == {"version": 1, "inactive_percent": 40,
                                          "active_percent": 77},
              json.dumps(wg.load_cfg_file(probe), ensure_ascii=False))
    finally:
        wg.CFG_PATH = real_cfg_path

    # 节流：连续多次调用不应每次都写盘
    calls = {"n": 0}
    real_save = wg.save_cfg_file

    def counting(d2, path=None):
        calls["n"] += 1
        return real_save(d2, path)

    try:
        wg.save_cfg_file = counting
        c6 = wg.GlassConfig(cfg_path=os.path.join(d, "throttle.json"))
        eng6 = wg.GlassEngine(c6)
        for v in range(50, 90):
            eng6.set_alpha_targets(inactive_pct=v)
        n_after = calls["n"]
        check("拖动 40 次被节流（写盘次数 < 40）", n_after < 40, "写盘 %d 次" % n_after)
        eng6.save_cfg(force=True)
        check("force 一定落盘", calls["n"] == n_after + 1)
        check("节流后最终值正确",
              wg.load_cfg_file(os.path.join(d, "throttle.json")).get("inactive_percent") == 89,
              json.dumps(wg.load_cfg_file(os.path.join(d, "throttle.json"))))
    finally:
        wg.save_cfg_file = real_save


def test_menu_input():
    """直接喂菜单消息给输入处理，验证滚轮/点击的解析。

    这里不弹真实菜单，只把 `_item_rect` 换成固定矩形，就能精确验证
    「消息里的哪个字段被当成滚轮增量」——之前就是这里读错了字段
    （从 wParam 取，拿到的是光标 y 坐标），导致滚轮完全不受控。
    """
    print("\nE. 菜单输入层：滚轮 / 点击的字段解析")
    cfg = wg.GlassConfig(cfg_path="")
    eng = wg.GlassEngine(cfg)
    tray = wg.TrayIcon(eng)

    state = {"v": 50}
    sl = wg.MenuSlider(wg.CMD_SLIDE_INACTIVE, "t", 5, 95,
                       lambda: state["v"], lambda v: state.__setitem__("v", v))
    sl.pos, sl.hmenu = 3, None
    tray._sliders = [sl]
    rect = wt.RECT(100, 100, 400, 142)
    tray._item_rect = lambda s: rect
    tray._redraw_item = lambda rc: None

    def feed(wparam, lparam):
        msg = wg.MENUMSG()
        msg.message = wg.WM_MOUSEWHEEL
        msg.wParam = wparam
        msg.lParam = lparam
        msg.pt = wt.POINT(250, 120)          # 光标压在滑块上
        return tray._handle_menu_input(msg, wg.WM_MOUSEWHEEL)

    DOWN = ((-120 << 16) & 0xFFFFFFFF)

    # 上滚：wParam 低=x 高=y，增量在 lParam 高 16 位
    state["v"] = 50
    consumed = feed((250 | (120 << 16)) & 0xFFFFFFFF, (120 << 16))
    check("滚轮上滚 +1%（增量取 lParam 高 16 位）", state["v"] == 51,
          "50 -> %d" % state["v"])
    check("滚轮消息被滑块消费（菜单不会自己去滚）", consumed is True)

    # 下滚：老代码会从 wParam 取到 y=120 → 误判成上滚，这一条就是那个回归
    state["v"] = 50
    feed((250 | (120 << 16)) & 0xFFFFFFFF, DOWN)
    check("滚轮下滚 -1%（不再把 y 坐标当增量）", state["v"] == 49,
          "50 -> %d" % state["v"])

    # 边界：到顶再上滚不越界
    state["v"] = 95
    feed((250 | (120 << 16)) & 0xFFFFFFFF, (120 << 16))
    check("滚轮在 95% 上限处夹住", state["v"] == 95, "%d" % state["v"])

    # 光标不在滑块上：不消费，交回菜单
    state["v"] = 50
    msg = wg.MENUMSG()
    msg.message = wg.WM_MOUSEWHEEL
    msg.wParam = (250 | (120 << 16)) & 0xFFFFFFFF
    msg.lParam = (120 << 16)
    msg.pt = wt.POINT(10, 10)                # 滑块矩形之外
    not_hit = tray._handle_menu_input(msg, wg.WM_MOUSEWHEEL)
    check("光标不在滑块上时滚轮不被消费", not_hit is False and state["v"] == 50,
          "值 %d" % state["v"])

    # 点击：按下即跳到对应位置，并且被消费（菜单不关闭 → 才能接着拖）
    state["v"] = 50
    msg = wg.MENUMSG()
    msg.message = wg.WM_LBUTTONDOWN
    msg.wParam, msg.lParam = 0, 0
    msg.pt = wt.POINT(rect.left + wg.SLIDER_PAD_X, 120)      # 条最左端 → 5%
    click_consumed = tray._handle_menu_input(msg, wg.WM_LBUTTONDOWN)
    check("点击最左端 -> 最小值 5%", state["v"] == 5, "%d" % state["v"])
    check("点击被消费（菜单保持打开）", click_consumed is True)

    # 拖动中的 WM_MOUSEMOVE 必须放行，否则菜单高亮和方向键都失效
    tray._dragging = False
    msg = wg.MENUMSG()
    msg.message = wg.WM_MOUSEMOVE
    msg.wParam, msg.lParam = 0, 0
    msg.pt = wt.POINT(rect.right - wg.SLIDER_PAD_X, 120)
    move_consumed = tray._handle_menu_input(msg, wg.WM_MOUSEMOVE)
    check("WM_MOUSEMOVE 放行（不吞）", move_consumed is False)


def test_startup_paths():
    """启动路径的边界：没有配置文件、没有参数时也必须能起来。

    这一条是踩出来的：`apply_saved({}, None, None)` 早先原样返回 (None, None)，
    构造函数里 `float(None)` 直接 TypeError —— 也就是**新机器首次运行必崩**，
    而带着自己生成的 config.json 反复跑测试永远发现不了。
    """
    print("\nF. 启动路径：空配置 / 无参数不能崩")
    check("GlassConfig() 无参数 → 40/100",
          (wg.GlassConfig().inactive_pct, wg.GlassConfig().active_pct) == (40, 100),
          "%d/%d" % (wg.GlassConfig().inactive_pct, wg.GlassConfig().active_pct))
    c = wg.GlassConfig(inactive_alpha=None, active_alpha=None)
    check("GlassConfig(None, None) → 回落内置默认 40/100",
          (c.inactive_pct, c.active_pct) == (40, 100),
          "%d/%d" % (c.inactive_pct, c.active_pct))
    check("apply_saved({}, None, None) 返回数字而不是 None",
          wg.GlassConfig.apply_saved({}, None, None) == (40, 100),
          "%r" % (wg.GlassConfig.apply_saved({}, None, None),))
    check("apply_saved 里命令行优先",
          wg.GlassConfig.apply_saved({"inactive_percent": 30}, 55, None)
          == (55, 100))

    # 真跑一遍 CLI：这才是当初暴露问题的那条路
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    for extra, desc in ((["--list", "--no-config"], "--no-config 无参数"),
                        (["--list"], "默认启动路径")):
        try:
            r = subprocess.run([sys.executable, os.path.join(here, "win_glass.py")]
                               + extra, capture_output=True, timeout=60)
            out = (r.stdout or b"").decode("utf-8", "replace")
            check("CLI %s 能正常起来（rc=0）" % desc, r.returncode == 0,
                  "rc=%d %s" % (r.returncode,
                                (r.stderr or b"").decode("utf-8", "replace")[-120:]))
            check("CLI %s 输出里能看到 40%%/100%%" % desc,
                  "40%" in out and "100%" in out, out.splitlines()[0] if out else "")
        except Exception as e:
            check("CLI %s 能正常起来（rc=0）" % desc, False, repr(e))


def main():
    print("=" * 72)
    print("win_glass 托盘滑块测试")
    print("=" * 72)
    test_quantize()
    test_mapping()
    test_draw()
    test_persist()
    test_menu_input()
    test_startup_paths()
    print("\n" + "=" * 72)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED: %s" % f)
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
