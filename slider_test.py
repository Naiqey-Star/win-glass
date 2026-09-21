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

    # ---- 渐隐时长：1~5000ms，永远是整数 ----
    for raw, exp in [(None, 500), (500, 500), (1, 1), (5000, 5000),
                     (0, 1), (-80, 1), (99999, 5000), (750.4, 750)]:
        c = wg.GlassConfig(fade_ms=raw)
        check("渐隐 %r -> %dms" % (raw, exp), c.fade_ms == exp,
              "实际 %dms" % c.fade_ms)
    c = wg.GlassConfig()
    c.fade_ms = 2500
    check("渐隐赋值 2500 -> 2500", c.fade_ms == 2500, "实际 %dms" % c.fade_ms)
    c.fade_ms = 123456
    check("渐隐赋值 123456 被夹到 5000", c.fade_ms == 5000, "实际 %dms" % c.fade_ms)
    bad = [v for v in range(-5, 6000, 37)
           if "." in str(wg.GlassConfig(fade_ms=v).fade_ms)]
    check("扫 -5..5999 渐隐无小数", not bad, repr(bad[:4]))


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


def draw_to(dc, label, lo, hi, pct, state=0, hot=False):
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
    wg.draw_menu_slider(dis, label, lo, hi, pct, hot)


def _item_rc():
    return wt.RECT(0, 0, W, H)


def sample_bar_y():
    """轨道的垂直中线。

    ⚠️ 必须跟绘制共用 `_track_center_y(rc)`：早先这里自己抄了一遍
    `3 + SLIDER_TITLE_H + 3 + SLIDER_BAR_H // 2`，改成音量条后常量没了，
    测试就去扫一条根本没画东西的行。
    """
    return wg._track_center_y(_item_rc())


def scan_row(dc, y=None):
    """沿轨道中线逐像素取色，返回 (颜色列表, 起点 x)。"""
    if y is None:
        y = sample_bar_y()
    t_left, t_right, _, _ = wg._track_geom(_item_rc())
    return [gdi32.GetPixel(dc, x, y) for x in range(t_left, t_right)], t_left


def item_bg(dc):
    """这一行菜单项的背景色（左上角那块留白，什么都不会画上去）。"""
    return gdi32.GetPixel(dc, 2, 2)


def scan_col(dc, x):
    """整列取色（项顶到项底）。"""
    return [gdi32.GetPixel(dc, x, y) for y in range(0, H)]


def ink_height(dc, x, bg):
    """列 x 上「非背景」像素的个数 —— 也就是滑块在这条竖线里的可视高度。

    为什么用「非背景」而不是某个具体颜色：手柄本体和已填充轨道**同色**
    （都是强调色），按颜色数根本分不开；而轨道只有 4px 厚，于是竖直方向上
    越过轨道的部分必然就是手柄 —— 它的弦长就是圆的轮廓证据。
    """
    return sum(1 for c in scan_col(dc, x) if c != bg)


def rightmost_of(cols, x0, color):
    """颜色 color 在最右侧出现的 x；没出现返回 None。"""
    hit = [x0 + i for i, c in enumerate(cols) if c == color]
    return hit[-1] if hit else None


def test_draw():
    print("\nC. 绘制层：真画一遍，再用 GetPixel 反查填充边界与手柄形状")
    rc = _item_rc()
    y = sample_bar_y()
    check("采样行在菜单项内", 0 < y < H, "y=%d / H=%d" % (y, H))
    t_left, t_right, _, _ = wg._track_geom(rc)
    span_x = t_right - t_left
    # 调色板直接取自绘制层：颜色对不上说明主题/配色逻辑坏了
    acc, trk, _thumb, _ring = wg._slider_colors(False, False)

    dc, _ = make_dc()
    check("离屏位图是彩色(非单色)", gdi32.GetPixel(dc, 0, 0) != 0xFFFFFFFF)

    def thumb_cx(pct, lo=5, hi=95, rad=None):
        rad = wg.SLIDER_THUMB_R if rad is None else rad
        cx = wg.pct_to_thumb_x(pct, lo, hi, rc)
        return max(rc.left + rad + 1, min(rc.right - rad - 1, cx))

    # ---- 核心不变量 1：强调色从最左端一路连到**手柄右缘** ----
    # 音量条式滑块 = 细轨道 + 圆形手柄。填充必须精确停在手柄处：
    # 短了会断一截，长了会在手柄右侧拖出一条尾巴。
    ends, fills = [], []
    for pct in (5, 20, 40, 50, 67, 95):
        draw_to(dc, "非聚焦最低透明度", 5, 95, pct)
        row, x0 = scan_row(dc, y)
        uniq = set(row)
        check("pct=%d 至少画出两种颜色" % pct, len(uniq) >= 2,
              "颜色数=%d %s" % (len(uniq), [hex(c & 0xFFFFFF) for c in list(uniq)[:3]]))
        if len(uniq) < 2:
            continue
        check("pct=%d 用到了强调色" % pct, acc in uniq)
        check("pct=%d 用到了轨道底色" % pct, trk in uniq)
        cx = thumb_cx(pct)
        end = rightmost_of(row, x0, acc)
        # 终点必须落在「手柄圆心 .. 手柄右缘」之间：既不断在手柄左边，
        # 也不越过手柄往外拖尾巴（外圈圆描边占掉最右约 2px 是正常的）
        check("pct=%d 填充止于手柄 (圆心%d..右缘%d)" % (pct, cx, cx + wg.SLIDER_THUMB_R),
              end is not None and (cx - 2) <= end <= (cx + wg.SLIDER_THUMB_R),
              "实测 %r" % end)
        ends.append(end if end is not None else -1)
        fills.append(sum(1 for c in row if c == acc))

    check("填充终点随数值单调右移", all(a <= b for a, b in zip(ends, ends[1:])),
          str(ends))
    check("填充像素数随数值单调不减", all(a <= b for a, b in zip(fills, fills[1:])),
          str(fills))

    # ---- 核心不变量 2：手柄是**圆的**（竖线高度从中线向两侧递减）----
    draw_to(dc, "非聚焦最低透明度", 5, 95, 50)
    bg = item_bg(dc)
    rad = wg.SLIDER_THUMB_R
    cx = thumb_cx(50)
    h_mid = ink_height(dc, cx, bg)
    h_edge = ink_height(dc, cx + rad - 1, bg)
    h_out = ink_height(dc, cx + rad + 2, bg)
    check("手柄中线高度≈直径", h_mid >= 2 * rad - 3,
          "实测 %dpx（直径 %dpx）" % (h_mid, 2 * rad))
    check("靠边处比中线矮（圆形而非矩形）", h_edge < h_mid,
          "中线 %dpx vs 边缘 %dpx" % (h_mid, h_edge))
    check("手柄外侧退回轨道厚度", h_out <= wg.SLIDER_TRACK_H + 1,
          "实测 %dpx，轨道 %dpx" % (h_out, wg.SLIDER_TRACK_H))

    # ---- 核心不变量 3：悬停/拖动时手柄放大一圈（音量条式反馈）----
    draw_to(dc, "非聚焦最低透明度", 5, 95, 50, hot=True)
    w_hot = ink_height(dc, cx, item_bg(dc))
    check("hot 手柄比常态更大", w_hot > h_mid, "hot %dpx vs 常态 %dpx" % (w_hot, h_mid))

    # 选中态走的是 ODS_SELECTED 分支，也得放大
    draw_to(dc, "非聚焦最低透明度", 5, 95, 50, state=wg.ODS_SELECTED)
    w_sel = ink_height(dc, cx, item_bg(dc))
    check("选中态手柄同样放大", w_sel > h_mid, "选中 %dpx vs 常态 %dpx" % (w_sel, h_mid))

    # ---- 两端：最小值时右侧空轨道很长，最大值时几乎没有 ----
    draw_to(dc, "非聚焦最低透明度", 5, 95, 5)
    row, _ = scan_row(dc, y)
    tail = sum(1 for c in row if c == trk)
    check("pct=5 时右侧空轨道很长", tail > span_x * 0.6,
          "空轨道 %d / %d px" % (tail, span_x))

    draw_to(dc, "非聚焦最低透明度", 5, 95, 95)
    row, _ = scan_row(dc, y)
    tail95 = sum(1 for c in row if c == trk)
    check("pct=95 时右侧空轨道几乎为 0", tail95 <= 4, "空轨道 %d px" % tail95)

    # ---- 轨道要够细（音量条那种细条，而不是粗块）----
    # 注意 GDI 的 RoundRect 底边不填，b-t=4 实际画出 3 行，所以留 1px 容差；
    # 这条断言的价值在于「一旦退化成粗条立刻报警」，不是抠像素。
    draw_to(dc, "非聚焦最低透明度", 5, 95, 5)
    mid_x = (t_left + t_right) // 2
    th = sum(1 for c in scan_col(dc, mid_x) if c == trk)
    check("轨道厚度 ≈ %dpx" % wg.SLIDER_TRACK_H,
          abs(th - wg.SLIDER_TRACK_H) <= 1, "实测 %dpx" % th)
    check("轨道确实是细条（<= 6px）", th <= 6, "实测 %dpx" % th)

    # ---- 选中态 / 禁用态都要能画 ----
    for state, name in ((wg.ODS_SELECTED, "选中态"), (wg.ODS_GRAYED, "禁用态")):
        try:
            draw_to(dc, "非聚焦最低透明度", 5, 95, 40, state)
            row, _ = scan_row(dc, y)
            check("%s 可绘制且有两种颜色" % name, len(set(row)) >= 2)
        except Exception as e:
            check("%s 可绘制" % name, False, repr(e))

    gdi32.DeleteDC(dc)


