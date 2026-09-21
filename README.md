# win-glass · Windows 窗口聚焦透明度工具

> **让当前正在用的窗口保持清晰，其余窗口自动变半透明。**
> 纯 Python 标准库实现（`ctypes`），不依赖 pywin32，无后台服务，退出即还原。

你有没有过这种体验：屏幕上开了十几个窗口，想看清当前在用的那个，却总被后面的窗口干扰？

**win-glass** 就是解决这个问题的：它常驻在系统托盘，实时盯着窗口焦点——

| 窗口状态 | 透明度 |
| --- | --- |
| **正在使用的窗口**（有焦点） | **100%** 完全不透明 |
| **置顶窗口**（Always on Top） | **100%** 完全不透明 |
| 其他所有窗口 | **40%** 半透明（可调） |

焦点一换，透明度在 **500ms 内平滑过渡**，不会生硬地跳变。

![工作原理](assets/how-it-works.svg)

---

## 目录

- [下载安装](#下载安装)
- [快速上手](#快速上手)
- [系统托盘怎么用](#系统托盘怎么用)
- [命令行参数](#命令行参数)
- [它是怎么做到的](#它是怎么做到的)
- [常见问题](#常见问题)
- [已知限制](#已知限制)
- [从源码构建](#从源码构建)
- [项目结构](#项目结构)
- [许可](#许可)

---

## 下载安装

从 [**Releases 页面**](../../releases/latest) 下载 `win_glass_setup_v1.1.0.exe`，双击即可。

| 项目 | 说明 |
| --- | --- |
| 系统要求 | Windows 10 / 11（64 位） |
| 需要 Python 吗 | **不需要**，安装包里已包含运行时 |
| 需要管理员权限吗 | **不需要**，不弹 UAC |
| 安装位置 | `%LOCALAPPDATA%\Programs\win_glass`（用户目录） |
| 卸载 | 控制面板「程序和功能」→ win_glass；或直接运行安装目录里的 `uninstall.exe` |

安装完成后，在开始菜单搜索 **win_glass** 打开。

> **安装包本身是命令行程序**，双击后会有一个黑窗口显示安装进度，这是正常的；
> 装完之后日常使用的 `win_glass.exe` **完全没有任何窗口**，只会在右下角托盘出现一个图标。

---

## 快速上手

1. 双击 `win_glass_setup_v1.1.0.exe` 完成安装
2. 开始菜单搜索 `win_glass` 启动
3. 右下角系统托盘出现图标 → **它已经在工作了**
4. 随手指点几个窗口，你会看到：你正在用的那个是清晰的，其他都变淡了

想让它开机自动运行？用管理员以外的普通身份执行：

```bat
win_glass_setup_v1.1.0.exe --autostart
```

取消开机自启：`win_glass_setup_v1.1.0.exe --no-autostart`

---

## 系统托盘怎么用

日常只需要用托盘图标，不用记命令：

| 操作 | 效果 |
| --- | --- |
| **左键单击** | 暂停 / 继续（暂停时**所有窗口立刻恢复 100%**） |
| **右键** | 弹出菜单：暂停、立即恢复、**两个透明度滑块**、打开日志、退出 |

托盘图标**不会出现在任务栏，也不会出现在 Alt+Tab 里**，不占地方。

> 退出时（无论点「退出」、注销还是关机）程序都会把**所有窗口的透明度和样式原样还原**。
> 万一遇到异常导致没还原，重新运行一次再正常退出即可。

### 右键菜单里的两个滑块

在菜单里直接调透明度，不用记命令、也不用重启：

```
┌──────────────────────────────┐
│ 暂停（所有窗口恢复 100%）        │
│ 立即把所有窗口恢复 100%          │
├──────────────────────────────┤
│ 非聚焦最低透明度          40%  │  ← 拖动 / 滚轮 / ←→ 微调
│ ▮▮▮▮▮▮▮▮▮▮▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯ │
│ 聚焦最高透明度           100%  │
│ ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮ │
├──────────────────────────────┤
│ 打开日志                       │
│ 退出（还原全部窗口）             │
└──────────────────────────────┘
```

| 滑块 | 作用 | 范围 | 默认 |
| --- | --- | --- | --- |
| **非聚焦最低透明度** | 没在用的窗口淡化到多少 | **5% ~ 95%** | 40% |
| **聚焦最高透明度** | 你正在用的窗口清晰到多少 | **5% ~ 100%** | 100% |

- **分段式显示**：一格 = 1%，条上被点亮多少格就是多少百分比，一眼能数出来
- **步进恒为 1%**，数值始终是**整数**，不会出现小数点
- 三种调法：**按住拖动**、**鼠标滚轮**（±1%）、**左右方向键**（±1%，想精确到某个值时最方便）
- **改完自动记住**：写入 `%LOCALAPPDATA%\win_glass\config.json`，下次开机照旧
- 拖动时菜单**不会关**，松手后接着点别的项或点外面关闭

> 注意：滑块的改动会**立刻**作用到桌面窗口上——这是设计如此，所见即所得。
> 如果不希望留下记录，用 `--no-config` 启动，改动就只在本次运行有效。

---

## 命令行参数

窗口化版本没有控制台，所以想看输出请用随包安装的 **`win_glass-console.exe`**（同一份程序，带控制台）。
位置：`%LOCALAPPDATA%\Programs\win_glass\win_glass-console.exe`

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--inactive-alpha <0.05~0.95>` | `0.40` | 未聚焦窗口的透明度（也接受 `5~95` 这种整数百分比写法） |
| `--active-alpha <0.05~1.0>` | `1.00` | 聚焦 / 置顶窗口的透明度（也接受 `5~100`） |
| `--no-config` | 关 | **既不读也不写**配置文件，滑块改动只在本次运行有效 |
| `--save-config` | 关 | 把本次命令行参数**写入配置文件**后继续运行 |
| `--fade-ms <毫秒>` | `500` | 渐变时长，设 `0` 立刻生效无动画 |
| `--fps <帧率>` | `60` | 动画帧率 |
| `--scan <秒>` | `0.15` | 焦点变化检测间隔 |
| `--rescan <秒>` | `0.50` | 窗口列表全量重扫间隔 |
| `--exclude <类名,...>` | 空 | **额外**排除的窗口类名，逗号分隔 |
| `--no-skip-fullscreen` | 关 | 不跳过全屏窗口（默认会跳过全屏，避免看电影/玩游戏时被改） |
| `--skip-foreign-layered` | 关 | 跳过那些**自己已经在用**分层透明度的窗口（如 Electron 应用） |
| `--no-restore` | 关 | 退出时**不**还原透明度（一般不要用） |
| `--no-tray` | 关 | 不创建托盘图标（纯命令行运行） |
| `--log <路径>` | `%LOCALAPPDATA%\win_glass\win_glass.log` | 日志文件位置 |
| `--duration <秒>` | `0`（常驻） | 跑指定秒数后自动退出并还原 |
| `-v`, `--verbose` | 关 | 每次状态变化都打印 |
| `--list` | — | **只列出**当前窗口及各自的目标透明度，不做任何修改 |
| `--self-test` | — | 用自带的测试窗口验证透明度链路是否正常 |
| `--version` | — | 打印版本号 |
| `-h`, `--help` | — | 帮助 |

常用示例：

```bat
:: 想让背景更淡一点
win_glass-console.exe --inactive-alpha 0.25

:: 想让过渡更快
win_glass-console.exe --fade-ms 200

:: 想先看看它会接管哪些窗口，再决定要不要排除
win_glass-console.exe --list

:: 排除某个软件的窗口
win_glass-console.exe --exclude MyAppClass,AnotherClass

:: 跑 30 秒自动退出，用来快速试效果
win_glass-console.exe --duration 30

:: 临时试一下、不留记录（滑块改动也只在本次运行生效）
win_glass-console.exe --no-config --inactive-alpha 0.25

:: 把这次的设置固化成默认值
win_glass-console.exe --save-config --inactive-alpha 0.25 --active-alpha 1.0
```

---

## 它是怎么做到的

用一句话概括：**给窗口加上 `WS_EX_LAYERED` 扩展样式，再用 `SetLayeredWindowAttributes` 设置整窗 alpha**。

```
① 用 EnumWindows 枚举所有顶层窗口
② 过滤掉不该动的（桌面、任务栏、输入法、提示框…）
③ 判断状态：有焦点 / 置顶 → 目标 100%；其余 → 目标 40%
④ 状态变了就起一段 500ms 缓动动画，逐帧写入 alpha
⑤ 退出时把 alpha 与扩展样式还原
```

技术上有几个容易踩的坑，这个项目都处理了：

| 坑 | 后果 | 处理方式 |
| --- | --- | --- |
| 64 位下窗口句柄被截断 | `SetWindowLong` 失效甚至崩溃 | 统一用 `GetWindowLongPtrW` / `SetWindowLongPtrW`，32 位才回退 |
| `SetLayeredWindowAttributes` 的 alpha 参数被截断 | 255 变成 -1，效果错乱 | 该参数实际是 `BYTE`，ctypes 里按 `DWORD` 声明并由低位取值 |
| 加了扩展样式却不生效 | 窗口毫无变化 | 首次挂 `WS_EX_LAYERED` 后补一次 `SetWindowPos(SWP_FRAMECHANGED)`；**只在首次**，每帧都调会闪 |
| Electron / Chromium 应用自己已在用分层 | 覆盖了它的透明度、退出还原不回去 | 接管前先 `GetLayeredWindowAttributes()` 记录原值，退出时原样还原；也可用 `--skip-foreign-layered` 直接跳过 |
| 改坏了窗口（黑屏、无法交互） | 影响正常使用 | 设置失败就标记为 `failed` 并**从此不再重试**，绝不反复折腾同一个窗口 |
| 误伤桌面 / 任务栏 / 输入法 | 系统界面变半透明 | 内置排除清单（见下） |
| 把 `WM_MEASUREITEM` 与 `WM_DRAWITEM` 的值记反 | 消息照样收得到，但拿到的是**另一个结构体**：宽高写进了绘制结构体的 `itemAction/itemState`，绘制时读到的 `rcItem` 又是测量结构体里的垃圾值 → **菜单项尺寸怎么设都不生效、整项一片空白** | 两个常量写在一起并加注释固定下来（`WM_DRAWITEM=0x2B` / `WM_MEASUREITEM=0x2C`），自检脚本 `probe_map.py` 可直接打出「消息号 ↔ 结构体形状」对照 |

### 右键菜单里的滑块是怎么塞进去的

Win32 的弹出菜单**没有滑块控件**，`TrackPopupMenu` 期间菜单会跑自己的一套模态消息循环，
普通子窗口控件（`msctls_trackbar32`）放不进去。所以这两个滑块是「自绘 + 消息钩子」拼出来的：

| 环节 | 用到的接口 | 作用 |
| --- | --- | --- |
| 建项 | `InsertMenuItemW` + `MFT_OWNERDRAW` | 菜单里留出一块由程序自己画的位置 |
| 定尺寸 | `WM_MEASUREITEM` | 告诉系统这一项要 300×42（两行：标题 + 数值 / 分段条） |
| 画出来 | `WM_DRAWITEM` | 用系统给的 `hDC` + `rcItem` 自己画：先铺底槽，再按 1% 一格 `FillRect` 出分段条 |
| 拖动 | `SetWindowsHookExW(WH_MSGFILTER)` | 钩住**菜单模态循环内部**的鼠标消息，才能做到「拖着菜单不关」 |
| 跟手重绘 | `InvalidateRect` + `UpdateWindow` | 值一变就只重画这一项，不重开菜单 |

几个关键点：

- 拖动时必须**吞掉**鼠标按下/抬起消息（改写 `msg.message = WM_NULL` 并 `return 1`），否则点一下菜单就关了；
  但 **`WM_MOUSEMOVE` 故意不吞**——菜单靠它高亮光标下的项，吞了方向键微调也就永远不生效
- 滚轮增量在 **`lParam` 的高 16 位**（`wParam` 装的是光标坐标）；读错字段会表现为「滚轮乱跳或完全不动」
- 系统会在请求宽度上再加一段菜单留白，所以实测菜单项比请求值宽一点，高度是精确的
- 百分比在内存与配置里**都是整数**，不是「先存小数再四舍五入显示」——这样 1% 步进是结构性保证，不可能出现小数点

**内置排除的窗口类**（不会动它们）：

```
Progman, WorkerW, Shell_TrayWnd, Shell_SecondaryTrayWnd, SysShadow,
ForegroundStaging, MultitaskingViewFrame, XamlExplorerHostIslandWindow,
Windows.UI.Core.CoreWindow, Windows.Internal.Shell.TabProxyWindow,
ApplicationFrameWindow, TaskListThumbnailWnd, DV2ControlHost,
tooltips_class32, MsgIMEWindowClass, Default IME, IME,
NarratorHelperWindow, Windows.UI.Composition.DesktopWindowContentBridge
```

另外，**全屏窗口默认跳过**——你在看电影或玩游戏时不会被干扰。

---

## 常见问题

**Q：装上后没反应？**
A：先确认右下角托盘区有图标（可能被折叠进「隐藏的图标」里了）。再运行 `win_glass-console.exe --list` 看它是否识别到了窗口。日志在 `%LOCALAPPDATA%\win_glass\win_glass.log`。

**Q：某个软件的窗口没变透明？**
A：多半是它在内置排除清单里，或者它是全屏窗口，或者它自己已经在用分层透明度。用 `--list` 可以确认；如果是 Electron 应用（VS Code、Discord 等），它们自带透明度处理，跳过是**有意为之**，避免互相打架。

**Q：任务栏 / 桌面变透明了？**
A：不应该发生（它们在排除清单里）。如果遇到请提 issue，附上 `--list` 的输出。

**Q：会影响性能吗？**
A：不会明显影响。它只做两件事：低频枚举窗口 + 动画期间按帧写一个属性。项目自带的长跑测试会采样内存与 CPU。

**Q：右键菜单里的滑块，调完的值会自己记住吗？**
A：会。**非聚焦最低透明度**与**聚焦最高透明度**都存在 `%LOCALAPPDATA%\win_glass\config.json`，下次启动自动生效。想临时试一下不落盘，用 `--no-config` 启动。

**Q：滑块为什么不能拖一点点？我想要 41.5%。**
A：**故意的**。滑块是分段式、步进固定 1%、取值恒为整数——这也是本项目的设计目标之一。想要更精细的过渡，调 `--fade-ms` 比调百分比更有效。

**Q：滑块拖不动 / 菜单一拖就关？**
A：如果你在用**第三方外壳增强工具**（StartAllBack、ExplorerPatcher、Windhawk、Winstep 等），它们会挂钩菜单代码，可能干扰自绘菜单项。先在干净的 Windows 上试一次，能定位是不是这个原因；日志与 `--list` 的输出对排查也有帮助。

**Q：怎么彻底卸载？**
A：控制面板「程序和功能」里卸载，或运行安装目录下的 `uninstall.exe`。卸载前它会**先礼貌地请程序退出**，让所有窗口恢复正常，再删除文件与注册表项。

**Q：为什么不支持 macOS / Linux？**
A：核心依赖的是 Windows 的 `WS_EX_LAYERED` 机制，其他系统没有对应实现。macOS 上类似效果需要辅助功能 API 且权限门槛高，暂不考虑。

---

## 已知限制

- 只支持 **Windows x64**（Windows 10 / 11）
- 某些**独占全屏**或**硬件加速自绘**的程序（部分游戏、播放器）不吃 `WS_EX_LAYERED`，属系统限制
- 如果 Windows 的**桌面窗口管理器（DWM）被关闭**，效果可能异常
- 内置排除清单是经验值，遇到特殊软件用 `--exclude` 补充
- 装到用户目录（不需要管理员），因此**只对当前用户生效**；多用户环境需各自安装

---

## 从源码构建

需要 Python 3.10+ 和 PyInstaller 6.x。

```bat
:: 1) 直接运行（需要 PySide 以外的库都可用；本程序只用标准库）
python win_glass.py --list

:: 2) 打包出 exe 与安装包（产物在 dist\ ）
pip install pyinstaller
python build.py
```

`build.py` 会用**当前正在运行它的解释器**来调用 PyInstaller，所以你不需要改任何路径。
要指定别的解释器，设置环境变量 `WIN_GLASS_PY` 即可。

产物：

| 文件 | 说明 |
| --- | --- |
| `dist\win_glass.exe` | 主程序：无控制台窗口 + 系统托盘 |
| `dist\win_glass-console.exe` | 同样的程序，带控制台，用于 `--list` / `-v` 等诊断 |
| `dist\win_glass_setup_v1.1.0.exe` | 安装包（内含上面两个 + 图标 + 卸载器） |

### 自检与测试

```bat
:: 用自带测试窗口验证透明度链路
python win_glass.py --self-test

:: 滑块：取值 / 坐标映射 / 真画一遍并用 GetPixel 反查填充边界 / 持久化 / 滚轮与点击的字段解析
python slider_test.py

:: 托盘菜单滑块实机验证：真弹菜单、合成鼠标拖动、截图、断言菜单项尺寸与落盘值
python menu_e2e_test.py

:: 端到端：真实切换窗口焦点，断言透明度在 100% 与 40% 之间正确变化
python e2e_test.py

:: 健壮性：参数边界 / 零窗口 / 30 秒长跑内存与 CPU / 强杀还原 / 托盘 / 优雅退出
python robustness_test.py

:: 安装包：沙盒里完整走 安装 → 校验 → 卸载 → 清理
python install_test.py

:: 排查自绘菜单用的诊断脚本：打印「消息号 ↔ 结构体形状」对照
python probe_map.py
```

测试脚本都用「正在运行它的解释器」和「脚本自身所在目录」，clone 下来直接就能跑。

> `menu_e2e_test.py` 会在你的桌面上**真的弹出一次托盘菜单**（约 2 秒后自动关闭，全程不动任何真实窗口的透明度）。
> `probe_map.py` 同样会短暂弹一次菜单。

---

## 项目结构

```
win-glass/
├── win_glass.py           主程序（窗口枚举、透明度引擎、托盘、托盘菜单滑块、CLI）
├── installer.py           安装器 / 卸载器（打包成 setup exe）
├── build.py               一键打包脚本
├── make_icon.py           生成 icon.ico
├── victim_window.py       测试用的「靶子窗口」
├── slider_test.py         滑块单元测试（取值 / 映射 / 绘制 / 持久化 / 输入解析）
├── menu_e2e_test.py       托盘菜单滑块实机验证
├── probe_map.py           自绘菜单诊断：消息号 ↔ 结构体形状
├── e2e_test.py            端到端测试
├── robustness_test.py     健壮性 / 可用性测试
├── install_test.py        安装包沙盒测试
├── icon.ico               图标
├── docs/
│   ├── win_glass_v1.0.1_fix_report.md   v1.0.1 修复报告（含问题根因分析）
│   └── win_glass_v1.1.0_slider_report.md  v1.1.0 滑块实现与排障记录
├── assets/
│   └── how-it-works.svg   原理示意图
├── tools/out/             发布产物的 SHA256 校验值
└── RELEASE_NOTES.md / CHANGELOG.md
```

---

## 许可

**本项目未附开源许可证（All rights reserved）。**

这意味着代码虽然公开可见，但默认**不授予**复制、修改、再分发或商用的权利。
如果你希望以某种开源许可证发布（例如 MIT / Apache-2.0），或想授权他人使用，
请通过 issue 联系作者。

---

<sub>作者：月见八千代 (Yachiyo) · 用纯 `ctypes` 手工对接 Win32 的一次尝试</sub>
