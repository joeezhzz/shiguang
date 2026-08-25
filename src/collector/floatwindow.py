"""拾光 · 悬浮窗（真机版）
- 全局快捷键 Ctrl+Shift+V 唤出/隐藏（注册在 main.py）
- 唤起时自动读取剪贴板：文本 / 图片 / 复制的文件，一步到位
- 文件拖拽直接收纳
- 保存时 AI 自动分类（断网降级规则），可手动调整重要度/效用期/截止时间
- Enter 保存 · Esc 取消
"""
import os
import time
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QPlainTextEdit, QLabel, QPushButton, QButtonGroup,
                               QFrame)

import json

from storage import db
from classifier.classifier import classify, classify_chat, is_chat
from ocr.ocr import ocr_image

TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "tmp")


class InputBox(QPlainTextEdit):
    """拦截回车/ESC 的输入框"""
    submitted = Signal()
    cancelled = Signal()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Return and not (e.modifiers() & Qt.ShiftModifier):
            self.submitted.emit()
            return
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(e)


class PreWorker(QThread):
    """预分类：唤起时后台跑 AI，结果实时显示在建议区"""
    done = Signal(dict)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self):
        try:
            self.done.emit(classify(self.text))
        except Exception as e:
            print(f"[preclassify] {e}")


class SaveWorker(QThread):
    """保存：存媒体 → OCR → AI 分类 → 入库（全在后台，不卡 UI）"""
    done = Signal(int)
    failed = Signal(str)

    def __init__(self, text, image_path, files, source, priority, period, due_date, parent=None):
        super().__init__(parent)
        self.text, self.image_path, self.files = text, image_path, files
        self.source, self.priority, self.period, self.due_date = source, priority, period, due_date

    def run(self):
        try:
            media_path, kind, ocr = None, "text", None
            if self.image_path:
                kind = "image"
                media_path = db.save_media(self.image_path)
                try:
                    ocr = ocr_image(db.media_abs_path(media_path))
                except Exception as e:
                    print(f"[ocr] {e}")
                if not self.text and ocr:
                    self.text = ocr.split("\n")[0][:50]
            elif self.files:
                kind = "file"
                media_path = db.save_media(self.files[0])
                self.text = self.text or os.path.basename(self.files[0])

            chat = bool(self.text.strip()) and is_chat(self.text)
            cls = classify_chat(self.text) if chat else (classify(self.text) if self.text.strip() else None)
            card_id = db.create_card(
                kind=kind, content=(self.text or "")[:2000], media_path=media_path,
                source=self.source,
                topic=(cls or {}).get("topic", "其他"),
                priority=self.priority or (cls or {}).get("priority", "中"),
                period=self.period or (cls or {}).get("period", "永久参考"),
                due_date=self.due_date or (cls or {}).get("due_date"),
                ocr_text=ocr,
                tags=",".join((cls or {}).get("tags", [])) or None,
                main_point=(cls or {}).get("main_point") if chat else None,
                branches=json.dumps((cls or {}).get("branches"), ensure_ascii=False)
                if chat and (cls or {}).get("branches") else None,
            )
            if self.image_path and os.path.exists(self.image_path):
                os.remove(self.image_path)  # 清理剪贴板临时图
            self.done.emit(card_id)
        except Exception as e:
            self.failed.emit(str(e))


class FloatWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(430, 400)
        self.setStyleSheet("""
            QWidget { background: rgba(28,30,42,250); color: white; font-size: 13px; }
            QPlainTextEdit { background: white; color: #222; border-radius: 8px;
                             border: none; padding: 8px; font-size: 13px; }
            QLabel#title { font-size: 15px; font-weight: bold; padding: 8px 10px 0 10px; }
            QLabel#hint  { font-size: 12px; color: #8b90a5; padding: 0 10px 8px 10px; }
            QLabel#suggest { background: rgba(158,203,255,25); color: #9ecbff;
                             border-radius: 6px; padding: 6px 10px; font-size: 12px; }
            QLabel#preview { border-radius: 8px; }
            QLabel#fileTag { background: rgba(255,255,255,12); border-radius: 6px;
                             padding: 4px 8px; font-size: 12px; color: #c9cddd; }
            QPushButton { background: rgba(255,255,255,14); border: 1px solid rgba(255,255,255,20);
                          border-radius: 6px; padding: 4px 10px; color: #dfe2ee; }
            QPushButton:hover { background: rgba(255,255,255,24); }
            QPushButton:checked { background: #4f7cff; border-color: #4f7cff; color: white; }
            QLabel#rowLabel { color: #8b90a5; font-size: 12px; padding-right: 4px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        self.title = QLabel("📥 拾光 · 快速收纳")
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.input = InputBox()
        self.input.setPlaceholderText("粘贴或输入内容，Enter 保存（Shift+Enter 换行）")
        self.input.setFixedHeight(110)
        self.input.submitted.connect(self.on_save)
        self.input.cancelled.connect(self.hide)
        layout.addWidget(self.input)

        self.preview = QLabel()
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.hide()
        layout.addWidget(self.preview)

        self.file_tag = QLabel()
        self.file_tag.setObjectName("fileTag")
        self.file_tag.hide()
        layout.addWidget(self.file_tag)

        self.suggest = QLabel("AI 建议：—")
        self.suggest.setObjectName("suggest")
        layout.addWidget(self.suggest)

        # 重要度
        row1 = QHBoxLayout()
        row1.addWidget(self._mk_label("重要度"))
        self.pri_group = QButtonGroup(self)
        for t in ("高", "中", "低"):
            b = QPushButton(t)
            b.setCheckable(True)
            self.pri_group.addButton(b)
            row1.addWidget(b)
        row1.addStretch()
        layout.addLayout(row1)

        # 效用期
        row2 = QHBoxLayout()
        row2.addWidget(self._mk_label("效用期"))
        self.period_group = QButtonGroup(self)
        for t in ("短期任务", "长期计划", "永久参考"):
            b = QPushButton(t)
            b.setCheckable(True)
            self.period_group.addButton(b)
            row2.addWidget(b)
        row2.addStretch()
        layout.addLayout(row2)

        # 截止时间
        row3 = QHBoxLayout()
        row3.addWidget(self._mk_label("截止"))
        self.due_group = QButtonGroup(self)
        self.due_days = None
        for t, d in (("3天", 3), ("1周", 7), ("1月", 30), ("无", None)):
            b = QPushButton(t)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, dd=d: setattr(self, "due_days", dd))
            self.due_group.addButton(b)
            row3.addWidget(b)
        row3.addStretch()
        layout.addLayout(row3)

        self.hint = QLabel("Enter 保存 · Esc 取消 · 文件可直接拖进来")
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)

        self.image_path = None
        self.files = []
        self.last_cls = None
        self._drag_pos = None
        self._worker = None
        self._pre = None
        self.setAcceptDrops(True)

    # ---------- 工具 ----------
    @staticmethod
    def _mk_label(text):
        lb = QLabel(text)
        lb.setObjectName("rowLabel")
        return lb

    # ---------- 剪贴板一步录入 ----------
    def fill_from_clipboard(self):
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        self.files = []
        self._clear_media()

        pix = cb.pixmap()  # 无图时返回 null pixmap（offscreen 下 mimeData 可能为 None，故用 pixmap 判空）
        if not pix.isNull():
            self.preview.setPixmap(pix.scaledToWidth(360, Qt.SmoothTransformation))
            self.preview.show()
            os.makedirs(TMP_DIR, exist_ok=True)
            self.image_path = os.path.join(TMP_DIR, f"clip_{int(time.time())}.png")
            pix.save(self.image_path, "PNG")
        elif mime and mime.hasUrls():
            urls = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            if urls:
                self.files = urls
                self.file_tag.setText("📎 " + "、".join(os.path.basename(u) for u in urls[:3]))
                self.file_tag.show()

        text = cb.text().strip()
        if text and not self.input.toPlainText().strip():
            self.input.setPlainText(text)
            self._preclassify(text)

    def _preclassify(self, text):
        self.suggest.setText("AI 分类中…")
        self._pre = PreWorker(text, self)
        self._pre.done.connect(self._on_pre_done)
        self._pre.start()

    def _on_pre_done(self, cls):
        self.last_cls = cls
        due = cls.get("due_date") or "无"
        self.suggest.setText(
            f"AI 建议：{cls.get('topic')} · {cls.get('priority')} · {cls.get('period')} · 截止 {due}"
            + (f"  ｜{cls.get('summary')}" if cls.get("summary") else ""))

    def _clear_media(self):
        if self.image_path and os.path.exists(self.image_path):
            try:
                os.remove(self.image_path)
            except OSError:
                pass
        self.image_path = None
        self.preview.clear()
        self.preview.hide()
        self.file_tag.hide()

    # ---------- 保存 ----------
    def on_save(self):
        text = self.input.toPlainText().strip()
        if not text and not self.image_path and not self.files:
            self.hint.setText("⚠ 没有可保存的内容")
            return
        pri = self.pri_group.checkedButton().text() if self.pri_group.checkedButton() else None
        per = self.period_group.checkedButton().text() if self.period_group.checkedButton() else None
        due = None
        if self.due_days:
            due = (datetime.now() + timedelta(days=self.due_days)).strftime("%Y-%m-%d")
        if self.image_path:
            source = "截图"
        elif self.files:
            source = "拖拽"
        else:
            source = "剪贴板" if text == QApplication.clipboard().text().strip() else "手动"

        self.setEnabled(False)
        self.hint.setText("🔄 收纳中…")
        self._worker = SaveWorker(text, self.image_path, self.files, source, pri, per, due, self)
        self._worker.done.connect(self.on_saved)
        self._worker.failed.connect(self.on_failed)
        self._worker.start()

    def on_saved(self, card_id):
        self.last_cls = None
        self.input.clear()
        self._clear_media()
        for g in (self.pri_group, self.period_group, self.due_group):
            if g.checkedButton():
                g.setExclusive(False)
                g.checkedButton().setChecked(False)
                g.setExclusive(True)
        self.due_days = None
        self.setEnabled(True)
        self.hint.setText(f"✅ 已收纳（#{card_id}）")
        QTimer.singleShot(1200, self.hide)

    def on_failed(self, err):
        self.setEnabled(True)
        self.hint.setText(f"❌ 保存失败: {err}")

    # ---------- 无边框拖动 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    # ---------- 拖拽文件 ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if urls:
                self.files = urls
                self.file_tag.setText("📎 " + "、".join(os.path.basename(u) for u in urls[:3]))
                self.file_tag.show()
        e.acceptProposedAction()
