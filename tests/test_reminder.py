"""拾光 · 到期提醒逻辑测试（临时库隔离 + 注入日期）"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtCore import QCoreApplication

import storage.db as db
_tmp = tempfile.mkdtemp(prefix="shiguang_test_")
db.DATA_DIR = _tmp
db.DB_PATH = os.path.join(_tmp, "test.db")
db.MEDIA_DIR = os.path.join(_tmp, "media")
db.SETTINGS_PATH = os.path.join(_tmp, "settings.json")  # 关键：防止污染真实设置
db.init_db()

from reminder import Reminder

_app = QCoreApplication([])
TODAY = "2026-08-25"
ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}")


def mk(due, remind_days=None, status="待处理", last_remind=None, content="测试卡"):
    return db.create_card(content=content, due_date=due, remind_days=remind_days,
                          status=status, last_remind=last_remind)


r = Reminder(tray=None)  # tray=None 只测逻辑不弹通知
db.save_settings({"remind_enabled": True, "remind_days": 1})

print("== 到期提醒逻辑 ==")
cid = mk("2026-08-26", 1)  # 明天截止，提前1天 → 今天该提醒
res = r.check(TODAY)
check("提前1天提醒", any(c[0]["id"] == cid for c in res))

mk("2026-08-26", 1, last_remind=TODAY)  # 同卡已提醒过
res = r.check(TODAY)
check("同一天不重复提醒", sum(1 for c, _ in res if c["due_date"] == "2026-08-26") == 1)

mk("2026-08-26", 1, status="已完成")
res = r.check(TODAY)
check("已完成不提醒", sum(1 for c, _ in res if c["status"] == "已完成") == 0)

mk("2026-08-26", -1)
res = r.check(TODAY)
check("该卡设-1不提醒", sum(1 for c, _ in res if c["remind_days"] == -1) == 0)

mk("2026-08-28", 1)  # 后天截止，提前1天=明天 → 今天不提醒
res = r.check(TODAY)
check("未到提醒日不提醒", sum(1 for c, _ in res if c["due_date"] == "2026-08-28") == 0)

mk("2026-08-25", 1)  # 今天截止 → 窗口期内提醒
res = r.check(TODAY)
check("到期当天提醒", sum(1 for c, _ in res if c["due_date"] == "2026-08-25") >= 1)

cid2 = mk("2026-08-26", 1, content="剩余天数")
left = [x for x in r.check(TODAY) if x[0]["id"] == cid2]
check("剩余天数计算=1", bool(left) and left[0][1] == 1)

mk("2026-08-26", "1", content="字符串天数兼容")  # 模拟真实库 ALTER 加的 TEXT 列
res = r.check(TODAY)
check("字符串提前天数兼容", any(c["content"] == "字符串天数兼容" for c, _ in res))

db.save_settings({"remind_enabled": False, "remind_days": 1})
res = r.check(TODAY)
check("全局关闭不提醒", len(res) == 0)

print("== 清理 ==")
for c in db.list_cards():
    db.delete_card(c["id"])
check("测试数据清理", db.list_cards() == [])

print(f"\n结果: {ok} 通过 / {fail} 失败")
sys.exit(1 if fail else 0)