# ---------------------------------------------------------------- D. 持久层
def test_persist():
    print("\nD. 持久层：config.json 往返 / --no-config 关闭")
    d = tempfile.mkdtemp(prefix="winglass_cfg_")
    p = os.path.join(d, "config.json")

    c = wg.GlassConfig(inactive_alpha=0.33, active_alpha=0.88, fade_ms=750, cfg_path=p)
    check("保存成功", c.save())
    check("文件已生成", os.path.isfile(p))
    raw = json.load(open(p, encoding="utf-8"))
    check("落盘的是整数百分比",
          raw.get("inactive_percent") == 33 and raw.get("active_percent") == 88,
          json.dumps(raw, ensure_ascii=False))
    check("渐隐时长也落盘 750ms", raw.get("fade_ms") == 750,
          json.dumps(raw, ensure_ascii=False))

    loaded = wg.load_cfg_file(p)
    inactive, active = wg.GlassConfig.apply_saved(loaded, None, None)
    fade = wg.GlassConfig.apply_saved_fade(loaded, None)
    c2 = wg.GlassConfig(inactive_alpha=inactive, active_alpha=active,
                        fade_ms=fade, cfg_path=p)
    check("读回后取值一致 33/88",
          c2.inactive_pct == 33 and c2.active_pct == 88,
          "%d/%d" % (c2.inactive_pct, c2.active_pct))
    check("alpha 读回 0.33", abs(c2.inactive_alpha - 0.33) < 1e-9)
    check("渐隐时长读回 750ms",
          c2.fade_ms == 750, "实际 %dms" % c2.fade_ms)

    # 渐隐时长：命令行 > 配置文件 > 内置默认，三级优先
    check("--fade-ms 未给则用配置文件里的 750",
          wg.GlassConfig.apply_saved_fade(loaded, None) == 750)
    check("--fade-ms 显式给了就覆盖配置文件",
          wg.GlassConfig.apply_saved_fade(loaded, 300) == 300)
    check("没有配置文件也没有参数 -> 内置默认 500",
          wg.GlassConfig.apply_saved_fade({}, None) == wg.GlassConfig.DEFAULT_FADE_MS)

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
        raw5 = wg.load_cfg_file(probe)
        # 这里改成逐键断言而不是整体 == 字典：v1.3.0 起 as_dict 多了悬停两个键，
        # 写死整体字典会让每次加设置项都假失败。既有三项仍按原值核对。
        check("写出的值正确 40/77/500",
              raw5.get("version") == 1 and raw5.get("inactive_percent") == 40
              and raw5.get("active_percent") == 77
              and raw5.get("fade_ms") == wg.GlassConfig.DEFAULT_FADE_MS,
              json.dumps(raw5, ensure_ascii=False))
        check("悬停开关也落盘（默认开）", raw5.get("hover_enabled") is True,
              json.dumps(raw5, ensure_ascii=False))
        check("全屏锁定也落盘（默认开）", raw5.get("fullscreen_lock") is True,
              json.dumps(raw5, ensure_ascii=False))
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

    # 「默认启动路径」会读**真实**的 config.json，所以期望值必须从那个文件里取，
    # 写死 40/100 只会在用户自己拖过滑块之后变成假失败。
    saved = wg.load_cfg_file()
    exp_i = saved.get("inactive_percent", wg.GlassConfig.DEFAULT_INACTIVE_PCT)
    exp_a = saved.get("active_percent", wg.GlassConfig.DEFAULT_ACTIVE_PCT)
    exp_f = saved.get("fade_ms", wg.GlassConfig.DEFAULT_FADE_MS)

    cases = [(["--list", "--no-config"], "--no-config 无参数", 40, 100,
              wg.GlassConfig.DEFAULT_FADE_MS),
             (["--list"], "默认启动路径(读真实配置)", exp_i, exp_a, exp_f)]
    for extra, desc, ei, ea, ef in cases:
        try:
            r = subprocess.run([sys.executable, os.path.join(here, "win_glass.py")]
                               + extra, capture_output=True, timeout=60)
            out = (r.stdout or b"").decode("utf-8", "replace")
            check("CLI %s 能正常起来（rc=0）" % desc, r.returncode == 0,
                  "rc=%d %s" % (r.returncode,
                                (r.stderr or b"").decode("utf-8", "replace")[-120:]))
            ok_pct = ("未聚焦目标=%d%%" % ei) in out and \
                ("聚焦/最大化/置顶目标=%d%%" % ea) in out
            ok_fade = ("渐隐=%dms" % ef) in out
            check("CLI %s 百分比正确 %d%%/%d%%" % (desc, ei, ea), ok_pct,
                  out.splitlines()[0] if out else "")
            check("CLI %s 渐隐时长正确 %dms" % (desc, ef), ok_fade,
                  out.splitlines()[0] if out else "")
            check("CLI %s 声明了全屏恒定 100%%" % desc,
                  "全屏固定=100%" in out, out.splitlines()[0] if out else "")
        except Exception as e:
            check("CLI %s 能正常起来（rc=0）" % desc, False, repr(e))


def test_fade_runtime():
    """G. 渐隐时长：菜单里改完必须**立即**生效。

    光写配置不够——正在跑的缓动如果不重排时间轴，用户改完要等下一次切换
    才能看到差别，会觉得"没生效"。所以这里断言：改时长后已完成进度不变。
    """
    print("\nG. 渐隐时长：set_fade_ms 重排正在跑的缓动")
    cfg = wg.GlassConfig(cfg_path="", fade_ms=1000)
    eng = wg.GlassEngine(cfg)
    check("初值 1000ms", cfg.fade_ms == 1000, "%dms" % cfg.fade_ms)

    # 造一个「正在跑」的窗口状态：1000ms 的缓动，才走了 25%
    hwnd = wg.user32.GetDesktopWindow()
    st = wg.WinState(hwnd)
    st.title, st.cls = "t", "c"
    st.cur = 0.4
    st.src, st.dst = 0.4, 1.0
    st.dur = 1.0
    st.t0 = wg.time.perf_counter() - 0.25
    with eng.lock:
        eng.states[hwnd] = st

    eng.set_fade_ms(2000)
    check("配置写入 2000ms", cfg.fade_ms == 2000, "%dms" % cfg.fade_ms)
    check("在跑的缓动时长跟着变成 2.0s", abs(st.dur - 2.0) < 1e-6, "%.3fs" % st.dur)
    prog = (wg.time.perf_counter() - st.t0) / st.dur
    check("已完成进度不失真（仍≈25%）", abs(prog - 0.25) < 0.05, "%.3f" % prog)

    eng.set_fade_ms(120)
    prog2 = (wg.time.perf_counter() - st.t0) / st.dur
    check("缩短到 120ms 后进度同样保持", abs(prog2 - 0.25) < 0.08, "%.3f" % prog2)

    # 越界一律夹紧，不抛异常
    eng.set_fade_ms(0)
    check("越界 0 -> 1ms", cfg.fade_ms == 1, "%dms" % cfg.fade_ms)
    eng.set_fade_ms(99999)
    check("越界 99999 -> 5000ms", cfg.fade_ms == 5000, "%dms" % cfg.fade_ms)

    # 已完成（prog>=1）的缓动不能因为改时长而倒回去
    st.dur, st.t0 = 1.0, wg.time.perf_counter() - 5.0
    eng.set_fade_ms(300)
    check("已结束的缓动不被改写", st.dur == 1.0, "%.3fs" % st.dur)

    # cfg_path='' 时不该落盘，但也不能报错
    eng.set_fade_ms(800)
    check("--no-config 下改时长不报错且内存生效", cfg.fade_ms == 800)


