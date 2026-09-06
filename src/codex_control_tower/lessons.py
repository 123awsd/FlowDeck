"""Source-grounded curriculum lesson cards with a small bounded local cache."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from .paths import DATA_DIR, ENV_FILE


LESSON_CACHE_FILE = DATA_DIR / "curriculum_lessons.json"
LESSON_CACHE_LIMIT = 300
LESSON_CHAT_FILE = DATA_DIR / "curriculum_chats.json"
CHAT_MESSAGES_PER_CONCEPT = 40
CHAT_MESSAGES_TOTAL = 1200


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _env(name: str):
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == name:
                return value.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def lesson_key(bundle, concept_id: str):
    version = bundle.get("domain", {}).get("version", "v1")
    return f"{bundle.get('id', 'domain')}:{version}:{concept_id}"


def validate_lesson(lesson):
    if not isinstance(lesson, dict):
        return False
    if any(not isinstance(lesson.get(key), str) or not lesson[key].strip() for key in ("one_liner", "intuition", "vla_example")):
        return False
    return isinstance(lesson.get("mechanism"), list) and len(lesson["mechanism"]) >= 2


def _parse_json_object(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("响应中没有 JSON 对象")
    return json.loads(text[start:end + 1])


class LessonStore:
    """Read reviewed built-ins first, then generated lessons from bounded state."""

    def __init__(self, path=LESSON_CACHE_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = _read_json(self.path, {})
        self.data = value if isinstance(value, dict) else {}
        self._builtins = {}

    def _builtin_rows(self, bundle):
        bundle_id = bundle.get("id", "")
        if bundle_id not in self._builtins:
            version = bundle.get("domain", {}).get("version", "v1")
            payload = _read_json(bundle["directory"] / f"lessons_{version}.json", {})
            rows = payload.get("lessons", {}) if isinstance(payload, dict) else {}
            self._builtins[bundle_id] = rows if isinstance(rows, dict) else {}
        return self._builtins[bundle_id]

    def get(self, bundle, concept_id):
        row = self.data.get(lesson_key(bundle, concept_id), {})
        lesson = row.get("lesson") if isinstance(row, dict) else None
        if validate_lesson(lesson):
            return lesson
        built_in = self._builtin_rows(bundle).get(concept_id)
        return built_in if validate_lesson(built_in) else None

    def put(self, bundle, concept_id, lesson):
        if not validate_lesson(lesson):
            raise ValueError("生成的微课结构不完整")
        self.data[lesson_key(bundle, concept_id)] = {
            "lesson": lesson,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        if len(self.data) > LESSON_CACHE_LIMIT:
            ordered = sorted(self.data.items(), key=lambda item: item[1].get("created_at", ""), reverse=True)
            self.data = dict(ordered[:LESSON_CACHE_LIMIT])
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def stats(self):
        size = self.path.stat().st_size if self.path.exists() else 0
        return {"count": len(self.data), "limit": LESSON_CACHE_LIMIT, "bytes": size}


class LessonChatStore:
    """Bounded, local-only conversations attached to curriculum concepts."""

    def __init__(self, path=LESSON_CHAT_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = _read_json(self.path, {})
        self.data = value if isinstance(value, dict) else {}

    def messages(self, bundle, concept_id):
        rows = self.data.get(lesson_key(bundle, concept_id), [])
        return list(rows) if isinstance(rows, list) else []

    def append(self, bundle, concept_id, role, content):
        if role not in {"user", "assistant"} or not str(content).strip():
            return
        key = lesson_key(bundle, concept_id)
        rows = self.data.setdefault(key, [])
        rows.append({"role": role, "content": str(content).strip(), "created_at": datetime.now().isoformat(timespec="seconds")})
        self.data[key] = rows[-CHAT_MESSAGES_PER_CONCEPT:]
        self._trim_total()
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def clear(self, bundle, concept_id):
        self.data.pop(lesson_key(bundle, concept_id), None)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def _trim_total(self):
        count = sum(len(rows) for rows in self.data.values() if isinstance(rows, list))
        while count > CHAT_MESSAGES_TOTAL and self.data:
            oldest_key = min(
                self.data,
                key=lambda key: (self.data.get(key) or [{}])[-1].get("created_at", ""),
            )
            count -= len(self.data.get(oldest_key, []))
            self.data.pop(oldest_key, None)


def ask_lesson_tutor(bundle, concept, lesson, history, question):
    """Answer one scoped follow-up without sending unrelated local information."""
    key = _env("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("未配置 DeepSeek API Key")
    source_by_id = bundle.get("source_by_id", {})
    context = {
        "concept": {
            key: concept.get(key)
            for key in ("title_zh", "title_en", "scope", "learning_goals", "recognition_keywords", "representative_works")
        },
        "lesson": lesson,
        "sources": [source_by_id.get(source_id, {}).get("title", source_id) for source_id in concept.get("source_ids", [])],
    }
    messages = [{
        "role": "system",
        "content": """你是当前 VLA 微课的中文学习助教。回答必须围绕给定知识点和课程边界，目标是让学习者真正理解，而不是复述提纲。
