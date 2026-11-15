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
    bridge_url: str = "http://localhost:8765"
    bridge_model: str = ""
    bridge_token: str = field(default="", repr=False)
    budget_path: Path = ROOT / "artifacts/bridge-budget.sqlite"
    request_limit: int = 150
    request_timeout: float = 60
    max_model_calls: int = 6

    def __post_init__(self) -> None:
        if self.mode not in ("mock", "live"):
            raise ValueError("INVESTIGATOR_MODE must be mock or live.")
        try:
            url = urlsplit(self.bridge_url)
            port = url.port  # Accessing .port validates numeric syntax and range.
        except ValueError as exc:
            raise ValueError("Bridge URL has an invalid host or port.") from exc
        if (url.hostname not in ("localhost", "127.0.0.1", "::1")
                or url.scheme not in ("http", "https")
                or url.username is not None or url.password is not None
                or url.query or url.fragment or url.path not in ("", "/")
                or port == 0 or any(ord(char) < 33 for char in self.bridge_url)):
            raise ValueError("Bridge URL must be a loopback HTTP(S) origin with a valid port and no credentials or path.")
        if not 1 <= self.request_limit <= 150:
            raise ValueError("Bridge request limit must be between 1 and 150.")
        if not 1 <= self.max_model_calls <= 6 or not 1 <= self.request_timeout <= 120:
            raise ValueError("Model loop and timeout must be bounded.")
        if self.mode == "live" and not self.bridge_model.strip():
            raise ValueError("Set BRIDGE_MODEL to an identifier reported by your existing bridge.")

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(ROOT / ".env", override=False)
        mode = os.getenv("INVESTIGATOR_MODE", "mock")
        if mode not in ("mock", "live"):
            raise ValueError("INVESTIGATOR_MODE must be mock or live.")
        return cls(
            mode="live" if mode == "live" else "mock",
            database=Path(os.getenv("INVESTIGATOR_DB", str(ROOT / "data/prepared/incidents.sqlite"))),
            bridge_url=os.getenv("BRIDGE_URL", "http://localhost:8765"),
            bridge_model=os.getenv("BRIDGE_MODEL", ""),
            bridge_token=os.getenv("BRIDGE_TOKEN", ""),
            budget_path=Path(os.getenv("BRIDGE_BUDGET_PATH", str(ROOT / "artifacts/bridge-budget.sqlite"))),
            request_limit=int(os.getenv("BRIDGE_REQUEST_LIMIT", "150")),
            request_timeout=float(os.getenv("BRIDGE_TIMEOUT_SECONDS", "60")),
        )
