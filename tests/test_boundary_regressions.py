from dataclasses import replace
from pathlib import Path

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from src.agent.budget import RequestBudget
from src.api import create_app
from src.config import Settings
from src.storage.repository import create_database
from tests.test_api import observations


def live_fixture(tmp_path: Path):
    payment, evidence = observations()
    db = tmp_path / "case.sqlite"
    create_database(db, [payment], evidence)
    settings = Settings(mode="live", database=db, model_name="claude-opus-5.5",
                        budget_path=tmp_path / "budget.sqlite")
    body = {"payment_id": payment.id, "question": payment.symptom}
    return settings, body


@pytest.mark.parametrize("content_type,body", [("text/event-stream", ""), ("application/json", "{}")])
def test_empty_successful_stream_returns_structured_error_and_counts_request(tmp_path, monkeypatch, content_type, body):
    settings, query = live_fixture(tmp_path)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, headers={"content-type": content_type}, text=body)

    factory = anthropic.DefaultAsyncHttpxClient
    monkeypatch.setattr(anthropic, "DefaultAsyncHttpxClient", lambda **kwargs: factory(
        transport=httpx2.MockTransport(handler), **kwargs))
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.post("/api/investigate", json=query)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "bridge_unavailable"
    assert "invalid or incomplete" in response.json()["error"]["message"]
    assert len(requests) == RequestBudget(settings.budget_path).count() == 1


def test_constructor_failure_releases_slots_and_redacts_error(tmp_path, monkeypatch):
    settings, query = live_fixture(tmp_path)

    def invalid_constructor(*args, **kwargs):
        raise ValueError("synthetic-secret-in-sdk-error")

    monkeypatch.setattr("src.api.BridgeClient", invalid_constructor)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        responses = [client.post("/api/investigate", json=query) for _ in range(4)]
    assert [r.status_code for r in responses] == [502] * 4
    assert all(r.json()["error"]["code"] == "bridge_unavailable" for r in responses)
    assert all("synthetic-secret" not in r.text for r in responses)
    assert RequestBudget(settings.budget_path).count() == 0


def test_custom_header_configuration_error_does_not_exhaust_slots(tmp_path, monkeypatch):
    settings, query = live_fixture(tmp_path)
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "Authorization: Bearer synthetic-secret")
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        responses = [client.post("/api/investigate", json=query) for _ in range(3)]
    assert [r.status_code for r in responses] == [502] * 3
    assert all(not r.json()["error"]["retryable"] for r in responses)
    assert all("synthetic-secret" not in r.text for r in responses)
    assert RequestBudget(settings.budget_path).count() == 0


def test_self_contained_api_schema_without_csp_broken_interactive_docs(tmp_path):
    settings, _ = live_fixture(tmp_path)
    with TestClient(create_app(replace(settings, mode="mock"))) as client:
        schema = client.get("/api/openapi.json")
        assert schema.status_code == 200
        assert "/api/investigate" in schema.json()["paths"]
        assert client.get("/api/docs").status_code == 404
        assert "script-src 'self'" in schema.headers["content-security-policy"]
