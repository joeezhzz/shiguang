"""拾光 · 分类模块：DeepSeek AI 分类（优先）+ 规则降级（断网/失败时）

统一入口 classify(text) -> dict：
  {"topic": 主题, "priority": 高|中|低, "period": 效用期,
   "tags": [...], "due_date": "YYYY-MM-DD"|None, "summary": 摘要}
"""
import json
import os
import re
import urllib.request
from datetime import datetime

from storage.db import TOPICS, parse_due

MODELS = ["deepseek-chat", "deepseek-v4-flash"]
API_URL = "https://api.deepseek.com/chat/completions"


def load_api_key():
    """复用 Hermes config.yaml 里 custom provider 的 key（实测有效），备选 .env"""
    cfg = os.path.expanduser("~/AppData/Local/hermes/config.yaml")
    if os.path.exists(cfg):
        for line in open(cfg, encoding="utf-8"):
            s = line.strip()
            if s.startswith("api_key:"):
                v = s.split(":", 1)[1].strip().strip('"').strip("'")
                if v and not v.startswith("«redacted"):
                    return v
    envp = os.path.expanduser("~/AppData/Local/hermes/.env")
    if os.path.exists(envp):
        for line in open(envp, encoding="utf-8"):
            s = line.strip()
            if s.startswith("DEEPSEEK_API_KEY="):
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _ai_classify(text, today):
    key = load_api_key()
    if not key:
        raise RuntimeError("no api key")
    prompt = (
        f"今天是 {today}。用户把一条信息发给你，请归类。\n"
        "只输出严格 JSON，不要其他任何文字：\n"
        '{"topic": 从[' + ",".join(TOPICS) + ']选一个,'
        ' "priority": "高"|"中"|"低",'
        ' "period": "短期任务"|"长期计划"|"永久参考",'
        ' "tags": ["标签1","标签2"],'
        ' "due_date": "YYYY-MM-DD"或null（从原文推断截止日期，用今天的年份）,'
        ' "summary": "不超过20字"}\n'
        f"信息内容：{text[:2000]}"
    )
    body = json.dumps({
        "model": MODELS[0],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 300,
    }).encode()
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    content = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise ValueError("no json in reply")
    return _normalize(json.loads(m.group(0)), text, today)


def _normalize(d, text, today):
    topic = d.get("topic", "其他")
    if topic not in TOPICS:
        topic = "其他"
    priority = d.get("priority", "中")
    priority = priority if priority in ("高", "中", "低") else "中"
    period = d.get("period", "永久参考")
    period = period if period in ("短期任务", "长期计划", "永久参考") else "永久参考"
    tags = d.get("tags") or []
    tags = [str(t) for t in tags][:5]
    due = d.get("due_date")
    if due:
        m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(due))
        if m:
            due = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        else:
            due = None
    if not due:
        due = parse_due(text, datetime.strptime(today, "%Y-%m-%d"))
    summary = str(d.get("summary", ""))[:30]
    return {"topic": topic, "priority": priority, "period": period,
            "tags": tags, "due_date": due, "summary": summary}


# ---------- 规则降级（断网 / API 失败时兜底，保证功能不瘫） ----------

_RULES = [
    ("竞赛", ["竞赛", "报名", "比赛", "参赛", "挑战杯", "大创", "国赛", "省赛", "物理竞赛", "组队"]),
    ("考研保研", ["考研", "保研", "复试", "初试", "研究生", "推免", "调剂"]),
    ("学习方法", ["学习", "方法", "笔记", "复习", "备考", "课程", "教材", "网课", "刷题", "预习", "作业"]),
    ("就业赚钱", ["就业", "实习", "招聘", "简历", "面试", "兼职", "赚钱", "工资", "秋招", "春招", "offer"]),
    ("生活小妙招", ["妙招", "生活", "技巧", "省钱", "收纳", "菜谱", "健康", "锻炼"]),
]


def _rule_classify(text, today=None):
    today = today or datetime.now().strftime("%Y-%m-%d")
    topic = "其他"
    for t, kws in _RULES:
        if any(k in text for k in kws):
            topic = t
            break
    if any(k in text for k in ["截止", "报名", "提交", "申请", "ddl", "deadline", "明天", "本周", "尽快"]):
        priority, period = "高", "短期任务"
    elif any(k in text for k in ["计划", "坚持", "每天", "每周", "长期", "持续"]):
        priority, period = "中", "长期计划"
    else:
        priority, period = "中", "永久参考"
    due = parse_due(text, datetime.strptime(today, "%Y-%m-%d"))
    return {"topic": topic, "priority": priority, "period": period,
            "tags": [topic], "due_date": due, "summary": text[:20]}


def classify(text, today=None):
    """统一入口：AI 优先，失败自动降级规则分类"""
    if not text or not text.strip():
        return None
    today = today or datetime.now().strftime("%Y-%m-%d")
    try:
        return _ai_classify(text, today)
    except Exception as e:
        print(f"[classifier] AI 分类失败，降级规则分类: {e}")
        return _rule_classify(text, today)


if __name__ == "__main__":
    print(json.dumps(classify("社团群：深大物理竞赛报名，9月20日截止，一等奖3000元，需组队三人"), ensure_ascii=False, indent=2))
