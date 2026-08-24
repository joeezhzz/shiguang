"""Demo 2: 剪贴板读写（技术验证）
验证：①文本剪贴板读写 ②图片剪贴板读写（模拟"微信里复制图片→粘贴进悬浮窗"）
运行：python demo2_clipboard.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pyperclip
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt

app = QApplication([])

# --- 文本 ---
text = "深大竞赛报名通知：9月20日截止"
pyperclip.copy(text)
read = pyperclip.paste()
print("[文本] 写入:", text)
print("[文本] 读回:", read, "→", "OK" if read == text else "FAIL")

# --- 图片（模拟微信复制图片后剪贴板里是一张位图） ---
img = QImage(320, 200, QImage.Format_RGB32)
img.fill(Qt.red)
cb = QApplication.clipboard()
cb.setImage(img)
back = cb.image()
print(f"[图片] 写入 320x200 位图 → 读回 {back.width()}x{back.height()}",
      "→ OK" if back.width() == 320 and back.height() == 200 else "→ FAIL")
pm = cb.pixmap()
print("[图片] 剪贴板 pixmap 可用（可转存文件）:", "OK" if not pm.isNull() else "FAIL")
