from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Literal

from anthropic.types import ToolParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.domain.models import Analysis, Evidence, Payment
from src.domain.rules import analyze
from src.tools.runbooks import Runbook, RunbookStore


class PaymentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    payment_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class EventArgs(PaymentArgs):
    kind: Literal["all", "PaymentAttempt", "Authorization", "Capture", "ProviderEvent",
                  "WebhookDelivery", "ApplicationStatusObservation"] = "all"


class RunbookArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=3, ge=1, le=4)


TOOL_TYPES: dict[str, type[BaseModel]] = {
    "get_payment_evidence": PaymentArgs,
    "get_attempts_and_events": EventArgs,
    "check_inconsistencies": PaymentArgs,
    "retrieve_runbooks": RunbookArgs,
}
TOOL_DESCRIPTIONS = {
    "get_payment_evidence": "Read the selected payment's original context, quality warnings and provider payment records. Original source status is not lifecycle proof.",
    "get_attempts_and_events": "Read selected payment attempts, authorizations, captures, events, webhook deliveries and application observations; never infer event order from arrival order.",
    "check_inconsistencies": "Run authoritative deterministic rules on this investigation's complete evidence snapshot. Returns facts, gaps, conditional hypotheses and safe checks with citations. Always run before concluding.",
    "retrieve_runbooks": "Retrieve short versioned procedures by exact ID, category or keywords. Categories include payment, capture, authorization, webhook, duplicate, timestamp, missing, quality, support. No filesystem access.",
}


def tool_definitions() -> list[ToolParam]:
    return [
        {"name": name, "description": TOOL_DESCRIPTIONS[name],
         "input_schema": schema.model_json_schema()}
        for name, schema in TOOL_TYPES.items()
    ]


class ToolInputError(ValueError):
    pass


class ToolSession:
    def __init__(self, payment: Payment, evidence: list[Evidence]) -> None:
        self.payment = payment
        self.evidence = evidence
        self.analysis: Analysis | None = None
        self.runbooks: dict[str, Runbook] = {}
        self.store = RunbookStore()
        self.calls: list[dict] = []

    def execute(self, name: str, raw_arguments: str | dict) -> dict:
        start = perf_counter()
        if name not in TOOL_TYPES:
            raise ToolInputError("Unknown tool; only the four read-only tools are allowed.")
        try:
            payload = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            args = TOOL_TYPES[name].model_validate(payload)
        except (ValueError, TypeError, ValidationError) as exc:
            raise ToolInputError("Tool arguments do not match the declared schema.") from exc
        values = args.model_dump()
        if "payment_id" in values and values["payment_id"] != self.payment.id:
            raise ToolInputError("Tool access is limited to the selected payment.")
        result: dict[str, Any]
        if name == "get_payment_evidence":
            result = {
                "payment": self.payment.model_dump(mode="json"),
                "records": [e.model_dump(mode="json") for e in self.evidence if e.kind == "Payment"],
            }
        elif name == "get_attempts_and_events":
            kind = values["kind"]
            result = {"records": [e.model_dump(mode="json") for e in self.evidence
                                  if e.kind != "Payment" and (kind == "all" or kind == e.kind)]}
        elif name == "check_inconsistencies":
            self.analysis = analyze(self.payment, self.evidence)
            result = self.analysis.model_dump(mode="json")
        else:
            books = self.store.retrieve(values["query"], values["limit"])
            self.runbooks.update({book.id: book for book in books})
            result = {"runbooks": [book.public() for book in books]}
        self.calls.append({"name": name, "arguments": values, "result": result,
                           "duration_ms": round((perf_counter() - start) * 1000, 2)})
        return result
