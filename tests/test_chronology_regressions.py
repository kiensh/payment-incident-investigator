"""Small synthetic counterexamples for observation identity and chronology."""
from __future__ import annotations

import pytest

from src.domain.models import Payment
from src.domain.rules import analyze
from tests.test_domain import capture, record


@pytest.fixture
def payment():
    return Payment(id="pay_test", symptom="Please check the payment outcome.",
                   source_transaction_id="source-test", original={})


def provider(status="canceled", at="2026-01-01T10:05:00Z"):
    return record("Payment", "provider-snapshot", {
        "record_type": "provider_snapshot", "provider_status": status,
        "amount": "42.00", "currency": "USD",
        "capture_history_complete": True, "attempt_history_complete": True,
    }, at)


def display(name, status, at, channel="checkout"):
    return record("ApplicationStatusObservation", name, {
        "observation_id": name, "status": status, "channel": channel,
    }, at)


@pytest.mark.parametrize("attempt_time", [
    "2026-01-01T10:10:00Z", "2026-01-01T10:05:00Z", None, "2026-01-01T10:10:00",
])
def test_canceled_snapshot_cannot_close_uncovered_processing_activity(payment, attempt_time):
    attempt = record("PaymentAttempt", "processing-attempt", {
        "attempt_id": "attempt-1", "status": "processing",
    }, attempt_time)
    result = analyze(payment, [provider(), attempt,
                              display("checkout-failed", "failed", "2026-01-01T10:20:00Z")])
    assert (result.payment_state, result.disposition) == ("unknown", "check_required")
    assert "aligned_observations" not in result.applied_rules
    assert any({"provider-snapshot", "processing-attempt"} <= set(f.evidence_ids)
               for f in result.unknowns)


@pytest.mark.parametrize("timed_id,untimed_id", [("snapshot-a", "snapshot-z"), ("snapshot-z", "snapshot-a")])
def test_equivalent_snapshot_coverage_does_not_depend_on_evidence_ids(payment, timed_id, untimed_id):
    data = provider().data
    timed = record("Payment", timed_id, data, "2026-01-01T10:05:00Z")
    untimed = record("Payment", untimed_id, data, None)
    attempt = record("PaymentAttempt", "failed-attempt", {"attempt_id": "attempt-1", "status": "failed"},
                     "2026-01-01T10:00:00Z")
    records = [timed, untimed, attempt,
               display("checkout-failed", "failed", "2026-01-01T10:20:00Z")]
    result = analyze(payment, records)
    assert (result.payment_state, result.disposition) == ("failed", "no_escalation")
    cancellation = next(f for f in result.confirmed_facts if f.rule_id == "provider_canceled")
    assert cancellation.evidence_ids == [timed_id]
    assert "provider_snapshot_coverage_gap" not in result.applied_rules
    assert result.model_dump() == analyze(payment, list(reversed(records))).model_dump()


def test_later_complete_cancellation_can_resolve_an_older_processing_attempt(payment):
    attempt = record("PaymentAttempt", "processing-attempt", {
        "attempt_id": "attempt-1", "status": "processing",
    }, "2026-01-01T10:00:00Z")
    result = analyze(payment, [provider(), attempt,
                              display("checkout-failed", "failed", "2026-01-01T10:20:00Z")])
    assert (result.payment_state, result.disposition) == ("failed", "no_escalation")
    assert "provider_canceled" in result.applied_rules


@pytest.mark.parametrize("other_channel", ["back-office", "receipt", "support"])
def test_success_in_another_channel_does_not_resolve_checkout_failure(payment, other_channel):
    captured = capture(at="2026-01-01T10:00:00Z")
    checkout = display("checkout-failed", "failed", "2026-01-01T10:05:00Z")
    other = display("other-success", "succeeded", "2026-01-01T10:06:00Z", other_channel)
    result = analyze(payment, [captured, checkout, other])
    assert (result.payment_state, result.disposition) == ("captured", "check_required")
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "app_discrepancy")
    assert checkout.id in discrepancy.evidence_ids
    assert other.id not in discrepancy.evidence_ids
    assert "checkout" in discrepancy.text
    assert "app_order_unknown" not in result.applied_rules
    assert "aligned_observations" not in result.applied_rules


