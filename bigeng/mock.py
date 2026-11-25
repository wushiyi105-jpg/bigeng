"""离线模式:不调模型时,用能算准的规则改稿。

能做的:清空格、统标点、口语书面互转、删填充词、按分数抽句压缩、起标题。
不做的:扩写。扩写需要真的加内容,规则引擎加不出来——与其塞一段
模板腔的废话,不如老实给一份扩写骨架,让用户自己填。
"""

from __future__ import annotations

import re

from . import tools

_MARKERS = ("因此", "所以", "关键", "核心", "本质", "意味着", "结论", "但是", "然而", "因为", "首先", "其次")


def _tidy_para(p: str) -> str:
    p = p.replace("\u3000", " ").replace("\t", " ")
    p = re.sub(r"\s+", " ", p).strip()
    p = re.sub(r"\s+([，。；：！？、,.!?;:])", r"\1", p)
    p = re.sub(r"([，。；：！？、])\1+", r"\1", p)
    p = re.sub(r"[.．·]{2,}", "。", p)
    p = re.sub(r"[，,]{2,}", "，", p)
    p = re.sub(r"的的", "的", p)
    if p and not p.endswith(tuple("。！？!?…”")):
        p += "。"
    return p


def _tidy(text: str) -> str:
    paras = [p for p in re.split(r"\n+", text or "") if p.strip()]
    return "\n".join(_tidy_para(p) for p in paras)


def polish(text: str) -> dict:
    body = _tidy(text)
    return {"mode": "polish", "body": body, "offline": True, "checks": ["离线模式:仅做空格与标点清理,未改动措辞"]}


def rewrite(text: str, style: str) -> dict:
    body, n = _tidy(text), 0
    if style in ("formal", "正式"):
        body, n = tools.to_formal(body)
        body = tools.strip_fillers(body)
        note = "离线模式:口语词转书面、删填充词"
    elif style in ("oral", "口语"):
        body, n = tools.to_oral(body)
        note = "离线模式:书面词转口语"
    elif style in ("brief", "简洁"):
        body = tools.strip_fillers(body)
        body = re.sub(r"[，,]{2,}", ",", body)
        note = "离线模式:删除填充词与重复标点"
    else:
        note = "离线模式:仅做基础清理,该风格需要模型"
    return {"mode": f"rewrite:{style}", "body": body, "offline": True, "checks": [f"{note}(共 {n} 处替换)"]}


def _score(sentence: str) -> int:
    s = 0
    if any(m in sentence for m in _MARKERS):
        s += 2
    if tools.numbers(sentence):
        s += 1
    if 15 <= len(sentence) <= 70:
        s += 1
    return s


def shrink(text: str, ratio: float = 0.5) -> dict:
    """压缩:按分数抽句,保留原句原话,不重写。"""
    sents = tools.sentences(text)
    if not sents:
        return {"mode": "shrink", "body": text, "offline": True, "checks": ["原文为空"]}
    keep_n = max(1, int(len(sents) * ratio))
    ranked = sorted(range(len(sents)), key=lambda i: (-_score(sents[i]), i))[:keep_n]
    body = "\n".join(sents[i] for i in sorted(ranked))
    return {"mode": "shrink", "body": body, "offline": True, "checks": [f"离线模式:按标记词/数字打分保留原句 {keep_n}/{len(sents)} 句,未改写"]}


def expand(text: str) -> dict:
    """扩写骨架:每个段落给出四个可填的槽,不做假扩写。"""
    paras = tools.split_paragraphs(text)
    lines = ["【离线模式没有扩写能力,以下是可以照着填的骨架】", ""]
    for i, p in enumerate(paras, 1):
        kw = tools.keywords(p, 2)
        head = "、".join(kw) if kw else "这一段"
        lines.append(f"第 {i} 段主题:{head}")
        lines.append("  论点:把这一段的主张用一句话说死。")
        lines.append("  例子:给一个具体场景或对话,不要形容词堆砌。")
        lines.append("  数据:给一个数字,来源要能写出来。")
        lines.append("  收束:回扣上一段,说明它为什么重要。")
    return {"mode": "expand", "body": "\n".join(lines), "offline": True, "checks": ["离线模式:只输出扩写骨架,不编造内容"]}


def title(text: str) -> dict:
    cands = tools.title_candidates(text)
    return {
        "mode": "title",
        "body": "\n".join(f"{i}. {c}" for i, c in enumerate(cands, 1)) if cands else "给不出候选:原文太短",
        "candidates": cands,
        "offline": True,
        "checks": ["离线模式:标题由首句与高频词生成"],
    }
