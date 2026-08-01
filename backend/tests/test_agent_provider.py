"""Regression tests for the contextual Operator's LM Studio adapter."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.services.agent.provider import (
    AgentProviderError,
    OpenAICompatibleAgentProvider,
)


def _settings(*, storage_root: Path | None = None) -> Settings:
    return Settings(
        ai_agent_enabled=True,
        ai_model="grok",
        ai_base_url="http://127.0.0.1:1234/v1",
        **({"storage_root": storage_root} if storage_root is not None else {}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("thinking_enabled", "expected_reasoning_effort"),
    [(True, "medium"), (False, "none")],
)
async def test_complete_action_uses_live_catalog_model_and_requested_thinking_mode(
    thinking_enabled: bool,
    expected_reasoning_effort: str,
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive",
                            "owned_by": "organization_owner",
                        }
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/v1/chat/completions":
            request_body = json.loads(request.content)
            assert request_body["model"] == (
                "qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive"
            )
            assert request_body["reasoning_effort"] == expected_reasoning_effort
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"assistant_text": "Chat works.", "tool_call": None}
                                )
                            }
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = OpenAICompatibleAgentProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )
    result = await provider.complete_action(
        messages=[{"role": "user", "content": "Hello"}],
        response_schema={"type": "object"},
        idempotency_key="operator-regression",
        thinking_enabled=thinking_enabled,
    )

    assert result == {"assistant_text": "Chat works.", "tool_call": None}
    assert [request.url.path for request in requests] == [
        "/v1/models",
        "/v1/chat/completions",
    ]


@pytest.mark.asyncio
async def test_complete_action_exposes_bounded_lm_studio_error_message():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "live-model"}]})
        return httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "message": "No models loaded. Please load a model.",
                }
            },
        )

    provider = OpenAICompatibleAgentProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AgentProviderError) as exc_info:
        await provider.complete_action(
            messages=[{"role": "user", "content": "Hello"}],
            response_schema={"type": "object"},
            idempotency_key="operator-error-regression",
        )

    assert str(exc_info.value) == (
        "LM Studio request failed with HTTP 400: No models loaded. Please load a model."
    )


@pytest.mark.asyncio
async def test_complete_action_prefers_persisted_selection_over_catalog_order(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "lm-studio-model-selection.json").write_text(
        json.dumps(
            {
                "schema_name": "runtime.lm_studio_model_selection.v1",
                "model_id": "selected-model",
                "key": "selected-model",
                "display_name": "Selected model",
                "filename": "selected-model.gguf",
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "first-but-not-selected"},
                        {"id": "selected-model"},
                    ]
                },
            )
        if request.method == "POST" and request.url.path == "/v1/chat/completions":
            assert json.loads(request.content)["model"] == "selected-model"
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"assistant_text": "Selected.", "tool_call": None}
                                )
                            }
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = OpenAICompatibleAgentProvider(
        _settings(storage_root=tmp_path),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.complete_action(
        messages=[{"role": "user", "content": "Hello"}],
        response_schema={"type": "object"},
        idempotency_key="persisted-selection-regression",
    )

    assert result == {"assistant_text": "Selected.", "tool_call": None}
