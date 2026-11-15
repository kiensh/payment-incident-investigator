import copy
from pathlib import Path

from fastapi.testclient import TestClient

from evals.run import score_result
from src.api import create_app
from src.config import Settings
from src.storage.repository import create_database
from tests.test_api import observations


def test_grader_rejects_wrong_amount_with_existing_citations_and_invented_evidence(tmp_path: Path):
    payment, evidence = observations()
    db = tmp_path / "case.sqlite"
    create_database(db, [payment], evidence)
    with TestClient(create_app(Settings(database=db))) as client:
        result = client.post("/api/investigate", json={"payment_id": payment.id, "question": payment.symptom}).json()
    expected = {"payment_state": "captured", "disposition": "check_required"}
    source = [record.model_dump(mode="json") for record in evidence]
    assert score_result(result, expected, source) == []

    wrong_amount = copy.deepcopy(result)
    claim = next(f for f in wrong_amount["confirmed_facts"] if f["rule_id"] == "capture_success")
    claim["text"] = claim["text"].replace("10.00", "999.00")
    assert any("monetary claim contradicted" in error for error in score_result(wrong_amount, expected, source))

    fabricated = copy.deepcopy(result)
    next(r for r in fabricated["evidence"] if r["id"] == "rec_capture")["data"]["amount"] = "999.00"
    assert "returned evidence differs from the source snapshot" in score_result(fabricated, expected, source)

    unsupported_summary = copy.deepcopy(result)
    unsupported_summary["summary"] = "The customer was charged 999 USD. [rec_capture]"
    assert any("summary contains prose" in error for error in score_result(unsupported_summary, expected, source))

    always_escalate = copy.deepcopy(result)
    always_escalate["disposition"] = "escalate"
    normal_oracle = {"payment_state": "captured", "disposition": "no_escalation"}
    assert "unnecessary escalation/abstention on sufficient evidence" in score_result(always_escalate, normal_oracle)
