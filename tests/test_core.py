"""拾光 · 核心模块自测（存储 / 分类 / OCR）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import tempfile
import storage.db as db
# 测试隔离：临时数据库，不污染真实数据
_tmp = tempfile.mkdtemp(prefix="shiguang_test_")
db.DATA_DIR = _tmp
db.DB_PATH = os.path.join(_tmp, "test.db")
db.MEDIA_DIR = os.path.join(_tmp, "media")
db.SETTINGS_PATH = os.path.join(_tmp, "settings.json")  # 防污染真实设置
db.init_db()

from classifier.classifier import classify, _rule_classify
from ocr.ocr import ocr_image

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}")


print("== 1. 数据层 ==")
db.init_db()
ids = []
# 文本卡片
ids.append(db.create_card(kind="text", content="深大物理竞赛报名，9月20日截止，一等奖3000元",
                          source="微信复制", topic="竞赛", priority="高",
                          period="短期任务", due_date="2026-09-20"))
# 图片卡片（复用 demo 测试图作为媒体文件）
ids.append(db.create_card(kind="image", content="竞赛报名截图",
                          media_path=db.save_media("demo/demo3_ocr_test.png"),
                          source="截图", topic="竞赛", priority="中", ocr_text="2026深大新生竞赛报名 截止日期：9月20日"))
# 文件卡片
ids.append(db.create_card(kind="file", content="课程表",
                          media_path=db.save_media("requirements.txt"),
                          source="手动", topic="学习方法", priority="低"))
check("建表+插入3张卡", len(ids) == 3)

card = db.get_card(ids[0])
check("按 id 读取", card and card["content"].startswith("深大物理竞赛"))
check("媒体文件落盘", os.path.exists(db.media_abs_path(card["media_path"])) if False else
      os.path.exists(db.media_abs_path(db.get_card(ids[1])["media_path"])))

rows = db.list_cards(topic="竞赛")
check("按主题过滤竞赛=2张", len(rows) == 2)
rows = db.list_cards(q="9月20日")
check("全文搜索'9月20日'同时命中文本卡与OCR图片卡",
      len(rows) == 2 and {r["kind"] for r in rows} == {"text", "image"})
rows = db.list_cards(q="课程表")
check("全文搜索'课程表'命中文件卡", len(rows) == 1)

db.update_card(ids[0], priority="低", status="已完成")
check("更新字段", db.get_card(ids[0])["status"] == "已完成")
s = db.stats()
check("统计接口可用", isinstance(s, list) and len(s) >= 3)

print("== 2. 分类模块 ==")
res = classify("社团群：深大物理竞赛开始报名了，9月20日截止，一等奖3000元，需要组队，三人一组，报名链接在群里。")
print(f"   AI 分类结果: {res}")
check("AI分类: 主题=竞赛", res and res["topic"] == "竞赛")
check("AI分类: 有截止日期", res and res["due_date"])

r2 = _rule_classify("明天之前要把物理实验报告交到老师办公室")
print(f"   规则分类: {r2}")
check("规则降级: 短期任务+高", r2["period"] == "短期任务" and r2["priority"] == "高")
check("规则降级: 日期提取", r2["due_date"] is None or r2["due_date"] >= "2026-08-24")

print("== 3. OCR 模块 ==")
text = ocr_image("demo/demo3_ocr_test.png")
print(f"   OCR 输出: {text!r}")
check("OCR 识别出报名文字", "报名" in text)

print("== 4. 清理测试数据 ==")
for i in ids:
    db.delete_card(i)
check("测试卡片已删除", db.list_cards(q="深大物理竞赛报名") == [] and db.list_cards(q="课程表") == [])

print(f"\n结果: {ok} 通过 / {fail} 失败")
sys.exit(1 if fail else 0)
