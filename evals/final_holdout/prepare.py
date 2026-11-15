"""Fresh verifier-authored incident observations; no production analyzer or dev fixtures.

Written before executing analyzer/API. Expectations live separately and are never
passed to the database writer or runtime tools. Explicit wholly synthetic inputs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.domain.models import Evidence, Payment
from src.storage.repository import create_database

IDS = ["pay_9e52d7a1", "pay_28c1f0b6", "pay_76d9a305", "pay_5f0ab8c2", "pay_14b6e9d0"]


def build() -> tuple[list[Payment], list[Evidence]]:
    payments: list[Payment] = []
    evidence: list[Evidence] = []
    symptoms = [
        "The customer sees a receipt but several activity entries. Can we explain what was paid and whether support needs to act?",
        "The customer is asking how much of their order has been paid. The receipt screen looks complete. What can we confirm?",
        "Two support screenshots disagree and the notification timestamps look odd. Which payment state is supported?",
        "The checkout says failed and a notification was delivered. Can we tell the customer definitively that no money was captured?",
        "The customer saw a hold earlier and now sees failed. What is the current supported outcome and does this need escalation?",
    ]
    for i, (pid, symptom) in enumerate(zip(IDS, symptoms), 1):
        payments.append(Payment(id=pid, symptom=symptom, source_transaction_id=f"synthetic-final-{i}",
                                original={"origin": "Fresh final-verifier synthetic observations"},
                                warnings=["Wholly synthetic verifier case; no real payment or bank connection."]))

    def add(i: int, suffix: str, kind: str, data: dict, occurred: str | None,
            observed: str | None = None) -> None:
        evidence.append(Evidence(id=f"fv{i}-{suffix}", payment_id=IDS[i-1], kind=kind,
                                 source="Synthetic provider export" if kind != "ApplicationStatusObservation" else "Synthetic support screen observation",
                                 synthetic=True, occurred_at=occurred, observed_at=observed,
                                 data=data))

    def at(minute: int) -> str:
        return f"2026-10-24T10:{minute:02d}:00Z"

    def snap(i: int, status: str, amount: str, currency: str, complete: bool, minute: int) -> None:
        add(i, "snapshot", "Payment", {"record_type": "provider_snapshot", "provider_status": status,
            "amount": amount, "currency": currency, "capture_history_complete": complete,
            "attempt_history_complete": complete}, at(minute), at(minute+1))

    def app(i: int, suffix: str, status: str, time: str | None, observed: str | None = None) -> None:
        add(i, suffix, "ApplicationStatusObservation", {"observation_id": f"screen-{i}-{suffix}",
            "status": status, "channel": "support screenshot"}, time, observed)

    # F01: repeated observations of one capture and one attempt; recovered webhook.
    snap(1, "succeeded", "48.25", "GBP", True, 20)
    add(1, "try-old", "PaymentAttempt", {"attempt_id": "try-f1", "status": "processing"}, at(1), at(2))
    add(1, "try-new", "PaymentAttempt", {"attempt_id": "try-f1", "status": "succeeded"}, at(6), at(7))
    add(1, "auth", "Authorization", {"authorization_id": "hold-f1", "attempt_id": "try-f1", "status": "authorized", "amount": "60.00", "currency": "GBP"}, at(3), at(4))
    for suffix, seen in [("capture-a", 8), ("capture-b", 12)]:
        add(1, suffix, "Capture", {"capture_id": "cap-f1", "attempt_id": "try-f1", "authorization_id": "hold-f1", "status": "succeeded", "amount": "48.25", "currency": "GBP"}, at(6), at(seen))
    add(1, "event", "ProviderEvent", {"event_id": "event-f1", "event_type": "charge.captured", "subject_kind": "Capture", "subject_id": "cap-f1"}, at(6), at(7))
    add(1, "delivery-a", "WebhookDelivery", {"delivery_id": "delivery-f1-a", "event_id": "event-f1", "status": "failed", "http_status": 503, "attempt_number": 1}, at(8), at(8))
    add(1, "delivery-b", "WebhookDelivery", {"delivery_id": "delivery-f1-b", "event_id": "event-f1", "status": "delivered", "http_status": 204, "attempt_number": 2}, at(10), at(10))
    app(1, "screen-old", "pending", at(4), at(5))
    app(1, "screen-new", "succeeded", at(22), at(23))

    # F02: 40 EUR captured and 60 EUR merely pending; full 100 EUR not established.
    snap(2, "processing", "100.00", "EUR", True, 20)
    add(2, "try", "PaymentAttempt", {"attempt_id": "try-f2", "status": "processing"}, at(1), at(2))
    add(2, "auth", "Authorization", {"authorization_id": "hold-f2", "attempt_id": "try-f2", "status": "authorized", "amount": "100.00", "currency": "EUR"}, at(3), at(4))
    add(2, "capture-a", "Capture", {"capture_id": "cap-f2-a", "authorization_id": "hold-f2", "attempt_id": "try-f2", "status": "succeeded", "amount": "40.00", "currency": "EUR"}, at(5), at(6))
    add(2, "capture-b", "Capture", {"capture_id": "cap-f2-b", "authorization_id": "hold-f2", "attempt_id": "try-f2", "status": "pending", "amount": "60.00", "currency": "EUR"}, at(10), at(11))
    app(2, "screen", "succeeded", at(22), at(23))

    # F03: incomplete application ordering + tied business clocks with ordered receipt.
    snap(3, "succeeded", "31.75", "CAD", True, 20)
    add(3, "capture", "Capture", {"capture_id": "cap-f3", "status": "succeeded", "amount": "31.75", "currency": "CAD"}, at(10), at(11))
    app(3, "screen-a", "succeeded", at(22), at(23))
    app(3, "screen-b", "failed", "2026-10-24T10:25:00", at(26))
    add(3, "event-a", "ProviderEvent", {"event_id": "event-f3-a", "event_type": "payment_intent.payment_failed", "subject_kind": "Payment", "subject_id": IDS[2]}, at(10), at(12))
    add(3, "event-b", "ProviderEvent", {"event_id": "event-f3-b", "event_type": "payment_intent.succeeded", "subject_kind": "Payment", "subject_id": IDS[2]}, at(10), at(14))
    for suffix, evt, minute in [("a", "a", 12), ("b", "b", 14)]:
        add(3, f"delivery-{suffix}", "WebhookDelivery", {"delivery_id": f"delivery-f3-{suffix}", "event_id": f"event-f3-{evt}", "status": "delivered", "http_status": 200, "attempt_number": 1}, at(minute), at(minute))

    # F04: failed attempt + delivered failure notification is not complete capture history.
    snap(4, "requires_payment_method", "72.10", "USD", False, 20)
    add(4, "try", "PaymentAttempt", {"attempt_id": "try-f4", "status": "failed", "error_code": "card_declined"}, at(8), at(9))
    add(4, "auth", "Authorization", {"authorization_id": "hold-f4", "attempt_id": "try-f4", "status": "declined", "amount": "72.10", "currency": "USD"}, at(8), at(9))
    add(4, "event", "ProviderEvent", {"event_id": "event-f4", "event_type": "payment_intent.payment_failed", "subject_kind": "Payment", "subject_id": IDS[3]}, at(8), at(10))
    add(4, "delivery", "WebhookDelivery", {"delivery_id": "delivery-f4", "event_id": "event-f4", "status": "delivered", "http_status": 200, "attempt_number": 1}, at(10), at(10))
    app(4, "screen", "failed", at(22), at(23))

    # F05: canceled with complete no-capture history, ordered hold expiry, failed screen.
    snap(5, "canceled", "86.00", "USD", True, 20)
    add(5, "try", "PaymentAttempt", {"attempt_id": "try-f5", "status": "failed", "error_code": "authentication_required"}, at(15), at(16))
    for suffix, status, minute in [("auth-a", "authorized", 3), ("auth-b", "expired", 14)]:
        add(5, suffix, "Authorization", {"authorization_id": "hold-f5", "attempt_id": "try-f5", "status": status, "amount": "86.00", "currency": "USD"}, at(minute), at(minute+1))
    app(5, "screen-old", "authorized", at(4), at(5))
    app(5, "screen-new", "failed", at(22), at(23))
    return payments, evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ps, es = build()
    create_database(args.output, ps, es)
    print(f"Prepared {len(ps)} incidents and {len(es)} observations at {args.output}")
