# 2026-08-26 — 独立运行排障：退出 Hermes 后拾光照常使用

## 用户需求
拾光原本是 Hermes 会话的后台子进程，退出 Hermes 后托盘图标消失、程序停止。用户希望**不打开 Hermes 也能正常使用拾光**，且 README 里要能直接使用。

## 方案
- 新增 `启动拾光.vbs`：双击即用，用 **pythonw.exe**（Python 的 GUI 版，无控制台窗口）启动 `src/main.py`
- 新增 `启动拾光.bat`：带控制台窗口的调试版
- `main.py` 新增单实例检测（QSharedMemory 命名内存，比端口检测可靠）
- `main.py` 日志同时写入 `data/run.log`（脱离终端也能排查问题）

## 排障过程：托盘点击看板弹不出

### 现象
独立启动后托盘图标存在，单击/双击图标**看板不弹出，但输入法中英文切换**（说明焦点变化了，窗口"激活"了却看不到）。

### 诊断步骤
1. **加日志**：确认托盘 `activated` 信号正常触发、`show_board` 被调用、Qt 认为窗口 `visible=True`（大小 1140x740、位置正常）
2. **排除重复实例**：窗口枚举发现之前多次测试累积了 **6 个拾光实例**互相冲突 → 全部清理，单实例检测改用 QSharedMemory（端口检测有时序漏洞）
3. **Windows API 查窗口**：`GetWindowLong` 查 WS_VISIBLE 样式位——**不可靠**！用户能看到的窗口 WS_VISIBLE 也是 no（Qt 6 + Chromium 合成渲染，顶层窗口样式不代表内容可见性）
4. **截屏 + RapidOCR**：OCR 识别到看板内容（搜索框/筛选/卡片）确实渲染了，但**被 Hermes 窗口遮挡**
5. **对比实验**：用 Hermes 方式（terminal background）启动同一份代码 → 看板正常弹出 → 确认代码没问题，问题在启动环境

### 根因
**Windows 前台锁定（foreground lock）**：vbs 从后台启动的进程（pythonw）试图激活/置顶窗口时，Windows 会阻止（`activateWindow()` 失效），看板窗口显示在 Hermes 窗口后面 → 用户看不到，但焦点已被切换（输入法切换）。

Hermes 方式能弹出，是因为它通过 shell 启动、进程激活窗口的权限链不同。

### 修复
`BoardWindow.show_board()` 用 Windows 原生 API 强制显示/置顶/前台（绕过后台进程激活限制）：

```python
hwnd = int(self.winId())
user32 = ctypes.windll.user32
user32.ShowWindow(hwnd, 5)                       # SW_SHOW
user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002)  # HWND_TOP + NOSIZE + NOMOVE
user32.SetForegroundWindow(hwnd)
```

### 验证
用户确认：vbs 独立启动（pythonw）后单击托盘图标，**看板正常弹出** ✅。拾光是孤儿进程（父进程已退出），完全独立于 Hermes。

## 经验教训
1. **Qt 桌面程序的独立部署**：GUI 程序应该用 pythonw.exe（GUI 子系统）启动，不要用 python.exe + SW_HIDE 隐藏控制台（会导致窗口异常）
2. **Windows 前台锁定**：后台进程 `activateWindow()`/`raise_()` 可能被系统静默忽略，需要 `SetWindowPos(HWND_TOP)` + `SetForegroundWindow()` 强制
3. **窗口可见性诊断**：Qt 的 `isVisible()` 和 Windows 的 `IsWindowVisible`/`WS_VISIBLE` 都可能误导（Qt 6 合成渲染），最可靠的是截屏 + OCR 看实际屏幕
4. **单实例检测**：端口检测有时序漏洞（多个实例同时启动都能通过），QSharedMemory 命名内存才可靠
5. **日志落盘**：脱离终端运行的程序，日志要写到文件（`data/run.log`），这是唯一的排查手段
6. **不要基于假设修 bug**：曾为修"白屏"加 `--disable-gpu` 软件渲染，但真凶是前台锁定（遮挡）；软件渲染反而破坏 QtWebEngine 页面交互（图片/链接/文件点击无响应），移除后恢复。诊断必须基于事实（截屏/OCR/日志），先确认根因再动手
