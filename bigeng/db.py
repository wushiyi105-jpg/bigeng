"""笔耕的持久层:稿子 + 历史版本。

一个 sqlite 文件,一把锁。Web 是多线程的,`check_same_thread=False`
配上每次都过锁,才不会出现半写状态。
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bigeng.db")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("BIGENG_DB") or DEFAULT_PATH
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    chars INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    body TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE
                );
                """
            )
            self._conn.commit()

    # ---------------------------------------------------------------- 草稿
    def create_draft(self, title: str, body: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO drafts(title, body, chars, created_at, updated_at) VALUES(?,?,?,?,?)",
                (title.strip(), body.strip(), len(body.strip()), _now(), _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_draft(self, key: str | int):
        with self._lock:
            if str(key).isdigit():
                row = self._conn.execute("SELECT * FROM drafts WHERE id=?", (int(key),)).fetchone()
            else:
                row = self._conn.execute("SELECT * FROM drafts WHERE title=?", (str(key),)).fetchone()
            return dict(row) if row else None

    def list_drafts(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM drafts ORDER BY updated_at DESC, id DESC").fetchall()
            return [dict(r) for r in rows]

    def update_body(self, draft_id: int, body: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE drafts SET body=?, chars=?, updated_at=? WHERE id=?",
                (body, len(body), _now(), draft_id),
            )
            self._conn.commit()

    def delete_draft(self, draft_id: int) -> bool:
        with self._lock:
            self._conn.execute("DELETE FROM versions WHERE draft_id=?", (draft_id,))
            cur = self._conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
            self._conn.commit()
            return cur.rowcount > 0

    # ---------------------------------------------------------------- 版本
    def add_version(self, draft_id: int, mode: str, body: str, note: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO versions(draft_id, mode, body, note, created_at) VALUES(?,?,?,?,?)",
                (draft_id, mode, body, note, _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_versions(self, draft_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM versions WHERE draft_id=? ORDER BY id DESC", (draft_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def latest_version(self, draft_id: int, mode: str | None = None):
        with self._lock:
            if mode:
                row = self._conn.execute(
                    "SELECT * FROM versions WHERE draft_id=? AND mode=? ORDER BY id DESC LIMIT 1",
                    (draft_id, mode),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM versions WHERE draft_id=? ORDER BY id DESC LIMIT 1", (draft_id,)
                ).fetchone()
            return dict(row) if row else None

    def stats(self) -> dict:
        with self._lock:
            d = self._conn.execute("SELECT COUNT(*) c, COALESCE(SUM(chars),0) n FROM drafts").fetchone()
            v = self._conn.execute("SELECT COUNT(*) c FROM versions").fetchone()
            return {"drafts": d["c"], "chars": d["n"], "versions": v["c"]}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
