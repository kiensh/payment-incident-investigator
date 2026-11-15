"""Reproducibility, provenance, quality facts, and dev-only observation checks."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.domain.rules import analyze
from src.pipeline.prepare import (
    DEFAULT_ARCHIVE,
    DEFAULT_SCENARIOS,
    ROOT,
    build_observations,
    prepare,
    read_source,
)
from src.storage.repository import Repository, create_database


@pytest.fixture(scope="module")
def source() -> dict[str, Any]:
    return read_source()


def test_preserved_archive_matches_independently_recorded_checksums(source: dict[str, Any]) -> None:
    assert source["quality"]["archive_sha256"] == "dd88d321401d46b77e6fe7ffe17baaf3786bf207dde3fe270bc7535a0591360a"
    assert source["quality"]["csv_sha256"] == "8cad043a23452880e8de99e54457f72ba030578681c1614bf5ecae94adcc5c6c"
    assert source["quality"]["archive_bytes"] == 298762
    assert source["quality"]["csv_bytes"] == 903674
    provenance = json.loads((ROOT / "data/raw/provenance.json").read_text())
    assert provenance["metadata_verified_fields"]["licenseName"] == "MIT"
    assert provenance["creator"] == "Harun Rai"


def test_actual_source_quality_facts_are_rechecked(source: dict[str, Any]) -> None:
    quality = source["quality"]
    assert quality["row_count"] == quality["valid_row_count"] == 5000
    assert quality["merchant_id_count"] == 987
    assert quality["ambiguous_merchant_id_count"] == 962
    assert quality["status_counts"] == {"Successful": 4755, "Failed": 146, "Pending": 99}
    assert quality["invalid_rows"] == []
    assert quality["duplicate_transaction_id_count"] == 0
    assert not quality["explicit_currency_column"]
    assert quality["source_timezone"] is None
    assert quality["source_lifecycle_columns"] == []
    assert quality["currency_unknown_rows"] == quality["timezone_unspecified_rows"] == 5000
    names = quality["ambiguous_merchants"]["MERCH_0083"]
    assert {"Airbnb", "Bharat Gas", "BSNL"} <= set(names)


def test_card_selection_and_original_values_are_preserved(source: dict[str, Any]) -> None:
    payments, evidence = build_observations(source["rows"], source["quality"])
    original_by_id = {row["transaction_id"]: row for row in source["rows"]}
    assert len(payments) == 20
    assert len({payment.id for payment in payments}) == 20
    assert sum(row["payment_method"] in {"Credit Card", "Debit Card"} for row in source["rows"]) == 2014
    for payment in payments:
        assert payment.original == original_by_id[payment.source_transaction_id]
        assert payment.original["payment_method"] in {"Credit Card", "Debit Card"}
        assert payment.warnings
        context = next(item for item in evidence if item.payment_id == payment.id and item.kind == "Payment" and item.data["record_type"] == "source_context")
        assert context.data["currency"] is None
        assert context.occurred_at is not None and not context.occurred_at.endswith(("Z", "+00:00"))
        assert context.observed_at is None
        assert context.data["original_status"] == payment.original["transaction_status"]
    lifecycle = [item for item in evidence if "Synthetic demo" in item.source]
    assert lifecycle and all(item.synthetic and item.warnings for item in lifecycle)


def test_preparation_is_deterministic_and_never_serializes_specs(tmp_path: Path, source: dict[str, Any]) -> None:
    payments, evidence = build_observations(source["rows"], source["quality"])
    second_payments, second_evidence = build_observations(source["rows"], source["quality"])
    assert payments == second_payments and evidence == second_evidence
    one, two = tmp_path / "one.sqlite", tmp_path / "two.sqlite"
    create_database(one, payments, evidence)
    create_database(two, second_payments, second_evidence)
    assert one.read_bytes() == two.read_bytes()
    designs = yaml.safe_load(DEFAULT_SCENARIOS.read_text())["cases"]
    raw = one.read_bytes()
    for case in designs:
        assert case["design"].encode() not in raw
    assert b"required_rules" not in raw
    for payment in Repository(one).list_payments():
        assert set(payment.original) == set(source["rows"][0])
        assert payment.id.startswith("pay_")


def test_offline_prepare_reports_assumptions_and_source_attribution(tmp_path: Path) -> None:
    database, report = tmp_path / "incidents.sqlite", tmp_path / "quality.json"
    quality = prepare(database=database, report=report)
    assert quality["selected_row_count"] == 20
    assert quality["card_candidate_count"] == 2014
    assert quality["source_attribution"]["creator"] == "Harun Rai"
    assert "Original source currency remains null" in quality["demo_policy"]["currency"]
    assert len(Repository(database).list_payments()) == 20
    first_report = report.read_bytes()
    first_database = database.read_bytes()
    prepare(database=database, report=report)
    assert report.read_bytes() == first_report
    assert database.read_bytes() == first_database


def test_all_manual_development_expectations(source: dict[str, Any]) -> None:
    """Integration checks complement, not replace, independent unit-record tests."""
    payments, evidence = build_observations(source["rows"], source["quality"])
    expectations = json.loads((ROOT / "evals/expected/dev.json").read_text())["cases"]
    expected_by_id = {item["payment_id"]: item for item in expectations}
    assert len(expected_by_id) == 20
    dispositions = set()
    for payment in payments:
        expected = expected_by_id[payment.id]
        result = analyze(payment, [item for item in evidence if item.payment_id == payment.id])
        assert result.payment_state == expected["payment_state"], payment.id
        assert result.disposition == expected["disposition"], payment.id
        assert set(expected["required_rules"]) <= set(result.applied_rules), payment.id
        assert not set(expected["forbidden_rules"]).intersection(result.applied_rules), payment.id
        for claim in expected.get("required_claims", []):
            assert any(claim["text_contains"] in finding.text and set(claim["evidence_ids"]) <= set(finding.evidence_ids)
                       for finding in getattr(result, claim["section"])), (payment.id, claim)
        dispositions.add(result.disposition)
    assert dispositions == {"no_escalation", "check_required", "escalate"}


def test_source_reader_rejects_checksum_mismatch() -> None:
    with pytest.raises(ValueError, match="checksum mismatch"):
        read_source(DEFAULT_ARCHIVE, "0" * 64)


@pytest.mark.parametrize("member", ["../digital_wallet_transactions.csv", "/digital_wallet_transactions.csv", "setup.py"])
def test_unexpected_or_traversal_archive_members_rejected(tmp_path: Path, member: str) -> None:
    download = tmp_path / "isolated-download"
    download.mkdir()
    archive = download / "dataset.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(member, "untrusted content")
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="expected CSV"):
        read_source(archive, expected)
    assert sorted(path.name for path in download.iterdir()) == ["dataset.zip"]


def test_archive_is_never_extracted_and_download_sidecars_are_not_imported(tmp_path: Path) -> None:
    download = tmp_path / "isolated-download"
    download.mkdir()
    archive = download / "dataset.zip"
    archive.write_bytes(DEFAULT_ARCHIVE.read_bytes())
    (download / "csv.py").write_text("raise RuntimeError('UNTRUSTED CODE EXECUTED')\n")
    # CLI itself invokes the trusted reader with -I and a trusted working directory.
    result = read_source(archive)
    assert result["quality"]["row_count"] == 5000
    assert not (download / "digital_wallet_transactions.csv").exists()


def test_module_command_is_reproducible_offline(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "src.pipeline.prepare", "--database", str(tmp_path / "db.sqlite"), "--report", str(tmp_path / "report.json")],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["selected_row_count"] == 20
