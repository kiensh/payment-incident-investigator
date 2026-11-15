"""Repository safety and freshness tests against isolated temporary databases."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.domain.models import Evidence, Payment
from src.domain.rules import analyze
from src.storage.repository import Repository, create_database


def records() -> tuple[Payment, list[Evidence]]:
    payment = Payment(id="pay_test", symptom="Please check the status.", source_transaction_id="src-1", original={"transaction_status": "Successful"})
    evidence = [
        Evidence(id="ev-capture", payment_id=payment.id, kind="Capture", source="test", synthetic=True,
                 occurred_at="2026-01-01T10:00:00Z", observed_at="2026-01-01T10:00:01Z",
                 data={"capture_id": "capture-1", "status": "succeeded", "amount": "42.00", "currency": "USD"}),
        Evidence(id="ev-app", payment_id=payment.id, kind="ApplicationStatusObservation", source="test", synthetic=True,
                 occurred_at="2026-01-01T10:00:05Z", observed_at="2026-01-01T10:00:05Z",
                 data={"observation_id": "app-1", "status": "succeeded", "channel": "checkout"}),
    ]
    return payment, evidence


def test_read_roundtrip_and_unknown_id(tmp_path: Path) -> None:
    payment, evidence = records()
    path = tmp_path / "evidence.sqlite"
    create_database(path, [payment], evidence)
    repository = Repository(path)
    assert repository.list_payments() == [payment]
    assert repository.get_payment(payment.id) == payment
    assert {item.id for item in repository.get_evidence(payment.id)} == {item.id for item in evidence}
    assert repository.get_payment("absent") is None
    assert repository.get_evidence("absent") == []
    assert repository.get_snapshot("absent") is None


def test_missing_database_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        Repository(path).list_payments()
    assert not path.exists()


def test_connection_is_read_only_even_for_writable_file(tmp_path: Path) -> None:
    payment, evidence = records()
    path = tmp_path / "evidence.sqlite"
    create_database(path, [payment], evidence)
    repository = Repository(path)
    with repository._connection() as connection:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM evidence")
    assert len(repository.get_evidence(payment.id)) == 2


def test_payment_lookup_is_parameterized(tmp_path: Path) -> None:
    payment, evidence = records()
    path = tmp_path / "evidence.sqlite"
    create_database(path, [payment], evidence)
    repository = Repository(path)
    assert repository.get_payment("' OR 1=1 --") is None
    assert repository.get_snapshot("'; DROP TABLE evidence; --") is None
    assert repository.list_payments() == [payment]


def test_next_investigation_reads_changed_evidence(tmp_path: Path) -> None:
    payment, evidence = records()
    path = tmp_path / "evidence.sqlite"
    create_database(path, [payment], evidence)
    repository = Repository(path)
    first = repository.get_snapshot(payment.id)
    assert first is not None
    assert analyze(*first).disposition == "no_escalation"
    evidence[1].data["status"] = "failed"
    create_database(path, [payment], evidence)
    second = repository.get_snapshot(payment.id)
    assert second is not None
    assert analyze(*second).disposition == "check_required"
    assert next(item for item in first[1] if item.kind == "ApplicationStatusObservation").data["status"] == "succeeded"


def test_snapshot_reads_two_tables_in_one_transaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payment, evidence = records()
    path = tmp_path / "evidence.sqlite"
    create_database(path, [payment], evidence)
    original_connect = sqlite3.connect
    with original_connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    changed_payment = payment.model_copy(update={"symptom": "New observation arrived."})
    changed_evidence = evidence[1].model_copy(deep=True)
    changed_evidence.data["status"] = "failed"
    updated = False

    def connect_with_update(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = original_connect(*args, **kwargs)

        def update_between_queries(sql: str) -> None:
            nonlocal updated
            if not updated and sql.startswith("SELECT record_json FROM evidence"):
                updated = True
                with original_connect(path) as writer:
                    writer.execute("UPDATE payments SET record_json = ? WHERE payment_id = ?", (changed_payment.model_dump_json(), payment.id))
                    writer.execute("UPDATE evidence SET record_json = ? WHERE evidence_id = ?", (changed_evidence.model_dump_json(), changed_evidence.id))
        connection.set_trace_callback(update_between_queries)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect_with_update)
    repository = Repository(path)
    first = repository.get_snapshot(payment.id)
    assert updated
    assert first is not None and first[0].symptom == payment.symptom
    assert next(item for item in first[1] if item.kind == "ApplicationStatusObservation").data["status"] == "succeeded"
    second = repository.get_snapshot(payment.id)
    assert second is not None and second[0].symptom == changed_payment.symptom
    assert next(item for item in second[1] if item.kind == "ApplicationStatusObservation").data["status"] == "failed"


def test_invalid_new_database_cannot_replace_existing_one(tmp_path: Path) -> None:
    payment, evidence = records()
    path = tmp_path / "evidence.sqlite"
    create_database(path, [payment], evidence)
    original = path.read_bytes()
    evidence[0].data["amount"] = "NaN"
    with pytest.raises(ValueError):
        create_database(path, [payment], evidence)
    assert path.read_bytes() == original


def test_unknown_payment_and_cross_payment_object_links_are_rejected(tmp_path: Path) -> None:
    payment, evidence = records()
    with pytest.raises(ValueError, match="unknown payment"):
        create_database(tmp_path / "one.sqlite", [], evidence)
    other = payment.model_copy(update={"id": "pay_other"})
    event = Evidence(id="ev-event", payment_id=other.id, kind="ProviderEvent", source="test", synthetic=True,
                     data={"event_id": "event-other", "event_type": "charge.captured", "subject_kind": "Capture", "subject_id": "capture-1"})
    with pytest.raises(ValueError, match="cross-payment object"):
        create_database(tmp_path / "two.sqlite", [payment, other], evidence + [event])


def test_duplicate_evidence_ids_and_provider_identity_owners_are_rejected(tmp_path: Path) -> None:
    payment, evidence = records()
    with pytest.raises(ValueError, match="duplicate evidence"):
        create_database(tmp_path / "one.sqlite", [payment], evidence + [evidence[0]])
    other = payment.model_copy(update={"id": "pay_other"})
    other_capture = evidence[0].model_copy(update={"id": "ev-other", "payment_id": other.id})
    with pytest.raises(ValueError, match="multiple payments"):
        create_database(tmp_path / "two.sqlite", [payment, other], evidence + [other_capture])


def test_database_contains_observations_not_evaluation_tables(tmp_path: Path) -> None:
    payment, evidence = records()
    path = tmp_path / "evidence.sqlite"
    create_database(path, [payment], evidence)
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"payments", "evidence"}
        serialized = [json.loads(row[0]) for row in connection.execute("SELECT record_json FROM evidence")]
    assert not any({"expected", "design", "diagnosis", "scenario"}.intersection(item["data"]) for item in serialized)


def test_read_only_uri_handles_spaces_and_question_marks(tmp_path: Path) -> None:
    payment, evidence = records()
    path = tmp_path / "evidence space?name.sqlite"
    create_database(path, [payment], evidence)
    assert Repository(path).get_payment(payment.id) == payment