def test_success_in_the_same_channel_can_resolve_its_earlier_failure(payment):
    result = analyze(payment, [capture(at="2026-01-01T10:00:00Z"),
                              display("checkout-failed", "failed", "2026-01-01T10:05:00Z"),
                              display("checkout-recovered", "succeeded", "2026-01-01T10:06:00Z")])
    assert (result.payment_state, result.disposition) == ("captured", "no_escalation")
    assert not result.discrepancies


@pytest.mark.parametrize("early_id,later_id", [("capture-a", "capture-z"), ("capture-z", "capture-a")])
def test_repeated_capture_observation_cannot_hide_a_later_canceled_snapshot(payment, early_id, later_id):
    earlier = capture(early_id, at="2026-01-01T10:00:00Z")
    later = capture(later_id, at="2026-01-01T10:20:00Z")
    snapshot = provider(at="2026-01-01T10:10:00Z")
    items = [earlier, later, snapshot,
             display("checkout-success", "succeeded", "2026-01-01T10:30:00Z")]
    result = analyze(payment, items)
    assert (result.payment_state, result.disposition) == ("captured", "escalate")
    conflict = next(f for f in result.discrepancies if f.rule_id == "provider_snapshot_conflict")
    assert {earlier.id, snapshot.id} <= set(conflict.evidence_ids)
    assert "multiple_captures" not in result.applied_rules
    assert "capture_amount_mismatch" not in result.applied_rules
    assert sum(f.rule_id == "capture_success" for f in result.confirmed_facts) == 1
    assert result.model_dump() == analyze(payment, list(reversed(items))).model_dump()


@pytest.mark.parametrize("repeat_time", ["2026-01-01T10:20:00Z", None, "2026-01-01T10:20:00"])
def test_repeated_capture_observation_cannot_move_an_established_display_discrepancy(payment, repeat_time):
    earlier = capture("capture-z", at="2026-01-01T10:00:00Z")
    later = capture("capture-a", at=repeat_time)
    failed = display("checkout-failed", "failed", "2026-01-01T10:05:00Z")
    result = analyze(payment, [earlier, later, failed])
    assert (result.payment_state, result.disposition) == ("captured", "check_required")
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "app_discrepancy")
    assert {earlier.id, failed.id} <= set(discrepancy.evidence_ids)
    assert "app_precedes_financial" not in result.applied_rules
    assert "multiple_captures" not in result.applied_rules


@pytest.mark.parametrize("question,disposition", [
    ("How many captured payments are evidenced?", "no_escalation"),
    ("The customer remembers an error earlier in checkout. Is the order now complete?", "no_escalation"),
    ("Has checkout recovered?", "check_required"),
    ("Does the checkout still show failed?", "check_required"),
    ("The old checkout failed. Is checkout now updated?", "check_required"),
])
def test_historical_channel_gap_does_not_close_or_block_the_wrong_inquiry(payment, question, disposition):
    old = display("checkout-old", "failed", "2026-01-01T10:00:05Z")
    receipt = display("receipt-current", "succeeded", "2026-01-01T10:00:35Z", "order_page")
    result = analyze(payment, [old, capture(at="2026-01-01T10:00:20Z"), receipt,
                              provider("succeeded", at="2026-01-01T10:00:40Z")], question)
    assert (result.payment_state, result.disposition) == ("captured", disposition)
    assert not result.discrepancies
    historical = next(f for f in result.unknowns if f.rule_id == "app_precedes_financial")
    assert old.id in historical.evidence_ids
    assert receipt.id not in historical.evidence_ids
    if disposition == "no_escalation":
        alignment = next(f for f in result.confirmed_facts if f.rule_id == "aligned_observations")
        assert old.id not in alignment.evidence_ids
        assert receipt.id in alignment.evidence_ids
        assert "app_discrepancy" not in result.applied_rules


