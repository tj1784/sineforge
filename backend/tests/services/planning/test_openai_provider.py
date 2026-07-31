"""Tests for the OpenAI planning provider adapter and registry."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from backend.app.core.config import Settings
from backend.app.schemas.orchestration import (
    FailureCategory,
    LogicalModelProfile,
    PlanningContext,
    PlanningTaskType,
    ProviderRequestContract,
)
from backend.app.services.planning.errors import PlanningError, PlanningErrorCode
from backend.app.services.planning.openai_provider import OpenAIPlanningProvider
from backend.app.services.planning.provider import (
    MockPlanningProvider,
    TransportError,
    get_provider,
)
from backend.app.services.planning.provider_registry import (
    ProviderAvailability,
    build_provider_registry,
    describe_providers,
    refuse_local_cli_registration,
    resolve_provider,
)


def _context(**overrides: Any) -> PlanningContext:
    base = dict(
        story_id=uuid4(),
        title="Test Story",
        base_story="A short story about a lighthouse keeper and the sea.",
        target_duration_sec=48.0,
        logline="A keeper faces the storm.",
        tone="dramatic",
        visual_style="cinematic coastal",
        characters=[{"name": "Keeper", "role": "lead"}],
    )
    base.update(overrides)
    return PlanningContext(**base)


def _request(**overrides: Any) -> ProviderRequestContract:
    base = dict(
        task_type=PlanningTaskType.story_structure,
        logical_model=LogicalModelProfile.luna,
        resolved_model="gpt-4o-mini",
        provider_identifier="openai",
        context=_context(),
        constraints={},
        previous_output=None,
        repair_instructions=[],
        attempt_number=1,
        idempotency_key=f"idem_{uuid4().hex[:16]}",
    )
    base.update(overrides)
    return ProviderRequestContract(**base)


def _openai_success_body(payload: dict[str, Any], *, usage: dict[str, int] | None = None) -> bytes:
    envelope = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(payload),
                },
            }
        ],
        "usage": usage
        or {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33},
    }
    return json.dumps(envelope).encode("utf-8")


def _openai_text_body(content: str, *, usage: dict[str, int] | None = None) -> bytes:
    envelope = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                },
            }
        ],
        "usage": usage
        or {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33},
    }
    return json.dumps(envelope).encode("utf-8")


def _mock_client(response: httpx.Response) -> MagicMock:
    client = MagicMock()
    client.post.return_value = response
    client.close = MagicMock()
    return client


def _provider_with_client(client: MagicMock, **kwargs: Any) -> OpenAIPlanningProvider:
    defaults = dict(
        api_key="sk-test-key-not-real",
        transport_retries=1,
        timeout_sec=5.0,
        wall_time_sec=30.0,
        max_response_bytes=64_000,
        http_client_factory=lambda: client,
    )
    defaults.update(kwargs)
    return OpenAIPlanningProvider(**defaults)


def test_settings_logical_models_and_flags() -> None:
    settings = Settings(
        openai_planning_enabled=True,
        openai_api_key=SecretStr("sk-test"),
        openai_logical_model_luna="gpt-4o-mini",
        openai_logical_model_terra="gpt-4o",
        openai_logical_model_sol="gpt-4.1",
        openai_timeout_sec=45.0,
        openai_wall_time_sec=90.0,
        openai_transport_retries=2,
        openai_max_response_bytes=10000,
        openai_repair_instruction_limit=5,
    )
    assert settings.openai_configured is True
    assert settings.openai_logical_model_luna == "gpt-4o-mini"
    assert settings.openai_logical_model_terra == "gpt-4o"
    assert settings.openai_logical_model_sol == "gpt-4.1"
    assert settings.openai_timeout_sec == 45.0
    assert settings.openai_wall_time_sec == 90.0
    assert settings.openai_transport_retries == 2
    assert settings.openai_max_response_bytes == 10000
    # SecretStr does not leak via plain str of settings fields in dumps used for storage.
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test"


def test_settings_reject_executable_model_ids() -> None:
    with pytest.raises(ValidationError):
        Settings(openai_logical_model_luna="C:\\Windows\\System32\\cmd.exe")
    with pytest.raises(ValidationError):
        Settings(openai_logical_model_sol="powershell -Command Get-Process")
    with pytest.raises(ValidationError):
        Settings(openai_base_url="file:///tmp/evil")


def test_settings_disabled_without_key() -> None:
    settings = Settings(openai_planning_enabled=True, openai_api_key=None)
    assert settings.openai_configured is False
    settings2 = Settings(openai_planning_enabled=False, openai_api_key=SecretStr("sk-x"))
    assert settings2.openai_configured is False


def test_mock_remains_default_when_openai_not_configured() -> None:
    settings = Settings(openai_planning_enabled=False)
    registry = build_provider_registry(settings)
    assert MockPlanningProvider.identifier in registry
    assert OpenAIPlanningProvider.identifier not in registry
    provider = get_provider("mock", registry)
    assert isinstance(provider, MockPlanningProvider)


def test_registry_marks_stubs_not_implemented(tmp_path) -> None:
    settings = Settings(
        openai_planning_enabled=False,
        sulphur_planning_enabled=False,
        qwen_model_path=tmp_path / "missing-qwen.gguf",
    )
    status = {d.provider_identifier: d.availability_status for d in describe_providers(settings)}
    assert status["mock"] == ProviderAvailability.available
    assert status["openai"] == ProviderAvailability.not_configured
    assert status["anthropic"] == ProviderAvailability.not_implemented
    assert status["xai"] == ProviderAvailability.not_implemented
    assert status["qwen"] == ProviderAvailability.not_configured
    assert status["local_cli"] == ProviderAvailability.not_implemented
    assert status["custom"] == ProviderAvailability.not_implemented


def test_resolve_openai_not_configured() -> None:
    settings = Settings(openai_planning_enabled=False)
    with pytest.raises(PlanningError) as exc:
        resolve_provider("openai", settings=settings)
    assert exc.value.code == PlanningErrorCode.ROUTING_FAILED
    assert exc.value.details.get("availability_status") == ProviderAvailability.not_configured.value


def test_resolve_anthropic_not_implemented() -> None:
    with pytest.raises(PlanningError) as exc:
        resolve_provider("anthropic")
    assert exc.value.code == PlanningErrorCode.ROUTING_FAILED
    assert "not implemented" in exc.value.message.lower()


def test_local_cli_refuses_shell_and_paths() -> None:
    with pytest.raises(PlanningError) as exc:
        refuse_local_cli_registration(command="ffmpeg -i in.mp4", executable_path="/usr/bin/ffmpeg")
    assert exc.value.code == PlanningErrorCode.ROUTING_FAILED
    assert "shell" in exc.value.message.lower() or "executable" in exc.value.message.lower()

    with pytest.raises(PlanningError):
        resolve_provider(
            "local_cli",
            registration_options={"shell_command": "echo pwned"},
        )

    with pytest.raises(PlanningError):
        resolve_provider("custom")


def test_openai_success_structured_output_and_hashes() -> None:
    payload = {
        "summary": "Three-act structure",
        "acts": [
            {"name": "Setup", "target_pct": 0.25},
            {"name": "Confrontation", "target_pct": 0.5},
            {"name": "Resolution", "target_pct": 0.25},
        ],
        "target_duration_sec": 48.0,
    }
    response = httpx.Response(
        200,
        content=_openai_success_body(payload),
        headers={"x-request-id": "req_abc"},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    client = _mock_client(response)
    provider = _provider_with_client(client)
    req = _request(logical_model=LogicalModelProfile.terra)

    result = provider.invoke(req)

    assert result.status == "succeeded"
    assert result.payload["summary"] == "Three-act structure"
    assert result.usage.get("request_hash")
    assert result.usage.get("response_hash")
    assert result.usage.get("logical_model") == "terra"
    assert result.usage.get("resolved_model") == provider.model_terra
    assert result.usage.get("provider_request_id") == "req_abc"
    # No credential leakage in usage or payload.
    dumped = json.dumps(result.model_dump(mode="json"))
    assert "sk-test-key-not-real" not in dumped
    assert "api_key" not in result.payload

    # Idempotency-Key header set; Authorization present on wire but not in result.
    kwargs = client.post.call_args.kwargs
    assert kwargs["headers"]["Idempotency-Key"] == req.idempotency_key
    assert kwargs["headers"]["Authorization"].startswith("Bearer ")

    # Body uses config-mapped terra model, not an executable path.
    sent = kwargs["json"]
    assert sent["model"] == provider.model_terra
    assert "response_format" in sent
    assert sent["response_format"]["type"] == "json_schema"


def test_openai_logical_model_mapping() -> None:
    provider = OpenAIPlanningProvider(
        api_key="sk-test",
        model_luna="gpt-4o-mini",
        model_terra="gpt-4o",
        model_sol="gpt-4.1",
    )
    assert provider.resolve_logical_model(LogicalModelProfile.luna) == "gpt-4o-mini"
    assert provider.resolve_logical_model(LogicalModelProfile.terra) == "gpt-4o"
    assert provider.resolve_logical_model(LogicalModelProfile.sol) == "gpt-4.1"


def test_idempotent_replay_skips_second_http_call() -> None:
    payload = {
        "summary": "Structure",
        "acts": [{"name": "A", "target_pct": 1.0}],
        "target_duration_sec": 48.0,
    }
    response = httpx.Response(
        200,
        content=_openai_success_body(payload),
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    client = _mock_client(response)
    provider = _provider_with_client(client)
    req = _request(idempotency_key="idem_stable_key_001")

    first = provider.invoke(req)
    second = provider.invoke(req)

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert second.usage.get("idempotent_replay") is True
    assert client.post.call_count == 1


def test_transport_error_on_timeout_is_retryable_signal() -> None:
    client = MagicMock()
    client.post.side_effect = httpx.TimeoutException("timeout")
    provider = _provider_with_client(client, transport_retries=0)

    with pytest.raises(TransportError):
        provider.invoke(_request())


def test_bounded_transport_retries_then_raise() -> None:
    client = MagicMock()
    client.post.side_effect = httpx.ConnectError("boom")
    provider = _provider_with_client(client, transport_retries=2)

    with pytest.raises(TransportError):
        provider.invoke(_request())
    assert client.post.call_count == 3  # initial + 2 retries


def test_transient_http_429_retries_then_raises() -> None:
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    transient = httpx.Response(429, content=b'{"error":{"message":"rate"}}', request=req_obj)
    client = _mock_client(transient)
    provider = _provider_with_client(client, transport_retries=1)

    with pytest.raises(TransportError):
        provider.invoke(_request())
    assert client.post.call_count == 2


def test_schema_rejection_http_400_not_retried() -> None:
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    bad = httpx.Response(400, content=b'{"error":{"message":"schema"}}', request=req_obj)
    client = _mock_client(bad)
    provider = _provider_with_client(client, transport_retries=3)

    result = provider.invoke(_request())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.category == FailureCategory.validation
    assert result.error.retryable is False
    assert client.post.call_count == 1  # no retries for schema rejection


def test_policy_refusal_not_retried() -> None:
    envelope = {
        "choices": [
            {
                "finish_reason": "content_filter",
                "message": {"role": "assistant", "content": None, "refusal": "policy"},
            }
        ],
        "usage": {},
    }
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(200, content=json.dumps(envelope).encode(), request=req_obj)
    client = _mock_client(response)
    provider = _provider_with_client(client, transport_retries=3)

    result = provider.invoke(_request())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.retryable is False
    assert result.finish_category == "policy_refusal"
    assert client.post.call_count == 1


def test_semantic_validation_failure_not_retried() -> None:
    # Missing required keys → validation failed, single attempt.
    payload = {"acts": [], "target_duration_sec": 48.0}  # missing summary
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(200, content=_openai_success_body(payload), request=req_obj)
    client = _mock_client(response)
    provider = _provider_with_client(client, transport_retries=3)

    result = provider.invoke(_request())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.category == FailureCategory.validation
    assert result.error.retryable is False
    assert client.post.call_count == 1


def test_chain_of_thought_payload_rejected() -> None:
    payload = {
        "summary": "ok",
        "acts": [{"name": "A", "target_pct": 1.0}],
        "target_duration_sec": 48.0,
        "chain_of_thought": "secret reasoning",
    }
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(200, content=_openai_success_body(payload), request=req_obj)
    client = _mock_client(response)
    provider = _provider_with_client(client)

    result = provider.invoke(_request())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.category == FailureCategory.validation


def test_max_response_bytes_enforced() -> None:
    huge = b"x" * 2000
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(200, content=huge, request=req_obj)
    client = _mock_client(response)
    provider = _provider_with_client(client, max_response_bytes=1000, transport_retries=0)

    result = provider.invoke(_request())
    assert result.status == "failed"
    assert result.error is not None
    assert "max_response_bytes" in result.error.message
    assert result.error.retryable is False


def test_request_body_includes_repair_instructions_bounded() -> None:
    payload = {
        "summary": "ok",
        "acts": [{"name": "A", "target_pct": 1.0}],
        "target_duration_sec": 48.0,
    }
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(200, content=_openai_success_body(payload), request=req_obj)
    client = _mock_client(response)
    provider = _provider_with_client(client, repair_instruction_limit=2)

    req = _request(
        repair_instructions=[
            "Add summary",
            "Fix acts",
            "Ignored third",
        ]
    )
    provider.invoke(req)
    sent = client.post.call_args.kwargs["json"]
    user_content = json.loads(sent["messages"][1]["content"])
    assert len(user_content["repair_instructions"]) == 2


def test_registry_includes_openai_when_configured() -> None:
    settings = Settings(
        openai_planning_enabled=True,
        openai_api_key=SecretStr("sk-live-test"),
    )
    registry = build_provider_registry(settings)
    assert "openai" in registry
    assert isinstance(registry["openai"], OpenAIPlanningProvider)
    assert isinstance(registry["mock"], MockPlanningProvider)


def test_get_provider_falls_back_to_registry_openai() -> None:
    settings = Settings(
        openai_planning_enabled=True,
        openai_api_key=SecretStr("sk-live-test"),
    )
    # Empty explicit registry → resolve via settings-backed registry path.
    provider = resolve_provider("openai", registry={}, settings=settings)
    assert isinstance(provider, OpenAIPlanningProvider)


def test_shot_list_validation_requires_positive_duration() -> None:
    payload = {
        "summary": "shots",
        "shots": [{"order_index": 0, "duration_sec": 0, "title": "bad"}],
    }
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(200, content=_openai_success_body(payload), request=req_obj)
    client = _mock_client(response)
    provider = _provider_with_client(client)

    result = provider.invoke(_request(task_type=PlanningTaskType.shot_list))
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.category == FailureCategory.validation


def test_prompt_package_request_compacts_previous_output_for_local_context() -> None:
    provider = OpenAIPlanningProvider(api_key="sk-test-key-not-real")
    long_text = "dense shot detail " * 400
    previous_output = {
        "shots": [
            {
                "order_index": 0,
                "duration_sec": 8,
                "title": "Opening beat",
                "description": long_text,
                "camera_movement": long_text,
                "key_actions": [long_text, long_text],
                "visual_cues": [long_text],
            }
        ],
        "scenes": [{"scene_id": "scene-1", "title": "Scene", "description": long_text}],
        "characters": [{"name": "Lead", "description": long_text}],
        "task:shot_list": {"summary": long_text, "shots": [{"description": long_text}]},
        "task:scene_breakdown": {"summary": long_text, "scenes": [{"description": long_text}]},
    }

    body = provider._build_request_body(
        _request(
            task_type=PlanningTaskType.prompt_package,
            previous_output=previous_output,
        ),
        resolved_model="qwen3-4b",
    )
    user_payload = json.loads(body["messages"][1]["content"])
    compact = user_payload["previous_output"]

    assert set(compact) == {"shots", "scenes", "characters"}
    assert compact["shots"][0]["description"] == long_text[:280]
    assert not any(key.startswith("task:") for key in compact)
    assert len(json.dumps(body)) < 12_000


def test_prompt_package_accepts_plain_text_prompt_response() -> None:
    prompt_text = "cinematic wide shot, natural light, full body framing, realistic motion"
    req_obj = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(200, content=_openai_text_body(prompt_text), request=req_obj)
    client = _mock_client(response)
    provider = _provider_with_client(client)

    result = provider.invoke(
        _request(
            task_type=PlanningTaskType.prompt_package,
            previous_output={
                "shots": [
                    {"order_index": 0, "title": "Opening"},
                    {"order_index": 1, "title": "Second beat"},
                ]
            },
        )
    )

    assert result.status == "succeeded"
    assert result.finish_category == "plain_text_prompt_wrapped"
    assert result.payload["prompt_packages"] == [
        {
            "shot_order_index": 0,
            "image_prompt": prompt_text,
            "video_prompt": prompt_text,
            "source_format": "plain_text_response",
            "shot_title": "Opening",
        },
        {
            "shot_order_index": 1,
            "image_prompt": prompt_text,
            "video_prompt": prompt_text,
            "source_format": "plain_text_response",
            "shot_title": "Second beat",
        },
    ]


def test_production_proposal_request_sends_digest_not_full_prompt_packages() -> None:
    provider = OpenAIPlanningProvider(api_key="sk-test-key-not-real")
    long_prompt = "very long prompt package detail " * 500
    previous_output = {
        "shots": [
            {
                "order_index": index,
                "duration_sec": 8,
                "title": f"Shot {index}",
                "description": long_prompt,
            }
            for index in range(10)
        ],
        "prompt_packages": [
            {
                "shot_order_index": index,
                "image_prompt": long_prompt,
                "video_prompt": long_prompt,
            }
            for index in range(10)
        ],
        "task:prompt_package": {"prompt_packages": [{"image_prompt": long_prompt}]},
    }

    body = provider._build_request_body(
        _request(
            task_type=PlanningTaskType.production_proposal,
            previous_output=previous_output,
        ),
        resolved_model="qwen3-4b",
    )
    user_payload = json.loads(body["messages"][1]["content"])
    compact = user_payload["previous_output"]

    assert compact["source_counts"]["shots"] == 10
    assert compact["source_counts"]["prompt_packages"] == 10
    assert "prompt_packages" not in compact
    assert "prompt_package_coverage" in compact
    assert long_prompt not in json.dumps(body)
    assert len(json.dumps(body)) < 10_000


def test_http_400_reports_provider_message() -> None:
    req_obj = httpx.Request("POST", "http://127.0.0.1:1234/v1/chat/completions")
    response = httpx.Response(
        400,
        content=json.dumps(
            {
                "error": (
                    'Engine protocol predict request returned 400: '
                    '{"error":{"message":"request (5376 tokens) exceeds the available context size (5120 tokens)"}}'
                )
            }
        ).encode("utf-8"),
        request=req_obj,
    )
    client = _mock_client(response)
    provider = _provider_with_client(client)

    result = provider.invoke(_request(task_type=PlanningTaskType.prompt_package))

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.category == FailureCategory.validation
    assert "exceeds the available context size" in result.error.message
    assert result.error.details["http_status"] == 400
