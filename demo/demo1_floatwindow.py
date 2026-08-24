"""Demo 1: 悬浮窗 + 全局快捷键（技术验证）
验证：①置顶无边框悬浮窗能渲染 ②全局快捷键 Ctrl+Shift+V 注册成功 ③模拟录入事件流
运行：python demo1_floatwindow.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 无头验证；真机预览可删此行
import sys
import ctypes
import ctypes.wintypes

from PySide6.QtCore import Qt, QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QLabel

# --- Windows 全局快捷键常量 ---
MOD_CONTROL, MOD_SHIFT = 0x0002, 0x0004
WM_HOTKEY = 0x0312
VIRTUAL_KEY_V = 0x56


class HotkeyFilter(QAbstractNativeEventFilter):
    """监听 WM_HOTKEY 消息，触发回调"""
    def __init__(self, on_hotkey):
        super().__init__()
        self.on_hotkey = on_hotkey

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self.on_hotkey()
                return True, 0
        return False, 0


class FloatWindow(QWidget):
    """置顶无边框悬浮窗原型"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(400, 300)
        self.setStyleSheet("background: rgba(28,30,42,245); border-radius: 16px; color: white;")
        layout = QVBoxLayout(self)
        title = QLabel("📥 拾光 · 快速收纳")
        title.setStyleSheet("font-size: 15px; font-weight: bold; padding: 6px 10px;")
        self.input = QLineEdit()
        self.input.setPlaceholderText("内容已就绪，按 Enter 保存")
        self.input.setStyleSheet(
            "background: white; color: #222; border-radius: 8px; padding: 10px; font-size: 13px;")
        hint = QLabel("AI 建议：竞赛 · 高重要 · 7天截止   [Enter 保存 / Esc 取消]")
        hint.setStyleSheet("font-size: 12px; color: #9ecbff; padding: 4px 10px;")
        layout.addWidget(title)
        layout.addWidget(self.input)
        layout.addWidget(hint)
        self.input.returnPressed.connect(self.on_save)

    def on_save(self):
        print(f"[OK] 模拟保存内容: {self.input.text()}")
        self.hide()


def main():
    app = QApplication(sys.argv)

    # 注册全局快捷键 Ctrl+Shift+V（hwnd=None → 线程级注册，不依赖窗口）
    ok = bool(ctypes.windll.user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_SHIFT, VIRTUAL_KEY_V))
    print("[OK] 全局快捷键 Ctrl+Shift+V 注册成功" if ok else "[FAIL] 全局快捷键注册失败")

    w = FloatWindow()
    # 唤出回调：显示 + 置顶 + 聚焦输入框
    def on_hotkey():
        w.show()
        w.raise_()
        w.activateWindow()
        w.input.setFocus()
    app.installNativeEventFilter(HotkeyFilter(on_hotkey))
    w.show()

    # 渲染验证：离屏截图
    pix = w.grab()
    out = "demo/demo1_floatwindow.png"
    pix.save(out)
    print(f"[OK] 悬浮窗渲染截图: {out} ({pix.width()}x{pix.height()})")
    print("[OK] 置顶标志:", bool(w.windowFlags() & Qt.WindowStaysOnTopHint),
          "| 无边框标志:", bool(w.windowFlags() & Qt.FramelessWindowHint))

    # 模拟"唤出 → 输入 → 回车保存"事件流
    w.show()
    w.input.setText("深大竞赛报名通知：9月20日截止")
    w.on_save()
    print("[OK] 录入事件流跑通")
    app.quit()


if __name__ == "__main__":
    main()
