"""Independent small-record oracles; tests never use the scenario generator as an oracle."""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.domain.models import Evidence, Payment
from src.domain.ontology import load_ontology, validate_evidence_graph
from src.domain.rules import analyze


@pytest.fixture
def payment() -> Payment:
    return Payment(id="pay_test", symptom="Please check checkout.", source_transaction_id="source-1",
                   original={"transaction_status": "Successful"})


def record(kind: str, name: str, data: dict[str, Any], at: str | None = "2026-01-01T10:00:20Z",
           seen: str | None = None, payment_id: str = "pay_test") -> Evidence:
    return Evidence.model_validate({"id": name, "payment_id": payment_id, "kind": kind, "source": "independent test observation",
                                    "synthetic": True, "occurred_at": at, "observed_at": seen or at,
                                    "data": data, "warnings": []})


def capture(name: str = "capture-record", capture_id: str = "cap-1", status: str = "succeeded",
            amount: str = "42.00", currency: str | None = "USD", **kwargs: Any) -> Evidence:
    return record("Capture", name, {"capture_id": capture_id, "status": status,
                                    "amount": amount, "currency": currency}, **kwargs)


def app(status: str = "succeeded", name: str = "app-record", at: str | None = "2026-01-01T10:00:30Z",
        seen: str | None = None) -> Evidence:
    return record("ApplicationStatusObservation", name,
                  {"observation_id": name, "status": status, "channel": "checkout"}, at, seen)


def snapshot(status: str = "succeeded", *, complete: bool = False, **kwargs: Any) -> Evidence:
    data = {"record_type": "provider_snapshot", "provider_status": status, "amount": "42.00", "currency": "USD",
            "capture_history_complete": complete, "attempt_history_complete": complete}
    data.update(kwargs)
    return record("Payment", "provider-record", data, "2026-01-01T10:00:25Z")


def all_findings(result: Any) -> list[Any]:
    return [finding for field in ("confirmed_facts", "discrepancies", "hypotheses", "unknowns", "next_checks")
            for finding in getattr(result, field)]


def test_successful_source_status_does_not_establish_capture(payment: Payment) -> None:
    result = analyze(payment, [app("pending")])
    assert result.payment_state == "unknown"
    assert result.disposition == "check_required"
    assert not any(f.rule_id == "capture_success" for f in result.confirmed_facts)


@pytest.mark.parametrize("coarse_status", ["Successful", "Failed", "Pending"])
def test_all_coarse_statuses_are_non_authoritative(payment: Payment, coarse_status: str) -> None:
    payment.original["transaction_status"] = coarse_status
    result = analyze(payment, [])
    assert result.payment_state == "unknown"
    assert result.unknowns


def test_normal_capture_is_resolved_despite_source_quality_warnings(payment: Payment) -> None:
    payment.warnings = ["No original currency", "Ambiguous merchant identity"]
    result = analyze(payment, [capture(), snapshot(), app()])
    assert (result.payment_state, result.disposition) == ("captured", "no_escalation")
    assert not result.discrepancies
    assert not result.hypotheses
    fact = next(f for f in result.confirmed_facts if f.rule_id == "capture_success")
    assert fact.evidence_ids == ["capture-record"]
    assert "42.00 USD" in fact.text


def test_authorization_is_not_capture(payment: Payment) -> None:
    hold = record("Authorization", "hold-record", {"authorization_id": "hold-1", "status": "authorized", "amount": "42.00", "currency": "USD"})
    result = analyze(payment, [hold, app("pending")])
    assert (result.payment_state, result.disposition) == ("authorized", "check_required")
    assert "capture_success" not in result.applied_rules
    assert any("not completed" in f.text for f in result.unknowns)


def test_failed_capture_does_not_reverse_authorization(payment: Payment) -> None:
    hold = record("Authorization", "hold-record", {"authorization_id": "hold-1", "status": "authorized", "amount": "42.00", "currency": "USD"})
    result = analyze(payment, [hold, capture(status="failed"), app("failed")])
    assert result.payment_state == "authorized"
    assert "capture_failed" in result.applied_rules
    assert "attempt_failure" not in result.applied_rules


