"""Demo 4: DeepSeek API 分类（技术验证）
验证：AI 能按"主题/重要程度/效用期/截止时间"给出结构化分类建议
运行：python demo4_classify.py（自动读取 hermes 配置里的 DEEPSEEK_API_KEY，不打印 key）
"""
import os
import re
import json
import urllib.request


def load_key():
    """优先取 Hermes config.yaml 里 custom provider 的 key（实测有效），备选 .env"""
    cfg = os.path.expanduser("~/AppData/Local/hermes/config.yaml")
    if os.path.exists(cfg):
        for line in open(cfg, encoding="utf-8"):
            s = line.strip()
            if s.startswith("api_key:"):
                v = s.split(":", 1)[1].strip().strip('"').strip("'")
                if v and not v.startswith("«redacted"):
                    return v
    p = os.path.expanduser("~/AppData/Local/hermes/.env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            s = line.strip()
            if s.startswith("DEEPSEEK_API_KEY="):
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    return None


key = load_key()
if not key:
    print("[FAIL] 未找到 DEEPSEEK_API_KEY（~/.hermes/.env 或 AppData/Local/hermes/.env）")
    raise SystemExit(1)
print(f"[OK] 已读取 DEEPSEEK_API_KEY（长度 {len(key)}，内容不外显）")

sample = ("社团群里看到：第九届深大物理竞赛开始报名了，9月20日截止，一等奖有3000奖金，"
          "需要组队，三人一组，报名链接在群里。")

prompt = f"""你是信息整理助手。用户把一条信息发给你，请归类。
只输出严格 JSON，不要其他任何文字：
{{"主题": 从[学习方法,考研保研,竞赛,生活小妙招,就业赚钱,其他]选一个,
 "重要程度": 高|中|低,
 "效用期": 短期任务|长期计划|永久参考,
 "建议标签": ["标签1","标签2"],
 "截止时间": "YYYY-MM-DD"或null,
 "一句话摘要": "不超过20字"}}
信息内容：{sample}"""

req = urllib.request.Request(
    "https://api.deepseek.com/chat/completions",
    data=json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
)
with urllib.request.urlopen(req, timeout=60) as r:
    data = json.loads(r.read())

content = data["choices"][0]["message"]["content"]
m = re.search(r"\{.*\}", content, re.S)  # 容忍模型用 ```json 包裹
parsed = json.loads(m.group(0)) if m else {"raw": content}
print("[OK] API 返回分类建议：")
print(json.dumps(parsed, ensure_ascii=False, indent=2))
print("[OK] 结论: DeepSeek 分类通道可用")
