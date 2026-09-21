# win_glass v1.4.0 — 聚焦状态判定扩展（最大化 / 置顶 / 全屏）

**日期**：2026-09-21
**变更类型**：窗口状态判定逻辑扩展（`win_glass.py` / `slider_test.py` / `hover_live_test.py` / `build.py` / `installer.py`）
**上一版**：v1.3.0（悬停提亮）

---

## 一、需求

在原逻辑（聚焦 → 最高透明度；未聚焦 → 最低透明度；悬停 → 中间值）之上扩展两条规则：

| # | 新规则 | 说明 |
|---|---|---|
| ① | **最大化窗口、置顶窗口同样视为聚焦窗口** | 遵循已配置的「最高透明度」设置（用户把最高值调到 80%，它们就跟着变 80%） |
| ② | **应用全屏运行时透明度恒为 100%** | **不受**「最高透明度」设置影响（最高值调到 5% 也仍是 100%） |

---

## 二、判定优先级链

```
全屏 (恒 100%)
  └─ 聚焦 (前台窗口)        → cfg.active_pct
      └─ 最大化 IsZoomed()  → cfg.active_pct
          └─ 置顶 TOPMOST   → cfg.active_pct
              └─ 悬停 (光标压住) → max(inactive, 中点)
                  └─ 未聚焦      → cfg.inactive_pct
```

为什么**全屏必须排在最前**：真正的全屏（F11 / 无边框全屏）`IsZoomed()` 返回 **False**，
只是矩形铺满屏幕；而最大化窗口 `IsZoomed()` 返回 **True**，矩形只覆盖 `rcWork`（不含任务栏）。
两者互斥，但一旦用「最大化」去解释全屏窗口，就会把它错当成"跟随最高值设置"的普通窗口。

---

## 三、三个判定分别用什么 API

| 概念 | 判定 | 覆盖矩形 |
|---|---|---|
| 最大化 | `user32.IsZoomed(hwnd)` | `rcWork`（不含任务栏） |
| 全屏 | 窗口矩形 ⊇ 显示器 `rcMonitor`（`MonitorFromWindow` + `GetMonitorInfoW`） | 整屏（含任务栏区域） |
| 置顶 | `GetWindowLong(GWL_EXSTYLE) & WS_EX_TOPMOST` | 无关 |

⚠️ **本次踩到的坑**：`IsZoomed` 必须显式声明 argtypes，否则 ctypes 在 64 位把 `HWND`
当 `int` 传、高 32 位被截断，**静默返回错误结果**（不报错，最难查）：

```python
user32.IsZoomed.argtypes = [wt.HWND]
user32.IsZoomed.restype  = wt.BOOL
```

新增 `read_window_state(hwnd, st=None) -> (top, zoomed, fs)` 统一封装三个判定，
并把结果写回 `WinState` 缓存，避免各处重复调用 API。

---

## 四、实现要点

### 1. `target_for()` 收成强制关键字参数

```python
def target_for(cfg, hwnd, *, is_fg=False, top=False, zoomed=False,
               fullscreen=False, hover_hwnd=0):
    if fullscreen:
        return cfg.fullscreen_alpha, "全屏", False
    if is_fg:
        return cfg.active_alpha, "聚焦", False
    if zoomed:
        return cfg.active_alpha, "最大化", False
    if top:
        return cfg.active_alpha, "置顶", False
    ...
```

改成关键字参数是**刻意的**：这些布尔量语义相近，位置传参极容易把 `top` / `zoomed`
写反，而写反的后果是"看不出错"（都是 `active_alpha`），只有测试能抓。

### 2. `fullscreen_alpha` 用独立常量，不复用 `active_pct`

```python
FULLSCREEN_ALPHA = 1.0        # 硬编码，用户不可调
```

如果复用 `cfg.active_pct`，用户把「最高透明度」调到 80% 时，"全屏恒 100%"
这条规则就会**静默失效**，而且没有任何报错。

### 3. 全屏 100% 的快捷路径：不加 `WS_EX_LAYERED`