def test_failed_attempt_without_complete_history_is_unknown(payment: Payment) -> None:
    attempt = record("PaymentAttempt", "attempt-record", {"attempt_id": "attempt-1", "status": "failed", "error_code": "card_declined"})
    result = analyze(payment, [attempt, snapshot("requires_payment_method"), app("failed")])
    assert result.payment_state == "unknown"
    assert "attempt_failure" not in result.applied_rules


def test_complete_failed_view_can_resolve_without_escalation(payment: Payment) -> None:
    attempt = record("PaymentAttempt", "attempt-record", {"attempt_id": "attempt-1", "status": "failed", "error_code": "card_declined"})
    provider = snapshot("requires_payment_method", complete=True)
    result = analyze(payment, [attempt, provider, app("failed")])
    assert (result.payment_state, result.disposition) == ("failed", "no_escalation")
    fact = next(f for f in result.confirmed_facts if f.rule_id == "attempt_failure")
    assert set(fact.evidence_ids) == {attempt.id, provider.id}
    assert "capture_success" not in result.applied_rules


def test_complete_snapshot_cannot_cover_an_attempt_that_happened_later(payment: Payment) -> None:
    attempt = record("PaymentAttempt", "attempt-record", {"attempt_id": "attempt-1", "status": "failed"}, "2026-01-01T10:00:28Z")
    result = analyze(payment, [attempt, snapshot("requires_payment_method", complete=True), app("failed")])
    assert result.payment_state == "unknown"


def test_repeated_attempts_are_not_repeated_captures(payment: Payment) -> None:
    first = record("PaymentAttempt", "attempt-1", {"attempt_id": "a1", "status": "failed"}, "2026-01-01T10:00:01Z")
    second = record("PaymentAttempt", "attempt-2", {"attempt_id": "a2", "status": "succeeded"}, "2026-01-01T10:00:10Z")
    result = analyze(payment, [first, second, capture(), snapshot(), app()])
    assert result.disposition == "no_escalation"
    assert sum(f.rule_id == "capture_success" for f in result.confirmed_facts) == 1
    assert "multiple_captures" not in result.applied_rules


def test_webhook_failure_does_not_change_capture_state(payment: Payment) -> None:
    event = record("ProviderEvent", "event-record", {"event_id": "event-1", "event_type": "payment_intent.succeeded", "subject_kind": "Payment", "subject_id": payment.id})
    delivery = record("WebhookDelivery", "delivery-record", {"delivery_id": "d1", "event_id": "event-1", "status": "failed", "http_status": 500, "attempt_number": 1})
    result = analyze(payment, [capture(), snapshot(), app("failed"), event, delivery])
    assert (result.payment_state, result.disposition) == ("captured", "check_required")
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "app_discrepancy")
    assert set(discrepancy.evidence_ids) == {"capture-record", "app-record"}
    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].text.startswith("If ")
    assert "delivery-record" in result.hypotheses[0].evidence_ids


def test_repeated_delivery_does_not_create_an_extra_capture(payment: Payment) -> None:
    event = record("ProviderEvent", "event-record", {"event_id": "event-1", "event_type": "payment_intent.succeeded", "subject_kind": "Payment", "subject_id": payment.id})
    deliveries = [record("WebhookDelivery", f"delivery-{n}", {"delivery_id": f"d{n}", "event_id": "event-1", "status": "delivered", "http_status": 200, "attempt_number": n}) for n in (1, 2, 3)]
    result = analyze(payment, [capture(), snapshot(), app(), event, *deliveries])
    assert result.disposition == "no_escalation"
    fact = next(f for f in result.confirmed_facts if f.rule_id == "duplicate_delivery")
    assert set(fact.evidence_ids) == {item.id for item in deliveries}
    assert "multiple_captures" not in result.applied_rules


def test_two_successful_capture_ids_escalate_without_inventing_intent(payment: Payment) -> None:
    second = capture("capture-record-2", "cap-2")
    result = analyze(payment, [capture(), second, snapshot(), app()])
    assert (result.payment_state, result.disposition) == ("captured", "escalate")
    fact = next(f for f in result.discrepancies if f.rule_id == "multiple_captures")
    assert set(fact.evidence_ids) == {"capture-record", "capture-record-2"}
    assert "whether" in fact.text
    assert "capture_amount_mismatch" in result.applied_rules