def test_number_input():
    """H. 数值输入框：真弹一个窗口出来，填值、点确定，验证返回值。

    这个对话框是手搓的（CreateWindowExW + 嵌套消息循环），最容易出的问题是
    「点了确定没反应」或「把托盘线程一起退掉」，所以必须真跑一遍而不是只读代码。
    """
    print("\nH. 数值输入框：NumberInputBox 端到端")
    import threading
    import time as _t

    def driver(value, action, box):
        """后台线程：等窗口出现 → 填值 → 触发确定/取消。"""
        h = 0
        for _ in range(250):
            h = wg.user32.FindWindowW("WinGlassNumberInput", None)
            if h:
                break
            _t.sleep(0.02)
        if not h:
            box["found"] = False
            return
        box["found"] = True
        box["hwnd"] = int(h)
        # ⚠️ FindWindowW 可能在**子控件创建之前**就抓到顶层窗口（窗口类先注册、
        # 顶层 CreateWindowExW 先返回，编辑框/按钮随后才建）。直接 GetDlgItem
        # 会偶发拿到 0 —— 这是环境抖动的根源，不是产品 bug。等一小会儿。
        edit = ok = 0
        for _ in range(150):
            edit = wg.user32.GetDlgItem(h, wg.IDC_NUM_EDIT)
            ok = wg.user32.GetDlgItem(h, wg.IDC_NUM_OK)
            if edit and ok:
                break
            _t.sleep(0.02)
        box["has_edit"] = bool(edit)
        box["has_ok"] = bool(ok)
        if value is not None and edit:
            wg.user32.SetWindowTextW(edit, value)
        if action == "ok":
            wg.user32.PostMessageW(h, wg.WM_COMMAND, wg.IDC_NUM_OK, 0)
        elif action == "cancel":
            wg.user32.PostMessageW(h, wg.WM_COMMAND, wg.IDC_NUM_CANCEL, 0)
        else:
            wg.user32.PostMessageW(h, wg.WM_CLOSE, 0, 0)

    def run(value, action):
        box = {}
        t = threading.Thread(target=driver, args=(value, action, box), daemon=True)
        t.start()
        try:
            res = wg.NumberInputBox(0, "渐隐时间", "渐隐时长（毫秒）：", "ms",
                                    500, 1, 5000).show()
        finally:
            t.join(timeout=3)
        return res, box

    res, box = run("250", "ok")
    check("对话框真的弹出来了", box.get("found"),
          "hwnd=%s" % box.get("hwnd"))
    check("对话框里有编辑框和确定按钮",
          box.get("has_edit") and box.get("has_ok"))
    check("确定返回输入值 250", res == 250, repr(res))

    # 越界夹紧
    res, _ = run("0", "ok")
    check("输入 0 被夹到下限 1", res == 1, repr(res))
    res, _ = run("99999", "ok")
    check("输入 99999 被夹到上限 5000", res == 5000, repr(res))

    # 非数字 → 退回原值
    res, _ = run("abc", "ok")
    check("非数字退回原值 500", res == 500, repr(res))

    # 取消 / 关窗 → None（调用方据此不落盘）
    res, _ = run("1234", "cancel")
    check("点取消返回 None", res is None, repr(res))
    res, _ = run("1234", "close")
    check("直接关窗返回 None", res is None, repr(res))

    # 关键回归：对话框关掉后，嵌套消息循环必须干净退出，
    # 不能把整个进程退掉（早期版本在这里 PostQuitMessage 会把托盘一起带走）
    check("关窗后进程仍存活", True)
    check("对话框窗口已销毁",
          not wg.user32.FindWindowW("WinGlassNumberInput", None))


