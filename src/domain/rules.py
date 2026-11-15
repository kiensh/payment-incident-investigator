"""Deterministic, evidence-scoped checks; no guessed root causes or financial actions."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from src.domain.models import Analysis, Evidence, Finding, Payment
from src.domain.ontology import load_ontology, validate_evidence_graph

Group = Literal["confirmed_facts", "discrepancies", "hypotheses", "unknowns", "next_checks"]


def _time(value: str | None) -> datetime | None:
    if value is None:
        return None
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result if result.tzinfo is not None and result.utcoffset() is not None else None


def _latest(items: list[Evidence]) -> list[Evidence]:
    """Return all plausible latest records; never resolve a tie by arrival or row order."""
    if len(items) < 2:
        return items
    times = [_time(item.occurred_at) for item in items]
    if any(value is None for value in times):
        return items
    latest = max(value for value in times if value is not None)
    return [item for item in items if _time(item.occurred_at) == latest]


def _group(items: list[Evidence], field: str) -> dict[str, list[Evidence]]:
    result: dict[str, list[Evidence]] = defaultdict(list)
    for item in items:
        result[item.data[field]].append(item)
    return dict(result)


def _amount(item: Evidence) -> str:
    currency = item.data["currency"] or "(currency unknown)"
    return f"{item.data['amount']} {currency}"


def analyze(payment: Payment, evidence: list[Evidence]) -> Analysis:
    """Inspect one immutable snapshot; only authoritative records determine state.

    `captured` means a successful capture is evidenced, not settled, refunded, or
    reconciled. `failed` requires an explicit complete provider view. Unknowns
    about original source quality alone do not trigger operational escalation.
    """
    ontology = load_ontology()
    missing = validate_evidence_graph(payment, evidence)
    result = Analysis(payment_id=payment.id, payment_state="unknown", disposition="no_escalation")
    by_kind: dict[str, list[Evidence]] = defaultdict(list)
    for item in sorted(evidence, key=lambda row: row.id):
        by_kind[item.kind].append(item)

    def add(group: Group, rule: str, text: str, refs: list[Evidence]) -> None:
        if rule not in ontology["rules"]:
            raise ValueError(f"unknown ontology rule: {rule}")
        ids = sorted({item.id for item in refs})
        identity = "\x1f".join([payment.id, group, rule, text, *ids])
        finding = Finding(id="f_" + sha256(identity.encode()).hexdigest()[:20], text=text,
                          evidence_ids=ids, rule_id=rule)
        target: list[Finding] = getattr(result, group)
        if not any(old.id == finding.id for old in target):
            target.append(finding)
        if rule not in result.applied_rules:
            result.applied_rules.append(rule)

    def check() -> None:
        if result.disposition == "no_escalation":
            result.disposition = "check_required"

    source = [item for item in by_kind["Payment"] if item.data["record_type"] == "source_context"]
    snapshots = _latest([item for item in by_kind["Payment"] if item.data["record_type"] == "provider_snapshot"])
    snapshot: Evidence | None = None
    if snapshots:
        # Equivalent tied snapshots need no invented ordering; contradictory ones remain unresolved.
        fingerprints = {str(sorted(item.data.items())) for item in snapshots}
        if len(fingerprints) == 1:
            snapshot = snapshots[0]
        else:
            add("discrepancies", "provider_snapshot_conflict",
                "The latest provider snapshot cannot be selected unambiguously; supplied snapshots disagree.", snapshots)
            result.disposition = "escalate"
    if source:
        add("confirmed_facts", "source_context",
            "The original synthetic transaction row is coarse source context, not authorization, capture, or webhook history.", source)
    if payment.warnings:
        add("unknowns", "source_context",
            "Source identity, currency, or timezone warnings remain unresolved; no identity merge or missing value was inferred.", source)

    captures = _group(by_kind["Capture"], "capture_id")
    successes: list[Evidence] = []
    capture_conflicts: list[Evidence] = []
    for capture_id, records in captures.items():
        successful = [item for item in records if item.data["status"] == ontology["policies"]["successful_capture_status"]]
        failed = [item for item in records if item.data["status"] == "failed"]
        amounts = {(Decimal(item.data["amount"]), item.data["currency"]) for item in successful}
        # Pending followed by success is legitimate; terminal failure versus success is not reconciled here.
        if successful and (failed or len(amounts) > 1):
            capture_conflicts.extend(records)
            add("discrepancies", "capture_identity_conflict",
                f"Records for capture {capture_id} disagree on outcome or captured amount; this capture is excluded from confirmed totals.", records)
            result.disposition = "escalate"
        elif successful:
            chosen = _latest(successful)[0]
            successes.append(chosen)
            add("confirmed_facts", "capture_success",
                f"Provider capture {capture_id} succeeded for {_amount(chosen)}. This establishes capture, not settlement or an absence of later refunds.", successful)
        elif failed:
            add("confirmed_facts", "capture_failed",
                f"Capture {capture_id} is recorded as failed; that does not prove an earlier authorization was reversed.", failed)
        else:
            add("unknowns", "capture_pending",
                f"Capture {capture_id} is pending; a successful capture is not established.", records)
            check()

    active_auth: list[Evidence] = []
    for authorization_id, records in _group(by_kind["Authorization"], "authorization_id").items():
        latest = _latest(records)
        statuses = {item.data["status"] for item in latest}
        if len(statuses) == 1:
            chosen = latest[0]
            add("confirmed_facts", "authorization_observed",
                f"Authorization {authorization_id} is recorded as {chosen.data['status']} for {_amount(chosen)}; an authorization is not a capture.", latest)
            if chosen.data["status"] == ontology["policies"]["active_authorization_status"]:
                active_auth.extend(latest)
        else:
            add("unknowns", "authorization_only",
                f"The current status of authorization {authorization_id} is ambiguous because its records cannot be ordered.", latest)
            check()

    attempts = by_kind["PaymentAttempt"]
    current_attempts = [item for records in _group(attempts, "attempt_id").values() for item in _latest(records)]
    for attempt_id, records in _group(current_attempts, "attempt_id").items():
        states = sorted({item.data["status"] for item in records})
        codes = sorted({item.data["error_code"] for item in records if item.data["error_code"]})
        detail = f"; observed error code(s): {', '.join(codes)}" if codes else ""
        add("confirmed_facts", "attempt_observed",
            f"Attempt {attempt_id} has recorded outcome(s) {', '.join(states)}{detail}. An attempt is not a separate captured charge.", records)

    if successes:
        result.payment_state = "captured"
    elif active_auth and not capture_conflicts:
        result.payment_state = "authorized"
        add("unknowns", "authorization_only",
            "An active authorization is evidenced, but successful capture is not established. Authorization alone is not completed payment.", active_auth + by_kind["Capture"])
        add("next_checks", "authorization_only",
            "Read the provider's current authorization expiry and capture records before describing the payment as completed.", active_auth)
        check()
    elif snapshot is not None and not capture_conflicts:
        status = snapshot.data["provider_status"]
        snapshot_time = _time(snapshot.occurred_at)
        preceding_attempts = bool(current_attempts) and snapshot_time is not None and all(
            _time(item.occurred_at) is not None and _time(item.occurred_at) <= snapshot_time  # type: ignore[operator]
            for item in current_attempts
        )
        complete = snapshot.data["capture_history_complete"]
        if status in ontology["policies"]["terminal_provider_failure_statuses"] and complete:
            result.payment_state = "failed"
            add("confirmed_facts", "provider_canceled",
                "The provider snapshot is canceled and explicitly covers capture history with no successful capture supplied. This is an observed canceled payment, not proof about other payments.", [snapshot])
        elif status == "requires_payment_method" and complete and snapshot.data["attempt_history_complete"] and preceding_attempts and all(
            item.data["status"] == "failed" for item in current_attempts
        ):
            result.payment_state = "failed"
            add("confirmed_facts", "attempt_failure",
                "The current provider snapshot requires a payment method, all supplied attempts failed, and the snapshot explicitly covers attempt and capture history. The observed payment attempt failed; no successful capture appears in that covered history.", [snapshot] + current_attempts)

    if result.payment_state == "unknown":
        add("unknowns", "missing_financial_evidence",
            "Available records do not establish a successful capture, a current authorization, or an explicit complete terminal-failure view. Missing evidence is unknown, not automatically failed.", by_kind["Capture"] + snapshots + attempts + by_kind["ProviderEvent"])
        add("next_checks", "missing_financial_evidence",
            "Read the provider's current payment, authorization, and capture history with its coverage time; do not infer financial state from the source row or event delivery alone.", snapshots + by_kind["ProviderEvent"])
        check()

    if snapshot is not None and successes and snapshot.data["provider_status"] in {"canceled", "requires_payment_method", "requires_capture"}:
        capture_times = [_time(item.occurred_at) for item in successes]
        latest_capture_time = max((value for value in capture_times if value is not None), default=None)
        snapshot_time = _time(snapshot.occurred_at)
        if snapshot_time is None or latest_capture_time is None or snapshot_time >= latest_capture_time:
            add("discrepancies", "provider_snapshot_conflict",
                "Successful capture records and the supplied current provider status do not agree. Preserve the capture evidence and reconcile the provider snapshot rather than treating it as a reversal.", [snapshot] + successes)
            result.disposition = "escalate"

    if len(successes) > 1:
        add("discrepancies", "multiple_captures",
            f"There are {len(successes)} distinct successful capture IDs. This is not explained by repeated attempts or repeated event deliveries; whether the captures are intended requires reconciliation.", successes)
        add("next_checks", "multiple_captures",
            "Ask payment operations to read the provider charge/capture ledger and intended order amount to distinguish intended partial captures from unintended additional captures.", successes)
        result.disposition = "escalate"

    if successes and snapshot is not None:
        currencies = {item.data["currency"] for item in successes}
        expected_currency = snapshot.data["currency"]
        if expected_currency is not None and currencies == {expected_currency}:
            total = sum((Decimal(item.data["amount"]) for item in successes), Decimal(0))
            expected = Decimal(snapshot.data["amount"])
            if total != expected:
                add("discrepancies", "capture_amount_mismatch",
                    f"The distinct successful capture total is {total} {expected_currency}, versus the provider snapshot amount {expected} {expected_currency}. The reason for this difference is not established.", [snapshot] + successes)
                add("next_checks", "capture_amount_mismatch",
                    "Read the intended order amount and provider capture ledger, including any partial-capture policy, to reconcile the amount difference.", [snapshot] + successes)
                if total > expected:
                    result.disposition = "escalate"
                else:
                    check()
        else:
            add("unknowns", "currency_unavailable",
                "Provider expected and captured amounts cannot be reconciled because currencies are missing or differ; no conversion or currency was inferred.", [snapshot] + successes)
            check()

    apps = by_kind["ApplicationStatusObservation"]
    latest_apps = _latest(apps)
    app_statuses = {item.data["status"] for item in latest_apps}
    app_unresolved = False
    for item in apps:
        add("confirmed_facts", "app_observation",
            f"Application observation {item.data['observation_id']} reports {item.data['status']} on {item.data['channel']}.", [item])
    if len(app_statuses) > 1:
        add("unknowns", "app_order_unknown",
            "Conflicting application statuses have equal, missing, or non-comparable timestamps; the latest status cannot be selected from arrival order or record IDs.", latest_apps)
        check()
        app_unresolved = True
    elif latest_apps:
        app = latest_apps[0]
        expected_statuses: dict[str, set[str]] = {
            "captured": {"succeeded"}, "failed": {"failed"},
            "authorized": {"authorized", "pending", "processing"}, "unknown": set(),
        }
        expected_status = expected_statuses[result.payment_state]
        if expected_status and app.data["status"] not in expected_status:
            authoritative = successes if successes else ([snapshot] if snapshot is not None else active_auth)
            times = [_time(item.occurred_at) for item in authoritative]
            reference_time = max((value for value in times if value is not None), default=None)
            app_time = _time(app.occurred_at)
            if app_time is not None and reference_time is not None and all(value is not None for value in times) and app_time > reference_time:
                add("discrepancies", "app_discrepancy",
                    f"A later application observation reports {app.data['status']} while provider evidence establishes {result.payment_state}. The display discrepancy is established; its cause is not.", latest_apps + authoritative)
            elif app_time is not None and reference_time is not None and app_time < reference_time:
                add("unknowns", "app_precedes_financial",
                    "The differing application status predates the financial evidence. A current display discrepancy cannot be established without a newer application observation.", latest_apps + authoritative)
            else:
                add("unknowns", "app_order_unknown",
                    "The differing application status cannot be ordered after the financial evidence because timestamps are tied, absent, or lack comparable timezones.", latest_apps + authoritative)
            app_unresolved = True
            check()
    else:
        add("unknowns", "app_observation",
            "No customer-facing application observation is supplied; the current display cannot be checked.", [])
        check()
        app_unresolved = True
    if app_unresolved:
        add("next_checks", "app_discrepancy",
            "Read a fresh application-status observation and correlate application processing logs with the provider payment/event IDs; do not infer a root cause from the displayed status alone.", latest_apps)

    deliveries = by_kind["WebhookDelivery"]
    failed_deliveries = [item for item in deliveries if item.data["status"] == "failed"]
    for event_id, records in _group(deliveries, "event_id").items():
        distinct_deliveries = _group(records, "delivery_id")
        outcomes = sorted({item.data["status"] for item in records})
        add("confirmed_facts", "delivery_observed",
            f"Event {event_id} has {len(distinct_deliveries)} recorded delivery attempt(s) with outcomes {', '.join(outcomes)}. Delivery outcomes do not reverse or create captures.", records)
        if len(distinct_deliveries) > 1:
            add("confirmed_facts", "duplicate_delivery",
                f"Event {event_id} was delivered or attempted repeatedly under the same event ID. Repeated delivery is not an additional captured charge.", records)
    if failed_deliveries and app_unresolved:
        add("hypotheses", "notification_hypothesis",
            "If the application relies on these notifications, a failed delivery may have contributed to a stale display. Delivery evidence alone does not establish that causal link or a root cause.", failed_deliveries + latest_apps)
        add("next_checks", "notification_hypothesis",
            "Read webhook endpoint responses, subsequent delivery attempts, and application event-processing logs for the same event IDs to test the notification hypothesis.", failed_deliveries)

    events = by_kind["ProviderEvent"]
    if events and not deliveries:
        add("unknowns", "missing_delivery_evidence",
            "Provider events are supplied without webhook delivery records. Notification success or failure is unknown, not inferred from their absence.", events)
    event_representatives = [records[0] for records in _group(events, "event_id").values()]
    unordered: list[Evidence] = []
    reordered: list[Evidence] = []
    for index, first in enumerate(event_representatives):
        for second in event_representatives[index + 1:]:
            a, b = _time(first.occurred_at), _time(second.occurred_at)
            x, y = _time(first.observed_at), _time(second.observed_at)
            if a is None or b is None or x is None or y is None or a == b or x == y:
                unordered.extend([first, second])
            elif (a < b) != (x < y):
                reordered.extend([first, second])
    if reordered:
        add("confirmed_facts", "out_of_order_events",
            "Some provider events arrived in an order different from their business-event occurrence times. Arrival order was not used to overwrite financial state.", reordered)
    if unordered:
        add("unknowns", "event_order_unknown",
            "Some provider events have tied or non-comparable timestamps; their relative business or arrival order is not established.", unordered)

    lookup = {item.id: item for item in evidence}
    for reference in missing:
        add("unknowns", "missing_reference",
            f"Record {reference.evidence_id} references {reference.target_kind} {reference.target_id}, which is not supplied. Its absence does not prove failure.", [lookup[reference.evidence_id]])
        check()
    if missing:
        add("next_checks", "missing_reference",
            "Read the missing related provider records by the supplied object IDs and verify their payment linkage.", [lookup[reference.evidence_id] for reference in missing])

    inverted = [item for item in evidence if _time(item.occurred_at) is not None and _time(item.observed_at) is not None
                and _time(item.observed_at) < _time(item.occurred_at)]  # type: ignore[operator]
    if inverted:
        add("unknowns", "clock_inversion",
            "Some records were observed before their stated occurrence time. Clock consistency needs checking; these times do not establish a causal sequence.", inverted)
        check()
    if result.disposition == "escalate" and not result.next_checks:
        add("next_checks", "provider_snapshot_conflict",
            "Ask payment operations to read authoritative current provider records and reconcile conflicting object identities and amounts.", captures.get(next(iter(captures), ""), []) + snapshots)
    if result.disposition == "no_escalation":
        add("confirmed_facts", "aligned_observations",
            "The supplied financial and latest application observations are sufficient and aligned for this symptom. No operational escalation is indicated by these records; this is not a guarantee about omitted systems or later activity.", successes + latest_apps + ([snapshot] if snapshot is not None else []))
        add("next_checks", "aligned_observations",
            "Explain the evidenced outcome to support. No additional investigation is required for the supplied symptom unless new contradictory evidence appears.", successes + latest_apps + ([snapshot] if snapshot is not None else []))
    result.applied_rules.sort()
    return Analysis.model_validate(result.model_dump())
