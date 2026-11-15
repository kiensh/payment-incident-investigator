"""Independent observation fixtures, authored before any candidate invocation.

Run from the repository root with:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m evals.holdout.prepare \
    --database artifacts/independent-domain-holdout.sqlite

This writer imports only observable schemas and the database writer, never the
production analyzer, scenario generator, development cases, or answer keys.
All records are new synthetic observations; no original wallet history is implied.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.domain.models import Evidence, Payment
from src.storage.repository import create_database

ROOT = Path(__file__).resolve().parents[2]


def observations() -> tuple[list[Payment], list[Evidence]]:
    payments: list[Payment] = []
    evidence: list[Evidence] = []

    def payment(n: int, symptom: str, original_status: str = "Pending") -> str:
        pid = f"pay_h{n:02d}_7c9a"
        payments.append(Payment(
            id=pid, symptom=symptom, source_transaction_id=f"syn-row-{n:02d}",
            original={"transaction_id": f"syn-row-{n:02d}", "status": original_status,
                      "payment_method": "Credit Card", "currency": None},
            warnings=["Independent synthetic fixture; original currency is unspecified, not repaired."],
        ))
        return pid

    def row(n: int, suffix: str, kind: str, minute: str | None, data: dict,
            observed: str | None = None) -> None:
        def clock(value: str | None) -> str | None:
            return f"2026-02-{n:02d}T{value}Z" if value else None
        evidence.append(Evidence(
            id=f"h{n:02d}_{suffix}", payment_id=f"pay_h{n:02d}_7c9a", kind=kind,
            source="independent synthetic observation stream v1", synthetic=True,
            occurred_at=clock(minute), observed_at=clock(observed or minute), data=data,
        ))

    def snapshot(n: int, suffix: str, time: str, amount: str, status: str,
                 complete: bool = True, currency: str | None = "USD") -> None:
        row(n, suffix, "Payment", time, dict(record_type="provider_snapshot", amount=amount,
            currency=currency, provider_status=status, capture_history_complete=complete,
            attempt_history_complete=complete))

    def attempt(n: int, suffix: str, time: str, aid: str, status: str, error: str | None = None) -> None:
        row(n, suffix, "PaymentAttempt", time, dict(attempt_id=aid, status=status, error_code=error))

    def capture(n: int, suffix: str, time: str, cid: str, amount: str,
                status: str = "succeeded", currency: str | None = "USD", aid: str | None = None) -> None:
        row(n, suffix, "Capture", time, dict(capture_id=cid, amount=amount, currency=currency,
            status=status, attempt_id=aid))

    def auth(n: int, suffix: str, time: str, aid: str, amount: str, status: str,
             attempt_id: str | None = None) -> None:
        row(n, suffix, "Authorization", time, dict(authorization_id=aid, amount=amount,
            currency="USD", status=status, attempt_id=attempt_id))

    def app(n: int, suffix: str, time: str | None, status: str, channel: str) -> None:
        row(n, suffix, "ApplicationStatusObservation", time,
            dict(observation_id=f"ui-{n:02d}-{suffix}", status=status, channel=channel))

    def event(n: int, suffix: str, time: str, eid: str, event_type: str,
              observed: str, subject_kind: str = "Payment", subject_id: str | None = None) -> None:
        row(n, suffix, "ProviderEvent", time,
            dict(event_id=eid, event_type=event_type, subject_kind=subject_kind,
                 subject_id=subject_id or f"pay_h{n:02d}_7c9a"), observed)

    def delivery(n: int, suffix: str, time: str, eid: str, status: str, http: int, number: int) -> None:
        row(n, suffix, "WebhookDelivery", time, dict(delivery_id=f"delivery-{n:02d}-{suffix}",
            event_id=eid, status=status, http_status=http, attempt_number=number))

    payment(1, "The customer pressed pay several times and now sees a receipt. How many captured payments are evidenced?", "Failed")
    for index, error in enumerate(["card_declined", "authentication_required", "processing_error"], 1):
        attempt(1, f"a{index}", f"08:0{index}:00", f"attempt-01-{index}", "failed", error)
    attempt(1, "a4a", "08:04:00", "attempt-01-4", "processing")
    attempt(1, "a4b", "08:05:00", "attempt-01-4", "succeeded")
    capture(1, "c1a", "08:04:30", "capture-01-a", "187.43", "pending", aid="attempt-01-4")
    capture(1, "c1b", "08:05:00", "capture-01-a", "187.43", aid="attempt-01-4")
    capture(1, "c1c", "08:05:10", "capture-01-a", "187.430", aid="attempt-01-4")
    snapshot(1, "p1", "08:06:00", "187.43", "succeeded")
    event(1, "e1", "08:05:00", "event-01-a", "payment_intent.succeeded", "08:05:20")
    delivery(1, "d1", "08:05:20", "event-01-a", "failed", 503, 1)
    delivery(1, "d2", "08:06:20", "event-01-a", "delivered", 204, 2)
    delivery(1, "d3", "08:07:00", "event-01-a", "delivered", 200, 3)
    app(1, "u1", "08:02:00", "failed", "checkout")
    app(1, "u2", "08:08:00", "succeeded", "receipt")

    payment(2, "The customer has two decline messages and no receipt. Can support explain the outcome without opening an engineering incident?", "Successful")
    attempt(2, "a1", "11:00:00", "attempt-02-a", "failed", "insufficient_funds")
    auth(2, "z1", "11:00:05", "authorization-02-a", "29.85", "declined", "attempt-02-a")
    attempt(2, "a2", "11:03:00", "attempt-02-b", "failed", "card_declined")
    auth(2, "z2", "11:03:05", "authorization-02-b", "29.85", "declined", "attempt-02-b")
    snapshot(2, "p1", "11:05:00", "29.85", "requires_payment_method")
    event(2, "e1", "11:03:00", "event-02-a", "payment_intent.payment_failed", "11:04:00")
    delivery(2, "d1", "11:04:00", "event-02-a", "delivered", 200, 1)
    app(2, "u1", "11:06:00", "failed", "checkout")

    payment(3, "The customer completed the bank challenge and the order screen says paid. Can we confirm funds were captured?")
    attempt(3, "a1", "10:00:00", "attempt-03-a", "requires_action")
    attempt(3, "a2", "10:02:00", "attempt-03-a", "succeeded")
    auth(3, "z1", "10:02:00", "authorization-03-a", "73.20", "authorized", "attempt-03-a")
    capture(3, "c1", "10:03:00", "capture-03-a", "73.20", "pending", aid="attempt-03-a")
    snapshot(3, "p1", "10:04:00", "73.20", "requires_capture", False)
    app(3, "u1", "10:05:00", "succeeded", "order-page")

    payment(4, "The receipt page still says failed and support received notifications in an odd sequence. What can we establish?")
    attempt(4, "a1", "14:00:00", "attempt-04-a", "failed", "authentication_required")
    attempt(4, "a2", "14:02:00", "attempt-04-b", "succeeded")
    capture(4, "c1", "14:03:00", "capture-04-a", "61.08", aid="attempt-04-b")
    snapshot(4, "p1", "14:04:00", "61.08", "succeeded")
    event(4, "e1", "14:00:00", "event-04-a", "payment_intent.payment_failed", "14:07:00")
    event(4, "e2", "14:03:00", "event-04-b", "payment_intent.succeeded", "14:03:20")
    delivery(4, "d1", "14:07:00", "event-04-a", "delivered", 200, 1)
    delivery(4, "d2", "14:03:20", "event-04-b", "failed", 504, 1)
    app(4, "u1", "14:08:00", "failed", "receipt")

    payment(5, "The order screen says complete but finance cannot find the underlying record. Is completion proven?", "Failed")
    snapshot(5, "p1", "16:05:00", "204.99", "succeeded", False)
    event(5, "e1", "16:04:00", "event-05-a", "charge.captured", "16:04:10", "Capture", "capture-05-a")
    delivery(5, "d1", "16:04:10", "event-05-a", "delivered", 202, 1)
    app(5, "u1", "16:06:00", "succeeded", "order-page")

    payment(6, "The customer sees two entries associated with one order. Is that just repeated messaging or does operations need to reconcile them?")
    auth(6, "z1", "09:00:00", "authorization-06-a", "20.35", "authorized")
    capture(6, "c1", "09:05:00", "capture-06-a", "8.20")
    capture(6, "c2", "09:09:00", "capture-06-b", "12.15")
    snapshot(6, "p1", "09:03:00", "20.35", "requires_capture")
    snapshot(6, "p2", "09:10:00", "20.35", "succeeded")
    app(6, "u1", "09:11:00", "succeeded", "order-page")

    payment(7, "Two finance exports disagree for this order. Can we tell support the captured amount yet?")
    capture(7, "c1", "12:00:00", "capture-07-a", "44.10", currency="USD")
    capture(7, "c2", "12:00:00", "capture-07-a", "44.10", currency="EUR")
    snapshot(7, "p1", "12:02:00", "44.10", "succeeded")
    app(7, "u1", "12:03:00", "succeeded", "order-page")

    payment(8, "The customer is asking how much is held on their card while the order waits. Can we state an exact hold amount?")
    auth(8, "z1", "13:00:00", "authorization-08-a", "90.00", "authorized")
    auth(8, "z2", "13:00:00", "authorization-08-a", "120.00", "authorized")
    snapshot(8, "p1", "13:01:00", "120.00", "requires_capture", False)
    app(8, "u1", "13:02:00", "authorized", "order-page")

    payment(9, "Several status exports say failed, one export has no timestamp, and the customer still sees failed. Is the display consistent with payment evidence?")
    capture(9, "c1", "09:05:00", "capture-09-a", "18.66")
    snapshot(9, "p1", "09:06:00", "18.66", "succeeded")
    app(9, "u1", "09:00:00", "failed", "status-export-a")
    app(9, "u2", None, "failed", "status-export-b")
    app(9, "u3", "09:10:00", "failed", "checkout")

    payment(10, "The receipt looks correct, but our support webhook still returns errors on every delivery. Is this notification issue resolved, and what is safe to check next?")
    capture(10, "c1", "17:00:00", "capture-10-a", "56.02")
    snapshot(10, "p1", "17:01:00", "56.02", "succeeded")
    event(10, "e1", "17:00:00", "event-10-a", "payment_intent.succeeded", "17:00:10")
    delivery(10, "d1", "17:00:10", "event-10-a", "failed", 500, 1)
    delivery(10, "d2", "17:03:00", "event-10-a", "failed", 503, 2)
    delivery(10, "d3", "17:08:00", "event-10-a", "failed", 504, 3)
    app(10, "u1", "17:09:00", "succeeded", "receipt")
    return payments, evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "artifacts/independent-domain-holdout.sqlite")
    args = parser.parse_args()
    path = args.database.resolve()
    if path == (ROOT / "data/prepared/incidents.sqlite").resolve():
        parser.error("Refusing to replace the default prepared database.")
    payments, evidence = observations()
    create_database(path, payments, evidence)
    print(f"Prepared {len(payments)} independent incidents / {len(evidence)} observations in {path}")


if __name__ == "__main__":
    main()
