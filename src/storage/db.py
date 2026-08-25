"""拾光 · 数据层：SQLite 卡片存储 + 媒体文件库

- 卡片：文本 / 图片 / 文件三类，统一入库
- 媒体文件（图片、上传的文件）保存在 data/media/，数据库存相对路径
- 线程安全（Qt 悬浮窗与 Flask 看板可能同时访问）
- 聊天记录卡片额外存 main_point（主观点）+ branches（分支 JSON）
"""
import os
import re
import sqlite3
import shutil
import threading
import uuid
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
DB_PATH = os.path.join(DATA_DIR, "shiguang.db")
MEDIA_DIR = os.path.join(DATA_DIR, "media")

TOPICS = ["学习方法", "考研保研", "竞赛", "生活小妙招", "就业赚钱", "其他"]
PRIORITIES = ["高", "中", "低"]
PERIODS = ["短期任务", "长期计划", "永久参考"]
STATUSES = ["待处理", "进行中", "已完成", "已归档"]

_lock = threading.Lock()


def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """建表（幂等）"""
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL DEFAULT 'text',      -- text / image / file
                    content TEXT NOT NULL DEFAULT '',        -- 文本内容或描述（聊天记录为原文）
                    media_path TEXT,                         -- 相对 data/ 的媒体路径
                    source TEXT DEFAULT '手动',              -- 微信复制/截图/网页/手动
                    topic TEXT DEFAULT '其他',
                    priority TEXT DEFAULT '中',
                    period TEXT DEFAULT '永久参考',
                    due_date TEXT,                           -- YYYY-MM-DD
                    status TEXT DEFAULT '待处理',
                    ocr_text TEXT,                           -- 图片 OCR 结果
                    note TEXT,
                    tags TEXT,                               -- 逗号分隔的建议标签
                    main_point TEXT,                         -- 聊天记录主观点
                    branches TEXT,                           -- 分支 JSON：[{type:qa|note,...}]
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            # 兼容旧表：补齐新增列
            cols = [r[1] for r in conn.execute("PRAGMA table_info(cards)")]
            for col in ("tags", "main_point", "branches"):
                if col not in cols:
                    conn.execute(f"ALTER TABLE cards ADD COLUMN {col} TEXT")
            for col in ("topic", "priority", "status", "due_date"):
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON cards({col})")
            conn.commit()
        finally:
            conn.close()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_media(src_path):
    """把图片/文件复制进 data/media/，返回相对路径（data/media/xxx）"""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    ext = os.path.splitext(src_path)[1] or ".bin"
    name = uuid.uuid4().hex[:12] + ext
    dst = os.path.join(MEDIA_DIR, name)
    shutil.copy2(src_path, dst)
    return "media/" + name  # 统一正斜杠，跨平台一致（Windows 下 os.path.join 会出反斜杠）


def media_abs_path(rel_path):
    if not rel_path:
        return None
    return os.path.join(DATA_DIR, rel_path)


def create_card(kind="text", content="", media_path=None, source="手动",
                topic="其他", priority="中", period="永久参考",
                due_date=None, status="待处理", ocr_text=None, note=None, tags=None,
                main_point=None, branches=None):
    with _lock:
        conn = _conn()
        try:
            now = _now()
            cur = conn.execute(
                """INSERT INTO cards (kind, content, media_path, source, topic,
                   priority, period, due_date, status, ocr_text, note, tags,
                   main_point, branches, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (kind, content, media_path, source, topic, priority,
                 period, due_date, status, ocr_text, note, tags,
                 main_point, branches, now, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_card(card_id):
    with _lock:
        conn = _conn()
        try:
            row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_cards(topic=None, priority=None, status=None, period=None, q=None):
    """查询卡片；q 为全文搜索（内容/OCR/备注/标签/主观点）"""
    sql = "SELECT * FROM cards WHERE 1=1"
    args = []
    if topic:
        sql += " AND topic=?"; args.append(topic)
    if priority:
        sql += " AND priority=?"; args.append(priority)
    if status:
        sql += " AND status=?"; args.append(status)
    if period:
        sql += " AND period=?"; args.append(period)
    if q:
        sql += (" AND (content LIKE ? OR ocr_text LIKE ? OR note LIKE ? "
                "OR tags LIKE ? OR main_point LIKE ?)")
        args += [f"%{q}%"] * 5
    sql += " ORDER BY created_at DESC"
    with _lock:
        conn = _conn()
        try:
            rows = conn.execute(sql, args).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def update_card(card_id, **fields):
    """更新指定字段（白名单），返回是否成功"""
    allowed = {"content", "source", "topic", "priority", "period",
               "due_date", "status", "ocr_text", "note", "tags",
               "main_point", "branches"}
    keys = [k for k in fields if k in allowed]
    if not keys:
        return False
    sets = ", ".join(f"{k}=?" for k in keys)
    args = [fields[k] for k in keys] + [_now(), card_id]
    with _lock:
        conn = _conn()
        try:
            cur = conn.execute(f"UPDATE cards SET {sets}, updated_at=? WHERE id=?", args)
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def delete_card(card_id):
    """删除卡片及其媒体文件"""
    card = get_card(card_id)
    with _lock:
        conn = _conn()
        try:
            conn.execute("DELETE FROM cards WHERE id=?", (card_id,))
            conn.commit()
        finally:
            conn.close()
    if card and card.get("media_path"):
        p = media_abs_path(card["media_path"])
        if p and os.path.exists(p):
            os.remove(p)


def stats():
    """看板统计：各状态/主题/优先级数量"""
    with _lock:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT status, topic, priority, COUNT(*) n FROM cards GROUP BY status, topic, priority"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_topics():
    """主题列表 = 内置 5 类 + 用户自定义（从已存卡片中自动收集）"""
    with _lock:
        conn = _conn()
        try:
            rows = conn.execute("SELECT DISTINCT topic FROM cards WHERE topic IS NOT NULL AND topic != ''").fetchall()
        finally:
            conn.close()
    custom = [r["topic"] for r in rows if r["topic"] not in TOPICS]
    return TOPICS + custom


def parse_due(text, now=None):
    """从文本里粗提取日期：'9月20日' → '2026-09-20'；失败返回 None"""
    if not text:
        return None
    now = now or datetime.now()
    m = re.search(r"(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if m:
        return f"{now.year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


init_db()
