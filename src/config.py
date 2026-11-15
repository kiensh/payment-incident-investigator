from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    mode: Literal["mock", "live"] = "mock"
    database: Path = ROOT / "data/prepared/incidents.sqlite"
    model_base_url: str = "http://localhost:8765/cc"
    model_name: str = ""
    model_api_key: str = field(default="", repr=False)
    budget_path: Path = ROOT / "artifacts/bridge-budget.sqlite"
    budget_scope: Literal["persistent", "session"] = "persistent"
    request_limit: int = 150
    request_timeout: float = 60
    max_model_calls: int = 6

    def __post_init__(self) -> None:
        if self.mode not in ("mock", "live"):
            raise ValueError("INVESTIGATOR_MODE must be mock or live.")
        if self.budget_scope not in ("persistent", "session"):
            raise ValueError("INVESTIGATOR_BUDGET_SCOPE must be persistent or session.")
        try:
            url = urlsplit(self.model_base_url)
            port = url.port  # Accessing .port validates numeric syntax and range.
        except ValueError as exc:
            raise ValueError("ANTHROPIC_BASE_URL has an invalid host or port.") from exc
        if (url.hostname not in ("localhost", "127.0.0.1", "::1")
                or url.scheme not in ("http", "https")
                or url.username is not None or url.password is not None
                or url.query or url.fragment or url.path not in ("", "/", "/cc", "/cc/")
                or port == 0 or any(ord(char) < 33 for char in self.model_base_url)):
            raise ValueError("ANTHROPIC_BASE_URL must be a loopback HTTP(S) URL with a valid port, optional /cc prefix, and no credentials, query or fragment.")
        if not 1 <= self.request_limit <= 150:
            raise ValueError("INVESTIGATOR_REQUEST_LIMIT must be between 1 and 150.")
        if not 1 <= self.max_model_calls <= 6 or not 1 <= self.request_timeout <= 120:
            raise ValueError("Model loop and timeout must be bounded.")
        if self.mode == "live" and not self.model_name.strip():
            raise ValueError("Set ANTHROPIC_MODEL to an identifier supported by the configured model API.")

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(ROOT / ".env", override=False)
        mode = os.getenv("INVESTIGATOR_MODE", "mock")
        if mode not in ("mock", "live"):
            raise ValueError("INVESTIGATOR_MODE must be mock or live.")
        scope = os.getenv("INVESTIGATOR_BUDGET_SCOPE", "persistent")
        if scope not in ("persistent", "session"):
            raise ValueError("INVESTIGATOR_BUDGET_SCOPE must be persistent or session.")
        return cls(
            mode="live" if mode == "live" else "mock",
            database=Path(os.getenv("INVESTIGATOR_DB", str(ROOT / "data/prepared/incidents.sqlite"))),
            model_base_url=os.getenv("ANTHROPIC_BASE_URL", "http://localhost:8765/cc"),
            model_name=os.getenv("ANTHROPIC_MODEL", ""),
            model_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            budget_path=Path(os.getenv("INVESTIGATOR_BUDGET_PATH", str(ROOT / "artifacts/bridge-budget.sqlite"))),
            budget_scope="session" if scope == "session" else "persistent",
            request_limit=int(os.getenv("INVESTIGATOR_REQUEST_LIMIT", "150")),
            request_timeout=float(os.getenv("INVESTIGATOR_TIMEOUT_SECONDS", "60")),
        )
