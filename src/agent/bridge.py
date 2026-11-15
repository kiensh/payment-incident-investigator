from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

import anthropic
from anthropic.types import Message, MessageParam, ToolParam

from src.agent.budget import RequestBudget
from src.config import Settings


class BridgeFailure(RuntimeError):
    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def numeric_usage(value: Any) -> dict:
    """Expose numeric accounting only, never arbitrary provider strings or raw responses."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > 80:
            continue
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            result[key] = item
        elif isinstance(item, dict):
            result[key] = numeric_usage(item)
    return result


class BridgeClient:
    def __init__(self, settings: Settings, budget: RequestBudget) -> None:
        self.settings = settings
        self.budget = budget
        self.model = settings.bridge_model
        self.requests = 0
        self.retries = 0
        self.usage: list[dict] = []
        # This bridge ignores client auth and owns its upstream OAuth credentials.
        # Explicit public sentinel prevents unrelated SDK environment auth discovery.
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.bridge_token or "copilot-bridge",
            base_url=settings.bridge_url.rstrip("/") + "/cc",
            max_retries=0,
            timeout=settings.request_timeout,
            http_client=anthropic.DefaultAsyncHttpxClient(trust_env=False, follow_redirects=False),
        )

    async def close(self) -> None:
        await self.client.close()

    async def complete(self, system: str, messages: list[MessageParam], tools: list[ToolParam]) -> Message:
        request_id = self.budget.reserve()
        self.requests += 1
        started = perf_counter()
        status = "infrastructure_error"
        usage: dict = {}
        try:
            async with asyncio.timeout(self.settings.request_timeout):
                async with self.client.messages.stream(
                    model=self.model,
                    max_tokens=4096,
                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                    messages=messages,
                    tools=tools,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "medium"},
                ) as stream:
                    message = await stream.get_final_message()
            usage = numeric_usage(message.usage.model_dump())
            copilot = numeric_usage(getattr(message, "copilot_usage", None))
            if copilot:
                usage["copilot_usage"] = copilot
            self.usage.append(usage)
            status = "completed" if message.stop_reason in ("end_turn", "tool_use") else "incomplete"
            return message
        except anthropic.AuthenticationError as exc:
            raise BridgeFailure("The local bridge's existing authentication is unavailable. No alternative provider was used.", False) from exc
        except anthropic.NotFoundError as exc:
            raise BridgeFailure("The configured bridge endpoint or model is unavailable. Check bridge model discovery.", False) from exc
        except anthropic.RateLimitError as exc:
            raise BridgeFailure("The bridge is rate-limited. Wait before retrying this investigation.") from exc
        except anthropic.APIStatusError as exc:
            raise BridgeFailure(f"The local bridge returned HTTP {exc.status_code}; no financial action occurred.", exc.status_code >= 500) from exc
        except (anthropic.APIConnectionError, TimeoutError) as exc:
            raise BridgeFailure("The local bridge could not complete the request in time. No alternative provider was used.") from exc
        except (ValueError, anthropic.APIResponseValidationError) as exc:
            raise BridgeFailure("The bridge returned an invalid or incomplete response.") from exc
        finally:
            self.budget.finish(request_id, status, round((perf_counter() - started) * 1000, 2), usage)
