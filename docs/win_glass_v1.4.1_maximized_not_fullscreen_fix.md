# win_glass v1.4.1 — 修复：最大化窗口被误判为「全屏」

**日期**：2026-09-21
**现象**：任何窗口一旦最大化，透明度就变成 100%，用户设的「最高透明度」失效
**性质**：v1.4.0 引入的回归（全屏判定误判）
**改动文件**：`win_glass.py`（核心）· `slider_test.py` · `hover_live_test.py` · `fs_probe.py`（新增取证脚本）· `build.py` · `installer.py`

---

## 一、根因

`_is_fullscreen()` 原来只做一件事：**判断窗口矩形是否包含屏幕矩形**，且**零容差**。

```python
# 旧实现（有 bug）
def _is_fullscreen(hwnd, rc):
    ...
    m = mi.rcMonitor
    return (rc.left <= m.left and rc.top <= m.top
            and rc.right >= m.right and rc.bottom >= m.bottom)
```

问题在于 **Windows 最大化窗口的矩形本来就会"越出"屏幕边缘**：

窗口最大化时，Windows 要让窗口的**可见边框**正好贴到屏幕边，而窗口还带着一圈
看不见的缩放边框（`SM_CXSIZEFRAME` + `SM_CXPADDEDBORDER`），所以矩形会被**朝外撑开**。

本机实测（`fs_probe.py`，Windows / 1920×1080）：

| 状态 | IsZoomed | 窗口矩形 | 窗口 − 屏幕 |
|---|---|---|---|
| 普通窗口 | False | (120, 120, 656, 479) | L+120 T+120 R−1264 B−601 |
| **最大化** | **True** | **(−8, −8, 1928, 1088)** | **L−8 T−8 R+8 B+8** |
| 真全屏（F11） | False | (0, 0, 1920, 1080) | L+0 T+0 R+0 B+0 |

于是对最大化窗口逐条代入旧判定：

```
rc.left(-8)    <= m.left(0)      →  ✓
rc.top(-8)     <= m.top(0)       →  ✓
rc.right(1928) >= m.right(1920)  →  ✓      ← 越出反而"帮助"通过了包含判定
rc.bottom(1088)>= m.bottom(1080) →  ✓
```

**包含判定必然成立 → 最大化被当成全屏 → `FULLSCREEN_ALPHA = 1.0` → 100%。**

越出屏幕这件事不是异常，反而是**破坏力来源**：它让"覆盖屏幕"这个条件变得更容易成立。

### 加重因素：本机 `rcWork == rcMonitor`

任务栏设成自动隐藏时，`rcWork` 与 `rcMonitor` **完全相等**（本机实测两者都是
`(0,0,1920,1080)`）。所以 v1.4.0 注释里写的"最大化只覆盖 rcWork、全屏覆盖 rcMonitor"
这条区分思路**在自动隐藏任务栏的机器上直接失效** —— 不能再依赖它。

---

## 二、修复思路

**核心：把「最大化」和「全屏」当成两个互斥的独立状态，用 `IsZoomed()` 一票否决。**

真全屏的 `IsZoomed()` 是 **False** —— F11、无边框全屏、游戏全屏都只是把矩形撑满，
**不走 `SW_MAXIMIZE`**；而用户按最大化按钮的窗口 `IsZoomed()` 一定是 **True**。
这正是两者能干净分开的依据。

### 1. `_is_fullscreen()` 增加 `zoomed` 前置否决（关键改动）

```python
def _is_fullscreen(hwnd, rc, *, zoomed: bool = None) -> bool:
    if zoomed is None:
        zoomed = bool(user32.IsZoomed(hwnd))
    if zoomed:
        return False            # ← 最大化永远不是全屏（短路，连监视器都不查）
    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    ...
    return rect_covers_monitor(rc, mi.rcMonitor)
```

`zoomed` 设计成可选关键字参数：调用方已有该值时直接传入，省一次 Win32 往返
（`read_window_state` 就是这么用的）。

### 2. 矩形判定抽成纯函数并留容差

