"""Evaluate through POST /api/investigate, with fresh per-case databases and apps."""
from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from evals.support import audit_support
from src.api import create_app
from src.config import ROOT, Settings
from src.storage.repository import Repository, create_database

SECTIONS = ("confirmed_facts", "discrepancies", "hypotheses", "unknowns", "next_checks")


def score_result(result: dict, expected: dict, source_evidence: list[dict] | None = None) -> list[str]:
    failures = audit_support(result)
    if source_evidence is not None:
        source = {record["id"]: record for record in source_evidence}
        returned = {record["id"]: record for record in result["evidence"]}
        if returned != source or len(returned) != len(result["evidence"]):
            failures.append("returned evidence differs from the source snapshot")
    for field in ("payment_state", "disposition"):
        if result.get(field) != expected[field]:
            failures.append(f"{field}: expected {expected[field]}, got {result.get(field)}")
    rules = set(result["technical"]["applied_rules"])
    for rule in expected.get("required_rules", []):
        if rule not in rules:
            failures.append(f"missing required rule: {rule}")
    for rule in expected.get("forbidden_rules", []):
        if rule in rules:
            failures.append(f"unexpected rule: {rule}")
    evidence = {record["id"]: record for record in result["evidence"]}
    claims = [claim for section in SECTIONS for claim in result[section]]
    for claim in claims:
        if not set(claim["evidence_ids"]).issubset(evidence):
            failures.append(f"unknown evidence citation: {claim['id']}")
    for check in expected.get("required_claims", []):
        candidates = result.get(check["section"], [])
        matches = [claim for claim in candidates
                   if check.get("text_contains", "").lower() in claim["text"].lower()
                   and set(check.get("evidence_ids", [])).issubset(claim["evidence_ids"])]
        if not matches:
            failures.append(f"unsupported/missing expected claim: {check}")
    for check in expected.get("forbidden_text", []):
        if check.lower() in " ".join(claim["text"] for claim in claims).lower():
            failures.append(f"forbidden claim text: {check}")
    if not result["next_checks"]:
        failures.append("no safe next check or explicit close instruction")
    if not result["runbooks"]:
        failures.append("no consulted runbook")
    if result["mode"] == "live" and result["technical"]["model_requests"] < 1:
        failures.append("live result without model use")
    if expected["disposition"] == "no_escalation" and result["disposition"] != "no_escalation":
        failures.append("unnecessary escalation/abstention on sufficient evidence")
    return failures


def run(database: Path, expectations: Path, output: Path, settings: Settings,
        ids: set[str] | None = None) -> dict:
    expected_file = json.loads(expectations.read_text())
    cases = expected_file["cases"]
    if ids:
        cases = [case for case in cases if case["payment_id"] in ids]
        missing = ids - {case["payment_id"] for case in cases}
        if missing:
            raise ValueError(f"IDs absent from expectation file: {sorted(missing)}")
    if not cases:
        raise ValueError("No evaluation cases selected.")
    source = Repository(database)
    rows = []
    started = perf_counter()
    for case in cases:
        snapshot = source.get_snapshot(case["payment_id"])
        if snapshot is None:
            raise ValueError(f"Missing evaluation observation: {case['payment_id']}")
        payment, evidence = snapshot
        with tempfile.TemporaryDirectory(prefix="incident-eval-") as tmp:
            db = Path(tmp) / "case.sqlite"
            create_database(db, [payment], evidence)
            isolated = replace(settings, database=db)
            with TestClient(create_app(isolated), raise_server_exceptions=False) as client:
                response = client.post("/api/investigate", json={
                    "payment_id": payment.id,
                    "question": case.get("question", payment.symptom),
                })
            payload = response.json()
        if response.status_code != 200:
            code = payload.get("error", {}).get("code", "unhandled_error")
            category = "incorrect" if code == "unsupported_conclusion" else "infrastructure_error"
            rows.append({"payment_id": payment.id, "outcome": category,
                         "http_status": response.status_code, "error": payload})
        else:
            failures = score_result(payload, case, [record.model_dump(mode="json") for record in evidence])
            rows.append({"payment_id": payment.id, "outcome": "incorrect" if failures else "pass",
                         "failures": failures, "result": payload})
        print(f"{payment.id}: {rows[-1]['outcome']}", flush=True)
    counts = {key: sum(row["outcome"] == key for row in rows)
              for key in ("pass", "incorrect", "infrastructure_error")}
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "mode": settings.mode, "model": settings.bridge_model if settings.mode == "live" else None,
        "expectations": str(expectations.relative_to(ROOT)) if expectations.is_relative_to(ROOT) else expectations.name,
        "selected": len(rows), "counts": counts,
        "answer_pass_rate": counts["pass"] / (counts["pass"] + counts["incorrect"]) if counts["pass"] + counts["incorrect"] else None,
        "model_requests": sum(row.get("result", {}).get("technical", {}).get("model_requests", 0) for row in rows),
        "request_count_note": "Successful results only; persistent bridge-budget ledger also counts failed/incomplete investigations.",
        "duration_seconds": round(perf_counter() - started, 2), "cases": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/prepared/incidents.sqlite")
    parser.add_argument("--expected", type=Path, default=ROOT / "evals/expected/dev.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/eval-dev-mock.json")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--ids", help="Comma-separated payment IDs; omit for all incidents.")
    args = parser.parse_args()
    settings = replace(Settings.from_env(), mode=args.mode)
    report = run(args.database.resolve(), args.expected.resolve(), args.output.resolve(), settings,
                 set(args.ids.split(",")) if args.ids else None)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    if report["counts"]["incorrect"] or report["counts"]["infrastructure_error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
