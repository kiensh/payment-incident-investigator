"""Invariant checks for non-informative copies, partial captures, and channel selection."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.config import Settings
from src.domain.models import Payment
from src.domain.rules import analyze
from src.storage.repository import create_database
from tests.test_chronology_regressions import display
from tests.test_domain import capture, record


@pytest.fixture
def payment():
    return Payment(id="pay_test", symptom="Please check the payment outcome.",
                   source_transaction_id="source-test", original={})


def provider(amount="42.00", status="requires_capture", at="2026-01-01T09:59:00Z"):
    return record("Payment", "provider-snapshot", {
        "record_type": "provider_snapshot", "provider_status": status,
        "amount": amount, "currency": "USD",
        "capture_history_complete": True, "attempt_history_complete": True,
    }, at)


@pytest.mark.parametrize("copy_time", [None, "2026-01-01T10:20:00"])
@pytest.mark.parametrize("known_id,copy_id", [("capture-a", "capture-z"), ("capture-z", "capture-a")])
def test_untimed_copy_cannot_create_a_proven_provider_contradiction(payment, copy_time, known_id, copy_id):
    known = capture(known_id, at="2026-01-01T10:00:00Z")
    receipt = display("receipt", "succeeded", "2026-01-01T10:30:00Z", "receipt")
    baseline = analyze(payment, [provider(), known, receipt])
    assert (baseline.payment_state, baseline.disposition) == ("captured", "no_escalation")
    duplicate = capture(copy_id, amount="42", at=copy_time)
    records = [provider(), known, duplicate, receipt]
    result = analyze(payment, records)
    assert result.payment_state == "captured"
    assert result.disposition != "escalate"
    assert not any(f.rule_id == "provider_snapshot_conflict" for f in result.discrepancies)
    assert "multiple_captures" not in result.applied_rules
    assert "capture_amount_mismatch" not in result.applied_rules
    assert sum(f.rule_id == "capture_success" for f in result.confirmed_facts) == 1
    assert result.model_dump() == analyze(payment, list(reversed(records))).model_dump()


@pytest.mark.parametrize("snapshot_time", [None, "2026-01-01T10:00:00Z", "2026-01-01T10:10:00"])
def test_unordered_snapshot_time_is_uncertainty_not_a_proven_contradiction(payment, snapshot_time):
    result = analyze(payment, [provider(at=snapshot_time), capture(at="2026-01-01T10:00:00Z"),
                              display("receipt", "succeeded", "2026-01-01T10:30:00Z", "receipt")])
    assert (result.payment_state, result.disposition) == ("captured", "check_required")
    assert not any(f.rule_id == "provider_snapshot_conflict" for f in result.discrepancies)
    assert result.unknowns and result.next_checks


def test_untimed_copy_cannot_erase_a_proven_provider_contradiction(payment):
    earlier = capture("capture-early", at="2026-01-01T10:00:00Z")
    result = analyze(payment, [earlier, capture("capture-copy", at=None),
                              provider(status="canceled", at="2026-01-01T10:10:00Z"),
                              display("receipt", "succeeded", "2026-01-01T10:30:00Z", "receipt")])
    assert (result.payment_state, result.disposition) == ("captured", "escalate")
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "provider_snapshot_conflict")
    assert earlier.id in discrepancy.evidence_ids


@pytest.mark.parametrize("include_later_capture", [False, True])
def test_requires_capture_can_follow_a_partial_capture_without_contradiction(payment, include_later_capture):
    first = capture("capture-first", "cap-first", amount="40.00", at="2026-01-01T10:00:00Z")
    duplicate = capture("capture-copy", "cap-first", amount="40.00", at="2026-01-01T10:01:00Z")
    records = [first, duplicate, provider("100.00", at="2026-01-01T10:10:00Z"),
               display("checkout-progress", "processing", "2026-01-01T10:12:00Z")]
    if include_later_capture:
        records.append(capture("capture-last", "cap-last", amount="60.00", at="2026-01-01T10:20:00Z"))
    result = analyze(payment, records)
    assert result.payment_state == "captured"
    assert result.disposition == ("escalate" if include_later_capture else "check_required")
    assert not any(f.rule_id in {"provider_snapshot_conflict", "app_discrepancy"} for f in result.discrepancies)


def test_requires_capture_after_the_full_expected_amount_is_still_a_conflict(payment):
    records = [capture("capture-first", "cap-first", amount="40.00", at="2026-01-01T10:00:00Z"),
               capture("capture-last", "cap-last", amount="60.00", at="2026-01-01T10:05:00Z"),
               provider("100.00", at="2026-01-01T10:10:00Z"),
               display("receipt", "succeeded", "2026-01-01T10:30:00Z", "receipt")]
    result = analyze(payment, records)
    assert (result.payment_state, result.disposition) == ("captured", "escalate")
    assert any(f.rule_id == "provider_snapshot_conflict" for f in result.discrepancies)


@pytest.mark.parametrize("status", ["processing", "pending", "authorized", "requires_action"])
def test_processing_between_partial_captures_is_not_a_proven_display_discrepancy(payment, status):
    first = capture("capture-first", "cap-first", amount="40.00", at="2026-01-01T10:00:00Z")
    last = capture("capture-last", "cap-last", amount="60.00", at="2026-01-01T10:20:00Z")
    records = [provider("100.00"), first, last,
               display("checkout-progress", status, "2026-01-01T10:10:00Z")]
    result = analyze(payment, records)
    assert result.payment_state == "captured"
    assert "multiple_captures" in result.applied_rules
    assert not any(f.rule_id == "app_discrepancy" for f in result.discrepancies)
    assert result.model_dump() == analyze(payment, list(reversed(records))).model_dump()


@pytest.mark.parametrize("expected_amount", ["100.00", None])
def test_one_partial_or_unscoped_capture_does_not_require_a_successful_display(payment, expected_amount):
    records = [capture(amount="40.00", at="2026-01-01T10:00:00Z"),
               display("checkout-progress", "processing", "2026-01-01T10:30:00Z")]
    if expected_amount is not None:
        records.append(provider(expected_amount))
    result = analyze(payment, records)
    assert (result.payment_state, result.disposition) == ("captured", "check_required")
    assert not any(f.rule_id == "app_discrepancy" for f in result.discrepancies)


def test_processing_after_full_capture_coverage_can_be_a_display_discrepancy(payment):
    first = capture("capture-first", "cap-first", amount="40.00", at="2026-01-01T10:00:00Z")
    last = capture("capture-last", "cap-last", amount="60.00", at="2026-01-01T10:20:00Z")
    result = analyze(payment, [provider("100.00"), first, last,
                              display("checkout-progress", "processing", "2026-01-01T10:30:00Z")])
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "app_discrepancy")
    assert {first.id, last.id} <= set(discrepancy.evidence_ids)


@pytest.mark.parametrize("copy_time", ["2026-01-01T10:20:00Z", None])
def test_equivalent_capture_copy_does_not_delay_known_full_coverage(payment, copy_time):
    earlier = capture("capture-early", amount="40.00", at="2026-01-01T10:00:00Z")
    result = analyze(payment, [provider("40.00"), earlier,
                              capture("capture-copy", amount="40.00", at=copy_time),
                              display("checkout-progress", "processing", "2026-01-01T10:10:00Z")])
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "app_discrepancy")
    assert earlier.id in discrepancy.evidence_ids
    assert "multiple_captures" not in result.applied_rules


@pytest.mark.parametrize("first_amount", ["40.00", "100.00"])
@pytest.mark.parametrize("later_time", ["2026-01-01T10:20:00Z", None])
def test_later_distinct_capture_does_not_erase_a_proven_failed_display(payment, first_amount, later_time):
    first = capture("capture-first", "cap-first", amount=first_amount, at="2026-01-01T10:00:00Z")
    failed = display("checkout-failed", "failed", "2026-01-01T10:10:00Z")
    initial = [provider("100.00"), first, failed]
    baseline = analyze(payment, initial)
    assert any(f.rule_id == "app_discrepancy" for f in baseline.discrepancies)
    later = capture("capture-later", "cap-later", amount="60.00", at=later_time)
    result = analyze(payment, initial + [later])
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "app_discrepancy")
    assert {first.id, failed.id} <= set(discrepancy.evidence_ids)
    assert later.id not in discrepancy.evidence_ids
    assert result.payment_state == "captured"


@pytest.mark.parametrize("later_status,later_time", [
    ("pending", "2026-01-01T10:20:00Z"),
    ("succeeded", "2026-01-01T10:20:00Z"),
    ("succeeded", None),
])
def test_later_capture_activity_does_not_retract_prior_full_amount_coverage(payment, later_status, later_time):
    first = capture("capture-first", "cap-first", amount="100.00", at="2026-01-01T10:00:00Z")
    processing = display("checkout-progress", "processing", "2026-01-01T10:10:00Z")
    initial = [provider("100.00"), first, processing]
    baseline = analyze(payment, initial)
    assert any(f.rule_id == "app_discrepancy" for f in baseline.discrepancies)
    later = capture("capture-later", "cap-later", status=later_status, amount="60.00", at=later_time)
    result = analyze(payment, initial + [later])
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "app_discrepancy")
    assert {first.id, processing.id, "provider-snapshot"} <= set(discrepancy.evidence_ids)
    assert later.id not in discrepancy.evidence_ids
    assert result.payment_state == "captured"
    assert ("capture_pending" if later_status == "pending" else "multiple_captures") in result.applied_rules


@pytest.mark.parametrize("question,disposition", [
    ("Does the receipt screen show a successful payment?", "no_escalation"),
    ("Does the receipt display show a successful payment?", "no_escalation"),
    ("Does the checkout screen show a successful payment?", "check_required"),
    ("Does the screen show a successful payment?", "check_required"),
    ("Does the receipt screen show success, and has checkout recovered?", "check_required"),
    ("The checkout failed earlier. Does the receipt screen show success?", "no_escalation"),
])
def test_explicit_channel_takes_precedence_over_generic_display_terms(payment, tmp_path, question, disposition):
    records = [capture(at="2026-01-01T10:00:20Z"),
               display("checkout-old", "failed", "2026-01-01T10:00:05Z"),
               display("receipt-current", "succeeded", "2026-01-01T10:00:30Z", "receipt")]
    database = tmp_path / "channels.sqlite"
    create_database(database, [payment], records)
    with TestClient(create_app(Settings(mode="mock", database=database))) as client:
        response = client.post("/api/investigate", json={"payment_id": payment.id, "question": question})
    assert response.status_code == 200
    result = response.json()
    assert (result["payment_state"], result["disposition"]) == ("captured", disposition)
    assert result["technical"]["model_requests"] == 0
    assert not result["discrepancies"]
    if disposition == "no_escalation":
        assert not any(f["rule_id"] == "app_discrepancy" for f in result["next_checks"])
