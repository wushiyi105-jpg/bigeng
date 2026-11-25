"""命令行入口:python -m bigeng <命令> [选项]。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, agent, llm, tools
from . import db as dbmod
from .llm import LLMError

MOCK_BANNER = (
    "⚠️  当前为离线模式(未配置 LLM_API_KEY),改写由内置规则完成。\n"
    "   在 .env 填入 LLM_API_KEY 后,润色与改写交给大模型。\n"
)
STYLES = {"formal": "正式", "oral": "口语", "brief": "简洁"}


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def render_draft(d: dict) -> str:
    return f"[{d['id']}] {d['title']}  {d['chars']} 字  {d['updated_at']}"


def render_result(r: dict) -> str:
    head = f"✍️  {r['mode']}"
    if r.get("offline"):
        head += "  ·  离线模式"
    head += f"  ·  {r['stats']['before']} → {r['stats']['after']} 字"
    lines = [head, ""]
    for c in r.get("checks", []):
        lines.append(f"  · {c}")
    if r.get("rejected"):
        lines.append("  ! 校验没过,上面返回的是原文,原稿没有被替换")
    lines += ["", r.get("body", "")]
    return "\n".join(lines)


_OPEN: list = []


def _db(args) -> dbmod.Database:
    db = dbmod.Database(getattr(args, "db", None))
    _OPEN.append(db)
    return db


def _close_all() -> None:
    for d in _OPEN:
        d.close()
    _OPEN.clear()


def _draft(args, db):
    d = db.get_draft(args.key)
    if not d:
        print(f"❌ 找不到稿子:{args.key}", file=sys.stderr)
        sys.exit(1)
    return d


def _emit(args, db, draft, mode, **kw) -> None:
    r = agent.transform(draft, mode, config=llm.config_from_args(args), force_mock=args.mock, **kw)
    if args.save and r.get("body") and mode != "title" and not r.get("rejected"):
        vid = db.add_version(draft["id"], r["mode"], r["body"], r.get("note", ""))
        db.update_body(draft["id"], r["body"])
        r["version_id"] = vid
        r["saved"] = True
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(render_result(r))
        if r.get("saved"):
            print(f"\n✅ 已存为版本 v{r['version_id']},稿子正文已更新")


def cmd_new(args):
    db = _db(args)
    body = _read_input(args.file)
    if not body.strip():
        print("❌ 正文为空", file=sys.stderr)
        sys.exit(1)
    title = args.title
    if not title:
        cands = tools.title_candidates(body)
        title = cands[0] if cands else "未命名"
    did = db.create_draft(title, body)
    db.add_version(did, "original", body.strip(), "初稿")
    print(f"✅ 已建稿 [{did}] {title}  {tools.chars(body)} 字")


def cmd_list(args):
    db = _db(args)
    ds = db.list_drafts()
    if args.json:
        print(json.dumps(ds, ensure_ascii=False, indent=2))
        return
    if not ds:
        print("(空)用 bigeng new 建一篇稿子")
        return
    for d in ds:
        print(render_draft(d))


def cmd_show(args):
    db = _db(args)
    d = _draft(args, db)
    sents = tools.sentences(d["body"])
    print(f"✍️  [{d['id']}] {d['title']}")
    print(f"{d['chars']} 字 / {len(sents)} 句 / 数字 {len(tools.numbers(d['body']))} 处 / 更新于 {d['updated_at']}")
    vs = db.list_versions(d["id"])
    print(f"历史版本 {len(vs)} 个:" + ("  " + "、".join(v["mode"] for v in vs[:6]) if vs else ""))
    print("\n" + d["body"][:300] + ("…" if d["chars"] > 300 else ""))


def _cmd_transform(mode, **kw):
    def run(args):
        db = _db(args)
        _emit(args, db, _draft(args, db), mode, **kw)
    return run


def cmd_rewrite(args):
    db = _db(args)
    style = args.style
    _emit(args, db, _draft(args, db), "rewrite", style=style)


def cmd_title(args):
    db = _db(args)
    r = agent.transform(_draft(args, db), "title", config=llm.config_from_args(args), force_mock=args.mock)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        lines = "\n".join(f"{i}. {t}" for i, t in enumerate(r.get("candidates", []), 1))
        print(lines or r.get("body", ""))


def cmd_versions(args):
    db = _db(args)
    d = _draft(args, db)
    vs = db.list_versions(d["id"])
    if args.json:
        print(json.dumps(vs, ensure_ascii=False, indent=2))
        return
    for v in vs:
        print(f"v{v['id']}  {v['mode']:<14} {len(v['body'])} 字  {v['created_at']}  {v['note'][:30]}")


def cmd_show_version(args):
    db = _db(args)
    d = _draft(args, db)
    v = next((x for x in db.list_versions(d["id"]) if x["id"] == args.version), None)
    if not v:
        print(f"❌ 没有版本 v{args.version}", file=sys.stderr)
        sys.exit(1)
    print(v["body"])


def cmd_rm(args):
    db = _db(args)
    d = _draft(args, db)
    db.delete_draft(d["id"])
    print(f"🗑  已删除 [{d['id']}] {d['title']}")


def cmd_stats(args):
    print(json.dumps(_db(args).stats(), ensure_ascii=False))


def cmd_web(args):
    from . import web

    web.serve(host=args.host, port=args.port, db_path=args.db, force_mock=args.mock)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bigeng", description="笔耕 · 写作助手:润色、改写、扩写、缩写、起标题。")
    p.add_argument("--version", action="version", version=f"bigeng {__version__}")
    p.add_argument("--mock", action="store_true", help="强制离线模式(不调用模型)")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--api-key")
    p.add_argument("--db")

    sub = p.add_subparsers(dest="command", required=True)

    n = sub.add_parser("new", help="建一篇稿子(文件或 - 读 stdin)")
    n.add_argument("file")
    n.add_argument("--title")
    n.set_defaults(func=cmd_new)

    ls = sub.add_parser("list", help="列出稿子")
    ls.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="看稿子概况")
    sh.add_argument("key", help="id 或标题")
    sh.set_defaults(func=cmd_show)

    po = sub.add_parser("polish", help="润色")
    po.add_argument("key")
    po.add_argument("--save", action="store_true")
    po.set_defaults(func=_cmd_transform("polish"))

    rw = sub.add_parser("rewrite", help="按风格改写")
    rw.add_argument("key")
    rw.add_argument("--style", choices=list(STYLES), default="formal")
    rw.add_argument("--save", action="store_true")
    rw.set_defaults(func=cmd_rewrite)

    ex = sub.add_parser("expand", help="扩写")
    ex.add_argument("key")
    ex.add_argument("--save", action="store_true")
    ex.set_defaults(func=_cmd_transform("expand"))

    sr = sub.add_parser("shrink", help="缩写")
    sr.add_argument("key")
    sr.add_argument("--ratio", type=float, default=0.5)
    sr.add_argument("--save", action="store_true")

    def run_shrink(args):
        db = _db(args)
        _emit(args, db, _draft(args, db), "shrink", ratio=args.ratio)

    sr.set_defaults(func=run_shrink)

    ti = sub.add_parser("title", help="起标题")
    ti.add_argument("key")
    ti.set_defaults(func=cmd_title)

    vs = sub.add_parser("versions", help="历史版本")
    vs.add_argument("key")
    vs.set_defaults(func=cmd_versions)

    sv = sub.add_parser("version", help="看某个版本全文")
    sv.add_argument("key")
    sv.add_argument("version", type=int)
    sv.set_defaults(func=cmd_show_version)

    rm = sub.add_parser("rm", help="删稿")
    rm.add_argument("key")
    rm.set_defaults(func=cmd_rm)

    st = sub.add_parser("stats", help="统计")
    st.set_defaults(func=cmd_stats)

    wb = sub.add_parser("web", help="启动 Web 界面")
    wb.add_argument("--host", default="127.0.0.1")
    wb.add_argument("--port", type=int, default=8000)
    wb.set_defaults(func=cmd_web)
    return p


GLOBAL_FLAGS = ("--mock", "--json")
GLOBAL_OPTS = ("--model", "--base-url", "--api-key", "--db")


def hoist_globals(argv: list[str]) -> list[str]:
    """把全局开关挪到子命令之前,`bigeng polish 1 --mock` 也能跑。"""
    g, rest = [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in GLOBAL_FLAGS:
            g.append(a)
            i += 1
        elif a in GLOBAL_OPTS:
            g += [a, argv[i + 1]] if i + 1 < len(argv) else [a]
            i += 2
        elif any(a.startswith(o + "=") for o in GLOBAL_OPTS):
            g.append(a)
            i += 1
        else:
            rest.append(a)
            i += 1
    return g + rest


def main(argv=None):
    args = build_parser().parse_args(hoist_globals(list(sys.argv[1:] if argv is None else argv)))
    if not args.mock and args.command in ("polish", "rewrite", "expand", "shrink", "title"):
        if not llm.config_from_args(args).get("api_key"):
            print(MOCK_BANNER, file=sys.stderr)
    try:
        args.func(args)
    except LLMError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        _close_all()


if __name__ == "__main__":
    main()
