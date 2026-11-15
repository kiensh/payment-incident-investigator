"""Small executable ontology: relationships validate the observable evidence graph."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.domain.models import Evidence, Payment

ONTOLOGY_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "ontology.yaml"
# src/domain/ontology.py -> repository root is parents[2].


@lru_cache(maxsize=1)
def load_ontology() -> dict[str, Any]:
    with ONTOLOGY_PATH.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict) or not value.get("version"):
        raise ValueError("invalid ontology")
    if set(value["concepts"]) != set(Evidence.data_models):
        raise ValueError("ontology concepts and typed schemas disagree")
    return value


@dataclass(frozen=True)
class MissingReference:
    evidence_id: str
    field: str
    target_kind: str
    target_id: str


def validate_evidence_graph(payment: Payment, evidence: list[Evidence]) -> list[MissingReference]:
    """Reject identity corruption, while preserving genuinely absent evidence as unknown."""
    concepts = load_ontology()["concepts"]
    if len({item.id for item in evidence}) != len(evidence):
        raise ValueError("duplicate evidence ID")
    objects: dict[str, set[str]] = {payment.id: {"Payment"}}
    for item in evidence:
        if item.payment_id != payment.id:
            raise ValueError("cross-payment evidence is not allowed")
        identity = concepts[item.kind]["identity_field"]
        if identity:
            objects.setdefault(item.data[identity], set()).add(item.kind)
        if item.kind == "Payment" and item.data["record_type"] == "source_context":
            if item.data["source_transaction_id"] != payment.source_transaction_id:
                raise ValueError("source transaction relationship does not match payment")
    missing: list[MissingReference] = []
    for item in evidence:
        relations = list(concepts[item.kind]["relations"])
        if item.kind == "ProviderEvent":
            relations.append({"field": "subject_id", "target": item.data["subject_kind"]})
        for relation in relations:
            target = item.data.get(relation["field"])
            if target is None:
                continue
            known_kinds = objects.get(target)
            if known_kinds and relation["target"] not in known_kinds:
                raise ValueError(f"{item.id}: {relation['field']} references wrong entity kind")
            if not known_kinds:
                missing.append(MissingReference(item.id, relation["field"], relation["target"], target))
    return missing