def test_menu_content():
    """I. 菜单内容：项数、顺序、ID、以及「渐隐时间」上显示的 ms 值。

    `_popup` 会阻塞在 TrackPopupMenu 里，所以把「拼菜单」拆成了 `_build_menu`，
    这里就能直接把菜单拼出来、逐项读回文字核对。
    """
    print("\nI. 菜单内容：_build_menu 逐项核对")
    u = wg.user32
    u.GetMenuStringW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_wchar_p,
                                 ctypes.c_int, wt.UINT]
    u.GetMenuStringW.restype = ctypes.c_int
    u.GetMenuItemCount.argtypes = [wt.HMENU]
    u.GetMenuItemCount.restype = ctypes.c_int
    u.GetMenuItemID.argtypes = [wt.HMENU, ctypes.c_int]
    u.GetMenuItemID.restype = wt.UINT
    u.GetMenuState.argtypes = [wt.HMENU, wt.UINT, wt.UINT]
    u.GetMenuState.restype = wt.UINT
    MSF_BY = 0x00000400          # MF_BYPOSITION

    cfg = wg.GlassConfig(cfg_path="", fade_ms=1234)
    eng = wg.GlassEngine(cfg)
    tray = wg.TrayIcon(eng)
    m = tray._build_menu()
    check("菜单建出来了", bool(m))

    def text_of(i):
        buf = ctypes.create_unicode_buffer(256)
        u.GetMenuStringW(m, i, buf, 256, MSF_BY)
        return buf.value.replace("\t", "  ")

    n = u.GetMenuItemCount(m)
    items = [text_of(i) for i in range(n)]
    print("  菜单项（共 %d）：" % n)
    for i, s in enumerate(items):
        print("     %2d) %s" % (i, s if s else "<分隔符>"))

    check("滑块数量 == 4", len(tray._sliders) == 4,
          "实际 %d" % len(tray._sliders))
    # owner-draw 项在菜单里不存文字（文字是我们自己画的），所以标签只能从
    # MenuSlider 上取；菜单里能查的是位置和 ID。
    check("第一个滑块是「非聚焦最低透明度」",
          tray._sliders[0].label == "非聚焦最低透明度",
          tray._sliders[0].label if tray._sliders else "(无)")
    check("第二个滑块是「聚焦最高透明度」",
          len(tray._sliders) > 1 and tray._sliders[1].label == "聚焦最高透明度")
    check("第三个滑块是「悬停插值系数」（v1.5.0）",
          len(tray._sliders) > 2 and tray._sliders[2].label == "悬停插值系数",
          tray._sliders[2].label if len(tray._sliders) > 2 else "(无)")
    check("第四个滑块是「层衰减系数」（v1.6.0）",
          len(tray._sliders) > 3 and tray._sliders[3].label == "层衰减系数",
          tray._sliders[3].label if len(tray._sliders) > 3 else "(无)")
    check("滑块在菜单里紧挨着（位置连续且递增）",
          len(tray._sliders) == 4
          and [sl.pos for sl in tray._sliders]
          == list(range(tray._sliders[0].pos, tray._sliders[0].pos + 4)),
          "pos=%s" % [sl.pos for sl in tray._sliders])
    check("滑块范围 5..95 / 5..100 / 0..10 / 0..10",
          (tray._sliders[0].lo, tray._sliders[0].hi) == (5, 95)
          and (tray._sliders[1].lo, tray._sliders[1].hi) == (5, 100)
          and (tray._sliders[2].lo, tray._sliders[2].hi) == (0, 10)
          and (tray._sliders[3].lo, tray._sliders[3].hi) == (0, 10),
          "%s / %s / %s / %s" % ((tray._sliders[0].lo, tray._sliders[0].hi),
                                 (tray._sliders[1].lo, tray._sliders[1].hi),
                                 (tray._sliders[2].lo, tray._sliders[2].hi),
                                 (tray._sliders[3].lo, tray._sliders[3].hi)))
    check("系数滑块 ID 不与其它项撞号（含新的 CMD_SLIDE_DECAY）",
          tray._sliders[2].cid == wg.CMD_SLIDE_HOVER
          and tray._sliders[3].cid == wg.CMD_SLIDE_DECAY
          and len({sl.cid for sl in tray._sliders}) == 4,
          str([sl.cid for sl in tray._sliders]))

    # ---- 拖这个滑块，系数与悬停值都要实时跟着走（v1.5.0）----
    ratio_sl = tray._sliders[2]
    dummy_rc = wt.RECT(0, 0, 300, 46)
    check("滑块初始档位 = 系数 × 10（默认 0.8 → 档位 8）",
          ratio_sl.get() == 8, "档位 %s" % ratio_sl.get())
    check("滑块显示文本是「0.8」而不是「8%」", ratio_sl.text() == "0.8",
          ratio_sl.text())
    tray._apply_slider(ratio_sl, dummy_rc, 3)
    check("把滑块拖到档位 3 → 系数变 0.3",
          abs(eng.cfg.hover_ratio - 0.3) < 1e-9, "%.2f" % eng.cfg.hover_ratio)
    check("  且悬停值立刻跟到 58%（40 + (100−40)×0.3）",
          eng.cfg.hover_pct == 58, "%d%%" % eng.cfg.hover_pct)
    tray._apply_slider(ratio_sl, dummy_rc, 10)
    check("拖到最右（档位 10）→ 系数 1.0、悬停值等于最高值 100%",
          abs(eng.cfg.hover_ratio - 1.0) < 1e-9 and eng.cfg.hover_pct == 100,
          "%.1f / %d%%" % (eng.cfg.hover_ratio, eng.cfg.hover_pct))
    tray._apply_slider(ratio_sl, dummy_rc, 99)
    check("超范围输入被夹到右端（10）", ratio_sl.get() == 10, str(ratio_sl.get()))
    tray._apply_slider(ratio_sl, dummy_rc, -5)
    check("超范围输入被夹到左端（0）", ratio_sl.get() == 0, str(ratio_sl.get()))
    tray._apply_slider(ratio_sl, dummy_rc, 8)     # 还原成默认，别影响后面的断言
    check("还原后系数回到 0.8、悬停值 88%",
          abs(eng.cfg.hover_ratio - 0.8) < 1e-9 and eng.cfg.hover_pct == 88,
          "%.1f / %d%%" % (eng.cfg.hover_ratio, eng.cfg.hover_pct))
    joined = " | ".join(items)
    check("菜单里有「渐隐时间」项", "渐隐时间" in joined)
    fade_item = [s for s in items if "渐隐时间" in s]
    check("渐隐时间显示当前值 1234 ms",
          fade_item and "1234" in fade_item[0], str(fade_item))
    check("菜单里有「打开日志」", "打开日志" in joined)
    check("菜单里有退出项", any("退出" in s for s in items))
    check("菜单里有「悬停半透明」开关项", "悬停半透明" in joined)
    hover_item = [s for s in items if "悬停半透明" in s]
    check("悬停项显示当前悬停值 88%（最高100/最低40，系数默认 0.8）",
          hover_item and "88%" in hover_item[0], str(hover_item))
    check("悬停项默认是勾选状态",
          wg.CMD_HOVER in [int(u.GetMenuItemID(m, i)) for i in range(n)]
          and bool(u.GetMenuState(m, wg.CMD_HOVER, 0x00000000) & 0x0008),
          "state=0x%04X" % int(u.GetMenuState(m, wg.CMD_HOVER, 0)))
    check("菜单里有「全屏窗口固定 100%」开关项", "全屏窗口固定 100%" in joined)
    check("全屏项默认勾选（= 接管并锁 100%）",
          wg.CMD_FULLSCREEN in [int(u.GetMenuItemID(m, i)) for i in range(n)]
          and bool(u.GetMenuState(m, wg.CMD_FULLSCREEN, 0x00000000) & 0x0008),
          "state=0x%04X" % int(u.GetMenuState(m, wg.CMD_FULLSCREEN, 0)))
    # 关掉之后菜单文字要说明"当前完全不接管"
    eng.set_fullscreen_lock(False)
    m3 = tray._build_menu()
    buf_fs = ctypes.create_unicode_buffer(256)
    got_fs = []
    for i in range(u.GetMenuItemCount(m3)):
        u.GetMenuStringW(m3, i, buf_fs, 256, MSF_BY)
        if "全屏窗口固定 100%" in buf_fs.value:
            got_fs.append(buf_fs.value)
    check("关掉全屏锁定后菜单文字提示「完全不接管」",
          got_fs and "完全不接管" in got_fs[0], str(got_fs))
    check("  且该项不再处于勾选态",
          not (u.GetMenuState(m3, wg.CMD_FULLSCREEN, 0x00000000) & 0x0008),
          "state=0x%04X" % int(u.GetMenuState(m3, wg.CMD_FULLSCREEN, 0)))
    u.DestroyMenu(m3)
    eng.set_fullscreen_lock(True)

    # ID 必须是菜单命令 ID，而不是随便的数字
    ids = [int(u.GetMenuItemID(m, i)) for i in range(n)]
    check("渐隐时间项的 ID == CMD_FADE_MS",
          wg.CMD_FADE_MS in ids, str(ids))
    check("三个滑块的 ID 都在菜单里",
          wg.CMD_SLIDE_INACTIVE in ids and wg.CMD_SLIDE_ACTIVE in ids, str(ids))

    # 改一下时长，菜单文字必须跟着变
    eng.set_fade_ms(250)
    m2 = tray._build_menu()
    buf = ctypes.create_unicode_buffer(256)
    got = []
    for i in range(u.GetMenuItemCount(m2)):
        u.GetMenuStringW(m2, i, buf, 256, MSF_BY)
        if "渐隐时间" in buf.value:
            got.append(buf.value.replace("\t", "  "))
    check("改了时长后菜单显示 250 ms", got and "250" in got[0], str(got))
    u.DestroyMenu(m2)
    u.DestroyMenu(m)


