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

从 [**Releases 页面**](../../releases/latest) 下载 `win_glass_setup_v1.0.1.exe`，双击即可。

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

1. 双击 `win_glass_setup_v1.0.1.exe` 完成安装
2. 开始菜单搜索 `win_glass` 启动
3. 右下角系统托盘出现图标 → **它已经在工作了**
4. 随手指点几个窗口，你会看到：你正在用的那个是清晰的，其他都变淡了

想让它开机自动运行？用管理员以外的普通身份执行：

```bat
win_glass_setup_v1.0.1.exe --autostart
```

取消开机自启：`win_glass_setup_v1.0.1.exe --no-autostart`

---

## 系统托盘怎么用

日常只需要用托盘图标，不用记命令：

| 操作 | 效果 |
| --- | --- |
| **左键单击** | 暂停 / 继续（暂停时**所有窗口立刻恢复 100%**） |
| **右键** | 弹出菜单：暂停、立即恢复、打开日志、退出 |

托盘图标**不会出现在任务栏，也不会出现在 Alt+Tab 里**，不占地方。

> 退出时（无论点「退出」、注销还是关机）程序都会把**所有窗口的透明度和样式原样还原**。
> 万一遇到异常导致没还原，重新运行一次再正常退出即可。

---

## 命令行参数

窗口化版本没有控制台，所以想看输出请用随包安装的 **`win_glass-console.exe`**（同一份程序，带控制台）。
位置：`%LOCALAPPDATA%\Programs\win_glass\win_glass-console.exe`

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--inactive-alpha <0.05~1.0>` | `0.40` | 未聚焦窗口的透明度 |
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

:: 先看看它会接管哪些窗口，再决定要不要排除
win_glass-console.exe --list

:: 排除某个软件的窗口
win_glass-console.exe --exclude MyAppClass,AnotherClass

:: 跑 30 秒自动退出，用来快速试效果
win_glass-console.exe --duration 30
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
| `dist\win_glass_setup_v1.0.1.exe` | 安装包（内含上面两个 + 图标 + 卸载器） |

### 自检与测试

```bat
:: 用自带测试窗口验证透明度链路
python win_glass.py --self-test

:: 端到端：真实切换窗口焦点，断言透明度在 100% 与 40% 之间正确变化
python e2e_test.py

:: 健壮性：参数边界 / 零窗口 / 30 秒长跑内存与 CPU / 强杀还原 / 托盘 / 优雅退出
python robustness_test.py

:: 安装包：沙盒里完整走 安装 → 校验 → 卸载 → 清理
python install_test.py
```

测试脚本都用「正在运行它的解释器」和「脚本自身所在目录」，clone 下来直接就能跑。

---

## 项目结构

```
win-glass/
├── win_glass.py           主程序（窗口枚举、透明度引擎、托盘、CLI）
├── installer.py           安装器 / 卸载器（打包成 setup exe）
├── build.py               一键打包脚本
├── make_icon.py           生成 icon.ico
├── victim_window.py       测试用的「靶子窗口」
├── e2e_test.py            端到端测试
├── robustness_test.py     健壮性 / 可用性测试
├── install_test.py        安装包沙盒测试
├── icon.ico               图标
├── docs/
│   └── win_glass_v1.0.1_fix_report.md   v1.0.1 修复报告（含问题根因分析）
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
