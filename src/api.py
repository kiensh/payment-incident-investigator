from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.agent.bridge import BridgeClient, BridgeFailure
from src.agent.budget import BudgetExceeded, RequestBudget
from src.agent.investigator import AgentFailure, investigate
from src.config import ROOT, Settings
from src.domain.models import Analysis, Evidence
from src.storage.repository import Repository


def error(status: int, code: str, message: str, retryable: bool = False,
          diagnostics: dict | None = None) -> JSONResponse:
    detail: dict = {"code": code, "message": message, "retryable": retryable}
    if diagnostics is not None:
        detail["diagnostics"] = diagnostics
    return JSONResponse({"error": detail}, status_code=status)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int = 16384) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body.extend(event.get("body", b""))
            if len(body) > self.limit:
                await error(413, "input_too_large", "Request body exceeds the investigation input limit.")(scope, receive, send)
                return
            if not event.get("more_body", False):
                break
        sent = False

        async def limited_receive() -> Message:
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, limited_receive, send)


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    payment_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    question: str = Field(min_length=5, max_length=2000)

    @field_validator("payment_id", "question", mode="before")
    @classmethod
    def trim(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class InvestigationResponse(Analysis):
    investigation_id: str
    question: str
    mode: Literal["mock", "live"]
    synthetic: Literal[True]
    summary: str
    evidence: list[Evidence]
    data_warnings: list[str]
    runbooks: list[dict]
    technical: dict


def create_app(settings: Settings | None = None, static_dir: Path | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Payment Incident Investigator", version="0.1.0", docs_url=None, openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    repository = Repository(settings.database)
    budget = RequestBudget(settings.budget_path, settings.request_limit) if settings.mode == "live" else None
    slots = asyncio.Semaphore(2)
    app.state.settings = settings

    @app.middleware("http")
    async def local_browser_boundary(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        origin = request.headers.get("origin")
        allowed = {f"{request.url.scheme}://{request.headers.get('host', '')}",
                   "http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:4173", "http://127.0.0.1:4173"}
        if request.method == "POST" and origin and origin not in allowed:
            return error(403, "origin_rejected", "Only the local investigation workspace may submit browser requests.")
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(422, "invalid_input", "Use a payment ID containing letters, digits, underscores or hyphens, and a question of 5–2000 characters. No extra fields are accepted.")

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "mode": settings.mode, "data_ready": settings.database.is_file(),
                "model": settings.bridge_model if settings.mode == "live" else None}

    @app.get("/api/cases", response_model=None)
    async def cases() -> dict | JSONResponse:
        try:
            payments = repository.list_payments()
        except (OSError, sqlite3.Error, ValueError):
            return error(503, "data_not_ready", "Prepared evidence is unavailable. Run the offline preparation command.")
        return {"cases": [{"payment_id": p.id, "symptom": p.symptom} for p in payments], "synthetic": True}

    @app.post("/api/investigate", response_model=InvestigationResponse)
    async def run_investigation(body: InvestigationRequest) -> dict | JSONResponse:
        try:
            snapshot = repository.get_snapshot(body.payment_id)
        except (OSError, sqlite3.Error, ValueError):
            return error(503, "data_not_ready", "Prepared evidence is unavailable or invalid. Run the offline preparation command.")
        if snapshot is None:
            return error(404, "payment_not_found", "That payment ID is not in the prepared evidence.")
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.01)
        except TimeoutError:
            return error(429, "busy", "Two investigations are already running. Try again when one completes.", True)
        client: BridgeClient | None = None
        try:
            if budget is not None:
                try:
                    client = BridgeClient(settings, budget)
                except (TypeError, ValueError) as exc:
                    raise BridgeFailure("The local bridge client configuration is invalid.", False) from exc
            payment, evidence = snapshot
            return await investigate(payment, evidence, body.question, client, settings.max_model_calls)
        except BudgetExceeded:
            return error(429, "budget_exhausted", "The configured bridge request budget is exhausted. Offline mock checks remain available.")
        except BridgeFailure as exc:
            return error(502, "bridge_unavailable", str(exc), exc.retryable)
        except AgentFailure as exc:
            return error(502, "unsupported_conclusion", str(exc), True, exc.diagnostics)
        finally:
            try:
                if client is not None:
                    await client.close()
            finally:
                slots.release()

    built = static_dir if static_dir is not None else ROOT / "web/dist"
    if built.is_dir():
        app.mount("/", StaticFiles(directory=built, html=True), name="workspace")
    return app


app = create_app()