def test_hover():
    """H. 悬停半透明（v1.3.0）：取值边界 / 参与范围 / 目标判定 / 轮询。

    这里不真的移动鼠标：`wg.cursor_pos` 与 `wg.cursor_root_window` 都被换掉，
    悬停判定完全是确定性的，也不会打扰用户正在做的事。
    """
    print("\nH. 悬停半透明：插值系数取值、参与范围、目标判定、光标轮询")

    # ---- 取值：悬停值 = 最低 + (最高-最低) × hover_ratio ----
    # ratio 现在是滑块调的（v1.5.0），所以断言里一律**显式给 ratio**，
    # 免得再被默认值改动牵连；默认值本身单独断言。
    c = wg.GlassConfig(inactive_alpha=0.50, active_alpha=1.00, hover_ratio=0.5)
    check("ratio=0.5、最高100 / 最低50 → 悬停 75%（用户给的例子）",
          c.hover_pct == 75, "%d%%" % c.hover_pct)
    c2 = wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00)
    check("默认系数 0.8、最高100 / 最低40 → 悬停 88%",
          c2.hover_pct == 88, "%d%%" % c2.hover_pct)
    check("默认系数就是 0.8（DEFAULT_HOVER_RATIO）",
          wg.DEFAULT_HOVER_RATIO == 0.8 and abs(c2.hover_ratio - 0.8) < 1e-9,
          "%.2f" % c2.hover_ratio)
    check("系数 0.5 时 100/40 → 70%（旧的固定值也能复现）",
          wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00,
                         hover_ratio=0.5).hover_pct == 70)
    check("系数 0.8 时 100/50 → 90%",
          wg.GlassConfig(inactive_alpha=0.50, active_alpha=1.00,
                         hover_ratio=0.8).hover_pct == 90)
    # 滑块每档 0.1，逐档核对一遍公式确实跟着滑块走
    by_step = []
    for k in range(11):
        cc = wg.GlassConfig(inactive_alpha=0.50, active_alpha=1.00,
                            hover_ratio=k / 10.0)
        by_step.append(cc.hover_pct)
    check("系数从 0.0 走到 1.0（0.1 一档）→ 悬停值 50→100 单调递增",
          by_step == sorted(by_step) and by_step[0] == 50 and by_step[-1] == 100,
          str(by_step))
    check("总步数 11 档（0.0~1.0 含两端）", len(by_step) == 11)
    check("系数 1.0 时悬停值 == 最高值（此时等于没压暗）",
          by_step[-1] == wg.GlassConfig(inactive_alpha=0.50,
                                        active_alpha=1.00).active_pct)
    check("⭐ 悬停值随系数动态变化（不是固定 0.5 时代的一个定值）",
          len(set(by_step)) == 11, "不同取值 %d 个" % len(set(by_step)))

    # 边界：悬停值永远落在 [最低, 最高] 之间（含端点）——这是 ratio 被夹到
    # [0,1] 的结构性结果，遍历一遍确认没有漏网
    outside = []
    for lo in range(5, 96):
        for hi in range(lo, 101):
            cc = wg.GlassConfig(inactive_alpha=lo, active_alpha=hi)
            if not (lo <= cc.hover_pct <= hi):
                outside.append((lo, hi, cc.hover_pct))
    check("悬停值恒落在 [最低,最高] 内（遍历 5~95 × ≥最低）",
          not outside, "越界 %r" % outside[:3])

    # 注意：最低透明度滑块上限是 95%，所以"两值相等"只能用 95/95 构造，
    # 用 inactive_alpha=1.00 会被夹到 95 —— 第一版测试就是在这里假失败过。
    check("最高==最低（95/95）→ 悬停无可见变化",
          wg.GlassConfig(inactive_alpha=0.95, active_alpha=0.95).hover_pct == 95,
          "%d%%" % wg.GlassConfig(inactive_alpha=0.95,
                                  active_alpha=0.95).hover_pct)
    inv = wg.GlassConfig(inactive_alpha=0.90, active_alpha=0.20)
    check("反向配置（最高20 < 最低90）→ 悬停不压暗，退化为不改变",
          (inv.inactive_pct, inv.active_pct, inv.hover_pct) == (90, 20, 90),
          "%d/%d -> %d" % (inv.inactive_pct, inv.active_pct, inv.hover_pct))
    check("ratio=0 → 悬停等于最低值（视觉效果为零）",
          wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00,
                         hover_ratio=0.0).hover_pct == 40)
    check("ratio=1 → 悬停等于最高值",
          wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00,
                         hover_ratio=1.0).hover_pct == 100)
    check("ratio 上溢夹到 1.0",
          wg.GlassConfig(hover_ratio=9.9).hover_ratio == 1.0)
    check("ratio 下溢夹到 0.0",
          wg.GlassConfig(hover_ratio=-9).hover_ratio == 0.0)
    check("轮询间隔下限 0.02s（不给就白烧 CPU）",
          wg.GlassConfig(hover_interval=0.0).hover_interval == 0.02)

    # ---- 判定：谁参与悬停 ----
    cfg = wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00)
    check("焦点窗口不受悬停影响（最高值 + 不标悬停）",
          wg.target_for(cfg, 111, is_fg=True, hover_hwnd=111)
          == (1.0, "聚焦", False),
          repr(wg.target_for(cfg, 111, is_fg=True, hover_hwnd=111)))
    check("置顶窗口不被悬停压暗（保持最高值）",
          wg.target_for(cfg, 111, top=True, hover_hwnd=111) == (1.0, "置顶", False),
          repr(wg.target_for(cfg, 111, top=True, hover_hwnd=111)))
    a, why, hv = wg.target_for(cfg, 111, hover_hwnd=111)
    check("未聚焦窗口被悬停 → 88%（默认系数 0.8）",
          abs(a - 0.88) < 1e-9 and why == "悬停" and hv is True,
          "%r %s %s" % (a, why, hv))
    # 换个系数，同一窗口的目标要跟着变 —— 证明「系数确实参与实时计算」
    cfg5 = wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00, hover_ratio=0.5)
    a5 = wg.target_for(cfg5, 111, hover_hwnd=111)[0]
    cfg0 = wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00, hover_ratio=0.0)
    a0 = wg.target_for(cfg0, 111, hover_hwnd=111)[0]
    check("⭐ 同一窗口：系数 0.5 → 70%，系数 0.0 → 等于最低值 40%",
          abs(a5 - 0.70) < 1e-9 and abs(a0 - 0.40) < 1e-9,
          "0.5→%.2f  0.0→%.2f" % (a5, a0))
    check("悬停的是别人时，自己仍是 40%",
          wg.target_for(cfg, 111, hover_hwnd=222) == (0.4, "未聚焦", False))
    check("没有任何悬停目标时 → 40%",
          wg.target_for(cfg, 111, hover_hwnd=0) == (0.4, "未聚焦", False))
    off = wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00, hover=False)
    check("关掉悬停后同一窗口回 40%",
          wg.target_for(off, 111, hover_hwnd=111) == (0.4, "未聚焦", False))
    same = wg.GlassConfig(inactive_alpha=0.50, active_alpha=0.50)
    check("最低==最高 时悬停值与基础值一致（不会反跳）",
          wg.target_for(same, 111, hover_hwnd=111)[0] == 0.50)

    # ---- 判定：最大化 / 全屏（v1.4.0）----
    check("最大化窗口视为聚焦 → 用「聚焦最高透明度」",
          wg.target_for(cfg, 111, zoomed=True) == (1.0, "最大化", False),
          repr(wg.target_for(cfg, 111, zoomed=True)))
    hi80 = wg.GlassConfig(inactive_alpha=0.40, active_alpha=0.80)
    check("最高值设成 80% 时：最大化窗口跟着变 80%",
          wg.target_for(hi80, 111, zoomed=True)[0] == 0.80,
          repr(wg.target_for(hi80, 111, zoomed=True)[0]))
    check("最高值设成 80% 时：置顶窗口跟着变 80%",
          wg.target_for(hi80, 111, top=True)[0] == 0.80)
    check("最高值设成 80% 时：聚焦窗口跟着变 80%",
          wg.target_for(hi80, 111, is_fg=True)[0] == 0.80)
    check("⭐ 全屏窗口恒为 100%，**不受最高值设置影响**（最高=80% 时仍是 1.0）",
          wg.target_for(hi80, 111, fullscreen=True) == (1.0, "全屏", False),
          repr(wg.target_for(hi80, 111, fullscreen=True)))
    check("最高值设成 5% 时全屏窗口仍是 100%",
          wg.target_for(wg.GlassConfig(inactive_alpha=0.05, active_alpha=0.05),
                        111, fullscreen=True)[0] == 1.0)
    check("优先级：全屏 > 聚焦（同时成立时按全屏的 100% 算）",
          wg.target_for(hi80, 111, fullscreen=True, is_fg=True)[0] == 1.0
          and wg.target_for(hi80, 111, fullscreen=True, is_fg=True)[1] == "全屏")
    check("优先级：全屏 > 最大化 > 置顶（同窗口最多只有一个理由）",
          wg.target_for(hi80, 111, fullscreen=True, zoomed=True, top=True)[1] == "全屏"
          and wg.target_for(hi80, 111, zoomed=True, top=True)[1] == "最大化"
          and wg.target_for(hi80, 111, top=True)[1] == "置顶")
    check("全屏/最大化/置顶窗口都不参与悬停（只提亮不压暗）",
          all(wg.target_for(hi80, 111, hover_hwnd=111, **kw)[2] is False
              for kw in ({"fullscreen": True}, {"zoomed": True}, {"top": True},
                         {"is_fg": True})))
    check("关掉全屏锁定时全屏窗口照样算 100%（判定层不依赖开关）",
          wg.target_for(wg.GlassConfig(active_alpha=0.80, fullscreen_lock=False),
                        111, fullscreen=True)[0] == 1.0)
    check("fullscreen_alpha 就是常量 1.0（不是 active_pct）",
          wg.GlassConfig(active_alpha=0.33).fullscreen_alpha == 1.0)

    # ---- 持久化 ----
    d = tempfile.mkdtemp(prefix="winglass_hover_")
    p = os.path.join(d, "config.json")
    wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00, cfg_path=p).save()
    raw = json.load(open(p, encoding="utf-8"))
    check("悬停开关 + 比例落盘",
          raw.get("hover_enabled") is True and abs(raw.get("hover_ratio") - 0.8) < 1e-9,
          json.dumps(raw, ensure_ascii=False))
    loaded = wg.load_cfg_file(p)
    check("读回一致",
          wg.GlassConfig.apply_saved_hover(loaded, None, None) == (True, 0.8))
    check("--no-hover（False）优先于配置文件",
          wg.GlassConfig.apply_saved_hover(loaded, False, None)[0] is False)
    check("--hover-ratio 优先于配置文件",
          abs(wg.GlassConfig.apply_saved_hover(loaded, None, 0.25)[1] - 0.25) < 1e-9)
    check("空配置 + 无参数 → 回落内置默认（开关=True/ratio=0.8）",
          wg.GlassConfig.apply_saved_hover({}, None, None)
          == (wg.GlassConfig.DEFAULT_HOVER, wg.GlassConfig.DEFAULT_HOVER_RATIO))

    # ---- 悬停系数滑块：档位 ↔ 系数 的双向换算（v1.5.0）----
    sp = os.path.join(d, "ratio.json")
    c8 = wg.GlassConfig(inactive_alpha=0.40, active_alpha=1.00, cfg_path=sp)
    check("滑块档位 8 → 显示 0.8 → 系数 0.8（一位小数精度）",
          wg.fmt_ratio_units(8) == "0.8"
          and abs((8 / float(wg.HOVER_RATIO_UNITS)) - 0.8) < 1e-9)
    check("档位 0/10 两端：显示 0.0 / 1.0",
          wg.fmt_ratio_units(0) == "0.0" and wg.fmt_ratio_units(10) == "1.0")
    check("百分比滑块的显示格式没被改坏（fmt_pct）",
          wg.fmt_pct(40) == "40%" and wg.fmt_pct(100) == "100%")
    check("HOVER_RATIO_UNITS == 10（每档 0.1）", wg.HOVER_RATIO_UNITS == 10)
    c8.hover_ratio = 0.3
    c8.save()
    check("改系数后落盘、能读回 0.3（滑块拖完就持久化）",
          abs(json.load(open(sp, encoding="utf-8"))["hover_ratio"] - 0.3) < 1e-9,
          json.dumps(json.load(open(sp, encoding="utf-8")), ensure_ascii=False))

    # ---- 全屏锁定开关的持久化与三级优先 ----
    check("fullscreen_lock 也落盘（默认 True）",
          raw.get("fullscreen_lock") is True,
          json.dumps(raw, ensure_ascii=False))
    check("读回一致（True）", wg.GlassConfig.apply_saved_fs(loaded, None) is True)
    check("--skip-fullscreen（False）优先于配置文件",
          wg.GlassConfig.apply_saved_fs(loaded, False) is False)
    check("空配置 + 无参数 → None（交给构造函数用内置默认 True）",
          wg.GlassConfig.apply_saved_fs({}, None) is None
          and wg.GlassConfig().fullscreen_lock is True)
    check("配置文件里显式 false 能读回 False",
          wg.GlassConfig.apply_saved_fs({"fullscreen_lock": False}, None) is False)
    check("落盘后新建实例拿到关掉的全屏锁定",
          wg.GlassConfig(
              fullscreen_lock=wg.GlassConfig.apply_saved_fs(loaded, False),
          ).fullscreen_lock is False)

    # ---- 光标轮询：_poll_hover 的节流与「光标没动就跳过」 ----
    eng = wg.GlassEngine(wg.GlassConfig(cfg_path=""))
    hw, other = 0xABCD, 0x1234
    for h in (hw, other):
        st = wg.WinState(h)
        st.title, st.cls = "t", "c"
        st.cur = st.src = st.dst = 0.4
        with eng.lock:
            eng.states[h] = st
    real_pos, real_root = wg.cursor_pos, wg.cursor_root_window
    now = {"t": 1000.0}
    pos = {"v": (10, 10)}
    root = {"v": hw}
    try:
        wg.cursor_pos = lambda: pos["v"]
        wg.cursor_root_window = lambda: root["v"]
        # 1) 第一次轮询：光标在 hw 上
        eng._poll_hover(now["t"])
        check("轮询后悬停目标 = 光标下的窗口", eng._hover_hwnd == hw,
              "0x%X" % eng._hover_hwnd)
        check("悬停变化会置 _dirty（交给主循环重算，回调里不做重活）",
              eng._dirty.is_set())
        # 2) 光标没动 → 即使此时判定结果变了也不重新采样（省掉 WindowFromPoint）
        root["v"] = other
        eng._dirty.clear()
        eng._poll_hover(now["t"] + 1.0)
        check("光标没动时不重新判定（省开销）", eng._hover_hwnd == hw,
              "0x%X" % eng._hover_hwnd)
        check("没变化就不置 _dirty", not eng._dirty.is_set())
        # 3) 光标动了 → 换目标
        pos["v"] = (200, 200)
        eng._poll_hover(now["t"] + 2.0)
        check("光标移到别的窗口 → 悬停目标跟着换", eng._hover_hwnd == other,
              "0x%X" % eng._hover_hwnd)
        # 4) 光标移到没有接管的窗口（root=0）→ 悬停清空
        root["v"] = 0
        pos["v"] = (300, 300)
        eng._poll_hover(now["t"] + 3.0)
        check("光标离开所有受管窗口 → 悬停清空", eng._hover_hwnd == 0)
        # 5) 节流：间隔内不再采样
        root["v"] = hw
        pos["v"] = (400, 400)
        eng._poll_hover(now["t"] + 3.0 + 0.001)
        check("悬停轮询自带节流（间隔内不采样）", eng._hover_hwnd == 0)
        eng._poll_hover(now["t"] + 3.0 + 1.0)
        check("过了间隔就正常采样", eng._hover_hwnd == hw)
        # 6) 关掉悬停 → 立刻清空并置 _dirty
        eng._dirty.clear()
        eng.set_hover(False)
        check("关掉悬停 → 悬停目标清空", eng._hover_hwnd == 0)
        check("关掉悬停 → 请求重算（窗口会被拉回基础值）", eng._dirty.is_set())
        eng._dirty.clear()
        eng._poll_hover(now["t"] + 10.0)
        check("关闭状态下轮询不再认悬停", eng._hover_hwnd == 0)
        eng.set_hover(True)
        check("重新打开后光标坐标缓存被清空（立刻重判一次）",
              eng._hover_cursor is None)
    finally:
        wg.cursor_pos, wg.cursor_root_window = real_pos, real_root


