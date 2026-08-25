"""拾光 · 主入口：托盘常驻 + 全局快捷键 + 悬浮窗 + 本地看板服务

运行：python src/main.py （在项目根目录）

全局快捷键实现说明（重要）：
实测本环境（PySide6 6.11 + Windows）下 RegisterHotKey 注册成功但 WM_HOTKEY
不会被 Qt 事件循环派发（nativeEventFilter 收不到，线程级/窗口级均如此）。
因此改用 GetAsyncKeyState 主线程轮询（QTimer 80ms），v9 实测 100% 可靠，
且零依赖、无消息循环依赖、跨 Qt 版本稳定。
"""
import os
import sys
import ctypes
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPainterPath
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from collector.floatwindow import FloatWindow

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

    # 托盘
    tray = QSystemTrayIcon(make_icon(), app)
    tray.setToolTip("拾光 · 信息收纳")
    menu = QMenu()
    act_board = menu.addAction("📊 打开看板")
    act_quit = menu.addAction("退出")
    menu.addSeparator()
    act_board.triggered.connect(lambda: webbrowser.open(f"http://127.0.0.1:{PORT}"))
    act_quit.triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: (webbrowser.open(f"http://127.0.0.1:{PORT}")
                                           if reason == QSystemTrayIcon.DoubleClick else None))
    tray.show()
    tray.showMessage("拾光已就绪", "按 Ctrl+Shift+V 快速收纳内容", QSystemTrayIcon.Information, 2000)

    print("[拾光] 看板地址: http://127.0.0.1:%d  （托盘双击或右键打开）" % PORT)
    print("[拾光] 运行中… Ctrl+C 退出")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
