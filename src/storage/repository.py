"""Scoped read-only runtime access; the offline writer is deliberately separate."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.domain.models import Evidence, Payment
from src.domain.ontology import load_ontology, validate_evidence_graph

SCHEMA_VERSION = 1


class Repository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # mode=ro prevents accidental creation and writes even if the file is writable.
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise ValueError(f"unsupported evidence database schema: {version}")
            yield connection
        finally:
            connection.close()

    def list_payments(self) -> list[Payment]:
        with self._connection() as connection:
            rows = connection.execute("SELECT record_json FROM payments ORDER BY payment_id").fetchall()
        return [Payment.model_validate_json(row[0]) for row in rows]

    def get_payment(self, payment_id: str) -> Payment | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record_json FROM payments WHERE payment_id = ?", (payment_id,)
            ).fetchone()
        return Payment.model_validate_json(row[0]) if row else None

    def get_evidence(self, payment_id: str) -> list[Evidence]:
        snapshot = self.get_snapshot(payment_id)
        return snapshot[1] if snapshot else []

    def get_snapshot(self, payment_id: str) -> tuple[Payment, list[Evidence]] | None:
        """A fresh, internally consistent snapshot for one investigation.

        BEGIN establishes one SQLite read transaction for both tables. Replacing
        or updating the database never reuses a previous investigation's data.
        """
        with self._connection() as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT record_json FROM payments WHERE payment_id = ?", (payment_id,)
            ).fetchone()
            if row is None:
                return None
            payment = Payment.model_validate_json(row[0])
            rows = connection.execute(
                "SELECT record_json FROM evidence WHERE payment_id = ? ORDER BY evidence_id", (payment_id,)
            ).fetchall()
            evidence = [Evidence.model_validate_json(item[0]) for item in rows]
            validate_evidence_graph(payment, evidence)
            return payment, evidence


def create_database(path: Path, payments: list[Payment], evidence: list[Evidence]) -> None:
    """Offline/test preparation only; atomically replace a validated database.

    Runtime code only instantiates Repository and has no arbitrary SQL interface.
    No scenario specification or evaluation expectation is accepted by this API.
    """
    path = Path(path).resolve()
    # Revalidate models because callers may have mutated nested dicts after construction.
    payments = [Payment.model_validate(item.model_dump()) for item in payments]
    evidence = [Evidence.model_validate(item.model_dump()) for item in evidence]
    by_payment = {payment.id: payment for payment in payments}
    if len(by_payment) != len(payments):
        raise ValueError("duplicate payment ID")
    if len({item.id for item in evidence}) != len(evidence):
        raise ValueError("duplicate evidence ID")
    grouped: dict[str, list[Evidence]] = defaultdict(list)
    object_owners: dict[tuple[str, str], str] = {}
    concepts = load_ontology()["concepts"]
    for item in evidence:
        if item.payment_id not in by_payment:
            raise ValueError("evidence references an unknown payment")
        grouped[item.payment_id].append(item)
        identity = concepts[item.kind]["identity_field"]
        if identity:
            key = (item.kind, item.data[identity])
            owner = object_owners.setdefault(key, item.payment_id)
            if owner != item.payment_id:
                raise ValueError("one provider object identity belongs to multiple payments")
    for payment in payments:
        validate_evidence_graph(payment, grouped[payment.id])
        for item in grouped[payment.id]:
            relations = list(concepts[item.kind]["relations"])
            if item.kind == "ProviderEvent":
                relations.append({"field": "subject_id", "target": item.data["subject_kind"]})
            for relation in relations:
                target = item.data.get(relation["field"])
                if target is None:
                    continue
                referenced_owner = object_owners.get((relation["target"], target))
                if relation["target"] == "Payment" and target in by_payment:
                    referenced_owner = target
                if referenced_owner is not None and referenced_owner != payment.id:
                    raise ValueError("cross-payment object reference")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".prepare-", suffix=".sqlite", dir=path.parent)
    os.close(descriptor)
    try:
        with sqlite3.connect(temporary) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript("""
                CREATE TABLE payments (
                    payment_id TEXT PRIMARY KEY NOT NULL,
                    record_json TEXT NOT NULL CHECK(json_valid(record_json))
                );
                CREATE TABLE evidence (
                    evidence_id TEXT PRIMARY KEY NOT NULL,
                    payment_id TEXT NOT NULL REFERENCES payments(payment_id),
                    kind TEXT NOT NULL,
                    record_json TEXT NOT NULL CHECK(json_valid(record_json))
                );
                CREATE INDEX evidence_by_payment ON evidence(payment_id, evidence_id);
            """)
            connection.executemany(
                "INSERT INTO payments(payment_id, record_json) VALUES (?, ?)",
                [(item.id, json.dumps(item.model_dump(), sort_keys=True, ensure_ascii=False))
                 for item in sorted(payments, key=lambda row: row.id)],
            )
            connection.executemany(
                "INSERT INTO evidence(evidence_id, payment_id, kind, record_json) VALUES (?, ?, ?, ?)",
                [(item.id, item.payment_id, item.kind, json.dumps(item.model_dump(), sort_keys=True, ensure_ascii=False))
                 for item in sorted(evidence, key=lambda row: row.id)],
            )
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
