import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from src.agent.budget import BudgetExceeded, RequestBudget
from src.api import create_app
from src.config import ROOT, Settings
from tests.test_boundary_regressions import live_fixture


def test_legacy_ledger_migration_is_safe_for_concurrent_clients(tmp_path):
    path = tmp_path / "ledger.sqlite"
    original = (1, "2026-11-15T00:00:00+00:00", "completed", 12.5, '{"input_tokens": 7}')
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE requests (
            id INTEGER PRIMARY KEY, started_at TEXT NOT NULL,
            status TEXT NOT NULL, duration_ms REAL, usage TEXT
        )""")
        conn.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?)", original)

    with ThreadPoolExecutor(max_workers=4) as pool:
        clients = list(pool.map(lambda _: RequestBudget(path, 2, "session"), range(8)))
    assert all(client.count() == 0 for client in clients)
    request_id = clients[0].reserve()
    clients[0].finish(request_id, "infrastructure_error", 3, {})
    assert all(client.count() == 1 for client in clients)
    assert RequestBudget(path).count() == 2
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM requests WHERE id=1").fetchone() == (*original, None)
        assert conn.execute("SELECT session_id FROM requests WHERE id=?", (request_id,)).fetchone() == (clients[0].session_id,)


@pytest.mark.parametrize("scope,second_granted,total", [("persistent", 0, 2), ("session", 2, 4)])
def test_new_process_refreshes_only_session_allowance_and_preserves_history(
    tmp_path, scope, second_granted, total,
):
    path = tmp_path / "ledger.sqlite"
    script = """
import json
import sys
from pathlib import Path
from src.agent.budget import BudgetExceeded, RequestBudget
path, scope = Path(sys.argv[1]), sys.argv[2]
granted = 0
for _ in range(3):
    budget = RequestBudget(path, 2, scope)
    try:
        request_id = budget.reserve()
    except BudgetExceeded:
        continue
    budget.finish(request_id, "infrastructure_error", 1, {})
    granted += 1
print(json.dumps({"granted": granted, "used": budget.count(), "session": budget.session_id}))
"""

    def start_process():
        completed = subprocess.run(
            [sys.executable, "-c", script, str(path), scope], cwd=ROOT,
            capture_output=True, text=True, check=True, timeout=15,
        )
        return json.loads(completed.stdout)

    first, second = start_process(), start_process()
    assert first["session"] != second["session"]
    assert first["granted"] == 2
    assert second["granted"] == second_granted
    assert first["used"] == second["used"] == 2
    ledger = RequestBudget(path, 2)
    assert ledger.count() == total
    with pytest.raises(BudgetExceeded):
        ledger.reserve()
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM requests WHERE status='infrastructure_error'").fetchone()[0] == total


def test_api_session_cap_is_shared_across_app_instances(tmp_path, monkeypatch):
    settings, query = live_fixture(tmp_path)
    settings = replace(settings, budget_scope="session", request_limit=1)
    monkeypatch.setattr("src.agent.budget.SESSION_ID", "previous-process")
    old = RequestBudget(settings.budget_path, 1)
    old.reserve()
    monkeypatch.setattr("src.agent.budget.SESSION_ID", "current-process")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(503, json={"error": {"type": "api_error", "message": "unavailable"}})

    factory = anthropic.DefaultAsyncHttpxClient
    monkeypatch.setattr(anthropic, "DefaultAsyncHttpxClient", lambda **kwargs: factory(
        transport=httpx2.MockTransport(handler), **kwargs))
    with TestClient(create_app(settings)) as api:
        assert api.post("/api/investigate", json=query).status_code == 502
    with TestClient(create_app(settings)) as api:
        response = api.post("/api/investigate", json=query)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "budget_exhausted"
    assert "session" in response.json()["error"]["message"]
    assert len(requests) == RequestBudget(settings.budget_path, 1, "session").count() == 1
    assert old.count() == 2


def test_unknown_budget_scope_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="scope"):
        RequestBudget(tmp_path / "ledger.sqlite", scope="disabled")
    with pytest.raises(ValueError, match="INVESTIGATOR_BUDGET_SCOPE"):
        Settings(budget_scope="disabled")
