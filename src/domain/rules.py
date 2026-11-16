"""Deterministic, evidence-scoped checks; no guessed root causes or financial actions."""
from __future__ import annotations

import re
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
    known = [value for value in times if value is not None]
    if not known:
        return items
    latest = max(known)
    # An untimed record may be latest, but cannot make an older known record latest.
    return [item for item in items if _time(item.occurred_at) in (None, latest)]


def _group(items: list[Evidence], field: str) -> dict[str, list[Evidence]]:
    result: dict[str, list[Evidence]] = defaultdict(list)
    for item in items:
        result[item.data[field]].append(item)
    return dict(result)


def _amount(item: Evidence) -> str:
    currency = item.data["currency"] or "(currency unknown)"
    return f"{item.data['amount']} {currency}"


def _capture_coverage_before(records: list[Evidence], snapshot: Evidence | None,
                             at: datetime | None) -> list[Evidence]:
    """Proof that distinct known successes covered the supplied amount before an observation."""
    if snapshot is None or at is None or snapshot.data["currency"] is None:
        return []
    total = Decimal(0)
    refs: list[Evidence] = []
    for observations in _group(records, "capture_id").values():
        prior = [item for item in observations if item.data["currency"] == snapshot.data["currency"]
                 and (time := _time(item.occurred_at)) is not None and time < at]
        if prior:
            total += Decimal(prior[0].data["amount"])
            refs.extend(prior)
    return refs + [snapshot] if total >= Decimal(snapshot.data["amount"]) else []