def test_duplicate_capture_snapshot_is_deduplicated_by_capture_identity(payment: Payment) -> None:
    result = analyze(payment, [capture(), capture("capture-copy"), snapshot(), app()])
    assert result.disposition == "no_escalation"
    assert sum(f.rule_id == "capture_success" for f in result.confirmed_facts) == 1
    assert "multiple_captures" not in result.applied_rules


def test_pending_then_success_is_not_conflicting_terminal_capture(payment: Payment) -> None:
    pending = capture("capture-old", status="pending", at="2026-01-01T10:00:10Z")
    result = analyze(payment, [pending, capture(), snapshot(), app()])
    assert result.payment_state == "captured"
    assert result.disposition == "no_escalation"
    assert "capture_identity_conflict" not in result.applied_rules


def test_conflicting_same_capture_cannot_be_counted_as_confirmed(payment: Payment) -> None:
    result = analyze(payment, [capture(), capture("capture-other", status="failed"), snapshot(), app()])
    assert (result.payment_state, result.disposition) == ("unknown", "escalate")
    assert "capture_identity_conflict" in result.applied_rules
    assert "capture_success" not in result.applied_rules


def test_amount_reconciliation_does_not_convert_or_fill_missing_currency(payment: Payment) -> None:
    result = analyze(payment, [capture(currency=None), snapshot(), app()])
    assert result.payment_state == "captured"
    assert "currency_unavailable" in result.applied_rules
    assert "capture_amount_mismatch" not in result.applied_rules


def test_naive_source_dates_never_establish_cross_source_order(payment: Payment) -> None:
    result = analyze(payment, [capture(at="2026-01-01T10:00:20"), app("failed", at="2026-01-01T10:00:30")])
    assert result.payment_state == "captured"
    assert "app_order_unknown" in result.applied_rules
    assert not result.discrepancies


def test_equal_application_times_do_not_break_tie_by_arrival(payment: Payment) -> None:
    one = app("succeeded", "app-1", "2026-01-01T10:00:30Z", "2026-01-01T10:00:31Z")
    two = app("failed", "app-2", "2026-01-01T10:00:30Z", "2026-01-01T10:00:32Z")
    result = analyze(payment, [capture(), snapshot(), one, two])
    assert result.disposition == "check_required"
    assert "app_order_unknown" in result.applied_rules
    assert "aligned_observations" not in result.applied_rules


def test_old_failed_application_observation_is_not_a_current_discrepancy(payment: Payment) -> None:
    old = app("failed", at="2026-01-01T10:00:01Z", seen="2026-01-01T10:00:40Z")
    result = analyze(payment, [capture(), snapshot(), old])
    assert result.payment_state == "captured"
    assert "app_precedes_financial" in result.applied_rules
    assert not result.discrepancies


def test_new_successful_app_view_resolves_historical_failed_view(payment: Payment) -> None:
    old = app("failed", "app-old", "2026-01-01T10:00:01Z")
    result = analyze(payment, [capture(), snapshot(), old, app()])
    assert result.disposition == "no_escalation"
    assert not result.discrepancies


def test_event_arrival_is_not_business_order(payment: Payment) -> None:
    first = record("ProviderEvent", "event-first", {"event_id": "e1", "event_type": "payment_intent.processing", "subject_kind": "Payment", "subject_id": payment.id}, "2026-01-01T10:00:10Z", "2026-01-01T10:00:40Z")
    second = record("ProviderEvent", "event-second", {"event_id": "e2", "event_type": "payment_intent.succeeded", "subject_kind": "Payment", "subject_id": payment.id}, "2026-01-01T10:00:20Z", "2026-01-01T10:00:21Z")
    result = analyze(payment, [capture(), snapshot(), app(), first, second])
    assert result.payment_state == "captured"
    fact = next(f for f in result.confirmed_facts if f.rule_id == "out_of_order_events")
    assert set(fact.evidence_ids) == {first.id, second.id}