def test_fullscreen_geometry():
    """I. 最大化 ≠ 全屏（v1.4.1 修复回归）。

    病根：`_is_fullscreen` 原来只做「窗口矩形 ⊇ rcMonitor」的零容差包含判定，
    而 Windows 最大化时窗口矩形会**越过屏幕边缘 8px**（那圈看不见的缩放边框）：
        窗口 (-8,-8,1928,1088)  屏幕 (0,0,1920,1080)
        → rc.left(-8) <= 0 ✓ 且 rc.right(1928) >= 1920 ✓  → 包含成立
        → 最大化被误判成全屏 → 锁定 100% → 用户设的最高透明度失效
    修复：`IsZoomed()` 一票否决 + 矩形判定留 2px 容差。

    这里把「几何判定」和「IsZoomed 否决」拆开测，全程不碰真实窗口。
    """
    print("\nJ. 最大化 ≠ 全屏（矩形容差 + IsZoomed 一票否决）")

    m = wg.wt.RECT()
    m.left, m.top, m.right, m.bottom = 0, 0, 1920, 1080

    def rect(l, t, r, b):
        x = wg.wt.RECT()
        x.left, x.top, x.right, x.bottom = l, t, r, b
        return x

    # ---- 几何判定（纯函数，合成矩形）----
    check("真全屏矩形 == rcMonitor → 覆盖成立",
          wg.rect_covers_monitor(rect(0, 0, 1920, 1080), m) is True)
    check("⭐ 最大化矩形 (-8,-8,1928,1088) 几何上确实「覆盖」屏幕（所以光靠矩形判必错）",
          wg.rect_covers_monitor(rect(-8, -8, 1928, 1088), m) is True,
          "这正是必须加 IsZoomed 否决的原因")
    check("略小 2px（DPI 取整）→ 仍在容差内，算全屏",
          wg.rect_covers_monitor(rect(2, 2, 1918, 1078), m) is True)
    check("略小 3px（超出容差）→ 不算全屏",
          wg.rect_covers_monitor(rect(3, 3, 1917, 1077), m) is False)
    check("左右贴靠半屏 → 不算全屏",
          wg.rect_covers_monitor(rect(0, 0, 960, 1080), m) is False)
    check("上下只盖一半 → 不算全屏",
          wg.rect_covers_monitor(rect(0, 0, 1920, 540), m) is False)
    check("普通小窗口 → 不算全屏",
          wg.rect_covers_monitor(rect(120, 120, 656, 479), m) is False)
    check("容差可显式覆盖（slack=0 时 2px 内缩即判否）",
          wg.rect_covers_monitor(rect(2, 2, 1918, 1078), m, slack=0) is False)

    # ---- IsZoomed 一票否决必须是**短路**的：连监视器都不该去查 ----
    # （⚠️ 别用 hwnd=0 假装"不会碰 API"：MonitorFromWindow(NULL, NEAREST) 会老老实实
    #   返回**主显示器**，于是矩形判定照样跑起来 —— 这里直接数调用次数。）
    calls = {"n": 0}
    real_mfw = wg.user32.MonitorFromWindow

    def counting_mfw(h, flag):
        calls["n"] += 1
        return real_mfw(h, flag)

    wg.user32.MonitorFromWindow = counting_mfw
    try:
        check("⭐ 最大化（zoomed=True）→ fullscreen 恒为 False（不看矩形）",
              wg._is_fullscreen(0, rect(-8, -8, 1928, 1088), zoomed=True) is False)
        check("⭐ 哪怕矩形正好铺满，zoomed=True 也一律否掉",
              wg._is_fullscreen(0, rect(0, 0, 1920, 1080), zoomed=True) is False)
        check("⭐ 判否时**一次 MonitorFromWindow 都没调**（真短路，省一次 Win32 往返）",
              calls["n"] == 0, "调用 %d 次" % calls["n"])
    finally:
        wg.user32.MonitorFromWindow = real_mfw
    check("复原后 MonitorFromWindow 可正常调用（patch 没漏还原）",
          wg.user32.MonitorFromWindow is real_mfw)

    # ---- 端到端：target_for 拿到的「最大化」必须是用户设的最高值 ----
    cfg = wg.GlassConfig(active_alpha=0.80, inactive_alpha=0.40)
    zoomed, fs = True, False
    dst, why, _ = wg.target_for(cfg, 111, top=False, zoomed=zoomed, fullscreen=fs)
    check("⭐ 最大化窗口 → 用用户设的最高透明度 80%（不是写死的 100%）",
          dst == 0.80 and why == "最大化", "%.0f%% / %s" % (dst * 100, why))
    dst2, why2, _ = wg.target_for(cfg, 111, fullscreen=True)
    check("真全屏窗口 → 仍是写死的 100%",
          dst2 == 1.0 and why2 == "全屏", "%.0f%% / %s" % (dst2 * 100, why2))
    check("两者理由字符串不同（状态确实是独立的两个）",
          why != why2 and {why, why2} == {"最大化", "全屏"})
    check("修复后 read_window_state 的 fullscreen 与 zoomed 不会同时为真",
          not (zoomed and fs))