一个本来不透明的全屏窗口要设成 100%，正确做法是**什么都不做**。
一旦给它加上 `WS_EX_LAYERED`，DWM 翻转 / 硬件叠加（fullscreen optimization）
就会被关掉，全屏视频和游戏直接掉帧：

```python
if (alpha == 255 and st.fullscreen and not st.layered_owned
        and not (_GetWindowLong(hwnd, GWL_EXSTYLE) & WS_EX_LAYERED)):
    st.applied = alpha
    return True
```

### 4. 开关（`fullscreen_lock`）改变的是**可管理集合**

`is_manageable()` 在关闭锁定时直接把全屏窗口排除：

```python
if not cfg.fullscreen_lock and _is_fullscreen(hwnd, rc):
    return False
```

集合变更不就地同步状态，**交给下一轮 `_refresh_window_list()` 全量重扫**
（≤0.5s 延迟），只保留一条集合变更路径。

> 术语澄清：`--skip-fullscreen`（复用旧名）现在的含义是**完全不接管全屏窗口**
> （原样保留），与"接管并锁 100%"互斥；已废弃的 `--no-skip-fullscreen` 保留为
> 无操作参数，避免旧脚本报错。

### 5. 新增交互入口

| 入口 | 内容 |
|---|---|
| 托盘菜单 | 新增 `CMD_FULLSCREEN = 14`「全屏窗口固定 100%」勾选项 |
| CLI | `--skip-fullscreen`（关掉锁定）、`--active-alpha` help 补注"全屏恒 100%%" |
| `--list` | 输出新增 `F/Z/T` 标记列 + 「全屏固定=100%」行 |

> ⚠️ argparse 的 help 字符串里 `%` 必须写成 `%%`，否则触发
> `ValueError: badly formed help string` ⇒ **所有 CLI 子进程 rc=1**（本次真踩到，
> 连带 9 项测试失败，其中 8 项是"CLI 起不来"，1 项是夹紧断言被误判）。

### 6. 版本号三处同改

| 文件 | 位置 |
|---|---|
| `win_glass.py` | `APP_VER = "1.4.0"` |
| `build.py` | `VER = "1.4.0"`（单点生成 VSVersionInfo） |
| `installer.py` | `APP_VER = "1.4.0"` + `APP_DESC` 更新 |

---

## 五、验证结果

### 1. `slider_test.py` — 全量断言

```
通过 215 项，失败 0 项
```

新增/关键断言：

| 断言 | 结果 |
|---|---|
| 最大化窗口视为聚焦 → 用「聚焦最高透明度」 | ✅ |
| 最高值设成 80% 时：最大化 / 置顶 / 聚焦**都**跟着变 80% | ✅ |
| ⭐ 全屏窗口恒为 100%，**不受最高值设置影响**（最高=80% 时仍 1.0） | ✅ |
| 最高值设成 5% 时全屏窗口仍是 100% | ✅ |
| 优先级：全屏 > 聚焦（同时成立时按全屏 100% 算） | ✅ |
| 优先级：全屏 > 最大化 > 置顶（同窗口最多只有一个理由） | ✅ |
| 全屏/最大化/置顶窗口都不参与悬停（只提亮不压暗） | ✅ |
| 关掉全屏锁定时全屏窗口照样算 100%（判定层不依赖开关） | ✅ |
| `fullscreen_alpha` 就是常量 1.0（不是 `active_pct`） | ✅ |
| `fullscreen_lock` 落盘 / 读回 / CLI 优先于配置 | ✅ |
| 菜单：全屏项默认勾选、关掉后文字提示「完全不接管全屏」、不再勾选 | ✅ |
| CLI 启动路径含「聚焦/最大化/置顶目标=」与「全屏固定=100%」声明 | ✅ |

### 2. `hover_live_test.py` — 真实桌面判定链（零副作用）

```
通过 22 项，失败 0 项，跳过 1 项
```

真实窗口上只读核对（手算 F/Z/T 标记 + 期望目标，逐窗口比对）：