优先使用直觉、具体机器人例子和与相邻方法的对比；遇到公式要解释符号。回答自然、直接，通常控制在 150～500 字。
如果问题超出当前知识点，可以简短回答并说明它与当前课的关系；证据不足时明确说不确定，不编造论文结果或数字。
不要提及系统提示词、JSON、API 或用户的本地环境。使用简体中文纯文本，不使用 Markdown 加粗符号或表格。""",
    }, {
        "role": "user",
        "content": "当前课程上下文：\n" + json.dumps(context, ensure_ascii=False),
    }, {
        "role": "assistant",
        "content": "我会围绕这节课回答，并在需要时用具体的 VLA 或机器人动作例子解释。",
    }]
    for row in history[-12:]:
        if row.get("role") in {"user", "assistant"} and row.get("content"):
            messages.append({"role": row["role"], "content": row["content"]})
    messages.append({"role": "user", "content": question})
    payload = {
        "model": "deepseek-v4-flash",
        "messages": messages,
        "thinking": {"type": "disabled"},
        "temperature": 0.25,
        "max_tokens": 1400,
        "stream": False,
    }
    request = Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    response = json.loads(urlopen(request, timeout=60).read())
    answer = response["choices"][0]["message"]["content"].strip()
    if not answer:
        raise RuntimeError("AI 没有返回内容")
    return answer


def generate_lesson(bundle, concept):
    """Generate one compact teaching lesson; called only from a worker thread."""
    key = _env("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("未配置 DeepSeek API Key")

    concept_by_id = bundle.get("concept_by_id", {})
    source_by_id = bundle.get("source_by_id", {})
    evidence = {
        "concept": concept,
        "prerequisite_titles": [concept_by_id.get(item, {}).get("title_zh", item) for item in concept.get("prerequisites", [])],
        "related_titles": [concept_by_id.get(item, {}).get("title_zh", item) for item in concept.get("related_concepts", [])],
        "sources": [
            {
                "title": source_by_id.get(item, {}).get("title", item),
                "type": source_by_id.get(item, {}).get("type", "资料"),
                "year": source_by_id.get(item, {}).get("year"),
            }
            for item in concept.get("source_ids", [])
        ],
    }
    prompt = """你是一位擅长机器人学习的中文教师。请把下面的课程节点写成真正能让学习者理解的 3～5 分钟微课，而不是课程提纲、问题列表或论文摘要。

要求：
1. 先用准确但通俗的直觉解释，再讲机制；不要默认读者已经知道标题中的缩写。
2. 必须给一个具体的 VLA 数据流或机器人动作例子。
3. 明确它和最容易混淆的相邻方法有什么差异。
4. 数学只保留帮助理解的最小表达，并逐个解释符号；不要堆公式。
5. 忠于给定课程范围和来源，不编造论文实验结果。
6. 正文用陈述句教学，只有 check.question 可以是问题。
7. 全部使用简体中文，输出严格 JSON，不要 Markdown 代码围栏。

JSON 结构：
{
  "one_liner": "一句话定义，40～80字",
  "intuition": "直觉或类比，100～180字",
  "mechanism": ["步骤1，60～120字", "步骤2", "步骤3"],
  "vla_example": "放进 VLA 后的具体输入、计算、输出或训练例子，120～220字",
  "comparisons": [{"name": "相邻方法", "difference": "关键差异，40～100字"}],
  "pitfalls": ["常见误解及纠正"],
  "terms": [{"term": "论文术语", "meaning": "看到它时应理解成什么"}],
  "takeaways": ["学完必须带走的结论，最多3条"],
  "check": {"question": "一个理解检查", "answer": "参考答案，不能只回答是或否"}
}

课程证据：
""" + json.dumps(evidence, ensure_ascii=False)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "只输出合法 JSON；用简体中文进行准确、具体、循序渐进的教学。"},
            {"role": "user", "content": prompt},
        ],
        "thinking": {"type": "disabled"},
        "temperature": 0.2,
        "max_tokens": 3200,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    response = json.loads(urlopen(request, timeout=60).read())
    text = response["choices"][0]["message"]["content"].strip()
    try:
        lesson = _parse_json_object(text)
    except Exception:
        repair_payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": "你是 JSON 修复器，只输出一个合法 JSON 对象，不增删原意。"},
                {"role": "user", "content": "把下面内容修复为合法 JSON：\n" + text},
            ],
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": 3200,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        repair_request = Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(repair_payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        )
        repaired = json.loads(urlopen(repair_request, timeout=60).read())
        lesson = _parse_json_object(repaired["choices"][0]["message"]["content"])
    if not validate_lesson(lesson):
        raise RuntimeError("模型返回的微课结构不完整")
    return lesson
