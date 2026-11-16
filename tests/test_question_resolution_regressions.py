"""A resolved capture is not proof that a webhook-delivery inquiry is resolved."""
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.config import Settings
from src.domain.models import Payment
from src.storage.repository import Repository, create_database
from tests.test_domain import capture, record, snapshot


@pytest.fixture
def captured_without_delivery(tmp_path: Path) -> Iterator[TestClient]:
    payment = Payment(
        id="pay_test",
        symptom="Was this payment captured successfully?",
        source_transaction_id="source-1",
        original={"transaction_status": "Successful"},
    )
    evidence = [
        capture(),
        snapshot(complete=True),
        record(
            "ProviderEvent", "event-record",
            {"event_id": "event-capture", "event_type": "charge.captured",
             "subject_kind": "Capture", "subject_id": "cap-1"},
            at="2026-01-01T10:00:21Z",
        ),
        record(
            "ApplicationStatusObservation", "receipt-record",
            {"observation_id": "receipt-1", "status": "succeeded", "channel": "receipt"},
            at="2026-01-01T10:00:30Z",
        ),
    ]
    database = tmp_path / "question-resolution.sqlite"
    create_database(database, [payment], evidence)
    with TestClient(create_app(Settings(mode="mock", database=database))) as client:
        yield client


def _ask(client: TestClient, question: str) -> dict:
    response = client.post(
        "/api/investigate", json={"payment_id": "pay_test", "question": question},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["question"] == question
    assert result["mode"] == "mock"
    assert result["technical"]["model_requests"] == 0
    assert result["payment_state"] == "captured"
    assert not result["discrepancies"]
    assert not any(item["kind"] == "WebhookDelivery" for item in result["evidence"])
    assert any(
        finding["rule_id"] == "missing_delivery_evidence"
        and finding["evidence_ids"] == ["event-record"]
        for finding in result["unknowns"]
    )
    return result


def test_financial_question_does_not_require_unrelated_delivery_proof(
    captured_without_delivery: TestClient,
) -> None:
    result = _ask(captured_without_delivery, "Was this payment captured successfully?")
    assert result["disposition"] == "no_escalation"
    assert any(finding["rule_id"] == "capture_success" for finding in result["confirmed_facts"])


def test_webhook_question_does_not_receive_blanket_symptom_closure(
    captured_without_delivery: TestClient,
) -> None:
    result = _ask(captured_without_delivery, "Was the webhook delivered?")
    # Scoped financial/application alignment is safe; closing the inquiry is not.
    closure = " ".join(
        finding["text"] for section in ("confirmed_facts", "next_checks")
        for finding in result[section] if finding["rule_id"] == "aligned_observations"
    ).lower()
    assert "sufficient and aligned for this symptom" not in closure, closure
    assert "no additional investigation is required for the supplied symptom" not in closure, closure


def test_webhook_question_keeps_delivery_inquiry_open_without_changing_capture(
    captured_without_delivery: TestClient,
) -> None:
    result = _ask(captured_without_delivery, "Was the webhook delivered?")
    # A wording-only fix is not an inquiry-specific disposition or next check.
    assert result["disposition"] == "check_required", {
        key: result[key] for key in ("payment_state", "disposition", "unknowns", "next_checks")
    }
    assert any(
        "event-record" in finding["evidence_ids"]
        and any(word in finding["text"].lower() for word in ("webhook", "delivery"))
        for finding in result["next_checks"]
    ), result["next_checks"]


def _change_records(client, change):
    database = client.app.state.settings.database
    snapshot = Repository(database).get_snapshot("pay_test")
    assert snapshot is not None
    payment, evidence = snapshot
    create_database(database, [payment], change(evidence))


def _delivery(status="delivered"):
    return record("WebhookDelivery", "delivery-record", {
        "delivery_id": "delivery-1", "event_id": "event-capture", "status": status,
        "attempt_number": 1, "http_status": 200 if status == "delivered" else None,
    }, at="2026-01-01T10:00:25Z")


@pytest.mark.parametrize("question", [
    "Was the notification delivered?", "Did the callback reach the endpoint?", "WAS THE WEBHOOK DELIVERED?",
])
def test_notification_question_hints_keep_missing_delivery_open(captured_without_delivery, question):
    result = _ask(captured_without_delivery, question)
    assert result["disposition"] == "check_required"


def test_no_event_records_do_not_close_a_delivery_inquiry(captured_without_delivery):
    _change_records(captured_without_delivery, lambda records: [r for r in records if r.kind != "ProviderEvent"])
    response = captured_without_delivery.post("/api/investigate", json={
        "payment_id": "pay_test", "question": "Was the webhook delivered?",
    })
    assert response.status_code == 200
    result = response.json()
    assert (result["payment_state"], result["disposition"]) == ("captured", "check_required")
    assert any(f["rule_id"] == "missing_delivery_evidence" for f in result["next_checks"])


def test_delivery_for_one_event_does_not_cover_another(captured_without_delivery):
    event = record("ProviderEvent", "event-two", {
        "event_id": "event-other", "event_type": "charge.captured",
        "subject_kind": "Capture", "subject_id": "cap-1",
    }, at="2026-01-01T10:00:22Z")
    _change_records(captured_without_delivery, lambda records: records + [_delivery(), event])
    for question, disposition in [("Was the webhook delivered?", "check_required"),
                                  ("Was this payment captured successfully?", "no_escalation")]:
        response = captured_without_delivery.post("/api/investigate", json={
            "payment_id": "pay_test", "question": question,
        })
        assert response.status_code == 200
        result = response.json()
        assert (result["payment_state"], result["disposition"]) == ("captured", disposition)
        gap = next(f for f in result["unknowns"] if f["rule_id"] == "missing_delivery_evidence")
        assert gap["evidence_ids"] == [event.id]


def test_pending_delivery_is_not_a_resolved_delivery_inquiry(captured_without_delivery):
    _change_records(captured_without_delivery, lambda records: records + [_delivery("pending")])
    response = captured_without_delivery.post("/api/investigate", json={
        "payment_id": "pay_test", "question": "Was the webhook delivered?",
    })
    assert response.status_code == 200
    result = response.json()
    assert (result["payment_state"], result["disposition"]) == ("captured", "check_required")
    assert any(f["rule_id"] == "notification_unresolved" for f in result["unknowns"])


@pytest.mark.parametrize("processing_question", [
    "Was the webhook processed?", "Was the webhook handled?",
    "Did the application handle the webhook?", "Is the application handling the webhook?",
    "Did the application consume the webhook?", "Is the consumer consuming this notification?",
    "Can we confirm the application processes these callbacks?",
])
def test_successful_delivery_does_not_prove_processing(captured_without_delivery, processing_question):
    _change_records(captured_without_delivery, lambda records: records + [_delivery()])
    for question, disposition in [("Was the webhook delivered?", "no_escalation"),
                                  (processing_question, "check_required")]:
        response = captured_without_delivery.post("/api/investigate", json={
            "payment_id": "pay_test", "question": question,
        })
        assert response.status_code == 200
        result = response.json()
        assert (result["payment_state"], result["disposition"]) == ("captured", disposition)
        if disposition == "check_required":
            assert any(f["rule_id"] == "notification_processing_unknown" for f in result["unknowns"])
            assert "aligned_observations" not in result["technical"]["applied_rules"]
