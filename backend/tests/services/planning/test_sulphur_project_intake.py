from __future__ import annotations

import json

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.schemas.api import SulphurProjectPromptCreate
from backend.app.services.clip_planning import plan_scenes_for_duration
from backend.app.services.planning.sulphur_project_intake import (
    SulphurProjectIntakeError,
    build_sulphur_project_intake,
)


def configured_settings(tmp_path) -> Settings:
    model = tmp_path / "sulphur_prompt_enhancer_model-q8_0.gguf"
    model.write_bytes(b"test-model-evidence")
    return Settings(
        storage_root=tmp_path / "storage",
        sulphur_planning_enabled=True,
        sulphur_phase_one_enabled=True,
        sulphur_model_path=model,
        sulphur_model_id="sulphur-2-base",
        sulphur_base_url="http://127.0.0.1:1234/v1",
    )


def test_sulphur_intake_preserves_full_prompt_and_plans_required_scenes(tmp_path):
    source_prompt = (
        "Create a 2 minute 5 second noir film about a courier who must return a lost letter. "
        "Use 2.39:1 at 24 fps, restrained narration, rain, and no graphic violence."
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        assert request.url.path == "/v1/chat/completions"
        assert body["model"] == "sulphur-2-base"
        user_payload = json.loads(body["messages"][1]["content"])
        assert user_payload["source_message"] == source_prompt
        assert "ceil(total_seconds / 8)" in user_payload["runtime_rule"]
        content = {
            "title": "The Lost Letter",
            "description": "A rain-soaked noir short about duty and memory.",
            "target_duration_sec": 125,
            "audience": "Adult drama audiences",
            "genre": "Noir drama",
            "tone": "Restrained and melancholic",
            "point_of_view": "Third person",
            "visual_style": "Rain-soaked cinematic noir",
            "production_notes": "Preserve the lost letter as the visual anchor.",
            "language": "English",
            "narration_dialogue_preference": "Restrained narration",
            "source_fidelity_constraints": "The letter must be returned.",
            "content_constraints": "No graphic violence.",
            "aspect_ratio": "2.39:1",
            "fps": 24,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )

    intake = build_sulphur_project_intake(
        SulphurProjectPromptCreate(
            idempotency_key="sulphur-intake-test-1",
            workflow_lane="cineforge_studio",
            planning_agent="sulphur",
            prompt=source_prompt,
        ),
        settings=configured_settings(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    assert intake.workspace_payload.base_story == source_prompt
    assert intake.workspace_payload.target_duration_sec == 125
    assert intake.workspace_payload.preview_width == 1280
    assert intake.workspace_payload.final_height == 804
    assert intake.workspace_payload.run_phase_one is True
    assert intake.workspace_payload.bootstrap_phase_plan is True
    assert intake.workspace_payload.auto_approve_phases_through == 1
    assert intake.workspace_payload.run_phases_two_through_five is True
    assert intake.workspace_payload.require_production_plan_approval is False
    assert intake.workspace_payload.requested_chapter_count == 2
    assert intake.workspace_payload.prefer_local_providers is True
    assert intake.clip_plan.planned_scene_count == 16
    assert len(intake.clip_plan.scene_duration_plan_sec) == 16
    assert sum(intake.clip_plan.scene_duration_plan_sec) == pytest.approx(125, abs=1e-9)
    assert all(6 <= item <= 10 for item in intake.clip_plan.scene_duration_plan_sec)
    assert "exactly 16 scenes" in (intake.workspace_payload.production_notes or "")
    assert intake.planning_agent == "sulphur"
    assert intake.intake_model == "sulphur-2-base"


def test_scene_count_uses_ceiling_of_seconds_divided_by_eight():
    plan = plan_scenes_for_duration(300)

    assert plan.planned_scene_count == 38
    assert len(plan.scene_duration_plan_sec) == 38
    assert sum(plan.scene_duration_plan_sec) == pytest.approx(300, abs=1e-9)
    assert plan.durations_within_generation_range is True


def test_qwen_agent_uses_its_request_scoped_model_without_changing_global_selection(
    tmp_path,
):
    settings = configured_settings(tmp_path)
    qwen_model = tmp_path / "qwen3-4b-q4_k_m.gguf"
    qwen_model.write_bytes(b"test-qwen-model-evidence")
    settings = settings.model_copy(
        update={
            "qwen_model_path": qwen_model,
            "qwen_model_id": "qwen3-4b-test",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        assert body["model"] == "qwen3.5-9b-defiant"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "title": "Qwen Project",
                                    "description": "A request-scoped Qwen intake.",
                                    "target_duration_sec": 60,
                                }
                            )
                        }
                    }
                ]
            },
        )

    intake = build_sulphur_project_intake(
        SulphurProjectPromptCreate(
            idempotency_key="qwen-intake-test-001",
            workflow_lane="cineforge_studio",
            planning_agent="qwen",
            planning_model_id="qwen3.5-9b-defiant",
            prompt="Create a complete 60-second story about a night train.",
        ),
        settings=settings,
        transport=httpx.MockTransport(handler),
    )

    assert intake.planning_agent == "qwen"
    assert intake.intake_model == "qwen3.5-9b-defiant"
    assert intake.workspace_payload.planning_model_id == "qwen3.5-9b-defiant"
    assert intake.workspace_payload.privacy_preference == "Local-only Qwen planning"


