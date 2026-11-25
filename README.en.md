# bigeng (Cultivated Writing)

[![test](https://github.com/wushiyi105-jpg/bigeng/workflows/test/badge.svg)](https://github.com/wushiyi105-jpg/bigeng/actions)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![codecov](https://codecov.io/gh/wushiyi105-jpg/bigeng/branch/main/graph/badge.svg)](https://codecov.io/gh/wushiyi105-jpg/bigeng)

![usage](assets/demo.gif)

Drop a draft in: polish, rewrite, expand, shorten, title it — every change kept as a version.

Two things scare me when editing: breaking a number, and losing the version I liked. So bigeng's model only touches wording — **numbers and length ratios are checked locally**. If a rewrite introduces a number the draft never had, the whole result is rejected and the draft stays untouched. Every edit becomes a version, so you can always go back.

## Features

- **Five operations**: `polish`, `rewrite` (formal / colloquial / concise), `expand`, `shrink`, `title`.
- **Hard checks up front**: the number set is compared before and after — any invented number fails the whole rewrite; a length ratio outside that mode's band also fails. A rejected result returns the original text with the reason.
- **Version history**: each rewrite stores mode, body, note and timestamp. `versions` lists them, `version` prints one, `--save` writes back to the draft.
- **Offline mode**: with no key, a rule engine cleans spacing and punctuation, swaps colloquial/formal words, deletes filler, and shortens by scoring sentences on marker words and numbers. Expand is not attempted offline — it returns a skeleton instead, and says so.
- **Two entry points**: CLI for batch edits, web page for live editing. Standard library only.

## Quick start

```bash
git clone https://github.com/wushiyi105-jpg/bigeng.git
cd bigeng
python -m bigeng new draft.txt --title 下午三点总卡住
python -m bigeng polish 1 --save
```

No key means offline mode. To connect a model:

```bash
cp .env.example .env
# fill LLM_API_KEY; defaults to https://api.deepseek.com + deepseek-flash
```

Any OpenAI-compatible endpoint:

```bash
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4 LLM_MODEL=glm-4.6 python -m bigeng rewrite 1 --style formal
```

Web:

```bash
python -m bigeng web --port 8766
# http://127.0.0.1:8766
```

## Command reference

| Command | What it does |
| --- | --- |
| `new <file> [--title]` | Create a draft; `-` reads stdin; empty title is auto-generated |
| `list` | List drafts |
| `show <draft>` | Chars, sentences, number count, version summary |
| `polish <draft> [--save]` | Polish |
| `rewrite <draft> --style formal\|oral\|brief [--save]` | Rewrite in a style |
| `expand <draft> [--save]` | Expand |
| `shrink <draft> [--ratio 0.5] [--save]` | Shorten, default ratio 0.5 |
| `title <draft>` | Three title candidates |
| `versions <draft>` | Version list |
| `version <draft> <n>` | Print one version |
| `rm <draft>` / `stats` | Delete / stats |
| `web [--host] [--port]` | Web UI |

Global switches `--mock`, `--json`, `--model`, `--base-url`, `--api-key`, `--db` work before or after the subcommand. `<draft>` accepts an id or a title.

## How it works

```mermaid
flowchart TD
    CLI["cli.py<br/>argparse subcommands"] --> AGENT
    WEB["web.py<br/>ThreadingHTTPServer + single page"] --> AGENT
    AGENT["agent.py<br/>orchestration + hard checks"] -->|with key| LLM["llm.py<br/>urllib to /chat/completions"]
    AGENT -->|no key or --mock| MOCK["mock.py<br/>rule rewrites, sentence scoring"]
    AGENT --> CHECK["tools.py<br/>number set / length ratio / sentences"]
    MOCK --> CHECK
    CHECK --> DB["db.py<br/>drafts + versions, threading.Lock"]
```

Three decisions:

1. **The model touches wording, not facts.** `tools.new_numbers` diffs the number sets before and after; one extra number voids the whole rewrite. This is the guard against "helpfully" inventing a stat.
2. **Offline does not fake an expansion.** Rules cannot add real content, and padding adjectives is worse than nothing. `mock.expand` emits a four-slot skeleton (claim / example / number / close) labelled as a skeleton.
3. **The original always survives.** Nothing touches the draft body until `--save`; the initial text is stored as an `original` version, so there is always a way back.

Storage is one SQLite file with `check_same_thread=False` plus a `threading.Lock`; default `data/bigeng.db`, overridable with `BIGENG_DB`.

## Layout

```
bigeng/
├── bigeng/
│   ├── __init__.py / __main__.py
│   ├── llm.py     # OpenAI-compatible client + .env loader
│   ├── db.py      # drafts + versions (thread-safe)
│   ├── tools.py   # number sets, length ratio, sentences, titles
│   ├── mock.py    # offline rule rewrites
│   ├── agent.py   # five operations + hard checks
│   ├── cli.py     # command line
│   └── web.py     # web UI
├── data/draft-sample.json
├── tests/test_bigeng.py
├── assets/demo.gif
├── .github/workflows/test.yml
├── pyproject.toml
├── README.md / README.en.md
└── CHANGELOG.md / SECURITY.md / CODE_OF_CONDUCT.md / CONTRIBUTING.md
```

## Author

shiyi · GitHub [@wushiyi105-jpg](https://github.com/wushiyi105-jpg) · wushiyi105@gmail.com

MIT License, Copyright (c) 2026 wushiyi105-jpg
