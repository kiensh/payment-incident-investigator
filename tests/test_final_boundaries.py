"""Fresh-context boundary probes for frozen f172094; transport mocks, never live inference.

Run: uv run --frozen --offline pytest -q tests/test_final_boundaries.py
All mutable evidence and request ledgers are pytest temporary files. Synthetic
credential markers are deliberate test inputs, not real credentials.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import anthropic
import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient

from src.agent.bridge import BridgeClient, BridgeFailure, numeric_usage
from src.agent.budget import BudgetExceeded, RequestBudget
from src.api import create_app
from src.config import ROOT, Settings
from src.domain.models import Evidence, Payment
from src.storage.repository import Repository, create_database
from src.tools.session import ToolInputError, ToolSession, tool_definitions

MARKER = "synthetic-boundary-secret-not-real"


@pytest.fixture(autouse=True)
def isolated_sdk_environment(monkeypatch, tmp_path):
    # Explicit synthetic values avoid consulting any real credential/profile store.
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                 "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_PROFILE", "ANTHROPIC_LOG",
                 "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_IDENTITY_TOKEN_FILE",
                 "ANTHROPIC_FEDERATION_RULE_ID", "ANTHROPIC_ORGANIZATION_ID",
                 "ANTHROPIC_SERVICE_ACCOUNT_ID", "ANTHROPIC_WEBHOOK_SIGNING_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path / "empty-sdk-config"))


@pytest.fixture
def fixture_case(tmp_path):
    payment = Payment(id="pay_boundary", symptom="Please check the recorded payment status.",
                      source_transaction_id="synthetic_row", original={"transaction_status": "Pending"},
                      warnings=["Synthetic test; source currency is unknown."])
    evidence = [Evidence(id="rec_boundary", payment_id=payment.id, kind="ApplicationStatusObservation",
                         source="independent synthetic boundary fixture", synthetic=True,
                         observed_at="2026-11-01T00:00:00Z",
                         data={"observation_id": "app_boundary", "status": "pending", "channel": "checkout"})]
    database = tmp_path / "evidence.sqlite"
    create_database(database, [payment], evidence)
    settings = Settings(mode="live", database=database, bridge_model="claude-opus-5.5",
                        budget_path=tmp_path / "budget.sqlite", max_model_calls=2)
    return settings, {"payment_id": payment.id, "question": payment.symptom}, payment, evidence


def install_transport(monkeypatch, handler):
    original = anthropic.DefaultAsyncHttpxClient
    monkeypatch.setattr(anthropic, "DefaultAsyncHttpxClient", lambda **kwargs: original(
        transport=httpx2.MockTransport(handler), **kwargs))


def sse(content=(), usage=None, stop="end_turn", raw_message=None):
    message = {"id": "msg_boundary", "type": "message", "role": "assistant", "model": "claude-opus-5.5",
               "content": [], "stop_reason": None, "stop_sequence": None,
               "usage": {"input_tokens": 11, "output_tokens": 0} if usage is None else usage}
    if raw_message is not None:
        message.update(raw_message)
    events = [("message_start", {"type": "message_start", "message": message})]
    for index, block in enumerate(content):
        start = dict(block)
        if block["type"] == "text":
            start["text"] = ""
            delta = {"type": "text_delta", "text": block["text"]}
        elif block["type"] == "tool_use":
            start["input"] = {}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        else:
            delta = None
        events.append(("content_block_start", {"type": "content_block_start", "index": index, "content_block": start}))
        if delta:
            events.append(("content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}))
        events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    events += [("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                                  "usage": {"output_tokens": 3}}),
               ("message_stop", {"type": "message_stop"})]
    return "".join(f"event: {name}\ndata: {json.dumps(event)}\n\n" for name, event in events)


def stream_response(payload):
    return httpx2.Response(200, headers={"content-type": "text/event-stream"}, text=payload)


@pytest.mark.parametrize("configured_token", ["", "configured-synthetic-bridge-token"])
async def test_inherited_credentials_and_origin_cannot_override_explicit_bridge(fixture_case, monkeypatch, tmp_path, configured_token):
    settings, _, _, _ = fixture_case
    settings = replace(settings, bridge_token=configured_token)
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE",
                 "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_FEDERATION_RULE_ID",
                 "ANTHROPIC_ORGANIZATION_ID", "ANTHROPIC_SERVICE_ACCOUNT_ID"):
        monkeypatch.setenv(name, MARKER)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://must-not-contact.invalid/" + MARKER)
    monkeypatch.setenv("ANTHROPIC_IDENTITY_TOKEN_FILE", str(tmp_path / "must-not-read-token"))
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://must-not-contact.invalid:9182")
    seen = []

    def handler(request):
        seen.append(request)
        assert str(request.url) == "http://localhost:8765/cc/v1/messages"
        assert request.headers["x-api-key"] == (configured_token or "copilot-bridge")
        assert "authorization" not in request.headers
        assert MARKER not in str(request.headers) + request.content.decode()
        assert not json.loads(request.content).get("fallbacks")
        return httpx2.Response(503, json={"error": {"type": "api_error", "message": MARKER}})

    install_transport(monkeypatch, handler)
    ledger = RequestBudget(settings.budget_path)
    client = BridgeClient(settings, ledger)
    try:
        with pytest.raises(BridgeFailure) as caught:
            await client.complete("stable", [{"role": "user", "content": "synthetic check"}], [])
        assert MARKER not in str(caught.value)
        assert len(seen) == ledger.count() == client.requests == 1
        assert client.retries == 0
    finally:
        await client.close()


@pytest.mark.parametrize("custom", ["Authorization: Bearer " + MARKER, "X-Api-Key: " + MARKER,
                                   "brokenheader-" + MARKER, "X-Other: " + MARKER])
def test_all_nonempty_custom_headers_fail_before_transport_and_release_slots(fixture_case, monkeypatch, custom):
    settings, body, _, _ = fixture_case
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", custom)
    install_transport(monkeypatch, lambda request: pytest.fail("custom headers reached transport"))
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        results = [api.post("/api/investigate", json=body) for _ in range(4)]
    assert [r.status_code for r in results] == [502] * 4
    assert all(r.json()["error"]["retryable"] is False and MARKER not in r.text for r in results)
    assert RequestBudget(settings.budget_path).count() == 0


@pytest.mark.parametrize("token", ["bad\n" + MARKER, "bad\r" + MARKER, "nonascii-☃-" + MARKER])
def test_malformed_configured_token_is_structured_and_slots_survive(fixture_case, monkeypatch, token):
    settings, body, _, _ = fixture_case
    settings = replace(settings, bridge_token=token)
    install_transport(monkeypatch, lambda request: httpx2.Response(503, text=MARKER))
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        responses = [api.post("/api/investigate", json=body) for _ in range(4)]
    assert [r.status_code for r in responses] == [502] * 4
    assert all(r.json()["error"]["code"] == "bridge_unavailable" and MARKER not in r.text for r in responses)


@pytest.mark.parametrize("kwargs", [
    {"bridge_url": "http://localhost:bad"}, {"bridge_url": "http://localhost:0"},
    {"bridge_url": "http://localhost:65536"}, {"bridge_url": "http://localhost@evil.invalid"},
    {"bridge_url": "http://localhost/%2e%2e"}, {"bridge_url": "https://localhost/#secret"},
    {"request_timeout": float("nan")}, {"request_timeout": float("inf")},
    {"request_timeout": 0}, {"request_timeout": 121}, {"request_limit": 0},
    {"request_limit": 151}, {"max_model_calls": 0}, {"max_model_calls": 7},
])
def test_malformed_settings_rejected_at_construction(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


@pytest.mark.parametrize("status,retryable", [(401, False), (403, False), (404, False), (408, False),
                                             (422, False), (429, True), (500, True), (503, True)])
def test_failed_provider_status_is_redacted_one_request_no_retry(fixture_case, monkeypatch, status, retryable):
    settings, body, _, _ = fixture_case
    seen = []

    def handler(request):
        seen.append(request)
        return httpx2.Response(status, json={"error": {"type": "api_error", "message": MARKER}})

    install_transport(monkeypatch, handler)
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        response = api.post("/api/investigate", json=body)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "bridge_unavailable"
    assert response.json()["error"]["retryable"] is retryable
    assert MARKER not in response.text
    assert len(seen) == RequestBudget(settings.budget_path).count() == 1
    with sqlite3.connect(settings.budget_path) as conn:
        assert conn.execute("SELECT status, usage FROM requests").fetchall() == [("infrastructure_error", "{}")]


@pytest.mark.parametrize("payload", [
    "", "event: message_start\ndata: not-json\n\n",
    "event: message_start\ndata: null\n\n",
    "event: message_start\ndata: {\"type\":\"message_start\",\"message\":null}\n\n",
    sse(raw_message={"usage": None}), sse(raw_message={"usage": "malformed-usage"}),
    sse(raw_message={"content": None}),
    "event: content_block_delta\ndata: {\"type\":\"content_block_delta\",\"index\":99,\"delta\":{\"type\":\"text_delta\",\"text\":\"x\"}}\n\n",
], ids=["empty", "invalid-json", "null-event", "null-message", "null-usage", "string-usage", "null-content", "delta-without-start"])
def test_malformed_success_stream_is_structured_not_plain_500(fixture_case, monkeypatch, payload):
    settings, body, _, _ = fixture_case
    seen = []

    def handler(request):
        seen.append(request)
        return stream_response(payload)

    install_transport(monkeypatch, handler)
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        response = api.post("/api/investigate", json=body)
    assert response.status_code == 502, (response.status_code, response.text)
    assert response.json()["error"]["code"] in {"bridge_unavailable", "unsupported_conclusion"}
    assert len(seen) <= settings.max_model_calls
    assert len(seen) == RequestBudget(settings.budget_path).count()


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_never_forwards_credentials_off_configured_origin(fixture_case, monkeypatch, status):
    settings, body, _, _ = fixture_case
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx2.Response(status, headers={"location": "https://must-not-contact.invalid/" + MARKER})

    install_transport(monkeypatch, handler)
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        response = api.post("/api/investigate", json=body)
    assert response.status_code == 502
    assert MARKER not in response.text
    assert seen == ["http://localhost:8765/cc/v1/messages"]


@pytest.mark.parametrize("bad", [True, False, -1, float("inf"), float("-inf"), float("nan"), "42", MARKER, [3], None])
def test_accounting_values_drop_nonfinite_negative_boolean_and_string(bad):
    cleaned = numeric_usage({"input_tokens": bad, "output_tokens": 8,
                             "token_details": {MARKER: 123, "thinking_tokens": bad}, MARKER: 9})
    assert cleaned == {"output_tokens": 8, "token_details": {}}
    assert MARKER not in json.dumps(cleaned, allow_nan=False)


def test_usage_and_private_reasoning_never_reflected_in_api_or_ledger(fixture_case, monkeypatch):
    settings, body, _, _ = fixture_case
    count = 0
    # Valid protocol fields plus untrusted extension keys exercise the success path.
    # Invalid declared fields are rejected separately, before SDK serialization.
    dirty = {"input_tokens": 9, "output_tokens": 0, MARKER: 999,
             "cache_read_input_tokens": 7, "cache_creation_input_tokens": 0,
             "input_tokens_details": {"cached_tokens": 7, MARKER: 111}, "service_tier": "standard"}

    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            calls = [{"type": "tool_use", "id": f"tool_{i}", "name": name,
                      "input": ({"query": "missing support"} if name == "retrieve_runbooks" else {"payment_id": body["payment_id"]})}
                     for i, name in enumerate(("get_payment_evidence", "get_attempts_and_events", "check_inconsistencies", "retrieve_runbooks"))]
            content = [{"type": "thinking", "thinking": MARKER, "signature": MARKER}] + calls
            return stream_response(sse(content, usage=dirty, stop="tool_use", raw_message={"copilot_usage": dirty}))
        assert count == 2
        results = [json.loads(block["content"]) for block in json.loads(request.content)["messages"][-1]["content"]]
        analysis = next(r for r in results if "confirmed_facts" in r)
        books = next(r["runbooks"] for r in results if "runbooks" in r)
        finding = (analysis["confirmed_facts"] + analysis["unknowns"])[0]
        return stream_response(sse([{"type": "text", "text": json.dumps({"summary_finding_ids": [finding["id"]], "runbook_ids": [books[0]["id"]]})}], usage=dirty))

    install_transport(monkeypatch, handler)
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        response = api.post("/api/investigate", json=body)
    assert response.status_code == 200, response.text
    assert MARKER not in response.text
    assert response.json()["technical"]["model_requests"] == count == 2
    assert response.json()["technical"]["retries"] == 0
    json.dumps(response.json(), allow_nan=False)
    with sqlite3.connect(settings.budget_path) as conn:
        usage = conn.execute("SELECT usage FROM requests").fetchall()
    assert MARKER not in str(usage)
    assert "Infinity" not in str(usage) and "NaN" not in str(usage)


async def test_usage_secret_values_not_echoed_to_python_warnings(fixture_case, monkeypatch, recwarn):
    settings, _, _, _ = fixture_case
    dirty = {"input_tokens": 11, "output_tokens": 0, "cache_read_input_tokens": MARKER}
    install_transport(monkeypatch, lambda request: stream_response(sse(usage=dirty)))
    client = BridgeClient(settings, RequestBudget(settings.budget_path))
    try:
        # Invalid declared usage fields now fail closed, rather than being serialized.
        with pytest.raises(BridgeFailure, match="invalid or incomplete") as caught:
            await client.complete("stable", [{"role": "user", "content": "synthetic check"}], [])
        assert MARKER not in str(caught.value)
    finally:
        await client.close()
    assert MARKER not in "\n".join(str(item.message) for item in recwarn)


@pytest.mark.parametrize("invalid", [MARKER, float("inf"), None])
def test_invalid_declared_usage_is_rejected_without_warnings(fixture_case, monkeypatch, recwarn, invalid):
    settings, body, _, _ = fixture_case
    dirty = {"input_tokens": invalid, "output_tokens": 0, "cache_read_input_tokens": MARKER}
    install_transport(monkeypatch, lambda request: stream_response(sse(usage=dirty)))
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        response = api.post("/api/investigate", json=body)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "bridge_unavailable"
    assert MARKER not in response.text
    assert not list(recwarn)
    with sqlite3.connect(settings.budget_path) as conn:
        assert conn.execute("SELECT status, usage FROM requests").fetchall() == [("infrastructure_error", "{}")]


def test_exhausted_budget_does_not_touch_transport_and_survives_new_clients(fixture_case, monkeypatch):
    settings, body, _, _ = fixture_case
    settings = replace(settings, request_limit=1)
    ledger = RequestBudget(settings.budget_path, 1)
    ledger.reserve()  # A crash-reserved request must still count.
    install_transport(monkeypatch, lambda request: pytest.fail("exhausted budget reached transport"))
    for _ in range(3):
        with TestClient(create_app(settings), raise_server_exceptions=False) as api:
            response = api.post("/api/investigate", json=body)
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "budget_exhausted"
    assert ledger.count() == 1


def test_atomic_budget_competing_clients(tmp_path):
    path = tmp_path / "parallel.sqlite"
    RequestBudget(path, 3)

    def attempt(_):
        try:
            return RequestBudget(path, 3).reserve()
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=12) as pool:
        reserved = list(pool.map(attempt, range(24)))
    assert len([item for item in reserved if item is not None]) == RequestBudget(path, 3).count() == 3


async def test_two_slots_busy_third_then_all_slots_recover(fixture_case, monkeypatch):
    settings, body, _, _ = fixture_case
    entered = 0
    two_started = asyncio.Event()
    release = asyncio.Event()

    async def handler(request):
        nonlocal entered
        entered += 1
        if entered >= 2:
            two_started.set()
        await release.wait()
        return httpx2.Response(503, text=MARKER)

    install_transport(monkeypatch, handler)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings)), base_url="http://testserver") as api:
        first = asyncio.create_task(api.post("/api/investigate", json=body))
        second = asyncio.create_task(api.post("/api/investigate", json=body))
        await asyncio.wait_for(two_started.wait(), 5)
        third = await api.post("/api/investigate", json=body)
        assert third.status_code == 429 and third.json()["error"]["code"] == "busy"
        release.set()
        results = await asyncio.gather(first, second)
        assert [r.status_code for r in results] == [502, 502]
        recovered = await api.post("/api/investigate", json=body)
        assert recovered.status_code == 502
    assert entered == RequestBudget(settings.budget_path).count() == 3


def test_repository_and_tools_cannot_write_or_select_private_files(fixture_case):
    settings, _, payment, evidence = fixture_case
    original = settings.database.read_bytes()
    repository = Repository(settings.database)
    with repository._connection() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        assert connection.execute("PRAGMA trusted_schema").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM payments")
    session = ToolSession(payment, evidence)
    assert {tool["name"] for tool in tool_definitions()} == {
        "get_payment_evidence", "get_attempts_and_events", "check_inconsistencies", "retrieve_runbooks"}
    for name in ("read_file", "execute_sql", "shell", "refund", "retry_payment", "../../evals/expected/dev.json"):
        with pytest.raises(ToolInputError):
            session.execute(name, {"path": "/synthetic/private/answer-key"})
    with pytest.raises(ToolInputError):
        session.execute("get_payment_evidence", {"payment_id": "pay_another"})
    with pytest.raises(ToolInputError):
        session.execute("get_payment_evidence", {"payment_id": payment.id, "sql": "SELECT * FROM answer_keys"})
    assert session.execute("retrieve_runbooks", {"query": "../../evals/expected/dev.json"}) == {"runbooks": []}
    assert settings.database.read_bytes() == original


@pytest.mark.parametrize("path", ["/evals/expected/dev.json", "/data/prepared/incidents.sqlite", "/.env",
                                 "/artifacts/bridge-budget.sqlite", "/src/config.py", "/knowledge/ontology.yaml",
                                 "/assets/../../evals/expected/dev.json", "/%2e%2e/evals/expected/dev.json"])
def test_static_mount_does_not_serve_runtime_private_files(fixture_case, path):
    settings, _, _, _ = fixture_case
    with TestClient(create_app(replace(settings, mode="mock"), static_dir=ROOT / "web/dist")) as api:
        response = api.get(path)
    assert response.status_code == 404


def test_origin_host_input_boundaries_before_budget(fixture_case, monkeypatch):
    settings, body, _, _ = fixture_case
    install_transport(monkeypatch, lambda request: pytest.fail("invalid request reached transport"))
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        assert api.post("/api/investigate", json=body, headers={"Origin": "https://outside.invalid"}).status_code == 403
        assert api.post("/api/investigate", json=body, headers={"Host": "outside.invalid"}).status_code == 400
        assert api.post("/api/investigate", json={**body, "bridge_url": "https://outside.invalid"}).status_code == 422
        assert api.post("/api/investigate", content=b"a" * 16385).status_code == 413
        assert api.post("/api/investigate", json={**body, "payment_id": "../../evals/expected/dev.json"}).status_code == 422
        assert api.post("/api/refund", json=body).status_code in (404, 405)
    assert RequestBudget(settings.budget_path).count() == 0
