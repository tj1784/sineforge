from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.schemas.orchestration import PlanningTaskType, RoutingMode
from backend.app.services.planning.provider_registry import (
    ProviderAvailability,
    build_provider_registry,
    describe_providers,
    resolve_provider,
)
from backend.app.services.planning.routing import build_routing_snapshot, select_route
from backend.app.services.planning.sulphur_provider import (
    QwenPlanningProvider,
    SulphurPlanningProvider,
)


def configured_settings(tmp_path) -> Settings:
    model = tmp_path / "sulphur_prompt_enhancer_model-q8_0.gguf"
    model.write_bytes(b"test-model-evidence")
    return Settings(
        sulphur_planning_enabled=True,
        sulphur_phase_one_enabled=True,
        sulphur_model_path=model,
        sulphur_model_id="sulphur-2-base",
        qwen_model_path=tmp_path / "missing-qwen.gguf",
        sulphur_base_url="http://127.0.0.1:1234/v1",
    )


def test_sulphur_registry_uses_exact_configured_gguf(tmp_path):
    settings = configured_settings(tmp_path)
    registry = build_provider_registry(settings)
    descriptors = {
        item.provider_identifier: item
        for item in describe_providers(settings)
    }

    assert settings.sulphur_configured is True
    assert isinstance(registry["sulphur"], SulphurPlanningProvider)
    assert descriptors["sulphur"].availability_status == ProviderAvailability.available
    assert descriptors["sulphur"].routing_priority > descriptors["mock"].routing_priority
    assert "prompt_enhancement" in descriptors["sulphur"].capabilities


def test_automatic_local_routes_use_sulphur_when_qwen_is_not_installed(tmp_path):
    settings = configured_settings(tmp_path)
    descriptors = describe_providers(settings)
    snapshot = build_routing_snapshot(
        mode=RoutingMode.automatic,
        manual_routes=None,
        prefer_local_providers=True,
        prefer_hosted_providers=False,
        transport_retry_limit=1,
        time_budget_sec=600,
        task_types=list(PlanningTaskType),
    )
    snapshot["provider_catalog"] = [item.as_dict() for item in descriptors]

    decisions = [
        select_route(task_type=task, routing_snapshot=snapshot)
        for task in PlanningTaskType
    ]

    assert decisions
    assert all(item.provider_identifier == "sulphur" for item in decisions)


def test_automatic_local_routes_choose_qwen_by_default(tmp_path):
    settings = configured_settings(tmp_path)
    qwen = tmp_path / "qwen3-4b-q4_k_m.gguf"
    qwen.write_bytes(b"qwen-model-evidence")
    settings = settings.model_copy(
        update={
            "qwen_model_path": qwen,
            "qwen_model_id": "qwen3-4b",
        }
    )
    registry = build_provider_registry(settings)
    descriptors = describe_providers(settings)
    snapshot = build_routing_snapshot(
        mode=RoutingMode.automatic,
        manual_routes=None,
        prefer_local_providers=True,
        prefer_hosted_providers=False,
        transport_retry_limit=1,
        time_budget_sec=600,
        task_types=list(PlanningTaskType),
    )
    snapshot["provider_catalog"] = [item.as_dict() for item in descriptors]

    decisions = [
        select_route(task_type=task, routing_snapshot=snapshot)
        for task in PlanningTaskType
    ]

    assert isinstance(registry["qwen"], QwenPlanningProvider)
    assert isinstance(
        resolve_provider("qwen", registry={}, settings=settings),
        QwenPlanningProvider,
    )
    assert all(item.provider_identifier == "qwen" for item in decisions)


def test_sulphur_endpoint_must_remain_on_loopback(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"evidence")

    with pytest.raises(ValidationError, match="loopback"):
        Settings(
            sulphur_planning_enabled=True,
            sulphur_model_path=model,
            sulphur_base_url="https://example.com/v1",
        )
