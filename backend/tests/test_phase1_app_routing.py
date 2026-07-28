"""Application-level routing contract for the complete Storyboard Phase 1 API."""
from __future__ import annotations

import importlib
import subprocess
import sys
from collections import Counter

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from backend.app.api.routes import (
    assets,
    campaigns,
    health,
    jobs,
    orchestration_runs,
    projects,
    production,
    proposal_review,
    providers,
    runtime_catalog,
    storyboard,
    storyboard_crud,
    storyboard_settings,
    voices,
)
from backend.app.services.comfy.client import ComfyUIClient
from backend.app.services.comfy.submission import (
    ComfyWorkerPromptSubmissionAdapter,
    ControlledComfySubmissionService,
)
from backend.app.services.ffmpeg.service import FFmpegService
from backend.app.services.planning.openai_provider import OpenAIPlanningProvider
from backend.app.services.planning.provider import MockPlanningProvider
from backend.app.services.queue.worker import QueueWorker
from backend.app.services.runtime import gpu_leases
from backend.app.services.telemetry.gpu import GPUTelemetryService
from backend.app.services.voice_design.providers.elevenlabs import (
    ElevenLabsVoiceDesignProvider,
)
from backend.app.services.voice_design.providers.existing import ExistingProviderVoiceProvider
from backend.app.services.voice_design.providers.parler import ParlerLocalVoiceDesignProvider
from backend.app.services.voice_design.providers.placeholder import (
    ManualVoiceProvider,
    PlaceholderVoiceProvider,
)
from backend.app.services.voice_design.providers.qwen import (
    QwenCustomVoiceProvider,
    QwenVoiceDesignProvider,
)
from backend.app.services.voice_design.providers.user_provided import (
    UserProvidedConsentedProvider,
)
from backend.app.workers import voice_preview


REVIEWED_ROUTERS = (
    ("health", health.router),
    ("storyboard_settings", storyboard_settings.router),
    ("projects", projects.router),
    ("production", production.router),
    ("campaigns", campaigns.router),
    ("jobs", jobs.router),
    ("runtime_catalog", runtime_catalog.router),
    ("providers", providers.router),
    ("assets", assets.router),
    ("voices", voices.router),
    ("orchestration_runs", orchestration_runs.router),
    ("proposal_review", proposal_review.router),
    ("storyboard_crud", storyboard_crud.router),
    ("storyboard", storyboard.router),
)

REQUIRED_METHOD_PATHS = {
    ("GET", "/health"),
    ("GET", "/projects/{project_id}/storyboard-settings"),
    ("PUT", "/projects/{project_id}/storyboard-settings"),
    ("POST", "/projects"),
    ("GET", "/production/stories/{story_id}"),
    ("POST", "/production/stories/{story_id}/phases/1/generate"),
    ("PUT", "/production/stories/{story_id}/phases/1"),
    ("POST", "/campaigns"),
    ("GET", "/jobs"),
    ("GET", "/runtime-catalog"),
    ("GET", "/runtime-catalog/workflow-candidates"),
    ("GET", "/providers"),
    ("GET", "/providers/{provider_identifier}/capabilities"),
    ("POST", "/providers/{provider_identifier}/connection-test"),
    ("POST", "/stories/{story_id}/routing/validate"),
    ("POST", "/assets/projects/{project_id}/upload"),
    ("GET", "/voices/providers/discovery"),
    ("POST", "/orchestration/runs"),
    ("POST", "/proposal-review/validate"),
    ("GET", "/storyboard-crud/shots/{shot_id}/narration"),
    ("POST", "/storyboard/stories"),
}


def _create_app() -> FastAPI:
    from backend.app.main import create_app

    return create_app()


def _iter_api_routes(routes):
    """Yield API routes across eager and FastAPI lazy router inclusion."""

    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _iter_api_routes(original_router.routes)


def _method_path_pairs(routes) -> list[tuple[str, str]]:
    return [
        (method, route.path)
        for route in _iter_api_routes(routes)
        for method in sorted(route.methods)
    ]