```python
FS_SLACK = 2    # 只朝"略小"方向放宽，不朝"略大"方向放宽

def rect_covers_monitor(rc, m, slack=FS_SLACK) -> bool:
    return (rc.left <= m.left + slack and rc.top <= m.top + slack
            and rc.right >= m.right - slack and rc.bottom >= m.bottom - slack)
```

两个目的：
- **可测**：不碰任何 Win32 调用，测试里直接喂合成矩形（含那个经典的
  `(-8,-8,1928,1088)` 最大化矩形），把"几何判定"和"IsZoomed 否决"分开验证。
- **容差**：不同 DPI 缩放 / 进程 DPI 感知级别会让真全屏窗口的矩形差一两像素，
  "比屏幕小 1px"显然不该被踢出全屏。

### 3. `read_window_state()` 复用已取到的 `IsZoomed`

```python
zoomed = bool(user32.IsZoomed(hwnd))      # 一轮只取一次
top, zoomed, fs = ...                     # zoomed 进缓存
fs = _is_fullscreen(hwnd, rc, zoomed=zoomed)
```

---

## 三、涉及的关键代码位置

| 位置 | 改动 |
|---|---|
| `win_glass.py` `FS_SLACK = 2` | 新增容差常量（紧邻 `FULLSCREEN_ALPHA`） |
| `win_glass.py` `rect_covers_monitor()` | **新增**纯几何判定函数（可测） |
| `win_glass.py` `_is_fullscreen()` | ⭐ **核心修复**：加 `zoomed` 一票否决 + 用 `rect_covers_monitor` |
| `win_glass.py` `read_window_state()` | 把已取到的 `zoomed` 传给 `_is_fullscreen`（省一次调用）；更新 docstring |
| `win_glass.py` 模块头「全屏窗口」段落 | 补写"最大化 ≠ 全屏"与越出屏幕的说明 |
| `win_glass.py` `is_manageable()` | **无需改动**（它只在关掉全屏锁定时调 `_is_fullscreen(hwnd, rc)`，新签名向后兼容） |
| `win_glass.py` `target_for()` | **无需改动**（分支顺序本来就是全屏→聚焦→最大化→置顶，只是之前喂进来的 `fullscreen` 是错的） |
| 版本号三处 | `win_glass.py:APP_VER` / `build.py:VER` / `installer.py:APP_VER` +`APP_DESC` → `1.4.1` |

> 这也解释了为什么单元测试当时没抓住这个 bug：`target_for()` 是纯函数，测试一直
> 直接喂 `fullscreen=True`；而**判定层**（`IsZoomed` + 矩形）从未拿真实最大化窗口
> 验过。所以这次补了 `fs_probe.py` 用真窗口取证。

---

## 四、验证

### 1. `fs_probe.py` — 真实窗口取证（修复前后对比）

自建 tkinter 窗口，依次摆成 普通 / 最大化 / 真全屏 三态：

```
[B. 最大化]  IsZoomed = True
    窗口矩形 = (-8, -8, 1928, 1088)      监视器 = (0, 0, 1920, 1080)
    窗口-屏幕 = L-8 T-8 R+8 B+8
    修复前: _is_fullscreen() = True   → target_for = 100%  理由=全屏   ❌
    修复后: _is_fullscreen() = False  → target_for =  80%  理由=最大化 ✅
[C. 真全屏]  IsZoomed = False
    窗口矩形 = (0, 0, 1920, 1080)
    修复前后: _is_fullscreen() = True  → target_for = 100%  理由=全屏   ✅
```

测试配置：最高 = 80%，最低 = 40%，全屏恒 100%。

### 2. `slider_test.py` — 231 PASS / 0 FAIL

新增 **J 段「最大化 ≠ 全屏」** 16 项：

| 断言 | 结果 |
|---|---|
| 真全屏矩形 == rcMonitor → 覆盖成立 | ✅ |
| ⭐ 最大化矩形 `(-8,-8,1928,1088)` **几何上确实"覆盖"屏幕**（所以光靠矩形判必错） | ✅ |
| 略小 2px（DPI 取整）→ 在容差内，算全屏 | ✅ |
| 略小 3px（超出容差）→ 不算全屏 | ✅ |
| 左右贴靠半屏 / 只盖一半 / 普通小窗口 → 都不算全屏 | ✅ |
| ⭐ 最大化（`zoomed=True`）→ fullscreen 恒 `False`，不看矩形 | ✅ |
| ⭐ 判否时**一次 `MonitorFromWindow` 都没调**（真短路） | ✅ 调用 0 次 |
| ⭐ 最大化窗口 → 用用户设的**最高透明度 80%**（不是写死的 100%） | ✅ |
| 真全屏窗口 → 仍是写死的 100% | ✅ |
| 两者理由字符串不同（状态确实独立） | ✅ |

