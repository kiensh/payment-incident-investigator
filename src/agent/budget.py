from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class BudgetExceeded(RuntimeError):
    pass


class RequestBudget:
    """Cross-process request reservations: retries count even when the bridge fails."""

    def __init__(self, path: Path, limit: int = 150) -> None:
        self.path = path
        self.limit = limit
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=10)) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY, started_at TEXT NOT NULL,
                status TEXT NOT NULL, duration_ms REAL, usage TEXT
            )""")
            conn.commit()

    def reserve(self) -> int:
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            if count >= self.limit:
                raise BudgetExceeded("The configured bridge request budget is exhausted.")
            cursor = conn.execute(
                "INSERT INTO requests(started_at, status) VALUES (?, 'reserved')",
                (datetime.now(timezone.utc).isoformat(),),
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
            return int(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0])
