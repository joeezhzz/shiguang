"""拾光 · 主入口：托盘常驻 + 全局快捷键 + 悬浮窗 + 内嵌看板窗口 + 到期提醒

运行：python src/main.py （在项目根目录）

全局快捷键实现说明（重要）：
实测本环境（PySide6 6.11 + Windows）下 RegisterHotKey 注册成功但 WM_HOTKEY
不会被 Qt 事件循环派发（nativeEventFilter 收不到，线程级/窗口级均如此）。
因此改用 GetAsyncKeyState 主线程轮询（QTimer 80ms），实测 100% 可靠，
且零依赖、无消息循环依赖、跨 Qt 版本稳定。
"""
import os
# 关键：vbs 隐藏窗口（SW_HIDE）启动环境下，QtWebEngine 硬件加速可能初始化失败导致看板白屏，
# 必须在 QWebEngine 初始化前禁用 GPU、改用软件渲染
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
os.environ.setdefault("QT_OPENGL", "software")
import sys
import ctypes
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QTimer, QUrl, QSharedMemory
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPainterPath
from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QWidget,
                               QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QCheckBox, QSpinBox, QPushButton, QMessageBox)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

from storage import db
from collector.floatwindow import FloatWindow
from reminder import Reminder

class _Tee:
    """把输出同时写到多个流（用于把日志追加到文件，便于脱离终端时排查）"""
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()  # 立即落盘，方便脱离终端时实时排查
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


PORT = 8765


# 全局热键：Ctrl+Shift+V
HOTKEY = {"ctrl": 0x11, "shift": 0x10, "key": 0x56}


class GlobalHotkey:
    """基于 GetAsyncKeyState 轮询的全局热键（边沿触发，按住不重复）"""

    def __init__(self, combo, on_trigger, interval_ms=80):
        self.combo = combo
        self.on_trigger = on_trigger
        self._pressed = False
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(interval_ms)

    def _poll(self):
        u32 = ctypes.windll.user32
        ok = bool(u32.GetAsyncKeyState(self.combo["key"]) & 0x8000)
        for name in ("ctrl", "shift", "alt", "win"):
            if name in self.combo and not (u32.GetAsyncKeyState(self.combo[name]) & 0x8000):
                ok = False
                break
        if ok:
            if not self._pressed:
                self._pressed = True
                self.on_trigger()
        else:
            self._pressed = False


