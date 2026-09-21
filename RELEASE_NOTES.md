# v1.0.1 — 修复安装后不可用 · 改为无窗口 + 系统托盘

> **一句话**：这一版让 win-glass **装上就能用** —— 不再有命令行黑窗口，也不再依赖 `.vbs` 启动器。

让当前正在用的窗口保持清晰、其余窗口自动变半透明的小工具。常驻系统托盘，退出时全部还原。

---

## 📦 下载

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| `win_glass_setup_v1.0.1.exe` | 30 MB | **安装包**（双击即装，**不需要管理员权限**，不弹 UAC） |
| `win_glass_setup_v1.0.1.exe.sha256` | 100 B | 上述文件的 SHA256 校验值 |

包内已含运行时，**目标机器不需要安装 Python**。

```
cf036ab050f7d570e82bd815f836dcb6f34b242ffe0afd810798326b06a83e54  win_glass_setup_v1.0.1.exe
```

### 校验下载文件

```bash
# Linux / macOS
sha256sum -c win_glass_setup_v1.0.1.exe.sha256
```

```powershell
# Windows PowerShell
Get-FileHash .\win_glass_setup_v1.0.1.exe -Algorithm SHA256
```

---

## 🚀 安装与使用

1. 双击 `win_glass_setup_v1.0.1.exe`
   > 安装包本身是命令行程序，会有一个黑窗口显示安装进度，属正常现象。
2. 开始菜单搜索 **win_glass** 打开 → **不会再有任何命令行窗口**
3. 右下角托盘出现图标即已在工作

| 托盘操作 | 效果 |
| --- | --- |
| 左键单击 | 暂停 / 继续（暂停时所有窗口立刻恢复 100%） |
| 右键 | 暂停、立即恢复、打开日志、退出 |

- 安装位置：`%LOCALAPPDATA%\Programs\win_glass`（用户目录，不需要管理员）
- 开机自启：`win_glass_setup_v1.0.1.exe --autostart`（取消用 `--no-autostart`）
- 卸载：控制面板「程序和功能」→ win_glass，或安装目录下的 `uninstall.exe`

---

## ✨ 本版变更

### 修复

- **快捷方式弹出记事本** —— v1.0.0 用 `.vbs` 当启动器，在 `.vbs` 关联被改成记事本的机器上，
  双击只是「用记事本打开脚本」，程序从未启动。现已**彻底删除 `.vbs`**，快捷方式**直指 `win_glass.exe`**，
  升级安装时还会主动清理残留的旧 `.vbs`。
- **启动弹命令行黑窗口** —— 主程序由 `--console` 改为 **`--windowed`**，完全无窗口。
- **托盘「退出」不还原窗口** —— 退出判断用了会被自身置位的标志，导致窗口卡在 40%；改用独立守卫。
- **卸载时收不到退出信号** —— 托盘窗口由消息窗口改为隐藏顶层窗口，能正确收到 WM_CLOSE 并先还原再退出。
- **`--log` 参数失效** —— 窗口化模式下会被默认日志顶掉，现按目标路径重开文件句柄。

### 新增

- 系统托盘交互（托盘窗口带 `WS_EX_TOOLWINDOW`，**不进任务栏、不进 Alt+Tab**）
- 随包附带 `win_glass-console.exe`，用于 `--list` / `-v` 等需要看输出的诊断场景
- 日志文件：`%LOCALAPPDATA%\win_glass\win_glass.log`（托盘右键可直接打开）

---

## ✅ 验证结果

| 测试 | 内容 | 结果 |
| --- | --- | --- |
| `robustness_test.py` | 参数边界 / 零窗口 / 30s 长跑内存与 CPU / 强杀还原 / 托盘创建 / 优雅退出 | **27 PASS / 0 FAIL** |
| `e2e_test.py` | 真实窗口聚焦 ↔ 失焦切换，实测透明度 100% ↔ 40% | PASS |
| `install_test.py` | 沙盒完整走 安装 → 校验 → 卸载 → 清理，含「已无 `.vbs`」「快捷方式直指 exe」断言 | PASS |

关键证据（模拟卸载器的 `taskkill` 路径）：

```
[PASS] 托盘窗口是顶层窗口（taskkill 枚举得到）
[PASS] 托盘窗口带 WS_EX_TOOLWINDOW（不进任务栏/Alt+Tab）
[PASS] 托盘窗口不可见（不抢焦点）
[PASS] 退出前窗口已被接管（挂上 LAYERED）
[PASS] WM_CLOSE 触发优雅退出（未强杀）
[PASS] 退出后窗口已还原（LAYERED 摘除）
```

---

## 📋 环境要求

| 项 | 要求 |
| --- | --- |
| 系统 | Windows 10 / 11（**x64**） |
| Python | **不需要**，安装包已含运行时 |
| 管理员权限 | **不需要**（装到用户目录） |
| 其他依赖 | 无（程序只用 Windows 自带接口，纯 `ctypes`） |

---

## ⚠️ 已知限制

- 只支持 Windows；核心依赖 `WS_EX_LAYERED`，其他系统没有对应机制
- 部分**独占全屏**或**硬件加速自绘**的程序（某些游戏、播放器）不响应整窗透明度，属系统限制
- 默认**跳过全屏窗口**，避免看电影 / 玩游戏时被干扰（`--no-skip-fullscreen` 可关闭此行为）
- 部分 **Electron / Chromium** 应用自带分层透明度，默认会**记录其原值并在退出时还原**；
  也可用 `--skip-foreign-layered` 直接跳过
- 内置排除清单为经验值，遇到特殊软件可用 `--exclude <类名>` 补充

---

## 🔧 常用参数

```bat
:: 想先看看它会接管哪些窗口（不做任何修改）
win_glass-console.exe --list

:: 背景想更淡一点
win_glass-console.exe --inactive-alpha 0.25

:: 过渡想更快
win_glass-console.exe --fade-ms 200

:: 排除某个软件的窗口
win_glass-console.exe --exclude MyAppClass,AnotherClass
```

完整参数表、工作原理与常见问题见仓库 [README.md](README.md)。

---

## 📄 许可

**本项目未附开源许可证（All rights reserved）**，代码公开可见但不授予复制 / 修改 / 再分发 / 商用权利。
如需以开源许可证发布或授权使用，请通过 issue 联系作者。
