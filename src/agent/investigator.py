from __future__ import annotations

import json
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from anthropic.types import Message, MessageParam, ToolParam, ToolResultBlockParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agent.prompts import system_prompt
from src.domain.models import Analysis, Evidence, Finding, Payment
from src.tools.session import ToolInputError, ToolSession, tool_definitions

SECTIONS = ("confirmed_facts", "discrepancies", "hypotheses", "unknowns", "next_checks")
REQUIRED_TOOLS = {"get_payment_evidence", "get_attempts_and_events", "check_inconsistencies"}


class AgentFailure(RuntimeError):
    pass


class ModelClient(Protocol):
    requests: int
    retries: int
    usage: list[dict]
    model: str

    async def complete(self, system: str, messages: list[MessageParam], tools: list[ToolParam]) -> Message: ...


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary_finding_ids: list[str] = Field(min_length=1, max_length=4)
    runbook_ids: list[str] = Field(min_length=1, max_length=4)


def _findings(analysis: Analysis, sections: tuple[str, ...] = SECTIONS) -> dict[str, Finding]:
    return {f.id: f for section in sections for f in getattr(analysis, section)}


def _validate_selection(selection: Selection, session: ToolSession) -> list[Finding]:
    if session.analysis is None:
        raise AgentFailure("The agent did not run deterministic payment checks.")
    called = {call["name"] for call in session.calls}
    if not REQUIRED_TOOLS.issubset(called) or not session.runbooks:
        raise AgentFailure("The agent did not obtain the required evidence and procedures.")
    allowed = _findings(session.analysis, ("confirmed_facts", "discrepancies", "unknowns"))
    if any(fid not in allowed for fid in selection.summary_finding_ids):
        raise AgentFailure("The model selected unsupported findings.")
    if any(rid not in session.runbooks for rid in selection.runbook_ids):
        raise AgentFailure("The model selected a procedure it did not retrieve.")
    return [allowed[fid] for fid in dict.fromkeys(selection.summary_finding_ids)]


def _render(payment: Payment, question: str, session: ToolSession, summary: list[Finding],
            mode: str, started: float, client: ModelClient | None) -> dict:
    assert session.analysis is not None
    analysis = session.analysis
    evidence_ids = {record.id for record in session.evidence}
    for finding in _findings(analysis).values():
        if not set(finding.evidence_ids).issubset(evidence_ids):
            raise AgentFailure("A deterministic finding references unavailable evidence.")
    result = analysis.model_dump(mode="json")
    warnings = list(dict.fromkeys(payment.warnings + [w for e in session.evidence for w in e.warnings]))
    result.update({
        "investigation_id": str(uuid4()), "question": question,
        "mode": mode, "synthetic": True,
        "summary": " ".join(f.text + (" [" + ", ".join(f.evidence_ids) + "]" if f.evidence_ids else "")
                            for f in summary),
        "evidence": [e.model_dump(mode="json") for e in session.evidence],
        "data_warnings": warnings,
        "runbooks": [b.public() for b in session.runbooks.values()],
        "technical": {
            "tool_calls": session.calls, "applied_rules": analysis.applied_rules,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
            "model_requests": client.requests if client else 0,
            "retries": client.retries if client else 0,
            "usage": client.usage if client else [],
            "model": client.model if client else None,
            "cache": {
                "runbook_cache": f"{session.store.cache_hits} parsed-content hits; {session.store.cache_misses} misses",
                "provider_cache": "Stable system prefix requests ephemeral caching in live mode; provider-reported counters only, no claimed cost savings.",
            },
        },
    })
    return result


async def investigate(payment: Payment, evidence: list[Evidence], question: str,
                      client: ModelClient | None = None, max_calls: int = 5) -> dict:
    started = perf_counter()
    if len(evidence) > 250:
        raise AgentFailure("Evidence exceeds this MVP's bounded per-payment limit.")
    session = ToolSession(payment, evidence)
    if client is None:
        for name in ("get_payment_evidence", "get_attempts_and_events", "check_inconsistencies"):
            session.execute(name, {"payment_id": payment.id})
        session.execute("retrieve_runbooks", {"query": "payment webhook missing support", "limit": 4})
        assert session.analysis is not None
        analysis = session.analysis
        summary = (analysis.confirmed_facts[:1] + analysis.discrepancies[:1] + analysis.unknowns[:1])
        if not summary:
            raise AgentFailure("No supported findings are available for a summary.")
        return _render(payment, question, session, summary, "mock", started, None)

    system = system_prompt()
    messages: list[MessageParam] = [
        {"role": "user", "content": json.dumps({"payment_id": payment.id, "customer_question": question})},
    ]
    tools = tool_definitions()
    for _ in range(max_calls):
        response = await client.complete(system, messages, tools)
        if response.stop_reason not in ("end_turn", "tool_use"):
            raise AgentFailure("The model stopped before a complete supported conclusion; no incomplete tools were executed.")
        # Preserve complete SDK blocks in memory for replay, including signed thinking.
        # Only actual tool calls/results and validated findings enter public traces.
        messages.append({"role": "assistant", "content": response.content})
        tool_calls = [block for block in response.content if block.type == "tool_use"]
        if tool_calls:
            if len(tool_calls) > 8 or len(session.calls) + len(tool_calls) > 20:
                raise AgentFailure("The model exceeded the bounded tool-call limit.")
            results: list[ToolResultBlockParam] = []
            for call in tool_calls:
                is_error = False
                try:
                    if not isinstance(call.input, dict):
                        raise ToolInputError("Tool arguments must be an object.")
                    result = session.execute(call.name, call.input)
                except ToolInputError as exc:
                    result = {"error": str(exc)}
                    is_error = True
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": json.dumps(result), "is_error": is_error})
            messages.append({"role": "user", "content": results})
            continue
        content = "".join(block.text for block in response.content if block.type == "text")
        try:
            selection = Selection.model_validate_json(content)
            summary = _validate_selection(selection, session)
        except (ValidationError, AgentFailure):
            messages.append({"role": "user", "content": "Conclusion validation failed. Obtain all required evidence and a runbook, then return only the requested JSON using exact finding and runbook IDs from tool results."})
            continue
        return _render(payment, question, session, summary, "live", started, client)
    raise AgentFailure("The agent reached its bounded step limit without a supported conclusion. Retry the investigation or inspect the evidence offline.")
