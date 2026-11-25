"""纯函数层:字数、数字集合、比例、句子切分、标题候选。

这里的原则和读行一致:能算准的事绝不交给模型算。
数字有没有被模型改动、字数缩了多少,都属于能算准的。
"""

from __future__ import annotations

import re

SENT_END = "。！？；!?;"
_NUM = re.compile(r"\d+(?:\.\d+)?%?")
_FILLERS = ("其实", "基本上", "总的来说", "总体来看", "我觉得", "我认为", "真的", "非常", "比较", "稍微", "有点", "似乎")
_ORAL = {
    "搞": "做",
    "弄": "处理",
    "挺好": "较好",
    "特别": "尤其",
    "老是": "经常",
    "咋": "如何",
    "啥": "什么",
    "贼": "非常",
    "超": "很",
    "咱": "我们",
    "挺": "较",
}
_FORMAL_TO_ORAL = {v: k for k, v in _ORAL.items() if len(v) == 1}


def chars(text: str) -> int:
    """按字算,不区分中英文。"""
    return len((text or "").strip())


def sentences(text: str) -> list[str]:
    out, buf = [], ""
    for ch in text or "":
        buf += ch
        if ch in SENT_END or ch == "\n":
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def numbers(text: str) -> list[str]:
    """抽出所有数字(含小数与百分号),用于「不许凭空多出数字」的校验。"""
    return _NUM.findall(text or "")


def new_numbers(before: str, after: str) -> list[str]:
    """改写后多出来的数字。空的才叫通过。"""
    old = set(numbers(before))
    return [n for n in numbers(after) if n not in old]


def length_delta(before: str, after: str) -> dict:
    a, b = chars(before), chars(after)
    if a == 0:
        return {"before": 0, "after": b, "ratio": 1.0}
    return {"before": a, "after": b, "ratio": round(b / a, 3)}


def strip_fillers(text: str) -> str:
    for f in _FILLERS:
        text = text.replace(f, "")
    return re.sub(r"[，,]{2,}", ",", text)


def replace_words(text: str, table: dict) -> tuple[str, int]:
    """按词表替换,返回(新文本, 替换次数)。长词优先,避免「特别」被「特」抢先。"""
    n = 0
    for k in sorted(table, key=len, reverse=True):
        if k in text:
            n += text.count(k)
            text = text.replace(k, table[k])
    return text, n


def to_formal(text: str) -> tuple[str, int]:
    return replace_words(text, _ORAL)


def to_oral(text: str) -> tuple[str, int]:
    return replace_words(text, _FORMAL_TO_ORAL)


def keywords(text: str, limit: int = 5) -> list[str]:
    """极简关键词:去掉标点后按 2~4 字切,统计出现次数取高频。不追求准,只做标题素材。"""
    clean = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", " ", text or "")
    grams: dict[str, int] = {}
    for seg in clean.split():
        for n in (4, 3):
            for i in range(len(seg) - n + 1):
                g = seg[i : i + n]
                if g.strip() and not g.isdigit():
                    grams[g] = grams.get(g, 0) + 1
    ordered = sorted(grams.items(), key=lambda kv: (-kv[1] * len(kv[0]), kv[0]))
    picked: list[str] = []
    for g, _c in ordered:
        if any(g in p or p in g for p in picked):
            continue
        picked.append(g)
        if len(picked) >= limit:
            break
    return picked


def title_candidates(text: str, limit: int = 3) -> list[str]:
    """标题候选:首句压缩、关键词拼接。全部控制在一行能放下。"""
    out: list[str] = []
    first = sentences(text)
    if first:
        head = re.split(r"[，,。！？:：]", first[0])[0].strip()
        if 4 <= len(head) <= 18:
            out.append(head)
    kws = keywords(text, 2)
    for k in kws:
        for cand in (k, f"关于{k}的观察"):
            if len(cand) <= 20 and cand not in out:
                out.append(cand)
    return out[:limit]


def clamp_title(title: str, limit: int = 20) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip())
    return t if len(t) <= limit else t[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# 工具注册表(ReAct 用,给模型查稿子用的)
# ---------------------------------------------------------------------------
TOOLS = [
    {"name": "get_draft", "desc": "取回当前稿子正文。", "args": {}},
    {"name": "sentence_stats", "desc": "稿子的字数、句数、平均句长。", "args": {}},
    {"name": "find_sentence", "desc": "按关键词找原句,返回句号与原句。", "args": {"keyword": "要搜的词"}},
]


def tool_list_text() -> str:
    return "\n".join(f"- {t['name']}({', '.join(t['args']) or '无'}):{t['desc']}" for t in TOOLS)


def find_sentence(text: str, keyword: str, limit: int = 5) -> list[dict]:
    kw = (keyword or "").strip()
    if not kw:
        return []
    hits = [{"index": i, "text": s} for i, s in enumerate(sentences(text), 1) if kw in s]
    return hits[:limit]


def execute(name: str, args: dict, draft: dict) -> dict:
    text = draft.get("body", "")
    if name == "get_draft":
        return {"title": draft.get("title"), "body": text}
    if name == "sentence_stats":
        sents = sentences(text)
        avg = round(chars(text) / len(sents), 1) if sents else 0
        return {"chars": chars(text), "sentences": len(sents), "avg_len": avg}
    if name == "find_sentence":
        return {"hits": find_sentence(text, str(args.get("keyword", "")))}
    return {"error": f"未知工具: {name}"}


def dump(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
