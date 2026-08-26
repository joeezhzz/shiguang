"""拾光 · 聊天记录结构化整理测试"""
import json
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

from classifier.classifier import is_chat, classify_chat, _rule_classify_chat

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}")


chat_sample = """学长：考研英语单词用艾宾浩斯记忆法，每天早晚各背30分钟，配合真题阅读巩固
小明：真题什么时候开始刷合适？
学长：9月开始，先专注背单词
小红：作文模板需要背吗？
学长：11月开始背王江涛的模板就行"""

plain = "深大物理竞赛报名9月20日截止"

print("== 1. 聊天记录检测 ==")
check("识别多轮对话", is_chat(chat_sample))
check("普通文本不误判", not is_chat(plain))
check("单行不算聊天", not is_chat("学长：你好"))
check("空文本", not is_chat(""))
# 微信复制不带昵称的纯消息流
plain_flow = """想去做科研肯去联系老师就行，不过建议先了解一下自己想往哪个方向发展，老师都是干什么的再做决定
这些官网上都能查到
大一确定好了进去了是不是也是熟悉一下做一下苦力什么的呀
不一定，要看老师
也要看你的学习能力"""
check("识别无昵称纯消息流", is_chat(plain_flow))

print("== 2. AI 结构化整理（真实调用） ==")
res = classify_chat(chat_sample)
print(json.dumps(res, ensure_ascii=False, indent=2))
check("有主观点", bool(res.get("main_point")))
check("有分支", bool(res.get("branches")))
check("主题合法", res.get("topic") in db.TOPICS)

print("== 3. 规则降级 ==")
r = _rule_classify_chat(chat_sample)
check("降级有主观点+分支", bool(r.get("main_point")) and bool(r.get("branches")))

print("== 4. 数据库存取 + 搜索命中 ==")
cid = db.create_card(kind="text", content=chat_sample, source="微信复制",
                     topic=res["topic"], priority=res["priority"], period=res["period"],
                     tags=",".join(res.get("tags", [])), main_point=res["main_point"],
                     branches=json.dumps(res["branches"], ensure_ascii=False))
card = db.get_card(cid)
check("主观点入库", card["main_point"] == res["main_point"])
tag = res.get("tags", ["考研"])[0]
check("标签可搜索命中", any(c["id"] == cid for c in db.list_cards(q=tag)))
check("主观点可搜索命中", any(c["id"] == cid for c in db.list_cards(q=res["main_point"][:4])))
db.delete_card(cid)
check("清理", db.get_card(cid) is None)

print(f"\n结果: {ok} 通过 / {fail} 失败")
sys.exit(1 if fail else 0)
