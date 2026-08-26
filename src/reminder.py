"""拾光 · 到期提醒：定时检查卡片截止日期，通过托盘弹 Windows 通知

- 全局开关 + 全局默认提前天数（data/settings.json）
- 每条卡片可单独设置提醒（remind_days：null=跟随全局, -1=不提醒, N=提前N天）
- 每分钟检查一次；同一天不重复提醒（last_remind 字段防重）
"""
import os
import sys
from datetime import date, timedelta

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QSystemTrayIcon

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from storage import db

DONE_STATUSES = ("已完成", "已归档")


class Reminder(QObject):
    """每分钟检查一次；check() 返回今天需要提醒的卡片（纯逻辑，可注入 today 单测）"""

    def __init__(self, tray=None, interval_ms=60000, parent=None):
        super().__init__(parent)
        self.tray = tray
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(interval_ms)

    def check(self, today=None):
        """返回 [(card, days_left)] 需要提醒的卡片"""
        today = today or date.today().strftime("%Y-%m-%d")
        today_d = date.fromisoformat(today)
        settings = db.load_settings()
        if not settings.get("remind_enabled", True):
            return []
        out = []
        for card in db.list_cards():
            due = card.get("due_date")
            if not due or card.get("status") in DONE_STATUSES:
                continue
            days = card.get("remind_days")
            if days is None or days == "":
                days = int(settings.get("remind_days", 1))
            else:
                days = int(days)  # 兼容 ALTER 加的 TEXT 列（读出为字符串）
            if days < 0:
                continue  # 该卡不提醒
            try:
                due_d = date.fromisoformat(due)
            except ValueError:
                continue
            remind_d = due_d - timedelta(days=days)
            if remind_d <= today_d <= due_d and card.get("last_remind") != today:
                out.append((card, (due_d - today_d).days))
        return out

    def tick(self):
        today = date.today().strftime("%Y-%m-%d")
        due = self.check(today)
        if due:
            print(f"[提醒] {today} 检查到 {len(due)} 条待提醒卡片", flush=True)
        for card, left in due:
            db.update_card(card["id"], last_remind=today)
            if self.tray:
                summary = (card.get("main_point") or card.get("content") or "").split("\n")[0]
                summary = (summary or "（无内容）")[:30]
                if left >= 0:
                    msg = f"还剩 {left} 天 · {card.get('topic', '其他')}"
                else:
                    msg = f"已逾期 {-left} 天 · {card.get('topic', '其他')}"
                self.tray.showMessage("⏰ 拾光提醒", f"{summary}\n{msg}",
                                      QSystemTrayIcon.Information, 8000)
