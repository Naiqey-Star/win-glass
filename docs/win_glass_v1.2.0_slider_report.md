# win_glass v1.2.0 —— 滑块改音量条样式 & 修「拖动不重绘」的静默失败

> 这一版做三件事：把菜单滑块换成 Windows 任务栏音量条的样子、
> 修掉「鼠标停在滑块上拖动时数值和进度条不刷新」的 bug、新增「渐隐时间」调节。
>
> 其中那个 bug 是典型的**静默失败**：不打日志、不报错、消息也照样收得到，
> 只是**重绘打在了无关窗口上**。本文把根因和定位手法记下来。

---

## 一、要解决的问题

| 需求 | 说明 |
| --- | --- |
| 滑块换样式 | 与 Windows 任务栏音量滑块的外观 / 交互一致 |
| 实时跟手 | 拖动过程中数值与进度条**立即**重绘，不能等指针移开 |
| 新增渐隐时间 | 可输入数值，单位 ms |
| 版本号 | 1.1.0 → 1.2.0 |

## 二、外观：从「分段条」到「细轨道 + 圆形手柄」

v1.1.0 是分段式细格条（一格 1%，91/96 格）。v1.2.0 改成音量条的画法：

| 元素 | 画法 | 参数 |
| --- | --- | --- |
| 轨道 | `RoundRect` 圆头胶囊，`NULL_PEN` 只填充 | 厚 4px，两端各留 15px |
| 已填充 | 同款胶囊，从最左端画到**手柄圆心** | 颜色 = 系统强调色 |
| 手柄 | `Ellipse` 圆，半径随状态变 | 常态 R=7，悬停/拖动/选中 R=9 |
| 手柄描边 | 先画 R 的深色圆，再叠 R-1 的本体 | 做出 1px 描边感 |

几何上有一个**必须两端内缩**的点：手柄行程限制在 `[left+INSET, right-INSET]`，
`SLIDER_THUMB_INSET = SLIDER_THUMB_R_HOT = 9`。不内缩的话，滑到 0% / 100% 时
手柄会被菜单项边缘切掉半圆（因为 46px 高、手柄直径 18px）。

配色跟随系统强调色，读取顺序：

```
HKCU\Software\Microsoft\Windows\DWM\AccentColor          （低 24 位即 COLORREF）
  -> HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Accent\AccentColorMenu
  -> DwmGetColorizationColor
  -> 默认蓝 #2F6FE4
```

深色主题下轨道底 / 描边换用对比色；**选中行**（整行强调色背景）单独一套配色，
否则手柄和填充会糊在背景里看不见。

### 取值精度没有变

仍然是 **1% 步进、整数显示**，三种调法全部保留：按住拖动 / 滚轮 ±1% / 左右方向键 ±1%。
绘制（百分比 → 圆心 x）与命中判定（x → 百分比）**共用同一组坐标函数**
`_track_geom` / `pct_to_thumb_x` / `x_to_pct`，否则会出现「点在这里、手柄停在那里」。

## 三、根因：重绘打在了**无关窗口**上（静默失败）

### 症状

- 按住滑块拖动，**数值文字和进度条都不动**；
- 指针一移出菜单项，数值「啪」地跳到正确位置。

### 为什么「移出去就好了」

指针离开会触发菜单自己的高亮切换，菜单窗口因此收到一次正常的 `WM_PAINT` ——
**看起来像补上了，其实我们的重绘指令从头到尾没生效过**。这个假象是排障时最大的干扰。

### 真相

`SetWindowsHookExW(WH_MSGFILTER)` 的回调里，`MSGF_MENU` 分支能拿到
`msg.hwnd`，旧代码**无条件**把它缓存成「菜单窗口」：

```python
# 旧代码（错）
if not self._menu_hwnd and msg.hwnd:
    self._menu_hwnd = msg.hwnd          # ← 不一定是菜单窗口！
```

而 `MSGF_MENU` 回调收到的 `hwnd` **不保证是菜单窗口** —— 它是
「当前线程正在处理的这条消息所属的窗口」。实测钩子看到的第一条消息，
`hwnd` 是 shell 的 `SystemUserAdapterWindowClass`（一个和菜单毫无关系的辅助窗口），
于是它被缓存下来了。

