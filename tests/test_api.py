from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.config import Settings
from src.domain.models import Evidence, Payment
from src.storage.repository import create_database


def observations():
    payment = Payment(id="pay_test", symptom="The screen says payment failed. What happened?",
                      source_transaction_id="raw_1", original={"transaction_status": "Failed"},
                      warnings=["Original source currency is unknown."])
    base = {"payment_id": payment.id, "source": "synthetic fixture", "synthetic": True,
            "occurred_at": "2026-01-01T00:00:00Z", "observed_at": "2026-01-01T00:00:10Z"}
    evidence = [
        Evidence(**base, id="rec_pay", kind="Payment", data={"record_type": "provider_snapshot", "amount": "10.00", "currency": "USD", "provider_status": "succeeded", "capture_history_complete": True, "attempt_history_complete": True}),
        Evidence(**base, id="rec_attempt", kind="PaymentAttempt", data={"attempt_id": "att_1", "status": "succeeded"}),
        Evidence(**base, id="rec_capture", kind="Capture", data={"capture_id": "cap_1", "attempt_id": "att_1", "status": "succeeded", "amount": "10.00", "currency": "USD"}),
        Evidence(**{**base, "occurred_at": "2026-01-01T00:00:05Z"}, id="rec_app", kind="ApplicationStatusObservation", data={"observation_id": "app_1", "status": "failed", "channel": "checkout"}),
    ]
    return payment, evidence


@pytest.fixture
def prepared(tmp_path: Path):
    payment, evidence = observations()
    database = tmp_path / "test.sqlite"
    create_database(database, [payment], evidence)
    return Settings(database=database, budget_path=tmp_path / "budget.sqlite"), payment, evidence


def test_real_api_mock_result_contains_supported_evidence_and_trace(prepared):
    settings, payment, evidence = prepared
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["mode"] == "mock"
        cases = client.get("/api/cases").json()["cases"]
        assert cases == [{"payment_id": "pay_test", "symptom": payment.symptom}]
        response = client.post("/api/investigate", json={"payment_id": payment.id, "question": payment.symptom})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["payment_state"] == "captured"
    assert result["mode"] == "mock"
    assert result["technical"]["model_requests"] == 0
    assert len(result["technical"]["tool_calls"]) == 4
    assert result["discrepancies"] and result["runbooks"] and result["data_warnings"]
    assert {r["id"] for r in result["evidence"]} == {e.id for e in evidence}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("payload", [
    {"payment_id": "../../evals/expected/dev.json", "question": "hello"},
    {"payment_id": "pay_test", "question": "   "},
    {"payment_id": "pay_test", "question": "hello", "mode": "live"},
    {"payment_id": "pay_test", "question": "a" * 2001},
    {"payment_id": 3, "question": "hello"},
])
def test_input_errors_are_safe_and_readable(prepared, payload):
    settings, _, _ = prepared
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/investigate", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
    assert "input" not in response.json()["error"]


def test_not_found_missing_data_origins_and_body_size(prepared, tmp_path: Path):
    settings, _, _ = prepared
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/investigate", json={"payment_id": "missing", "question": "What happened?"}).status_code == 404
        assert client.post("/api/investigate", json={"payment_id": "pay_test", "question": "hello"}, headers={"Origin": "https://untrusted.example"}).status_code == 403
        assert client.post("/api/investigate", content=b"x" * 20000).status_code == 413
        assert client.get("/evals/expected/dev.json").status_code == 404
        assert client.post("/api/refund", json={}).status_code in (404, 405)
    with TestClient(create_app(Settings(database=tmp_path / "missing.sqlite"))) as client:
        assert client.get("/api/health").json()["data_ready"] is False
        assert client.get("/api/cases").status_code == 503


def test_next_investigation_reads_changed_evidence(prepared):
    settings, payment, evidence = prepared
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/investigate", json={"payment_id": payment.id, "question": payment.symptom}).json()
        new_evidence = [e for e in evidence if e.kind != "Capture"]
        for index, item in enumerate(new_evidence):
            if item.kind == "Payment":
                new_evidence[index] = Evidence(**{**item.model_dump(), "data": {**item.data, "provider_status": "processing", "capture_history_complete": False}})
        create_database(settings.database, [payment], new_evidence)
        second = client.post("/api/investigate", json={"payment_id": payment.id, "question": payment.symptom}).json()
    assert first["payment_state"] == "captured"
    assert second["payment_state"] == "unknown"
    assert first["investigation_id"] != second["investigation_id"]
    assert not any(record["id"] == "rec_capture" for record in second["evidence"])
