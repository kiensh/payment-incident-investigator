"""Repeatable offline preparation: `python -m src.pipeline.prepare`. No network required."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from src.domain.models import Evidence, Payment
from src.domain.ontology import load_ontology
from src.storage.repository import create_database

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = ROOT / "data/raw/digital-wallet/digital-wallet.zip"
DEFAULT_SCENARIOS = ROOT / "evals/dev/scenarios.yaml"
DEFAULT_DATABASE = ROOT / "data/prepared/incidents.sqlite"
DEFAULT_REPORT = ROOT / "data/prepared/quality_report.json"
ARCHIVE_SHA256 = "dd88d321401d46b77e6fe7ffe17baaf3786bf207dde3fe270bc7535a0591360a"
DEMO_EPOCH = datetime.fromisoformat("2026-01-15T10:00:00+00:00")
DEMO_WARNING = "Synthetic lifecycle observation, independently authored for the demo; not reconstructed source history."
DEMO_POLICY = {
    "version": "1.0.0",
    "provider_model": "Stripe PaymentIntent-inspired synthetic card lifecycle; no live provider records.",
    "currency": "USD is an explicit synthetic lifecycle test currency only. Original source currency remains null.",
    "amount": "Source product_amount numeric values are reused as synthetic test amounts, not asserted to be USD in the original dataset.",
    "time": "Lifecycle timestamps use a fixed 2026 UTC test clock unrelated to the source transaction date. The original source timezone remains null.",
    "identity": "No merchant identity is inferred or joined across source rows.",
}


def read_source(archive: Path = DEFAULT_ARCHIVE, expected_sha256: str = ARCHIVE_SHA256) -> dict[str, Any]:
    """Keep untrusted archive parsing in an isolated Python process and out of CWD/imports."""
    worker = Path(__file__).with_name("read_source.py")
    completed = subprocess.run(
        [sys.executable, "-I", str(worker), "--archive", str(archive.resolve()),
         "--expected-sha256", expected_sha256],
        cwd=worker.parent, check=False, capture_output=True, text=True, timeout=30,
    )
    if completed.returncode:
        # This is an offline diagnostic, not a runtime error containing source paths.
        raise ValueError("isolated source validation failed: " + completed.stderr.strip().splitlines()[-1])
    value: dict[str, Any] = json.loads(completed.stdout)
    return value


def _object_id(payment_id: str, local_id: str) -> str:
    if local_id == "$payment":
        return payment_id
    return "obj_" + hashlib.sha256(f"{payment_id}/{local_id}".encode()).hexdigest()[:16]


def _timestamp(value: int | str | None, index: int) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return (DEMO_EPOCH + timedelta(days=index, seconds=value)).isoformat()


def build_observations(
    rows: list[dict[str, str]], quality: dict[str, Any], scenarios_path: Path = DEFAULT_SCENARIOS,
) -> tuple[list[Payment], list[Evidence]]:
    """Compile private design specs into a strict allowlist of observable fields.

    Expectations are never read. Design labels, local IDs, and scenario metadata
    never enter Payment.original, Evidence.data, or SQLite.
    """
    with scenarios_path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    if not isinstance(document, dict) or document.get("version") != 1 or not isinstance(document.get("cases"), list):
        raise ValueError("invalid development observation specification")
    candidates = sorted(
        (row for row in rows if row["payment_method"] in {"Debit Card", "Credit Card"}),
        key=lambda row: row["transaction_id"],
    )
    if len(candidates) < len(document["cases"]):
        raise ValueError("not enough validated card source rows")
    concepts = load_ontology()["concepts"]
    payments: list[Payment] = []
    evidence: list[Evidence] = []
    for index, case in enumerate(document["cases"]):
        row = candidates[index]
        payment_id = case["payment_id"]
        warnings = ["Original source currency is not specified.", "Original source timestamp has no timezone."]
        if row["merchant_id"] in quality["ambiguous_merchants"]:
            warnings.append("Source merchant_id is associated with multiple merchant names; identity is not resolved or merged.")
        payment = Payment(id=payment_id, symptom=case["symptom"], source_transaction_id=row["transaction_id"],
                          original=dict(row), warnings=warnings)
        payments.append(payment)
        evidence.append(Evidence(
            id="ev_" + hashlib.sha256(f"{payment_id}/source".encode()).hexdigest()[:16],
            payment_id=payment_id, kind="Payment", source="Kaggle / Harun Rai / Digital Wallet Transactions v1 / original CSV row",
            synthetic=True, occurred_at=datetime.strptime(row["transaction_date"], "%Y-%m-%d %H:%M").isoformat(),
            observed_at=None, warnings=warnings + ["Original dataset is synthetic and supplies coarse status only."],
            data={"record_type": "source_context", "source_transaction_id": row["transaction_id"],
                  "amount": row["product_amount"], "currency": None,
                  "original_status": row["transaction_status"], "payment_method": row["payment_method"]},
        ))
        local_ids: set[str] = set()
        for observation in case["observations"]:
            local_id = observation["id"]
            if local_id in local_ids:
                raise ValueError("duplicate observation local ID")
            local_ids.add(local_id)
            kind = observation["kind"]
            if kind not in concepts:
                raise ValueError("unknown observation kind")
            data = dict(observation["data"])
            if kind in {"Payment", "Authorization", "Capture"}:
                raw_amount = data.get("amount", "$amount")
                if raw_amount == "$amount":
                    data["amount"] = row["product_amount"]
                elif isinstance(raw_amount, str) and raw_amount.startswith("$amount+"):
                    data["amount"] = format(Decimal(row["product_amount"]) + Decimal(raw_amount[8:]), "f")
                else:
                    data["amount"] = str(raw_amount)
                data.setdefault("currency", "USD")
            identity = concepts[kind]["identity_field"]
            if identity:
                data[identity] = _object_id(payment_id, data.get(identity, local_id))
            relations = list(concepts[kind]["relations"])
            if kind == "ProviderEvent":
                relations.append({"field": "subject_id", "target": data["subject_kind"]})
            for relation in relations:
                value = data.get(relation["field"])
                if value is not None:
                    data[relation["field"]] = _object_id(payment_id, value)
            at = _timestamp(observation.get("at"), index)
            seen = _timestamp(observation.get("seen", observation.get("at")), index)
            evidence.append(Evidence(
                id="ev_" + hashlib.sha256(f"{payment_id}/{local_id}".encode()).hexdigest()[:16],
                payment_id=payment_id, kind=kind, source="Synthetic demo / lifecycle observations v1 / explicit UTC and USD test policy",
                synthetic=True, occurred_at=at, observed_at=seen, data=data, warnings=[DEMO_WARNING],
            ))
    return payments, evidence


def prepare(
    archive: Path = DEFAULT_ARCHIVE, database: Path = DEFAULT_DATABASE,
    report: Path = DEFAULT_REPORT, scenarios: Path = DEFAULT_SCENARIOS,
) -> dict[str, Any]:
    source = read_source(archive)
    payments, evidence = build_observations(source["rows"], source["quality"], scenarios)
    create_database(database, payments, evidence)
    quality = source["quality"]
    quality.update({
        "preparation_version": "1.0.0", "ontology_version": load_ontology()["version"],
        "source_attribution": {"title": "Digital Wallet Transactions", "creator": "Harun Rai",
                               "url": "https://www.kaggle.com/datasets/harunrai/digital-wallet-transactions",
                               "listed_license": "MIT", "source_version": 1},
        "selection": "First validated Credit Card or Debit Card rows sorted by original transaction_id; one independent scenario per selected row.",
        "card_candidate_count": sum(row["payment_method"] in {"Debit Card", "Credit Card"} for row in source["rows"]),
        "selected_row_count": len(payments), "observable_evidence_count": len(evidence),
        "selected_transaction_ids": [payment.source_transaction_id for payment in payments],
        "demo_policy": DEMO_POLICY,
        "normalization": "Decimal strings normalized without binary floating point; original values retained verbatim. No merchant joins or currency/timezone imputations.",
        "runtime_boundary": "SQLite contains only payments and observable evidence; private designs and expected answers are excluded.",
    })
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(quality, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return quality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS,
                        help="Offline development observation specifications, never a runtime tool input")
    args = parser.parse_args()
    quality = prepare(args.archive, args.database, args.report, args.scenarios)
    print(json.dumps({key: quality[key] for key in (
        "row_count", "valid_row_count", "card_candidate_count", "selected_row_count", "observable_evidence_count",
        "ambiguous_merchant_id_count", "currency_unknown_rows", "timezone_unspecified_rows", "archive_sha256",
    )}, indent=2))


if __name__ == "__main__":
    main()