def test_create_app_does_not_execute_providers_models_workers_or_media_tools(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("create_app attempted a provider, model, worker, GPU, Comfy, or FFmpeg action")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(MockPlanningProvider, "invoke", forbidden)
    monkeypatch.setattr(OpenAIPlanningProvider, "invoke", forbidden)
    monkeypatch.setattr(QueueWorker, "run_once", forbidden)
    monkeypatch.setattr(QueueWorker, "run_batch", forbidden)
    monkeypatch.setattr(voice_preview, "run_voice_preview_job", forbidden)
    monkeypatch.setattr(gpu_leases, "acquire_lease", forbidden)
    monkeypatch.setattr(gpu_leases, "acquire_voice_preview_lease", forbidden)
    monkeypatch.setattr(GPUTelemetryService, "health", forbidden)
    monkeypatch.setattr(FFmpegService, "health", forbidden)
    monkeypatch.setattr(FFmpegService, "ffprobe_asset", forbidden)
    monkeypatch.setattr(FFmpegService, "save_probe_json", forbidden)

    for method_name in (
        "health",
        "get_object_info",
        "submit_prompt",
        "upload_image",
        "interrupt",
        "delete_queue_items",
        "free_memory",
    ):
        monkeypatch.setattr(ComfyUIClient, method_name, forbidden)
    monkeypatch.setattr(ComfyWorkerPromptSubmissionAdapter, "submit_prompt", forbidden)
    monkeypatch.setattr(ControlledComfySubmissionService, "submit_reserved_job", forbidden)

    for provider_type in (
        PlaceholderVoiceProvider,
        ManualVoiceProvider,
        ExistingProviderVoiceProvider,
        QwenVoiceDesignProvider,
        QwenCustomVoiceProvider,
        ElevenLabsVoiceDesignProvider,
        ParlerLocalVoiceDesignProvider,
        UserProvidedConsentedProvider,
    ):
        monkeypatch.setattr(provider_type, "generate_preview", forbidden)

    module_name = "backend.app.main"
    if module_name in sys.modules:
        main_module = importlib.reload(sys.modules[module_name])
    else:
        main_module = importlib.import_module(module_name)

    assert isinstance(main_module.app, FastAPI)
    assert main_module.app.openapi()["info"]["title"] == "CineForge Backend"


def test_all_reviewed_routers_are_mounted_in_required_order():
    app = _create_app()
    app_pairs = _method_path_pairs(app.routes)
    mounted = set(app_pairs)

    expected = {
        pair
        for _name, child_router in REVIEWED_ROUTERS
        for pair in _method_path_pairs(child_router.routes)
    }
    assert expected <= mounted
    assert REQUIRED_METHOD_PATHS <= mounted

    first_positions: list[tuple[str, int]] = []
    for name, child_router in REVIEWED_ROUTERS:
        child_pairs = set(_method_path_pairs(child_router.routes))
        first_positions.append(
            (name, min(index for index, pair in enumerate(app_pairs) if pair in child_pairs))
        )

    assert [position for _name, position in first_positions] == sorted(
        position for _name, position in first_positions
    ), first_positions


def test_application_has_no_duplicate_method_paths_or_operation_ids():
    app = _create_app()
    pair_counts = Counter(_method_path_pairs(app.routes))
    duplicate_pairs = {pair: count for pair, count in pair_counts.items() if count > 1}
    assert duplicate_pairs == {}

    operation_ids = [
        operation["operationId"]
        for path_item in app.openapi()["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))


def test_canonical_proposal_api_is_the_only_public_mutation_boundary():
    route_methods = set(_method_path_pairs(_create_app().routes))
    assert ("POST", "/proposal-review") in route_methods
    assert ("POST", "/proposal-review/{proposal_id}/review") in route_methods
    assert ("POST", "/proposal-review/{proposal_id}/apply") in route_methods
    assert not any(
        path.startswith("/storyboard-crud/proposals")
        for method, path in route_methods
        if method in {"POST", "PUT", "PATCH", "DELETE"}
    )


def test_internal_voice_asset_and_gpu_controls_are_not_publicly_mounted():
    mounted_paths = {
        route.path for route in _iter_api_routes(_create_app().routes)
    }

    assert not any(path.startswith("/voices/planning-assets") for path in mounted_paths)
    assert not any(path.startswith("/voices/gpu-leases") for path in mounted_paths)
