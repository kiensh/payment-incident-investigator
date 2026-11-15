"""Independent checks of rendered monetary claims against cited observations.

This is intentionally not the production analyzer. It checks a small supported
claim grammar; other conclusions still need the manual incident oracle/review.
"""
import re
from decimal import Decimal, InvalidOperation

SECTIONS = ("confirmed_facts", "discrepancies", "hypotheses", "unknowns", "next_checks")
MONEY = r"([0-9]+(?:\.[0-9]+)?) ([A-Z]{3}|\(currency unknown\))"


def audit_support(result: dict) -> list[str]:
    errors = []
    evidence = {record["id"]: record for record in result["evidence"]}
    for section in SECTIONS:
        for claim in result[section]:
            refs = [evidence[eid] for eid in claim["evidence_ids"] if eid in evidence]
            rule = claim["rule_id"]
            if rule not in ("capture_success", "authorization_observed"):
                continue
            kind = "Capture" if rule == "capture_success" else "Authorization"
            identity = "capture_id" if kind == "Capture" else "authorization_id"
            if not refs or any(record["kind"] != kind for record in refs):
                errors.append(f"unsupported {kind} references: {claim['id']}")
                continue
            identities = {record["data"][identity] for record in refs}
            statuses = {record["data"]["status"] for record in refs}
            amounts = {(Decimal(record["data"]["amount"]), record["data"]["currency"]) for record in refs}
            if rule == "capture_success":
                match = re.match(r"^Provider capture (\S+) succeeded for " + MONEY + r"\.", claim["text"])
                status = "succeeded"
            else:
                match = re.match(r"^Authorization (\S+) is recorded as (\S+) for " + MONEY + r";", claim["text"])
                status = match.group(2) if match else None
                if "(amount unresolved)" in claim["text"]:
                    unresolved = re.match(r"^Authorization (\S+) is recorded as (\S+) \(amount unresolved\);", claim["text"])
                    if (not unresolved or identities != {unresolved.group(1)}
                            or statuses != {unresolved.group(2)} or len(amounts) < 2):
                        errors.append(f"unsupported authorization uncertainty: {claim['id']}")
                    continue
            if not match:
                errors.append(f"unrecognized monetary claim grammar: {claim['id']}")
                continue
            amount_group = 2 if kind == "Capture" else 3
            try:
                amount = Decimal(match.group(amount_group))
            except InvalidOperation:
                errors.append(f"invalid claimed amount: {claim['id']}")
                continue
            currency_text = match.group(amount_group + 1)
            currency = None if currency_text == "(currency unknown)" else currency_text
            if identities != {match.group(1)} or statuses != {status} or amounts != {(amount, currency)}:
                errors.append(f"monetary claim contradicted by cited evidence: {claim['id']}")

    # The public summary must consist of complete cited findings, never new prose.
    candidates = []
    for section in ("confirmed_facts", "discrepancies", "unknowns"):
        for claim in result[section]:
            citation = " [" + ", ".join(claim["evidence_ids"]) + "]" if claim["evidence_ids"] else ""
            candidates.append(claim["text"] + citation)
    remaining = result.get("summary", "")
    count = 0
    while remaining:
        match_text = next((text for text in sorted(candidates, key=len, reverse=True)
                           if remaining == text or remaining.startswith(text + " ")), None)
        if match_text is None:
            errors.append("summary contains prose not grounded in supplied findings")
            break
        remaining = remaining[len(match_text):].lstrip()
        count += 1
    if not 1 <= count <= 4:
        errors.append("summary must select one to four grounded findings")
    return errors