后果：后续 `InvalidateRect` / `RedrawWindow` 全部打在那个无关窗口上。
**不报错、不返回失败、也不打日志**，菜单永远不会重绘。

### 修法

只接受**窗口类为 `#32768`**（Win32 菜单窗口类）的句柄，并且逐级校验回填：

```python
MENU_CLASS = "#32768"

# 1) 钩子里只认菜单类
if not self._menu_hwnd and msg.hwnd and _win_class(msg.hwnd) == MENU_CLASS:
    self._menu_hwnd = msg.hwnd

# 2) 重绘前再校验一遍：缓存 -> FindWindowW("#32768") -> 按项中心点 WindowFromPoint
hwnd = self._resolve_menu_hwnd(rc)
```

同时把重绘换成**强制同步**的 `RedrawWindow`：

```python
user32.RedrawWindow(hwnd, byref(local), None,
                    RDW_INVALIDATE | RDW_UPDATENOW)
```

`RedrawWindow(RDW_UPDATENOW)` 比 `InvalidateRect` + `UpdateWindow` 可靠：
菜单窗口的 `WM_PAINT` 有自己的节奏，`RDW_UPDATENOW` 会**立刻同步**画一遍。

### 怎么定位的

1. 加一个 `WIN_GLASS_DEBUG_REDRAW=1` 开关（源码里的 `DBG_REDRAW`），
   每次重绘打印 `hwnd / class / MapWindowPoints 结果 / 累计 WM_DRAWITEM 次数`。
2. 修复前：拖动过程中 `draw_total` **纹丝不动**（一直是 3），
   且打印出来的 `class=SystemUserAdapterWindowClass` ← 一眼就看出打错窗口了。
3. 修复后：`class=#32768`，`draw_total` 随拖动一路 5 → 7 → 9 → 11 → 15。

### 回归测试：`menu_live_test.py`

光有单测（`slider_test.py` 的离屏绘制段）**抓不到这个 bug** —— 它测的是
「画得对不对」，而这里的问题根本**没画**。

所以专门写了 `menu_live_test.py`：真弹菜单、用合成鼠标按住拖动、
**用 `BitBlt` 抓像素比对拖动前后的差异**，断言：

| 断言 | 阈值 |
| --- | --- |
| 拖动时**数值文字**区域像素发生变化（指针未离开该项） | 变化像素 ≥ 8 |
| 拖动时**进度条**区域像素发生变化（指针未离开该项） | 变化像素 ≥ 8 |
| 整场拖动菜单始终开着 | — |
| 点菜单外部正常关闭 | — |

> 抓图用 `GetDC(NULL)` + `CreateCompatibleDC` + `BitBlt` + `GetDIBits`，
> **不用 PIL 的 `ImageGrab`**：实测 PIL 抓图会干扰合成鼠标的时序，
> 同一份代码两次跑出不同结果（一次 7/7、一次只挂值断言）。纯 `BitBlt` 是只读的，确定性好。

有效性验证：把 `_redraw_item` 猴子补丁成空函数，该测试立刻报 2 个 FAIL ——
说明它**确实能抓住**这个 bug，而不是碰巧通过。

## 四、新增「渐隐时间」（ms）

| 项 | 设计 |
| --- | --- |
| 入口 | 托盘右键菜单「渐隐时间…\t500 ms」（`\t` 后面那段菜单会自动右对齐，正好和滑块右边的百分比列对齐） |
| 对话框 | 手搓的 `NumberInputBox`：`CreateWindowExW` + 嵌套 `GetMessageW` 循环 |
| 范围 | 1 ~ 5000 ms，默认 500；越界自动夹紧，填非数字退回原值，取消/关窗不动作 |
| 持久化 | `config.json` 新增键 `fade_ms`；优先级 **`--fade-ms` > 配置文件 > 默认 500** |

### 两个容易踩的点

**1) 改完必须立即生效，不能等下一次切换。**
只写配置是不够的：正在跑的缓动如果不重排时间轴，用户改完看不到差别，会以为没生效。
`set_fade_ms` 的做法是**保持「已完成进度」不变**，只把 `t0` 往回推到与新时长匹配的位置：

