from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

RUNBOOK_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "runbooks"


class Runbook(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    version: str
    title: str
    categories: tuple[str, ...]
    applicability: str
    required_evidence: tuple[str, ...]
    steps: tuple[str, ...]
    supported_conclusions: tuple[str, ...]
    escalation: tuple[str, ...]
    sources: tuple[str, ...]

    def public(self) -> dict:
        return self.model_dump(mode="json", exclude={"categories"})


@lru_cache(maxsize=32)
def _parse(content_hash: str, content: bytes) -> Runbook:
    # Hash and versioned content, never an investigation or mutable payment, are cached.
    return Runbook.model_validate(yaml.safe_load(content))


class RunbookStore:
    def __init__(self, directory: Path = RUNBOOK_DIR) -> None:
        self.directory = directory
        self.cache_hits = 0
        self.cache_misses = 0

    def retrieve(self, query: str, limit: int = 3) -> list[Runbook]:
        words = set(re.findall(r"[a-z0-9]+", query.lower()))
        ranked: list[tuple[int, str, Runbook]] = []
        for path in sorted(self.directory.glob("*.yaml")):
            content = path.read_bytes()
            before = _parse.cache_info()
            book = _parse(hashlib.sha256(content).hexdigest(), content)
            after = _parse.cache_info()
            self.cache_hits += after.hits - before.hits
            self.cache_misses += after.misses - before.misses
            exact = 100 if query.strip().lower() == book.id else 0
            category = 10 * len(words.intersection(book.categories))
            body = set(re.findall(r"[a-z0-9]+", f"{book.title} {book.applicability}".lower()))
            score = exact + category + len(words.intersection(body))
            if score:
                ranked.append((score, book.id, book))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        return [row[2] for row in ranked[:limit]]
