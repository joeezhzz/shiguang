"""拾光 · 悬浮窗（真机版）
两步流程：录入 → AI 分析（分类/结构化整理/OCR）→ 预览确认 → 入库
- 全局快捷键 Ctrl+Shift+V 唤出/隐藏（注册在 main.py）
- 唤起时自动读取剪贴板：文本 / 图片 / 复制的文件，一步到位；文件拖拽直接收纳
- Enter：触发 AI 分析 → 预览确认保存；Esc：取消
- 预览确认页可修改主题（支持自定义新主题）/重要度/效用期/截止，
  或选择「仅存原文」（不采纳 AI 整理，原文 100% 保留入库）
"""
import json
import os
import time
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QPlainTextEdit, QLabel, QPushButton, QButtonGroup,
                               QComboBox)

from storage import db
from classifier.classifier import classify, classify_chat, is_chat

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


class AnalyzeWorker(QThread):
    """后台分析：OCR（图片）→ AI 分类/结构化整理，产出预览数据"""
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, text, image_path, files, parent=None):
        super().__init__(parent)
        self.text, self.image_path, self.files = text, image_path, files

    def run(self):
        try:
            kind, media_path, ocr = "text", None, None
            if self.image_path:
                # 图片：不做 OCR、不自动分类（用户决策），直接归档；可手动填描述触发分类
                kind = "image"
                media_path = db.save_media(self.image_path)
            elif self.files:
                kind = "file"
                media_path = db.save_media(self.files[0])
                # 双保险：微信复制文件时剪贴板文本是 file:// 路径，用文件名代替
                if not self.text or self.text.startswith("file:///"):
                    self.text = os.path.basename(self.files[0])
            self.media_path = media_path  # 供外部/测试访问
            chat = bool(self.text.strip()) and is_chat(self.text)
            cls = classify_chat(self.text) if chat else (classify(self.text) if self.text.strip() else None)
            self.done.emit({
                "kind": kind, "text": self.text, "media_path": media_path,
                "ocr": ocr, "chat": chat, "cls": cls or {},
            })
        except Exception as e:
            self.failed.emit(str(e))


class SaveWorker(QThread):
    """入库（字段已在预览确认时确定）"""
    done = Signal(int)
    failed = Signal(str)

    def __init__(self, payload, parent=None):
        super().__init__(parent)
        self.payload = payload

    def run(self):
        try:
            card_id = db.create_card(**self.payload)
            self.done.emit(card_id)
        except Exception as e:
            self.failed.emit(str(e))


class FloatWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(440, 470)  # edit 高度；preview 模式动态加高
        self.setStyleSheet("""
            QWidget { background: rgba(28,30,42,252); color: white; font-size: 13px; }
            QPlainTextEdit { background: white; color: #222; border-radius: 8px;
                             border: none; padding: 8px; font-size: 13px; }
            QPlainTextEdit#result { background: rgba(255,255,255,10); color: #dfe2ee;
                                    border: 1px solid rgba(255,255,255,16); }
            QLabel#title { font-size: 15px; font-weight: bold; padding: 8px 10px 0 10px; }
            QLabel#hint  { font-size: 12px; color: #8b90a5; padding: 0 10px 8px 10px; }
            QLabel#suggest { background: rgba(158,203,255,25); color: #9ecbff;
                             border-radius: 6px; padding: 6px 10px; font-size: 12px; }
            QLabel#preview { border-radius: 8px; }
            QLabel#fileTag { background: rgba(255,255,255,12); border-radius: 6px;
                             padding: 4px 8px; font-size: 12px; color: #c9cddd; }
            QPushButton { background: rgba(255,255,255,14); border: 1px solid rgba(255,255,255,20);
                          border-radius: 6px; padding: 5px 12px; color: #dfe2ee; }
            QPushButton:hover { background: rgba(255,255,255,24); }
            QPushButton:checked { background: #4f7cff; border-color: #4f7cff; color: white; }
            QPushButton#confirm { background: #4f7cff; border-color: #4f7cff; color: white;
                                  font-weight: bold; }
            QPushButton#confirm:hover { background: #5f88ff; }
            QPushButton#raw { background: rgba(255,255,255,10); color: #c9cddd; }
            QComboBox { background: rgba(255,255,255,14); border: 1px solid rgba(255,255,255,20);
                        border-radius: 6px; padding: 4px 10px; color: white; }
            QComboBox QAbstractItemView { background: #2b2d42; color: white;
                                          selection-background-color: #4f7cff; }
            QLabel#rowLabel { color: #8b90a5; font-size: 12px; padding-right: 4px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        self.title = QLabel("📥 拾光 · 快速收纳")
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.input = InputBox()
        self.input.setPlaceholderText("粘贴或输入内容，Enter 开始整理（Shift+Enter 换行）")
        self.input.setFixedHeight(100)
        self.input.submitted.connect(self.on_save)
        self.input.cancelled.connect(self.on_cancel)
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

        # AI 整理结果预览区（只读）
        self.result_view = QPlainTextEdit()
        self.result_view.setObjectName("result")
        self.result_view.setReadOnly(True)
        self.result_view.setFixedHeight(110)
        layout.addWidget(self.result_view)

        # 选项区：主题 / 重要度 / 效用期 / 截止 / 按钮（预览确认时显示）
        self.options_box = QWidget()
        opt = QVBoxLayout(self.options_box)
        opt.setContentsMargins(0, 0, 0, 0)
        opt.setSpacing(8)

        row_topic = QHBoxLayout()
        row_topic.addWidget(self._mk_label("主题"))
        self.topic_combo = QComboBox()
        self.topic_combo.setEditable(True)
        self.topic_combo.addItems(db.get_topics())
        self.topic_combo.setMinimumWidth(200)
        row_topic.addWidget(self.topic_combo, 1)
        opt.addLayout(row_topic)

        row1 = QHBoxLayout()
        row1.addWidget(self._mk_label("重要度"))
        self.pri_group = QButtonGroup(self)
        for t in ("高", "中", "低"):
            b = QPushButton(t)
            b.setCheckable(True)
            self.pri_group.addButton(b)
            row1.addWidget(b)
        row1.addStretch()
        opt.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._mk_label("效用期"))
        self.period_group = QButtonGroup(self)
        for t in ("短期任务", "长期计划", "永久参考"):
            b = QPushButton(t)
            b.setCheckable(True)
            self.period_group.addButton(b)
            row2.addWidget(b)
        row2.addStretch()
        opt.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._mk_label("截止"))
        self.due_group = QButtonGroup(self)
        self.due_days = None
        self.due_chosen = False  # 用户是否显式选过截止（含"无"）；选过则 AI 识别不覆盖
        for t, d in (("3天", 3), ("1周", 7), ("1月", 30), ("无", None)):
            b = QPushButton(t)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, dd=d: (setattr(self, "due_days", dd),
                                                     setattr(self, "due_chosen", True)))
            self.due_group.addButton(b)
            row3.addWidget(b)
        row3.addStretch()
        opt.addLayout(row3)

        row_btn = QHBoxLayout()
        self.btn_confirm = QPushButton("✅ 确认保存")
        self.btn_confirm.setObjectName("confirm")
        self.btn_raw = QPushButton("📄 仅存原文")
        self.btn_raw.setObjectName("raw")
        self.btn_cancel = QPushButton("✕ 取消")
        self.btn_confirm.clicked.connect(self.on_confirm)
        self.btn_raw.clicked.connect(self.on_save_raw)
        self.btn_cancel.clicked.connect(self.on_cancel)
        row_btn.addWidget(self.btn_confirm)
        row_btn.addWidget(self.btn_raw)
        row_btn.addWidget(self.btn_cancel)
        opt.addLayout(row_btn)

        layout.addWidget(self.options_box)

        self.suggest = QLabel("AI 建议：—")
        self.suggest.setObjectName("suggest")
        layout.addWidget(self.suggest)

        self.hint = QLabel("Enter 开始整理 · Esc 取消 · 文件可直接拖进来")
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)

        self._mode = "edit"
        self._analyzed = None
        self._source = "手动"
        self.image_path = None
        self.files = []
        self._drag_pos = None
        self._analyzer = None
        self._saver = None
        self.setAcceptDrops(True)
        self._set_mode("edit")

    # ---------- 工具 ----------
    @staticmethod
    def _mk_label(text):
        lb = QLabel(text)
        lb.setObjectName("rowLabel")
        return lb

    def _set_mode(self, mode):
        """edit：录入态；preview：预览确认态"""
        self._mode = mode
        if mode == "edit":
            self.setFixedHeight(470)
            self.result_view.hide()
            self.options_box.hide()
            self.input.setEnabled(True)
        else:
            self.setFixedHeight(690)  # 预览确认：多出结果区+选项区
            self.result_view.show()
            self.options_box.show()
            self.input.setEnabled(False)
            self._refresh_topics()
            self.btn_confirm.setFocus()

    def _refresh_topics(self):
        current = self.topic_combo.currentText()
        self.topic_combo.clear()
        self.topic_combo.addItems(db.get_topics())
        if current:
            self.topic_combo.setCurrentText(current)

    # ---------- 剪贴板一步录入 ----------
    def fill_from_clipboard(self):
        if self._mode != "edit":
            return
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        self.files = []
        self._clear_media()

        pix = cb.pixmap()  # 无图时返回 null pixmap（offscreen 下 mimeData 可能为 None）
        has_image = not pix.isNull()
        if has_image:
            # 磁盘保存原始分辨率原图（放大查看清晰）；缩放只用于屏幕预览显示
            os.makedirs(TMP_DIR, exist_ok=True)
            self.image_path = os.path.join(TMP_DIR, f"clip_{int(time.time())}.png")
            pix.save(self.image_path, "PNG")
            show = pix.scaled(360, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation) \
                if (pix.width() > 360 or pix.height() > 150) else pix
            self.preview.setPixmap(show)
            self.preview.show()
        elif mime and mime.hasUrls():
            urls = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            if urls:
                self.files = urls
                self.file_tag.setText("📎 " + "、".join(os.path.basename(u) for u in urls[:3]))
                self.file_tag.show()

        # 有图片时忽略剪贴板文本（微信复制图片时文本是 file:// 路径，会污染内容字段）；
        # 微信复制文件时同理（文本为 file:///D:/... 本地路径，用文件名代替）
        text = cb.text().strip()
        if self.files and text.startswith("file:///"):
            text = ""
        if text and not has_image and not self.input.toPlainText().strip():
            self.input.setPlainText(text)

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

    # ---------- 流程：Enter → 分析 → 预览 → 确认 ----------
    def on_save(self):
        if self._mode == "preview":
            self.on_confirm()
            return
        text = self.input.toPlainText().strip()
        if not text and not self.image_path and not self.files:
            self.hint.setText("⚠ 没有可保存的内容")
            return
        if self.image_path:
            self._source = "截图"
        elif self.files:
            self._source = "拖拽"
        else:
            self._source = "剪贴板" if text == QApplication.clipboard().text().strip() else "手动"

        self._set_mode("preview")
        self.result_view.setPlainText("🔄 AI 正在分析整理…")
        self.hint.setText("AI 整理中，请稍候…")
        self._analyzer = AnalyzeWorker(text, self.image_path, self.files, self)
        self._analyzer.done.connect(self._on_analyzed)
        self._analyzer.failed.connect(self._on_analyze_failed)
        self._analyzer.start()

    def _on_analyzed(self, result):
        self._analyzed = result
        cls = result.get("cls") or {}
        if result.get("chat"):
            main = cls.get("main_point") or ""
            branches = cls.get("branches") or []
            lines = [f"📌 主观点：{main}"] if main else []
            for b in branches:
                if b.get("type") == "qa":
                    lines.append(f"❓ {b.get('q', '')}\n💡 {b.get('a', '')}")
                else:
                    lines.append(f"📎 {b.get('label', '补充')}：{b.get('text', '')}")
            self.result_view.setPlainText("\n\n".join(lines) or "（未能提炼，原文会完整保留）")
        elif result.get("kind") == "image":
            self.result_view.setPlainText("🖼 图片已就绪（不做文字识别）\n请在下方设置主题、重要度等分类")
        else:
            t = cls.get("main_point") or cls.get("summary")
            self.result_view.setPlainText(f"📝 摘要：{t or '（无文本摘要）'}")
        self.topic_combo.setCurrentText(cls.get("topic") or "其他")
        self.suggest.setText(f"AI 分类：{cls.get('topic', '其他')} · {cls.get('priority', '中')} · "
                             f"{cls.get('period', '永久参考')} · 截止 {cls.get('due_date') or '无'}")
        self.hint.setText("确认无误按 Enter 保存 · 可改主题/重要度/截止 · Esc 取消")
        self.btn_confirm.setFocus()

    def _on_analyze_failed(self, err):
        self.result_view.setPlainText(f"❌ AI 整理失败：{err}\n\n可点击「仅存原文」直接保存，或 Esc 取消")
        self._analyzed = None
        self.hint.setText("AI 整理失败，可仅存原文或取消")

    def _collect_payload(self, use_ai):
        a = self._analyzed
        cls = a.get("cls") or {}
        pri = self.pri_group.checkedButton().text() if self.pri_group.checkedButton() else (
            cls.get("priority") if use_ai else "中")
        per = self.period_group.checkedButton().text() if self.period_group.checkedButton() else (
            cls.get("period") if use_ai else "永久参考")
        due = None
        if self.due_chosen:
            # 用户显式选过截止（含"无"）→ 完全尊重用户选择，AI 识别不覆盖
            if self.due_days:
                due = (datetime.now() + timedelta(days=self.due_days)).strftime("%Y-%m-%d")
        elif use_ai:
            # 用户未主动选 → 采纳 AI 识别出的截止日期
            due = cls.get("due_date")
        payload = {
            "kind": a.get("kind", "text"),
            "content": (a.get("text") or "")[:2000],
            "media_path": a.get("media_path"),
            "source": self._source,
            "topic": self.topic_combo.currentText().strip() or "其他",
            "priority": pri,
            "period": per,
            "due_date": due,
            "ocr_text": a.get("ocr"),
        }
        if use_ai:
            payload["tags"] = ",".join(cls.get("tags", [])) or None
            # 卡片标题（链接卡=文章标题，普通卡=一句话要点；聊天卡=主观点）
            if cls.get("main_point"):
                payload["main_point"] = cls.get("main_point")
            if a.get("chat"):
                payload["branches"] = json.dumps(cls.get("branches"), ensure_ascii=False) \
                    if cls.get("branches") else None
        return payload

    def on_confirm(self):
        if not self._analyzed:
            return
        self._save(self._collect_payload(use_ai=True))

    def on_save_raw(self):
        """仅存原文：不采纳 AI 整理，主题/重要度等仍可手动选"""
        if not self._analyzed:
            return
        self._save(self._collect_payload(use_ai=False))

    def _save(self, payload):
        self.hint.setText("🔄 保存中…")
        self._saver = SaveWorker(payload, self)
        self._saver.done.connect(self._on_saved)
        self._saver.failed.connect(self._on_failed)
        self._saver.start()

    def _on_saved(self, card_id):
        self._clear_all()
        self.hint.setText(f"✅ 已收纳（#{card_id}）")
        QTimer.singleShot(1200, self.hide)

    def _on_failed(self, err):
        self.hint.setText(f"❌ 保存失败: {err}")

    # ---------- 取消 / 清空 ----------
    def on_cancel(self):
        if self._mode == "preview" and self._analyzed:
            self._clear_all()
        else:
            self._clear_all()
            self.hide()

    def _clear_all(self):
        self.input.clear()
        self._clear_media()
        self.result_view.clear()
        for g in (self.pri_group, self.period_group, self.due_group):
            if g.checkedButton():
                g.setExclusive(False)
                g.checkedButton().setChecked(False)
                g.setExclusive(True)
        self.due_days = None
        self.due_chosen = False
        self._analyzed = None
        self.input.setEnabled(True)
        self._set_mode("edit")
        self.suggest.setText("AI 建议：—")
        self.hint.setText("Enter 开始整理 · Esc 取消 · 文件可直接拖进来")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.on_cancel()
            return
        super().keyPressEvent(e)

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