def test_recovered_notification_does_not_explain_a_pre_capture_checkout_error(payment):
    event = record("ProviderEvent", "event-capture", {
        "event_id": "event-1", "event_type": "charge.captured", "subject_kind": "Capture", "subject_id": "cap-1",
    }, "2026-01-01T10:00:20Z")
    deliveries = [record("WebhookDelivery", name, {
        "delivery_id": name, "event_id": "event-1", "status": status,
        "http_status": status_code, "attempt_number": attempt,
    }, at) for name, status, status_code, attempt, at in [
        ("delivery-failed", "failed", 500, 1, "2026-01-01T10:00:25Z"),
        ("delivery-recovered", "delivered", 200, 2, "2026-01-01T10:00:30Z"),
    ]]
    result = analyze(payment, [capture(), event, *deliveries,
                              display("checkout-old", "failed", "2026-01-01T10:00:05Z"),
                              display("receipt-current", "succeeded", "2026-01-01T10:00:35Z", "receipt")],
                     "How many captured payments are evidenced?")
    assert (result.payment_state, result.disposition) == ("captured", "no_escalation")
    assert not result.hypotheses


@pytest.mark.parametrize("kind,data", [
    ("Capture", {"capture_id": "capture-pending", "status": "pending", "amount": "42.00", "currency": "USD"}),
    ("ProviderEvent", {"event_id": "event-processing", "event_type": "payment_intent.processing",
                       "subject_kind": "Payment", "subject_id": "pay_test"}),
    ("Authorization", {"authorization_id": "authorization-later", "status": "declined",
                       "amount": "42.00", "currency": "USD"}),
])
def test_cancellation_coverage_includes_other_financial_activity(payment, kind, data):
    activity = record(kind, "new-activity", data, "2026-01-01T10:10:00Z")
    result = analyze(payment, [provider(), activity,
                              display("checkout-failed", "failed", "2026-01-01T10:20:00Z")])
    assert (result.payment_state, result.disposition) == ("unknown", "check_required")
    assert "provider_snapshot_coverage_gap" in result.applied_rules


@pytest.mark.parametrize("kind,data", [
    ("PaymentAttempt", {"attempt_id": "attempt-failed", "status": "failed"}),
    ("Capture", {"capture_id": "capture-failed", "status": "failed", "amount": "42.00", "currency": "USD"}),
    ("ProviderEvent", {"event_id": "event-canceled", "event_type": "payment_intent.canceled",
                       "subject_kind": "Payment", "subject_id": "pay_test"}),
])
def test_compatible_terminal_observations_do_not_need_a_tie_break(payment, kind, data):
    activity = record(kind, "closed-activity", data, "2026-01-01T10:05:00Z")
    result = analyze(payment, [provider(), activity,
                              display("checkout-failed", "failed", "2026-01-01T10:20:00Z")])
    assert (result.payment_state, result.disposition) == ("failed", "no_escalation")
    assert "provider_snapshot_coverage_gap" not in result.applied_rules


def test_provider_status_before_all_capture_observations_is_not_a_current_conflict(payment):
    result = analyze(payment, [provider("requires_capture", at="2026-01-01T09:59:00Z"),
                              capture("capture-early", at="2026-01-01T10:00:00Z"),
                              capture("capture-copy", at="2026-01-01T10:20:00Z"),
                              display("receipt-current", "succeeded", "2026-01-01T10:30:00Z", "receipt")])
    assert (result.payment_state, result.disposition) == ("captured", "no_escalation")
    assert "provider_snapshot_conflict" not in result.applied_rules
    assert "multiple_captures" not in result.applied_rules
