"""拾光 · 集成测试：悬浮窗录入全流程 + Flask API"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage, QColor
import pyperclip

import tempfile
import storage.db as db
# 测试隔离：临时数据库，不污染真实数据
_tmp = tempfile.mkdtemp(prefix="shiguang_test_")
db.DATA_DIR = _tmp
db.DB_PATH = os.path.join(_tmp, "test.db")
db.MEDIA_DIR = os.path.join(_tmp, "media")
db.init_db()

from collector.floatwindow import FloatWindow
from web.app import create_app

app = QApplication([])
ok = fail = 0

# 清理上次运行可能残留的测试数据（防崩溃残留污染断言）
for _c in db.list_cards(q="社团招新面试") + db.list_cards(q="报名"):
    db.delete_card(_c["id"])


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}")


def wait_worker(w, timeout_ms=90000):
    loop = QEventLoop()
    w.done.connect(loop.quit)
    w.failed.connect(lambda e: print("   [worker失败]", e))
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


win = FloatWindow()
created = []

print("== 1. 文本录入（剪贴板 → AI分类 → 入库） ==")
text = "校会通知：社团招新面试改到9月28日下午，地点在物光楼203"
QApplication.clipboard().setText(text)  # offscreen 测试用 Qt 剪贴板（真机为系统剪贴板，两者互通）
win.show()
win.fill_from_clipboard()
check("剪贴板文本自动填入输入框", win.input.toPlainText().strip() == text)
win.on_save()
wait_worker(win._analyzer)
check("预览区展示AI整理结果",
      "摘要" in win.result_view.toPlainText() or "主观点" in win.result_view.toPlainText())
win.on_confirm()
wait_worker(win._saver)
cards = db.list_cards(q="社团招新面试")
check("文本卡已入库", len(cards) == 1)
if cards:
    c = cards[0]
    created.append(c["id"])
    print(f"   入库: 主题={c['topic']} 重要度={c['priority']} 效用期={c['period']} 截止={c['due_date']} tags={c['tags']} 来源={c['source']}")
    check("来源=剪贴板", c["source"] == "剪贴板")

print("== 2. 图片录入（剪贴板图片 → 保存+OCR → 入库） ==")
# offscreen 平台 Qt 画不出文字（无字体后端），用 PIL 生成真实可 OCR 的图（真机为真实截图，无此问题）
from PIL import Image, ImageDraw, ImageFont
_pil = Image.new("RGB", (600, 300), "white")
_d = ImageDraw.Draw(_pil)
_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
_d.text((30, 60), "物光创新实验室 招新报名", fill="black", font=_font)
_d.text((30, 140), "截止 10 月 15 日", fill="black", font=_font)
from PySide6.QtGui import QImage
_qimg = QImage(_pil.tobytes(), 600, 300, 600 * 3, QImage.Format_RGB888)
QApplication.clipboard().setImage(_qimg)
win.input.clear()
win.fill_from_clipboard()
check("剪贴板图片已载入预览", win.image_path is not None and os.path.exists(win.image_path))
win.on_save()
wait_worker(win._analyzer)
win.on_confirm()
wait_worker(win._saver)
cards = db.list_cards(q="报名")
imgs = [c for c in cards if c["kind"] == "image"]
check("图片卡已入库且OCR命中搜索", len(imgs) >= 1)
if imgs:
    c = imgs[0]
    created.append(c["id"])
    print(f"   OCR: {c['ocr_text']!r}")
    check("OCR提取出报名文字", c["ocr_text"] and "报名" in c["ocr_text"])
    check("媒体文件存在", c["media_path"] and os.path.exists(db.media_abs_path(c["media_path"])))

print("== 3. Flask API ==")
client = create_app().test_client()
r = client.get("/api/cards")
check("GET /api/cards 200", r.status_code == 200 and len(r.get_json()) >= 2)
if imgs:
    r = client.get("/media/" + imgs[0]["media_path"].split("/", 1)[1])
    check("GET /media 图片可访问", r.status_code == 200)
cid = created[0]
r = client.patch(f"/api/cards/{cid}", json={"status": "已完成"})
check("PATCH 改状态", r.get_json()["ok"] and db.get_card(cid)["status"] == "已完成")
r = client.delete(f"/api/cards/{cid}")
check("DELETE 删除", r.status_code == 200 and db.get_card(cid) is None)
created.pop(0)

print("== 4. 清理 ==")
for cid in created:
    db.delete_card(cid)
check("测试数据清理完毕", db.list_cards(q="社团招新面试") == [] and db.list_cards(q="报名") == [])

# 安全退出：等待仍在运行的后台线程，避免退出时段错误
for w in (win._analyzer, win._saver):
    if w is not None and w.isRunning():
        w.wait(30000)
app.quit()

print(f"\n结果: {ok} 通过 / {fail} 失败")
sys.stdout.flush()
os._exit(1 if fail else 0)  # 硬退出：跳过 Qt 析构，避免 offscreen 平台退出段错误