def test_success_event_without_capture_is_not_capture_proof(payment: Payment) -> None:
    event = record("ProviderEvent", "event-record", {"event_id": "e1", "event_type": "payment_intent.succeeded", "subject_kind": "Payment", "subject_id": payment.id})
    result = analyze(payment, [event, app()])
    assert result.payment_state == "unknown"
    assert "capture_success" not in result.applied_rules


def test_missing_related_record_is_unknown_not_failed(payment: Payment) -> None:
    delivery = record("WebhookDelivery", "delivery-record", {"delivery_id": "d1", "event_id": "missing-event", "status": "delivered", "http_status": 200, "attempt_number": 1})
    missing = validate_evidence_graph(payment, [delivery])
    assert len(missing) == 1
    assert missing[0].target_id == "missing-event"
    result = analyze(payment, [capture(), app(), delivery])
    assert result.payment_state == "captured"
    assert "missing_reference" in result.applied_rules


def test_relationship_with_known_wrong_kind_is_rejected(payment: Payment) -> None:
    wrong = record("WebhookDelivery", "delivery-record", {"delivery_id": "d1", "event_id": "cap-1", "status": "delivered", "http_status": 200, "attempt_number": 1})
    with pytest.raises(ValueError, match="wrong entity kind"):
        analyze(payment, [capture(), wrong])


def test_cross_payment_records_are_rejected(payment: Payment) -> None:
    with pytest.raises(ValueError, match="cross-payment"):
        analyze(payment, [capture(payment_id="other-payment")])


def test_findings_are_stable_unique_and_cite_existing_records(payment: Payment) -> None:
    items = [capture(), snapshot(), app("failed")]
    first = analyze(payment, items)
    second = analyze(payment, list(reversed(items)))
    assert first.model_dump() == second.model_dump()
    findings = all_findings(first)
    assert len({f.id for f in findings}) == len(findings)
    assert {eid for f in findings for eid in f.evidence_ids} <= {item.id for item in items}
    assert set(first.applied_rules) <= set(load_ontology()["rules"])


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1", "0", "not-money"])
def test_invalid_amounts_are_rejected(amount: str) -> None:
    with pytest.raises(ValidationError):
        capture(amount=amount)


def test_evaluation_metadata_and_wrong_kind_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        record("Capture", "capture-record", {"capture_id": "c1", "status": "succeeded", "amount": "42", "currency": "USD", "expected": "captured"})
    with pytest.raises(ValidationError):
        record("Capture", "capture-record", {"attempt_id": "a1", "status": "succeeded", "amount": "42", "currency": "USD"})


@pytest.mark.parametrize("status,http", [("failed", 200), ("delivered", 503), ("pending", 200)])
def test_delivery_status_must_match_response(status: str, http: int) -> None:
    with pytest.raises(ValidationError):
        record("WebhookDelivery", "d1", {"delivery_id": "d1", "event_id": "e1", "status": status, "http_status": http, "attempt_number": 1})


def test_source_context_cannot_assert_complete_provider_history() -> None:
    with pytest.raises(ValidationError):
        record("Payment", "source-record", {"record_type": "source_context", "source_transaction_id": "source-1", "original_status": "Successful", "payment_method": "Credit Card", "amount": "42", "currency": None, "capture_history_complete": True})


def test_equivalent_decimal_spelling_is_not_a_capture_conflict(payment: Payment) -> None:
    result = analyze(payment, [capture(), capture("capture-copy", amount="42"), snapshot(), app()])
    assert (result.payment_state, result.disposition) == ("captured", "no_escalation")
    assert "capture_identity_conflict" not in result.applied_rules


def test_extreme_decimal_exponents_are_rejected_without_expansion() -> None:
    with pytest.raises(ValidationError):
        capture(amount="1E-1000000000")


def test_history_completeness_requires_an_actual_boolean() -> None:
    with pytest.raises(ValidationError):
        snapshot("requires_payment_method", capture_history_complete="yes")


def test_timestamp_validation_preserves_unknown_timezone() -> None:
    assert capture(at="2026-01-01T10:00:20").occurred_at == "2026-01-01T10:00:20"
    with pytest.raises(ValidationError):
        capture(at="2026-01-01")