> ⚠️ 写测试时踩了个自坑：原以为传 `hwnd=0` 就能"零 API 调用"，结果
> `MonitorFromWindow(NULL, MONITOR_DEFAULTTONEAREST)` 会**老老实实返回主显示器**，
> 矩形判定照样跑。改成 monkeypatch 计数 `MonitorFromWindow` 调用次数，才真正证明短路。

### 3. `hover_live_test.py` — 24 PASS / 0 FAIL / 1 SKIP

G 段（真实窗口判定链）新增不变量：

| 断言 | 结果 |
|---|---|
| ⭐ 没有任何窗口同时被判为「最大化」和「全屏」（F 与 Z 互斥） | ✅ 本机 最大化=0 全屏=0 |
| ⭐ 被判为最大化的窗口目标 = 用户设的最高值（不是写死的 100%） | ✅ |
| 整轮 `SetLayeredWindowAttributes` / `SetWindowLongPtr` 调用次数 = 0 | ✅ 均 0 次 |

### 4. `fs_e2e.py` — 端到端：让**打包好的 exe** 给真实窗口分类

自建窗口依次摆四个状态，每段都调 `dist\win_glass-console.exe --list` 取回判定：

| 阶段 | HWND | `--list` 输出 | 期望 |
|---|---|---|---|
| A. 普通窗口 | 0x0046174C | `40%  未聚焦  ---` | ✅ |
| **B. 最大化** | — | **`80%  最大化  -Z-`** | ✅ **不是 100%**，Z 置位、F 不置位 |
| C. 真全屏 | 0x0078100A | `100%  全屏  F--` | ✅ F 置位、Z 不置位 |
| D. 全屏退回普通 | 0x0048174C | `40%  未聚焦  ---` | ✅ |

配置：最高 80% / 最低 40% / 全屏恒 100%。标记链 `--- → -Z- → F-- → ---`。

> ⚠️ 写这个脚本踩到两个坑（都不是产品 bug）：
> ① **Tk 切 `-fullscreen` 时会重建顶层窗口，HWND 变了**（0x0046174C → 0x0078100A），
> 所以每段都必须重新取句柄，不能用开头那个去找行；
> ② 测试窗口自己就是焦点窗口，所以「聚焦」会盖过「最大化」—— 两者用同一个
> 最高透明度，不影响断言，但说明**断言要盯住"绝不能是 100%"**，这才与焦点无关。

### 5. 打包产物

| 文件 | 大小 | 版本资源 |
|---|---|---|
| `win_glass.exe` | 11.07 MB | 1.4.1.0 |
| `win_glass-console.exe` | 11.08 MB | 1.4.1.0 |
| **`win_glass_setup_v1.4.1.exe`** | 29.82 MB | 1.4.1.0 |

`fs_probe.py` / `check_verinfo.py` / `fs_e2e.py` 都留在 `win_glass\` 下，以后改判定逻辑可直接复用。

---

## 五、修复后的完整判定链

```
全屏 (不是最大化 且 矩形覆盖 rcMonitor)  → 恒 100%
  └─ 聚焦（前台窗口）                    → cfg.active_pct
      └─ 最大化 IsZoomed()               → cfg.active_pct   ← 修复点：不再串到全屏
          └─ 置顶 WS_EX_TOPMOST          → cfg.active_pct
              └─ 悬停（光标压住）         → max(inactive, 中点)
                  └─ 未聚焦               → cfg.inactive_pct
```

「最大化」与「全屏」现在是**两个互斥的独立状态**：
- 最大化 → 跟随用户设的「最高透明度」，改了滑块立刻跟动
- 全屏 → 恒定 100%，不受「最高透明度」影响