```
   HWND       FZT  实际目标   理由     标题
   0x00010836 ---  100%     聚焦     WorkBuddy
  [PASS] 每个真实窗口的目标值/理由都与规则表一致
  [PASS] 全屏窗口（若有）目标恒为 100%，与「最高值设置」无关
  [PASS] 最高值=50% 时：全屏仍 100%，而最大化/置顶/聚焦都变 50%
  [PASS] 整轮验证中 SetLayeredWindowAttributes 调用次数 = 0   实际 0 次
  [PASS] 整轮验证中 SetWindowLongPtr(GWL_EXSTYLE) 调用次数 = 0   实际 0 次
```

> 注：本机现场只有 1 个真实受管窗口，全屏分支由**数值层**（`target_for` 纯函数 +
> 假 HWND）覆盖，而不是靠现场恰好有个全屏窗口。

---

## 六、产物

由 `build.py` 生成（`dist\`）：

| 文件 | 说明 |
|---|---|
| `win_glass.exe` | 主程序（单文件，窗口化 + 托盘） |
| `win_glass-console.exe` | 控制台诊断版（`--list` / `--verbose`） |
| `win_glass_setup_v1.4.0.exe` | **安装包**（内嵌上面两个 exe，双击即装/卸） |

安装路径 `%LOCALAPPDATA%\Programs\win_glass`（免 UAC）。
配置 `%LOCALAPPDATA%\win_glass\config.json`。

### 产物核对（实际跑的）

| 检查项 | 结果 |
|---|---|
| `win_glass-console.exe --version` | `win_glass 1.4.0` ✅ |
| `win_glass-console.exe --list` | 输出优先级链 + `FZT` 标记列 + 「全屏固定=100%」 ✅ |
| 三个 exe 的 `FileVersion` / `ProductVersion` | 全部 `1.4.0.0` ✅ |
| `win_glass_setup_v1.4.0.exe --help` | 正常打印「win_glass 1.4.0 安装/卸载程序」✅ |

> 版本资源用新增的 `check_verinfo.py` 读（纯 ctypes + `version.dll`）——本轮 PowerShell
> 工具**全程拿不到 stdout**（连 `Write-Output` 都空），改用 Python 更可靠。
> ⚠️ 读 `VS_FIXEDFILEINFO` 时版本号在 **[2]/[3]** 两个 DWORD，前两个是
> `dwSignature`(0xFEEF04BD) / `dwStrucVersion`；按 [0]/[1] 读会打出 `65263.1213.1.0`。

### 打包产物自检（关键证据：把最高值压到 80% 再跑）

```
$ win_glass-console.exe --self-test --inactive-alpha 40 --active-alpha 80 --fade-ms 300
[self-test] 滑块取值：非聚焦=40%  聚焦/最大化/置顶=80%  （均为整数百分比）
[self-test] 全屏取值：100%（恒定，不受聚焦最高透明度 80% 影响）   ← ★ 需求②成立
[self-test] 悬停取值：60%（最高/最低插值 0.50）
[self-test] 播放 300ms 缓动   80% -> 40% -> 60% -> 40% -> 100% -> 40% -> 80%
           204 196 178 153 128 110 102 106 115 128 140 149 153 ... 255 244 215 178 142 113 102 110 128 153 178 196
                                          ↑ 40%        ↑ 60%        ↑ 100%（全屏段）
```

「最高值 = 80%」时：聚焦/最大化/置顶段读回 **204（=80%）**，而全屏段读回 **255（=100%）**
且不随 80% 变动 —— 需求 ① 与 ② 在**真实 exe**上同时得到验证。

---

## 七、遗留 / 注意

1. **本机常驻旧版实例**（安装版 `win_glass.exe`），与现场 alpha 测试互相抢写 ⇒
   `e2e_test.py` / `robustness_test.py` 本轮未跑，用零副作用判定层验证替代。
   装新包前建议先在托盘菜单退出旧实例（或任务管理器结束进程）。
2. **分层位归属**：只有"我加的分层位"才由我还原（`st.layered_owned`）。别人的
   分层窗口退出时保持原样，全屏快捷路径同理。
3. `--no-skip-fullscreen` 已成为无操作参数（兼容旧脚本），新脚本请用
   `--skip-fullscreen` 表达"完全不接管全屏"。
