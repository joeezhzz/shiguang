"""拾光 · 主入口：托盘常驻 + 全局快捷键 + 悬浮窗 + 内嵌看板窗口 + 到期提醒

运行：python src/main.py （在项目根目录）

全局快捷键实现说明（重要）：
实测本环境（PySide6 6.11 + Windows）下 RegisterHotKey 注册成功但 WM_HOTKEY
不会被 Qt 事件循环派发（nativeEventFilter 收不到，线程级/窗口级均如此）。
因此改用 GetAsyncKeyState 主线程轮询（QTimer 80ms），实测 100% 可靠，
且零依赖、无消息循环依赖、跨 Qt 版本稳定。
"""
import os
import sys
import ctypes
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPainterPath
from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QWidget,
                               QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QCheckBox, QSpinBox, QPushButton)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

from storage import db
from collector.floatwindow import FloatWindow
from reminder import Reminder

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
        self.show()
        self.raise_()
        self.activateWindow()


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
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_icon())

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
    tray.activated.connect(lambda reason: show_board()
                           if reason == QSystemTrayIcon.DoubleClick else None)
    tray.show()

    # 到期提醒（每分钟检查，托盘弹通知）
    reminder = Reminder(tray)  # 保持引用

    tray.showMessage("拾光已就绪", "按 Ctrl+Shift+V 快速收纳 · 双击托盘打开看板",
                     QSystemTrayIcon.Information, 3000)
    print("[拾光] 看板内嵌窗口就绪（托盘双击/菜单打开）")
    print("[拾光] 到期提醒已启用（设置里可关）")
    print("[拾光] 运行中… Ctrl+C 退出")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
