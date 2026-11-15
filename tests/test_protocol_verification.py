"""Fresh final-verifier transport probes, retained for regression testing.

Mock transports and temporary ledgers only; no network or real credentials.
Originally verified against frozen candidate 16632d0.
"""
import json

import httpx2
import pytest
from fastapi.testclient import TestClient

from src.agent.budget import RequestBudget
from src.api import create_app
from tests.test_final_boundaries import fixture_case as fixture_case
from tests.test_final_boundaries import install_transport, sse, stream_response
from tests.test_final_boundaries import isolated_sdk_environment as isolated_sdk_environment

MARKER = "fresh-verifier-synthetic-private-marker-not-real"


@pytest.mark.parametrize("error_type", ["overloaded_error", "api_error", "rate_limit_error", "authentication_error"])
def test_sse_error_is_structured_redacted_and_slots_recover(fixture_case, monkeypatch, error_type):
    settings, body, _, _ = fixture_case
    seen = []
    payload = "event: error\ndata: " + json.dumps({
        "type": "error", "error": {"type": error_type, "message": MARKER}
    }) + "\n\n"

    def handler(request):
        seen.append(request)
        return stream_response(payload)

    install_transport(monkeypatch, handler)
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        responses = [api.post("/api/investigate", json=body) for _ in range(3)]
    assert len(seen) == RequestBudget(settings.budget_path).count() == 3
    assert all(MARKER not in response.text for response in responses)
    assert [response.status_code for response in responses] == [502, 502, 502]
    assert all(r.json()["error"]["code"] == "bridge_unavailable" for r in responses)


def test_transport_timeout_is_redacted_one_request(fixture_case, monkeypatch):
    settings, body, _, _ = fixture_case
    seen = []

    def handler(request):
        seen.append(request)
        raise httpx2.ReadTimeout(MARKER, request=request)

    install_transport(monkeypatch, handler)
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        response = api.post("/api/investigate", json=body)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "bridge_unavailable"
    assert MARKER not in response.text
    assert len(seen) == RequestBudget(settings.budget_path).count() == 1


@pytest.mark.parametrize("stop", ["max_tokens", "refusal", "pause_turn"])
def test_incomplete_stream_does_not_execute_tools(fixture_case, monkeypatch, stop):
    from src.tools.session import ToolSession

    settings, body, _, _ = fixture_case
    calls = [{"type": "tool_use", "id": "call_fresh", "name": "check_inconsistencies",
              "input": {"payment_id": body["payment_id"]}}]
    install_transport(monkeypatch, lambda request: stream_response(sse(calls, stop=stop)))
    monkeypatch.setattr(ToolSession, "execute", lambda *args: pytest.fail("incomplete tool executed"))
    with TestClient(create_app(settings), raise_server_exceptions=False) as api:
        response = api.post("/api/investigate", json=body)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "unsupported_conclusion"
    assert RequestBudget(settings.budget_path).count() == 1
