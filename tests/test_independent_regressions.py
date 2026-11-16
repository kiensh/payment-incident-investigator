"""Exposed independent cases are regression evidence, not untouched hold-outs."""
import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evals.holdout.prepare import observations
from evals.run import score_result
from src.api import create_app
from src.config import ROOT, Settings
from src.domain.models import Evidence
from src.domain.rules import analyze
from src.storage.repository import create_database


def test_resolution_adjudication_preserves_original_and_changes_only_h09_rule_ban():
    original_bytes = (ROOT / "evals/expected/holdout.json").read_bytes()
    original = json.loads(original_bytes)
    adjudicated = json.loads(
        (ROOT / "evals/expected/holdout_resolution_adjudicated.json").read_text()
    )
    assert sha256(original_bytes).hexdigest() == adjudicated["original_oracle_sha256"] == (
        "8b22e4ca4ce319f4d49ebcb3b27c75b227e8559cb68e3a901029f459e20fce68"
    )
    assert len(original["cases"]) == len(adjudicated["cases"]) == 10
    for before, after in zip(original["cases"], adjudicated["cases"], strict=True):
        expected = dict(before)
        if before["payment_id"] == "pay_h09_7c9a":
            expected["forbidden_rules"] = ["aligned_observations"]
        assert after == expected


@pytest.mark.parametrize("index", range(10))
def test_independently_authored_incidents_through_real_api(index: int, tmp_path: Path):
    payments, records = observations()
    payment = payments[index]
    evidence = [record for record in records if record.payment_id == payment.id]
    expected = json.loads(
        (ROOT / "evals/expected/holdout_resolution_adjudicated.json").read_text()
    )["cases"][index]
    db = tmp_path / "case.sqlite"
    create_database(db, [payment], evidence)
    with TestClient(create_app(Settings(mode="mock", database=db))) as client:
        response = client.post("/api/investigate", json={"payment_id": payment.id, "question": payment.symptom})
    assert response.status_code == 200
    result = response.json()
    assert result["technical"]["model_requests"] == 0
    assert score_result(result, expected) == []
    if payment.id == "pay_h09_7c9a":
        # Preserve visibility of the frozen oracle's intentionally unmodified raw result.
        original = json.loads((ROOT / "evals/expected/holdout.json").read_text())["cases"][index]
        assert score_result(result, original) == ["unexpected rule: app_precedes_financial"]


def test_synthetic_disclaimer_is_not_a_data_quality_diagnosis(tmp_path):
    from evals.final_holdout.prepare import build

    payments, records = build()
    payment = payments[0]
    evidence = [record for record in records if record.payment_id == payment.id]
    result = analyze(payment, evidence)
    assert not any(f.rule_id == "source_context" for f in result.unknowns)
    assert not any("currency, or timezone warnings" in f.text for f in result.unknowns)
    db = tmp_path / "warning.sqlite"
    create_database(db, [payment], evidence)
    with TestClient(create_app(Settings(database=db))) as client:
        response = client.post("/api/investigate", json={"payment_id": payment.id, "question": payment.symptom})
    assert response.status_code == 200
    assert payment.warnings[0] in response.json()["data_warnings"]


def test_authorization_conflict_does_not_quote_either_amount_as_confirmed():
    payments, records = observations()
    evidence = [record for record in records if record.payment_id == payments[7].id]
    result = analyze(payments[7], evidence)
    assert result.payment_state == "authorized"
    assert result.disposition == "escalate"
    monetary = next(f for f in result.unknowns if f.rule_id == "authorization_amount_conflict")
    assert set(monetary.evidence_ids) == {"h08_z1", "h08_z2"}
    confirmed = " ".join(f.text for f in result.confirmed_facts)
    assert "90.00" not in confirmed and "120.00" not in confirmed
    assert any("authorization" in f.text and "reconcile" in f.text for f in result.next_checks)


@pytest.mark.parametrize("untimed_status", ["failed", "succeeded"])
def test_known_discrepancy_survives_an_untimed_observation(untimed_status):
    payments, records = observations()
    evidence = [record for record in records if record.payment_id == payments[8].id]
    evidence = [Evidence(**{**r.model_dump(), "data": {**r.data, "status": untimed_status}})
                if r.id == "h09_u2" else r for r in evidence]
    result = analyze(payments[8], list(reversed(evidence)))
    assert (result.payment_state, result.disposition) == ("captured", "check_required")
    discrepancy = next(f for f in result.discrepancies if f.rule_id == "app_discrepancy")
    assert set(discrepancy.evidence_ids) == {"h09_c1", "h09_u3"}
    assert "failed" in discrepancy.text and "checkout" in discrepancy.text
    assert "aligned_observations" not in result.applied_rules
    historical = [f for f in result.unknowns if f.rule_id == "app_precedes_financial"]
    assert len(historical) == 1
    assert set(historical[0].evidence_ids) == {"h09_c1", "h09_u1"}
    assert "status-export-a" in historical[0].text
    unordered = [f for f in result.unknowns if f.rule_id == "app_order_unknown"]
    if untimed_status == "failed":
        assert unordered
    for finding in unordered:
        assert set(finding.evidence_ids) == {"h09_c1", "h09_u2"}
        assert "status-export-b" in finding.text
    # An untimed success in another channel need not create an ordering conflict.
    # Neither variant may move the known checkout discrepancy into an ordering gap.


@pytest.mark.parametrize("recovery_time,resolved", [
    ("2026-02-10T17:10:00Z", True),
    ("2026-02-10T17:08:00Z", False),
    (None, False),
])
def test_notification_recovery_requires_a_comparable_later_success(recovery_time, resolved):
    payments, records = observations()
    evidence = [record for record in records if record.payment_id == payments[9].id]
    last = next(record for record in evidence if record.id == "h10_d3")
    recovery = Evidence(**{**last.model_dump(), "id": "h10_d4", "occurred_at": recovery_time,
                           "observed_at": recovery_time,
                           "data": {**last.data, "delivery_id": "delivery-10-d4", "status": "delivered",
                                    "http_status": 204, "attempt_number": 4}})
    result = analyze(payments[9], evidence + [recovery])
    assert result.payment_state == "captured"
    assert result.disposition == ("no_escalation" if resolved else "check_required")
    assert ("notification_unresolved" in result.applied_rules) is not resolved
    assert not result.hypotheses  # Financial/display agreement does not imply delivery causation.