```python
prog = (now - st.t0) / st.dur            # 已完成比例
st.dur = new_dur                          # 换新时长
st.t0 = now - prog * new_dur              # 进度不变，反推新起点
```

**2) 对话框不能用 `PostQuitMessage`。**
这条线程同时还跑着托盘的 `GetMessage` 循环，`PostQuitMessage` 会把**整个程序**退掉。
所以嵌套循环靠 `IsDialogMessageW` 处理 Enter / Esc / Tab，关闭时用 `DestroyWindow`
唤醒外层循环。`slider_test.py` 的 H 段据此断言「关窗后进程仍存活」。

## 五、顺手修掉的测试脆弱性

| 问题 | 表现 | 修法 |
| --- | --- | --- |
| 期望值写死 | `e2e_test.py` 断言「100% ↔ 40%」、`slider_test.py` CLI 段断言「40%/100%」，用户一拖滑块就假失败 | 从配置文件 / 命令行实参**推导**期望值 |
| 测试写坏用户配置 | `e2e_test.py` / `robustness_test.py` 不带 `--no-config`，跑一次就覆盖真实 `config.json` | 统一加 `--no-config` |
| 等菜单用固定 `sleep` | 桌面一忙 1.2s 不够，菜单还没出来就断言 → flake | 改成轮询窗口类 `#32768`，最多等 6s |
| 测试沿用旧几何 | 改成音量条后，测试仍按「分段条满宽」算期望值 | 期望值公式跟着 `SLIDER_THUMB_INSET` 走 |
| 绘制/测试各写一遍公式 | `slider_test.py` 自己抄了一份轨道中线公式，常量删掉后扫到一条空行 | 抽出 `_track_center_y(rc)`，绘制与测试共用 |

## 六、验证

| 测试 | 内容 | 结果 |
| --- | --- | --- |
| `slider_test.py` | 取值量化与夹紧（含渐隐 1~5000ms）/ x→百分比映射 / **离屏真画 + `GetPixel` 反查「填充是否止于手柄」「手柄是否为圆」「悬停是否放大」「轨道是否为细条」** / 配置往返与节流 / 滚轮与点击字段 / **数值输入框端到端** / **菜单项逐项核对** | **153 PASS / 0 FAIL** |
| `menu_live_test.py` | **指针停在菜单项上拖动时数值文字与进度条是否实时重绘**（`BitBlt` 像素差异）+ 菜单不关闭 + 点外部关闭 | **7 PASS / 0 FAIL** |
| `menu_e2e_test.py` | 真弹菜单并截图 / 合成鼠标拖动 / 方向键微调 / 落盘整数 / 点外部关闭 | **18 PASS / 0 FAIL** |
| `robustness_test.py` | 参数边界 / 零窗口 / 30s 长跑 / 强杀还原 / 托盘 / 优雅退出 | **27 PASS / 0 FAIL** |
| `e2e_test.py` | 真实焦点切换，透明度 100% ↔ 40% | **PASS** |

绘制层的几条关键实测值（来自 `slider_test.py` C 段）：

```
pct=  5  填充止于手柄 (圆心 24..右缘 31)   实测 27
pct= 50  填充止于手柄 (圆心150..右缘157)   实测 153
pct= 95  填充止于手柄 (圆心276..右缘283)   实测 279
手柄中线高度 ≈ 直径      实测 13px（直径 14px）
靠边处比中线矮（圆形而非矩形）  中线 13px vs 边缘 3px
hot 手柄比常态更大        hot 17px vs 常态 13px
轨道确实是细条           实测 3px（RoundRect 底边不填，b-t=4 画 3 行）
pct=5  右侧空轨道 253 / 270 px
pct=95 右侧空轨道 1 px
```

## 七、观感确认

`probe_slider_render.py` 把 7 种状态离屏渲染成一张 PNG（`test_out/slider_render.png`），
不弹菜单、不动桌面窗口：

```
常态 5%（最左端）        常态 40%（默认）        常态 95%（最右端）
聚焦滑块 100%            悬停/拖动 60%（手柄放大）
选中行 60%（强调色背景）  禁用 40%
```