def _asks_about_current_channel(question: str, channel: str, available_channels: list[str]) -> bool:
    """Explicit channel names outrank generic display hints within each clause."""
    def normalized(value: str) -> str:
        return re.sub(r"[\s_-]+", " ", value.casefold()).strip()

    channel_name = normalized(channel)
    channel_names = {normalized(name) for name in available_channels} - {""}
    for clause in re.split(r"[.!?;\n]", question.casefold()):
        clause = normalized(clause)
        selected = {name for name in channel_names
                    if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", clause)}
        mentions_view = channel_name in selected if selected else bool(re.search(r"\b(?:screens?|displays?)\b", clause))
        historical = re.search(r"\b(?:earlier|previous(?:ly)?|old|historical|before)\b", clause)
        current = re.search(r"\b(?:still|current(?:ly)?|now|recover(?:ed|y)?|refresh(?:ed)?)\b", clause)
        if mentions_view and (current or not historical):
            return True
    return False


def analyze(payment: Payment, evidence: list[Evidence], question: str | None = None) -> Analysis:
    """Inspect one immutable snapshot; only authoritative records determine state.

    `captured` means a successful capture is evidenced, not settled, refunded, or
    reconciled. `failed` requires an explicit complete provider view. Unknowns
    about original source quality alone do not trigger operational escalation.
    Question hints add scoped checks; financial alignment never closes arbitrary inquiries.
    """
    inquiry = payment.symptom if question is None else question
    notification_inquiry = bool(re.search(
        r"\b(?:web[ -]?hooks?|notifications?|callbacks?|deliver(?:y|ies|ed)|endpoints?)\b",
        inquiry, re.IGNORECASE,
    ))
    processing_inquiry = notification_inquiry and bool(re.search(
        r"\b(?:process(?:ed|ing|es)?|handl(?:e[ds]?|ers?|ing)|consum(?:e[ds]?|ers?|ing)|applied)\b",
        inquiry, re.IGNORECASE,
    ))
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
            # An equivalent untimed copy must not discard established coverage time.
            snapshot = next((item for item in snapshots if _time(item.occurred_at) is not None), snapshots[0])
        else:
            add("discrepancies", "provider_snapshot_conflict",
                "The latest provider snapshot cannot be selected unambiguously; supplied snapshots disagree.", snapshots)
            result.disposition = "escalate"
    if source:
        add("confirmed_facts", "source_context",
            "The original synthetic transaction row is coarse source context, not authorization, capture, or webhook history.", source)
    for item in source:
        unspecified = ["currency"] if item.data["currency"] is None else []
        if item.occurred_at is None:
            unspecified.append("timestamp")
        elif _time(item.occurred_at) is None:
            unspecified.append("timezone")
        if unspecified:
            add("unknowns", "source_context",
                f"The original source record does not specify {' or '.join(unspecified)}; no missing value was inferred.", [item])
    # Free-text warnings are preserved verbatim in the workspace, not promoted to diagnoses.

    captures = _group(by_kind["Capture"], "capture_id")
    successes: list[Evidence] = []
    successful_observations: list[Evidence] = []
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
            # Count an identity once, but retain every observation for chronology.
            chosen = successful[0]
            successes.append(chosen)
            successful_observations.extend(successful)
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
    current_authorizations: list[Evidence] = []
    for authorization_id, records in _group(by_kind["Authorization"], "authorization_id").items():
        latest = _latest(records)
        current_authorizations.extend(latest)
        statuses = {item.data["status"] for item in latest}
        amounts = {(Decimal(item.data["amount"]), item.data["currency"]) for item in latest}
        if len(amounts) > 1:
            add("unknowns", "authorization_amount_conflict",
                f"The current amount or currency of authorization {authorization_id} is uncertain: its unordered records disagree. No exact held amount can be selected from these records.", latest)
            add("next_checks", "authorization_amount_conflict",
                "Ask payment operations to read current authoritative authorization records and reconcile the conflicting amount or currency before quoting an exact hold amount.", latest)
            result.disposition = "escalate"
        if len(statuses) == 1:
            chosen = latest[0]
            amount_detail = f" for {_amount(chosen)}" if len(amounts) == 1 else " (amount unresolved)"
            add("confirmed_facts", "authorization_observed",
                f"Authorization {authorization_id} is recorded as {chosen.data['status']}{amount_detail}; an authorization is not a capture.", latest)
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
        financial_activity = current_attempts + current_authorizations + by_kind["Capture"] + by_kind["ProviderEvent"]
        # Tied closed-state observations are compatible; tied ongoing activity is not ordered.
        uncovered = [item for item in financial_activity
                     if snapshot_time is None or (time := _time(item.occurred_at)) is None
                     or time > snapshot_time
                     or (time == snapshot_time
                         and item.data.get("status") not in {"failed", "declined", "expired", "voided"}
                         and item.data.get("event_type") not in {"payment_intent.canceled", "payment_intent.payment_failed"})]
        terminal_statuses = set(ontology["policies"]["terminal_provider_failure_statuses"]) | {"requires_payment_method"}
        if status in terminal_statuses and complete and uncovered:
            add("unknowns", "provider_snapshot_coverage_gap",
                "The provider snapshot cannot establish a current terminal failure: supplied financial activity is later, tied, or cannot be ordered against its coverage time.", [snapshot] + uncovered)
            add("next_checks", "provider_snapshot_coverage_gap",
                "Read a fresh provider snapshot and its covered attempt, authorization, capture, and event history before resolving the payment outcome.", [snapshot] + uncovered)
            check()
        elif status in ontology["policies"]["terminal_provider_failure_statuses"] and complete:
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
        snapshot_time = _time(snapshot.occurred_at)
        conflicting_captures = [item for item in successful_observations
                                if snapshot_time is not None and (time := _time(item.occurred_at)) is not None
                                and time < snapshot_time]
        if snapshot.data["provider_status"] == "requires_capture":
            # Requiring another capture is compatible with only a partial amount captured so far.
            prior_ids = {item.data["capture_id"] for item in conflicting_captures}
            prior = [item for item in successes if item.data["capture_id"] in prior_ids]
            currency = snapshot.data["currency"]
            if (currency is None or any(item.data["currency"] != currency for item in prior)
                    or sum((Decimal(item.data["amount"]) for item in prior), Decimal(0)) < Decimal(snapshot.data["amount"])):
                conflicting_captures = []
        if conflicting_captures:
            add("discrepancies", "provider_snapshot_conflict",
                "Successful capture records and the supplied current provider status do not agree. Preserve the capture evidence and reconcile the provider snapshot rather than treating it as a reversal.", [snapshot] + conflicting_captures)
            result.disposition = "escalate"
        else:
            unordered_captures = [item for item in successful_observations
                                  if snapshot_time is None or _time(item.occurred_at) in (None, snapshot_time)]
            if unordered_captures:
                add("unknowns", "provider_snapshot_order_unknown",
                    "The provider snapshot and some capture observations cannot be ordered. Missing timing does not establish a contradiction or reverse the recorded capture.", [snapshot] + unordered_captures)
                add("next_checks", "provider_snapshot_order_unknown",
                    "Read comparable provider snapshot and capture timestamps before deciding whether their statuses conflict.", [snapshot] + unordered_captures)
                check()

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
            add("next_checks", "currency_unavailable",
                "Read the provider's expected amount and capture currencies before deciding whether the expected amount has been captured; do not infer a conversion.", [snapshot] + successes)
            check()

    apps = by_kind["ApplicationStatusObservation"]
    channels = {channel: _latest(records) for channel, records in _group(apps, "channel").items()}
    latest_apps = [item for records in channels.values() for item in records]
    app_unresolved = False
    for item in apps:
        add("confirmed_facts", "app_observation",
            f"Application observation {item.data['observation_id']} reports {item.data['status']} on {item.data['channel']}.", [item])
    expected_statuses: dict[str, set[str]] = {
        "captured": {"succeeded"}, "failed": {"failed"},
        "authorized": {"authorized", "pending", "processing"}, "unknown": set(),
    }
    expected_status = expected_statuses[result.payment_state]
    authoritative = successful_observations if successes else ([snapshot] if snapshot is not None else active_auth)
    times = [_time(item.occurred_at) for item in authoritative]
    known_times = [value for value in times if value is not None]
    # Captured funds can contradict a failed display without proving whole-payment completion.
    reference_time = (min(known_times) if successes else max(known_times)) if known_times else None
    reference_records = [item for item in authoritative if _time(item.occurred_at) == reference_time] if successes else authoritative
    matching_apps = [item for item in latest_apps if item.data["status"] in expected_status]
    matching_later_apps = [item for item in matching_apps if reference_time is not None
                           and (time := _time(item.occurred_at)) is not None and time > reference_time]
    for channel, channel_apps in channels.items():
        if len({item.data["status"] for item in channel_apps}) > 1:
            add("unknowns", "app_order_unknown",
                f"Conflicting application statuses on {channel} have equal, missing, or non-comparable timestamps; that channel's latest status cannot be selected from arrival order or record IDs.", channel_apps)
            check()
            app_unresolved = True
        for status, status_apps in _group(channel_apps, "status").items():
            if not expected_status or status in expected_status:
                continue
            app_times = [_time(item.occurred_at) for item in status_apps]
            later_apps = [item for item in status_apps if reference_time is not None
                          and (time := _time(item.occurred_at)) is not None and time > reference_time]
            earlier_apps = (reference_time is not None and all(value is not None for value in times)
                            and all(time is not None and time < reference_time for time in app_times))
            comparison_records = reference_records
            if successes and status in {"pending", "processing", "authorized", "requires_action"}:
                coverage = [(item, _capture_coverage_before(successful_observations, snapshot, _time(item.occurred_at)))
                            for item in status_apps]
                later_apps = [item for item, refs in coverage if refs]
                comparison_records = [record for _, refs in coverage for record in refs]
                unconfirmed = [item for item, refs in coverage if not refs]
                if unconfirmed:
                    completion_refs = unconfirmed + authoritative + ([snapshot] if snapshot is not None else [])
                    add("unknowns", "app_completion_unconfirmed",
                        f"The {status} application observation on {channel} is not proved to follow capture of the full supplied expected amount. A recorded capture may be partial; it is not by itself whole-payment completion.", completion_refs)
                    if not (earlier_apps and matching_later_apps and not _asks_about_current_channel(inquiry, channel, list(channels))):
                        add("next_checks", "app_completion_unconfirmed",
                            f"Read provider amount coverage and the capture timeline, then a fresh {channel} observation, before treating an intermediate application status as a discrepancy.", completion_refs)
                        check()
                if not later_apps:
                    continue
            if later_apps and (successes or all(value is not None for value in times)):
                add("discrepancies", "app_discrepancy",
                    f"A later application observation reports {status} on {channel} while provider evidence establishes {result.payment_state}. The display discrepancy is established; its cause is not.", later_apps + comparison_records)
                untimed = [item for item in status_apps if _time(item.occurred_at) is None]
                if untimed:
                    add("unknowns", "app_order_unknown",
                        f"Additional application observations on {channel} lack comparable timestamps; their ordering remains unknown and does not erase the separately evidenced later display discrepancy.", untimed)
            elif earlier_apps:
                add("unknowns", "app_precedes_financial",
                    f"The differing application status on {channel} predates the financial evidence. That channel's current display cannot be established without a newer observation.", status_apps + authoritative)
                if matching_later_apps and not _asks_about_current_channel(inquiry, channel, list(channels)):
                    # A historical display gap need not block an evidenced financial answer.
                    continue
            else:
                add("unknowns", "app_order_unknown",
                    f"The differing application status on {channel} cannot be ordered after the financial evidence because timestamps are tied, absent, or lack comparable timezones.", status_apps + authoritative)
            app_unresolved = True
            check()
    if not latest_apps:
        add("unknowns", "app_observation",
            "No customer-facing application observation is supplied; the current display cannot be checked.", [])
        check()
        app_unresolved = True
    if app_unresolved:
        add("next_checks", "app_discrepancy",
            "Read a fresh application-status observation for each unresolved channel and correlate application processing logs with the provider payment/event IDs; another channel's success does not prove recovery. Do not infer a root cause from the displayed status alone.", latest_apps)

    deliveries = by_kind["WebhookDelivery"]
    deliveries_by_event = _group(deliveries, "event_id")
    failed_deliveries = [item for item in deliveries if item.data["status"] == "failed"]
    for event_id, records in deliveries_by_event.items():
        distinct_deliveries = _group(records, "delivery_id")
        outcomes = sorted({item.data["status"] for item in records})
        add("confirmed_facts", "delivery_observed",
            f"Event {event_id} has {len(distinct_deliveries)} recorded delivery attempt(s) with outcomes {', '.join(outcomes)}. Delivery outcomes do not reverse or create captures.", records)
        if len(distinct_deliveries) > 1:
            add("confirmed_facts", "duplicate_delivery",
                f"Event {event_id} was delivered or attempted repeatedly under the same event ID. Repeated delivery is not an additional captured charge.", records)
        failed_for_event = [item for item in records if item.data["status"] == "failed"]
        failure_times = [_time(item.occurred_at) for item in failed_for_event]
        recovered = any(
            (time := _time(item.occurred_at)) is not None
            and all(failed_time is not None and time > failed_time for failed_time in failure_times)
            for item in records if item.data["status"] == "delivered"
        )
        if failed_for_event and not recovered:
            add("unknowns", "notification_unresolved",
                f"Failed webhook deliveries for event {event_id} have no provably later successful delivery in the supplied records. Notification resolution is unconfirmed; this does not reverse captured funds.", records)
            add("next_checks", "notification_unresolved",
                "Read webhook endpoint responses and subsequent delivery attempts for this event, then inspect event-processing logs. Do not resend notifications or change payment state from this investigator.", failed_for_event)
            check()
        elif notification_inquiry and not any(item.data["status"] == "delivered" for item in records):
            add("unknowns", "notification_unresolved",
                f"The supplied delivery attempts for event {event_id} do not establish successful notification delivery. Financial capture does not answer this delivery inquiry.", records)
            add("next_checks", "notification_unresolved",
                "Read the current webhook endpoint response and delivery-attempt records for this event before answering the delivery inquiry; do not resend the notification.", records)
            check()
    if failed_deliveries and app_unresolved:
        add("hypotheses", "notification_hypothesis",
            "If the application relies on these notifications, a failed delivery may have contributed to a stale display. Delivery evidence alone does not establish that causal link or a root cause.", failed_deliveries + latest_apps)
        add("next_checks", "notification_hypothesis",
            "Read webhook endpoint responses, subsequent delivery attempts, and application event-processing logs for the same event IDs to test the notification hypothesis.", failed_deliveries)

    events = by_kind["ProviderEvent"]
    uncovered_events = [item for item in events if item.data["event_id"] not in deliveries_by_event]
    if uncovered_events:
        add("unknowns", "missing_delivery_evidence",
            "Some provider events have no corresponding webhook delivery records. Notification success or failure for those events is unknown, not inferred from their absence.", uncovered_events)
    if notification_inquiry and (uncovered_events or not events and not deliveries):
        if not uncovered_events:
            add("unknowns", "missing_delivery_evidence",
                "No provider event or webhook delivery records are supplied to answer this notification inquiry. Payment evidence alone does not establish delivery.", [])
        add("next_checks", "missing_delivery_evidence",
            "Read the provider event and webhook delivery records, including endpoint responses, for each event without delivery evidence before answering the notification inquiry. Missing records do not mean delivery failed.", uncovered_events)
        check()
    if processing_inquiry:
        add("unknowns", "notification_processing_unknown",
            "These records do not establish whether the application processed the notification. A successful delivery response is not proof of downstream processing.", events + deliveries)
        add("next_checks", "notification_processing_unknown",
            "Read application handler or consumer logs correlated to the provider event IDs before answering the notification-processing inquiry.", events + deliveries)
        check()
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
            "The supplied financial evidence and matching application observations support a consistent financial outcome without operational escalation. This does not establish recovery of every application channel, notification delivery, downstream processing, settlement, or resolution of every customer question.", successes + matching_apps + ([snapshot] if snapshot is not None else []))
        add("next_checks", "aligned_observations",
            "Explain the evidenced financial and application outcome to support. Review the customer's remaining question and any evidence gaps separately; do not treat financial alignment as proof that the inquiry is fully resolved.", successes + matching_apps + ([snapshot] if snapshot is not None else []))
    result.applied_rules.sort()
    return Analysis.model_validate(result.model_dump())