def make_icon():
    """程序图标：深蓝圆角方块 + 白字「拾」"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(2, 2, 60, 60, 16, 16)
    p.fillPath(path, QColor("#2b2d42"))
    p.setPen(QColor("white"))
    f = QFont("Microsoft YaHei", 26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "拾")
    p.end()
    return QIcon(pm)


class BoardPage(QWebEnginePage):
    """看板页：拦截外部链接点击，交给系统默认浏览器打开（内嵌窗口始终保持看板）"""

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() in ("http", "https") and nav_type == QWebEnginePage.NavigationTypeLinkClicked:
            webbrowser.open(url.toString())
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class BoardWindow(QWidget):
    """看板窗口：QtWebEngine 内嵌本地看板（浏览器全程不出现）"""

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("拾光 · 看板")
        self.resize(1140, 740)
        self.setWindowIcon(make_icon())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView(self)
        self.web.setPage(BoardPage(self.web))
        # target=_blank 的新窗口请求 → 系统默认浏览器打开
        self.web.page().newWindowRequested.connect(
            lambda req: webbrowser.open(req.requestedUrl().toString()))
        lay.addWidget(self.web)
        self.web.load(QUrl(url))

    def closeEvent(self, e):
        e.ignore()
        self.hide()  # 关闭=隐藏，程序常驻托盘

    def show_board(self):
        print(f"[拾光] 打开看板 before: visible={self.isVisible()}", flush=True)
        self.show()
        self.raise_()
        self.activateWindow()
        # 绕过 Windows「前台锁定」：后台启动的进程（如 vbs 独立运行）激活窗口会被系统阻止，
        # 导致看板被其他窗口遮挡看不到。用原生 API 强制显示/置顶/前台。
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 5)                       # SW_SHOW
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002)  # HWND_TOP + NOSIZE + NOMOVE
            user32.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"[拾光] 强制置顶失败: {e}", flush=True)
        QTimer.singleShot(800, lambda: print(
            f"[拾光] 看板状态 after: visible={self.isVisible()} "
            f"size={self.width()}x{self.height()} pos={self.x()},{self.y()} "
            f"web_loaded={self.web.isVisible()}", flush=True))


class SettingsDialog(QDialog):
    """设置：提醒开关 + 默认提前天数"""

    def __init__(self, parent=None):
        super().__init__(parent)
        s = db.load_settings()
        self.setWindowTitle("拾光 · 设置")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)

        self.cb_enable = QCheckBox("启用到期提醒（Windows 通知）")
        self.cb_enable.setChecked(bool(s.get("remind_enabled", True)))
        lay.addWidget(self.cb_enable)

        row = QHBoxLayout()
        row.addWidget(QLabel("默认提前提醒："))
        self.sp_days = QSpinBox()
        self.sp_days.setRange(0, 30)
        self.sp_days.setValue(int(s.get("remind_days", 1)))
        self.sp_days.setSuffix(" 天")
        row.addWidget(self.sp_days)
        row.addStretch()
        lay.addLayout(row)

        note = QLabel("每条卡片可在详情页单独设置提醒：\n跟随默认 / 到期当天 / 提前1·3·7天 / 不提醒")
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a90a3; font-size: 12px;")
        lay.addWidget(note)

        btns = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        lay.addLayout(btns)

    def save(self):
        db.save_settings({
            "remind_enabled": self.cb_enable.isChecked(),
            "remind_days": self.sp_days.value(),
        })
        self.accept()


def start_web():
    from web.app import create_app
    app = create_app()
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def main():
    # 日志写到 data/run.log（脱离终端运行时也能排查问题）
    try:
        _log = open(os.path.join(db.DATA_DIR, "run.log"), "a", encoding="utf-8")
        sys.stdout = _Tee(sys.stdout, _log)
        sys.stderr = _Tee(sys.stderr, _log)
    except OSError:
        pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_icon())

    # QtWebEngine 持久化 profile：让看板的 localStorage（如主题选择）重启后不丢
    QWebEngineProfile.defaultProfile().setPersistentStoragePath(
        os.path.join(db.DATA_DIR, "webprofile"))

    # 单实例检测（QSharedMemory，可靠且不依赖端口时序）
    _sm = QSharedMemory("ShiguangSingleInstance")
    if not _sm.create(1):
        QMessageBox.information(None, "拾光", "拾光已在运行中，请查看系统托盘图标。")
        return
    app._single_instance = _sm  # 保持引用，防止被回收

    # 本地看板服务（后台线程）
    threading.Thread(target=start_web, daemon=True).start()

    win = FloatWindow()

    # 全局快捷键 Ctrl+Shift+V（轮询实现，见类注释）
    def toggle():
        print("[拾光] 热键触发，唤出/隐藏悬浮窗", flush=True)
        if win.isVisible():
            win.hide()
        else:
            win.show()
            win.raise_()
            win.activateWindow()
            win.fill_from_clipboard()
    hotkey = GlobalHotkey(HOTKEY, toggle)  # 必须保存引用，否则被 GC 回收导致轮询停止
    print("[拾光] 全局快捷键 Ctrl+Shift+V 已启用")

    # 看板内嵌窗口
    board = BoardWindow(f"http://127.0.0.1:{PORT}")

    def show_board():
        board.show_board()

    # 托盘
    tray = QSystemTrayIcon(make_icon(), app)
    tray.setToolTip("拾光 · 信息收纳")
    menu = QMenu()
    act_board = menu.addAction("📊 打开看板")
    act_settings = menu.addAction("⚙️ 设置")
    menu.addSeparator()
    act_browser = menu.addAction("🌐 在浏览器打开")
    act_quit = menu.addAction("退出")
    act_board.triggered.connect(show_board)
    act_settings.triggered.connect(lambda: SettingsDialog().exec())
    act_browser.triggered.connect(lambda: webbrowser.open(f"http://127.0.0.1:{PORT}"))
    act_quit.triggered.connect(app.quit)
    tray.setContextMenu(menu)

    # 单击 / 双击托盘图标都打开看板（单击更符合直觉）
    def on_tray(reason):
        print(f"[拾光] 托盘触发 reason={reason}", flush=True)
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            show_board()

    tray.activated.connect(on_tray)
    tray.show()

    # 到期提醒（每分钟检查，托盘弹通知）
    reminder = Reminder(tray)  # 保持引用

    tray.showMessage("拾光已就绪", "按 Ctrl+Shift+V 快速收纳 · 单击托盘图标打开看板",
                     QSystemTrayIcon.Information, 3000)
    print("[拾光] 看板内嵌窗口就绪（托盘双击/菜单打开）")
    print("[拾光] 到期提醒已启用（设置里可关）")
    print("[拾光] 运行中… Ctrl+C 退出")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