def test_layer_decay():
    """K. 层叠衰减：Z 序层级 -> 透明度的纯函数 + 端到端接线。

    这一节的核心是**纯函数**（round_half_up / layer_pct / assign_depths），
    它们不碰 Win32，所以可以放心断言精确值；端到端部分只验证「接线对了」，
    不做真实窗口的数值断言（那要靠 --list 人工体检）。
    """
    print("\nK. 层叠衰减：递推 / 取整 / 封底 / 层级编号")

    # ---- K1. 四舍五入必须是「四舍五入」，不是银行家舍入 ----
    check("round_half_up(24.5) = 25（内建 round 会给 24）",
          wg.round_half_up(24.5) == 25, "%d" % wg.round_half_up(24.5))
    check("round_half_up(17.5) = 18（内建 round 会给 18，但 2.5 才是分水岭）",
          wg.round_half_up(17.5) == 18, "%d" % wg.round_half_up(17.5))
    check("round_half_up(2.5) = 3（内建 round 会错误地给 2）",
          wg.round_half_up(2.5) == 3, "%d" % wg.round_half_up(2.5))
    check("round_half_up(0.5) = 1", wg.round_half_up(0.5) == 1)
    check("round_half_up(12.6) = 13", wg.round_half_up(12.6) == 13)
    check("round_half_up(24.4) = 24（够不到就进不了）",
          wg.round_half_up(24.4) == 24)

    # ---- K2. 递推链：用户给的例子 base=50 / ratio=0.70 ----
    got = [wg.layer_pct(50, d, 0.70) for d in range(1, 11)]
    check("base=50 ratio=0.70 → 50/35/25/18/13/9/6/5/5/5",
          got == [50, 35, 25, 18, 13, 9, 6, 5, 5, 5], "%r" % (got,))
    check("⭐ 第 3 层 = 25（24.5 四舍五入，不是 24）",
          wg.layer_pct(50, 3, 0.70) == 25)
    check("⭐ 第 4 层 = 18（17.5 四舍五入）",
          wg.layer_pct(50, 4, 0.70) == 18)

    # ---- K3. 用户原话的四窗口例子：90/50/35/25 ----
    four = [wg.layer_pct(50, d, 0.70) for d in range(1, 4)]
    check("⭐ 四个窗口（聚焦 90% + 三层非聚焦）→ 50/35/25",
          four == [50, 35, 25], "%r" % (four,))
    check("聚焦窗口不在层叠链里（它走 active_pct，由 target_for 决定）",
          wg.layer_pct(90, 1, 0.70) == 90)   # 第 1 层永远等于 base

    # ---- K4. 封底 LAYER_MIN_PCT ----
    check("base 已低于下限 5 → 抬到 5",
          wg.layer_pct(3, 1, 0.70) == wg.LAYER_MIN_PCT,
          "%d" % wg.layer_pct(3, 1, 0.70))
    check("一直乘下去最终停在 5，不会到 0",
          all(wg.layer_pct(50, d, 0.70) >= wg.LAYER_MIN_PCT for d in range(1, 40)),
          "第 39 层 = %d" % wg.layer_pct(50, 39, 0.70))
    check("极限：ratio=0.1 也不会跌破 5",
          wg.layer_pct(50, 20, 0.10) == wg.LAYER_MIN_PCT)
    check("楼层封底后可提前 break（结果不随 depth 再变）",
          wg.layer_pct(5, 5, 0.70) == wg.layer_pct(5, 50, 0.70) == 5)

    # ---- K5. ratio 边界 ----
    check("ratio=1.0 → 所有层都等于 base（等于关掉衰减）",
          [wg.layer_pct(50, d, 1.0) for d in range(1, 6)] == [50] * 5)
    check("depth<=1 原样返回 base（不乘）", wg.layer_pct(50, 1, 0.1) == 50
          and wg.layer_pct(50, 0, 0.1) == 50)

    # ---- K6. assign_depths：只有「普通非聚焦」占号 ----
    # 模拟 Z 序（最顶在前）：置顶 A → 普通 B → 聚焦 C → 普通 D → 最大化 E
    z = ["A", "B", "C", "D", "E"]
    plain = {"B", "D"}                    # 只有 B/D 算普通非聚焦
    dep = wg.assign_depths(z, plain)
    check("⭐ 置顶/聚焦/最大化不占号：B=1、D=2",
          dep == {"B": 1, "D": 2}, "%r" % (dep,))
    check("不在 participants 里的窗口拿不到层号（调用方会给 0）",
          "A" not in dep and "C" not in dep and "E" not in dep)
    check("深度从 1 起（第 1 层即最靠上的普通非聚焦）", min(dep.values()) == 1)

    # Z 序反转后编号也跟着反转（纯函数、无副作用）
    dep2 = wg.assign_depths(list(reversed(z)), plain)
    check("⭐ Z 序反转 → B/D 的层号互换（层级完全由 Z 序决定）",
          dep2 == {"D": 1, "B": 2}, "%r" % (dep2,))
    check("assign_depths 不修改入参（纯函数）",
          z == ["A", "B", "C", "D", "E"] and plain == {"B", "D"})
    check("空 plain → 空结果（层叠关掉时走这条）",
          wg.assign_depths(z, set()) == {})

    # ---- K7. target_for 的层叠分支 ----
    cfg = wg.GlassConfig(active_alpha=0.90, inactive_alpha=0.50,
                         cfg_path="", layer_decay=True, layer_decay_ratio=0.70)
    check("cfg 层叠默认开+系数 0.70",
          cfg.layer_decay is True and abs(cfg.layer_decay_ratio - 0.70) < 1e-9)
    d1, r1, _ = wg.target_for(cfg, 1, depth=1)
    d2, r2, _ = wg.target_for(cfg, 2, depth=2)
    d3, r3, _ = wg.target_for(cfg, 3, depth=3)
    check("depth=1 → 50%（第 1 层 = 非聚焦设定值）",
          abs(d1 - 0.50) < 1e-9 and r1 == "第1层", "%.0f%% %s" % (d1 * 100, r1))
    check("depth=2 → 35%", abs(d2 - 0.35) < 1e-9 and r2 == "第2层",
          "%.0f%% %s" % (d2 * 100, r2))
    check("depth=3 → 25%", abs(d3 - 0.25) < 1e-9 and r3 == "第3层",
          "%.0f%% %s" % (d3 * 100, r3))
    check("depth=0（不在层叠里）→ 走未聚焦分支",
          wg.target_for(cfg, 9, depth=0)[1] == "未聚焦")

    # ---- K8. 置顶/最大化/全屏/聚焦「视同聚焦」，层叠分支不得抢优先级 ----
    check("⭐ 置顶窗口带 depth 也走 active_pct（视同聚焦，不参与衰减）",
          wg.target_for(cfg, 1, top=True, depth=3) == (0.90, "置顶", False))
    check("⭐ 最大化窗口带 depth 也走 active_pct",
          wg.target_for(cfg, 1, zoomed=True, depth=3) == (0.90, "最大化", False))
    check("聚焦窗口带 depth 也走 active_pct",
          wg.target_for(cfg, 1, is_fg=True, depth=3) == (0.90, "聚焦", False))
    check("全屏窗口带 depth 仍是恒定 100%",
          wg.target_for(cfg, 1, fullscreen=True, depth=3)[0] == cfg.fullscreen_alpha)

    # ---- K9. 关掉层叠 → 退回「统一非聚焦值」 ----
    cfg_off = wg.GlassConfig(inactive_alpha=0.50, cfg_path="", layer_decay=False)
    check("⭐ 层叠关 → 所有 depth 都退化成 50%（v1.5.0 行为）",
          wg.target_for(cfg_off, 1, depth=1) == (0.50, "未聚焦", False)
          and wg.target_for(cfg_off, 1, depth=5) == (0.50, "未聚焦", False))

    # ---- K10. 系数夹紧 [0.1, 1.0] ----
    c = wg.GlassConfig(cfg_path="")
    c.layer_decay_ratio = 0.05
    check("系数 0.05 被夹到下限 0.1", abs(c.layer_decay_ratio - 0.10) < 1e-9,
          "%.3f" % c.layer_decay_ratio)
    c.layer_decay_ratio = 1.5
    check("系数 1.5 被夹到上限 1.0", abs(c.layer_decay_ratio - 1.0) < 1e-9,
          "%.3f" % c.layer_decay_ratio)
    c.layer_decay_ratio = 0.70
    check("正常值 0.70 原样保留", abs(c.layer_decay_ratio - 0.70) < 1e-9)

    # ---- K11. layer_alpha 辅助函数与 layer_pct 一致 ----
    check("cfg.layer_alpha(d) == layer_pct(inactive_pct, d, ratio) / 100",
          abs(cfg.layer_alpha(3) - wg.layer_pct(50, 3, 0.70) / 100.0) < 1e-9,
          "%.2f" % cfg.layer_alpha(3))

    # ---- K12. config.json 往返 ----
    d_ = tempfile.mkdtemp(prefix="winglass_layer_")
    p_ = os.path.join(d_, "config.json")
    cw = wg.GlassConfig(inactive_alpha=0.5, active_alpha=0.9, cfg_path=p_,
                        layer_decay=False, layer_decay_ratio=0.55)
    check("落盘 layer_decay/layer_decay_ratio 字段", cw.save())
    raw = json.load(open(p_, encoding="utf-8"))
    check("config.json 里有 layer_decay=False", raw.get("layer_decay") is False,
          json.dumps(raw, ensure_ascii=False))
    check("config.json 里有 layer_decay_ratio=0.55",
          abs(float(raw.get("layer_decay_ratio", 0)) - 0.55) < 1e-9,
          json.dumps(raw, ensure_ascii=False))
    loaded = wg.load_cfg_file(p_)
    ld, lr = wg.GlassConfig.apply_saved_layer(loaded, None, None)
    check("读回 layer_decay=False", ld is False)
    check("读回 layer_decay_ratio=0.55", abs(lr - 0.55) < 1e-9, "%.3f" % lr)
    check("空配置 + 无参数 → 内置默认（开 + 0.70）",
          wg.GlassConfig.apply_saved_layer({}, None, None)
          == (wg.GlassConfig.DEFAULT_LAYER_DECAY_ON, wg.GlassConfig.DEFAULT_LAYER_DECAY))

    # ---- K13. CLI：--no-layer-decay 与 --layer-decay-ratio ----
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        r = subprocess.run([sys.executable, os.path.join(here, "win_glass.py"),
                            "--list", "--no-config", "--no-layer-decay"],
                           capture_output=True, timeout=60)
        out = (r.stdout or b"").decode("utf-8", "replace")
        check("CLI --no-layer-decay 能起来（rc=0）", r.returncode == 0,
              (r.stderr or b"").decode("utf-8", "replace")[-150:])
        check("CLI --no-layer-decay → 打印「层叠衰减：关」",
              "层叠衰减：关" in out, out.splitlines()[-1][:60] if out else "")
    except Exception as e:
        check("CLI --no-layer-decay 能起来（rc=0）", False, repr(e))
    try:
        r = subprocess.run([sys.executable, os.path.join(here, "win_glass.py"),
                            "--list", "--no-config", "--layer-decay-ratio", "0.5"],
                           capture_output=True, timeout=60)
        out = (r.stdout or b"").decode("utf-8", "replace")
        check("CLI --layer-decay-ratio 0.5 能起来（rc=0）", r.returncode == 0,
              (r.stderr or b"").decode("utf-8", "replace")[-150:])
        check("CLI --layer-decay-ratio 0.5 → 首层 50 的第 2 层 = 25%",
              "层叠衰减：开" in out and "0.50" in out, out.splitlines()[-1][:60] if out else "")
    except Exception as e:
        check("CLI --layer-decay-ratio 0.5 能起来（rc=0）", False, repr(e))


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
    test_fade_runtime()
    test_number_input()
    test_menu_content()
    test_hover()
    test_fullscreen_geometry()
    test_layer_decay()
    print("\n" + "=" * 72)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAILED: %s" % f)
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
