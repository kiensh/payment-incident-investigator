from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

SESSION_ID = uuid4().hex


class BudgetExceeded(RuntimeError):
    pass


class RequestBudget:
    """Atomic capped reservations with persistent history, optionally scoped to this process."""

    def __init__(self, path: Path, limit: int = 150,
                 scope: Literal["persistent", "session"] = "persistent") -> None:
        if scope not in ("persistent", "session"):
            raise ValueError("Request budget scope must be persistent or session.")
        self.path = path
        self.limit = limit
        self.scope = scope
        self.session_id = SESSION_ID
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=10)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY, started_at TEXT NOT NULL,
                status TEXT NOT NULL, duration_ms REAL, usage TEXT, session_id TEXT
            )""")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(requests)")}
            if "session_id" not in columns:
                conn.execute("ALTER TABLE requests ADD COLUMN session_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS requests_session_id ON requests(session_id)")
            conn.commit()

    def _count(self, conn: sqlite3.Connection) -> int:
        if self.scope == "session":
            return int(conn.execute("SELECT COUNT(*) FROM requests WHERE session_id=?",
                                    (self.session_id,)).fetchone()[0])
        return int(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0])

    def reserve(self) -> int:
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self._count(conn) >= self.limit:
                raise BudgetExceeded("The configured model request budget is exhausted.")
            cursor = conn.execute(
                "INSERT INTO requests(started_at, status, session_id) VALUES (?, 'reserved', ?)",
                (datetime.now(timezone.utc).isoformat(), self.session_id),
            )
            request_id = cursor.lastrowid
            conn.commit()
            assert request_id is not None
            return request_id

    def finish(self, request_id: int, status: str, duration_ms: float, usage: dict) -> None:
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("UPDATE requests SET status=?, duration_ms=?, usage=? WHERE id=?",
                         (status, duration_ms, json.dumps(usage), request_id))
            conn.commit()

    def count(self) -> int:
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            return self._count(conn)
