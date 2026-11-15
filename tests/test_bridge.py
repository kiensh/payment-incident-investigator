import json
from pathlib import Path

import anthropic
import httpx2
import pytest

from src.agent.bridge import BridgeClient, BridgeFailure, numeric_usage
from src.agent.budget import RequestBudget
from src.config import Settings


def make_client(tmp_path: Path, handler):
    settings = Settings(mode="live", bridge_model="claude-opus-5.5", budget_path=tmp_path / "budget.sqlite")
    budget = RequestBudget(settings.budget_path, 5)
    client = BridgeClient(settings, budget)
    return client, budget, handler


async def test_sdk_uses_verified_route_placeholder_auth_and_no_hidden_retries(tmp_path: Path):
    requests = []

    def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        assert str(request.url) == "http://localhost:8765/cc/v1/messages"
        assert request.headers["x-api-key"] == "copilot-bridge"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert body["model"] == "claude-opus-5.5"
        assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert not body.get("fallbacks")
        return httpx2.Response(503, json={"error": {"type": "api_error", "message": "must-not-be-reflected"}})

    client, budget, _ = make_client(tmp_path, handler)
    await client.client.close()
    client.client = anthropic.AsyncAnthropic(
        api_key="copilot-bridge", base_url="http://localhost:8765/cc", max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    with pytest.raises(BridgeFailure) as caught:
        await client.complete("stable", [{"role": "user", "content": "hello"}], [])
    assert "must-not-be-reflected" not in str(caught.value)
    assert len(requests) == budget.count() == client.requests == 1
    assert client.retries == 0
    await client.close()


async def test_streaming_usage_is_not_double_counted(tmp_path: Path):
    message = {"id": "msg_fixture", "type": "message", "role": "assistant", "model": "claude-opus-5.5",
               "content": [], "stop_reason": None, "stop_sequence": None,
               "usage": {"input_tokens": 10, "output_tokens": 0, "cache_read_input_tokens": 100,
                         "cache_creation_input_tokens": 20}}
    events = [
        ("message_start", {"type": "message_start", "message": message}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "{}"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 2}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    payload = "".join(f"event: {name}\ndata: {json.dumps(event)}\n\n" for name, event in events)

    def handler(request):
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, text=payload)

    client, budget, _ = make_client(tmp_path, handler)
    await client.client.close()
    client.client = anthropic.AsyncAnthropic(
        api_key="copilot-bridge", base_url="http://localhost:8765/cc", max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    result = await client.complete("stable", [{"role": "user", "content": "hello"}], [])
    assert result.stop_reason == "end_turn"
    assert client.usage[0]["input_tokens"] == 10
    assert client.usage[0]["output_tokens"] == 2
    assert client.usage[0]["cache_read_input_tokens"] == 100
    assert budget.count() == 1
    await client.close()


def test_usage_drops_untrusted_strings_keys_and_nonfinite_numbers():
    assert numeric_usage({"input_tokens": 9, "message": "private", "secret-in-a-key": 17,
                          "output_tokens": float("nan"), "cache_creation_input_tokens": float("inf"),
                          "total_tokens": -1, "output_tokens_details": {"text": "hidden", "thinking_tokens": 3}}) == {
        "input_tokens": 9, "output_tokens_details": {"thinking_tokens": 3}}


def test_inherited_custom_headers_fail_closed_before_transport(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "Authorization: Bearer synthetic-test-secret\nX-Api-Key: synthetic-test-key\nX-Other: synthetic-test-value")
    settings = Settings(mode="live", bridge_model="claude-opus-5.5", budget_path=tmp_path / "budget.sqlite")
    budget = RequestBudget(settings.budget_path)
    with pytest.raises(BridgeFailure) as caught:
        BridgeClient(settings, budget)
    assert "synthetic-test-secret" not in str(caught.value)
    assert "custom headers" in str(caught.value)
    assert not caught.value.retryable
    assert budget.count() == 0
