"""编排:模型主路径 + 离线回退 + 硬校验。

模型的活儿是措辞,数字与比例这些硬指标留在这里算。
改写后多出一个原文没有的数字,整篇不采用——数字错一次,读者就再也不信了。
"""

from __future__ import annotations

from . import llm, mock, tools
from .llm import LLMError

MAX_STEPS = 12

BASE_RULES = """你在改一篇用户自己的稿子。只输出 JSON,不要解释。
硬规则:
- 不许凭空加数字、日期、人名、机构名;原文没有的就不写。
- 不许改变原文的事实主张与立场,只改措辞与结构。
- 中文用全角标点。"""

POLISH_SYSTEM = BASE_RULES + """
任务:润色。修顺句子、去重复、补标点,不删信息、不换观点。
输出:{"body":"润色后的全文","note":"一句话说明你改了什么"}"""

REWRITE_SYSTEM = BASE_RULES + """
任务:改写。目标风格是「__STYLE__」。
formal=正式书面,oral=日常口语,brief=简洁克制。
输出:{"body":"改写后的全文","note":"一句话说明改动重点"}"""

EXPAND_SYSTEM = BASE_RULES + """
任务:扩写。把每段的论点补成有细节的段落:加具体场景、可核实的例子、必要的过渡。
不许为了变长灌形容词,不许编数据。
输出:{"body":"扩写后的全文","note":"一句话说明补了什么"}"""

SHRINK_SYSTEM = BASE_RULES + """
任务:缩写。保留全部关键论点与数字,删掉铺垫、重复、举例中与论点无关的细节。
只删不加,不许出现原文没有的判断。
输出:{"body":"缩写后的全文","note":"一句话说明删了什么"}"""

TITLE_SYSTEM = BASE_RULES + """
任务:给这篇稿子起 3 个标题。每个不超过 20 字,具体、有信息量,不要「浅谈」「漫谈」这类空话。
输出:{"titles":["标题1","标题2","标题3"]}"""

_ABILITIES = {
    "polish": (POLISH_SYSTEM, 800),
    "rewrite": (REWRITE_SYSTEM, 800),
    "expand": (EXPAND_SYSTEM, 1600),
    "shrink": (SHRINK_SYSTEM, 800),
    "title": (TITLE_SYSTEM, 300),
}


def _use_model(config: dict | None, force_mock: bool) -> bool:
    if force_mock:
        return False
    return bool({**llm.default_config(), **(config or {})}.get("api_key"))


def _cfg(config: dict | None) -> dict:
    return {**llm.default_config(), **(config or {})}


def _chat(messages, config, max_tokens=1200, temperature=0.3) -> str:
    return llm.chat(messages, config=_cfg(config), temperature=temperature, max_tokens=max_tokens)


def _limits(mode: str) -> tuple[float, float]:
    """每种改法的字数比例区间。"""
    if mode.startswith("rewrite:brief") or mode == "shrink":
        return 0.25, 0.75
    if mode == "expand":
        return 1.2, 3.0
    if mode == "polish" or mode.startswith("rewrite"):
        return 0.6, 1.4
    return 0.1, 5.0


def checks(before: str, after: str, mode: str) -> list[str]:
    """硬校验,返回问题清单。空列表才算全过。"""
    problems = []
    fresh = tools.new_numbers(before, after)
    if fresh:
        problems.append("多出原文没有的数字:" + "、".join(fresh[:5]))
    lo, hi = _limits(mode)
    delta = tools.length_delta(before, after)
    if not lo <= delta["ratio"] <= hi:
        problems.append(f"字数比例 {delta['ratio']} 不在 [{lo}, {hi}]")
    if not after.strip():
        problems.append("结果为空")
    return problems


def transform(draft: dict, mode: str, config: dict | None = None, force_mock: bool = False,
              style: str = "formal", ratio: float = 0.5) -> dict:
    """统一入口:polish / rewrite / expand / shrink / title。"""
    text = draft.get("body", "")
    label = mode if mode != "rewrite" else f"rewrite:{style}"

    if not _use_model(config, force_mock):
        if mode == "polish":
            r = mock.polish(text)
        elif mode == "rewrite":
            r = mock.rewrite(text, style)
        elif mode == "expand":
            r = mock.expand(text)
        elif mode == "shrink":
            r = mock.shrink(text, ratio)
        elif mode == "title":
            r = mock.title(text)
        else:
            raise LLMError(f"未知能力: {mode}")
        r["stats"] = {"before": tools.chars(text), "after": tools.chars(r["body"])}
        return r

    system, budget = _ABILITIES[mode]
    system = system.replace("__STYLE__", style)
    task = {"polish": "润色下面这篇稿子。", "rewrite": f"把下面这篇稿子改写成「{style}」风格。",
            "expand": "扩写下面这篇稿子。", "shrink": f"把下面这篇缩写到原文的 {int(ratio * 100)}% 左右。",
            "title": "给下面这篇稿子起标题。"}[mode]
    raw = _chat([
        {"role": "system", "content": system},
        {"role": "user", "content": f"{task}\n\n标题:{draft.get('title', '')}\n\n正文:\n{text}"},
    ], config, max_tokens=budget)
    data = llm.extract_json(raw)

    if mode == "title":
        titles = [tools.clamp_title(str(t)) for t in data.get("titles", []) if str(t).strip()]
        fresh = [t for t in titles if not tools.new_numbers(text, t)]
        return {"mode": "title", "body": "\n".join(titles), "candidates": fresh,
                "offline": False, "stats": {"before": tools.chars(text), "after": 0}}

    body = str(data.get("body", "")).strip()
    problems = checks(text, body, label)
    return {
        "mode": label,
        "body": body if not problems else text,
        "note": data.get("note", ""),
        "checks": problems or ["硬校验通过:数字未变、字数比例正常"],
        "rejected": bool(problems),
        "offline": False,
        "stats": {"before": tools.chars(text), "after": tools.chars(body)},
    }