def test_explicit_runtime_overrides_sulphur_fallback_arithmetic(tmp_path):
    source_prompt = (
        "Create a 60-second short. Use exactly eight 7.5-second visual beats "
        "and render at 24 fps."
    )
    content = {
        "title": "One Minute",
        "description": "A one-minute visual short.",
        "target_duration_sec": 300,
        "audience": "General audience",
        "genre": "Drama",
        "tone": "Grounded",
        "point_of_view": "Third person",
        "visual_style": "Photoreal",
        "production_notes": "",
        "language": "English",
        "narration_dialogue_preference": "",
        "source_fidelity_constraints": "",
        "content_constraints": "",
        "aspect_ratio": "16:9",
        "fps": 24,
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )
    )

    intake = build_sulphur_project_intake(
        SulphurProjectPromptCreate(
            idempotency_key="sulphur-runtime-correction",
            workflow_lane="cineforge_studio",
            planning_agent="sulphur",
            prompt=source_prompt,
        ),
        settings=configured_settings(tmp_path),
        transport=transport,
    )

    assert intake.brief.target_duration_sec == 60
    assert intake.workspace_payload.target_duration_sec == 60
    assert intake.clip_plan.planned_scene_count == 8
    assert sum(intake.clip_plan.scene_duration_plan_sec) == pytest.approx(60, abs=1e-9)


def test_word_and_compound_runtimes_are_deterministic(tmp_path):
    content = {
        "title": "Runtime Parsing",
        "description": "Runtime parser coverage.",
        "target_duration_sec": 300,
        "audience": "General audience",
        "genre": "Drama",
        "tone": "Grounded",
        "point_of_view": "Third person",
        "visual_style": "Photoreal",
        "production_notes": "",
        "language": "English",
        "narration_dialogue_preference": "",
        "source_fidelity_constraints": "",
        "content_constraints": "",
        "aspect_ratio": "16:9",
        "fps": 24,
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )
    )

    one_minute = build_sulphur_project_intake(
        SulphurProjectPromptCreate(
            idempotency_key="sulphur-runtime-one-minute",
            workflow_lane="cineforge_studio",
            planning_agent="sulphur",
            prompt="Create a one-minute cinematic short about a train station.",
        ),
        settings=configured_settings(tmp_path),
        transport=transport,
    )
    compound = build_sulphur_project_intake(
        SulphurProjectPromptCreate(
            idempotency_key="sulphur-runtime-compound",
            workflow_lane="cineforge_studio",
            planning_agent="sulphur",
            prompt="Create a 2 minute 5 second cinematic short about a courier.",
        ),
        settings=configured_settings(tmp_path),
        transport=transport,
    )

    assert one_minute.brief.target_duration_sec == 60
    assert compound.brief.target_duration_sec == 125


def test_invalid_sulphur_brief_fails_before_project_creation(tmp_path):
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}]},
        )
    )

    with pytest.raises(SulphurProjectIntakeError, match="valid project brief"):
        build_sulphur_project_intake(
            SulphurProjectPromptCreate(
                idempotency_key="sulphur-intake-test-2",
                workflow_lane="cineforge_studio",
                planning_agent="sulphur",
                prompt="Create a complete one-minute cinematic story about a winter lighthouse.",
            ),
            settings=configured_settings(tmp_path),
            transport=transport,
        )
