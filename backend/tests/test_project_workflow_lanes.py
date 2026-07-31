"""Focused project-lane persistence and fail-closed planning coverage."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
import hashlib
import json
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import (
    Base,
    OrchestrationRun,
    Project,
    ProjectWorkspaceCreation,
    Story,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.schemas.api import (
    ProjectRead,
    SulphurProjectPromptCreate,
)
from backend.app.schemas.orchestration import CreateOrchestrationRunRequest
from backend.app.schemas.providers import RoutingPreflightRequest
from backend.app.schemas.production import PhaseOneGenerationInput
from backend.app.schemas.project_workflows import (
    ProjectWorkflowLane,
    is_cineforge_studio_workflow_lane,
)
from backend.app.schemas.storyboard_settings import (
    ProjectStoryboardSettingsUpdate,
)
from backend.app.services import production_phases
from backend.app.services import storyboard_settings as settings_service
from backend.app.services.planning.engine import PlanningEngine
from backend.app.services.planning.errors import PlanningError, PlanningErrorCode
from backend.app.services.planning.provider import MockPlanningProvider
from backend.app.services.planning.provider_registry import (
    ProviderAvailability,
    ProviderDescriptor,
)
from backend.app.services.planning.provider_contract import (
    validate_story_routing,
)
from backend.app.core.config import Settings


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _workspace_payload(**overrides) -> dict:
    payload = {
        "idempotency_key": "agentless-workspace-contract-001",
        "name": "Agentless Podcast",
        "workflow_lane": "agentless",
        "description": "Deterministic scene-reset production.",
        "source_mode": "story",
        "story_title": "Agentless Podcast",
        "base_story": "A host interviews a craft expert in a consistent studio.",
        "target_duration_sec": 50,
        "fps": 24,
        "production_profile_key": "ltx_base@2",
        "planning_agent": "qwen",
        "prompt_artifact_format": "json",
        "prompt_schema_version": "sineforge.local-planning-prompt/v1",
        "run_phase_one": True,
        "prefer_hosted_providers": False,
        "prefer_local_providers": True,
        "allow_model_download": False,
        "allow_rendering": False,
        "orchestration_mode": "deterministic_python",
        "privacy_preference": "Local only",
        "quality_preference": "Quality weighted",
        "cost_sensitivity": "Local compute",
    }
    payload.update(overrides)
    return payload


def _agentless_story(db: Session) -> Story:
    project = Project(
        id=uuid4(),
        name="Agentless",
        description=None,
        workflow_lane=ProjectWorkflowLane.agentless.value,
    )
    db.add(project)
    db.flush()
    story = Story(
        id=uuid4(),
        project_id=project.id,
        title="Scene Reset",
        base_story="A stable character speaks in ten-second scene-reset units.",
        target_duration_sec=30,
        approval_state="draft",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


def test_project_creation_requires_and_persists_explicit_lane(
    client: TestClient,
) -> None:
    missing = client.post("/projects", json={"name": "Missing lane"})
    invalid = client.post(
        "/projects",
        json={"name": "Invalid lane", "workflow_lane": "autonomous"},
    )
    created = client.post(
        "/projects",
        json={"name": "Agentless", "workflow_lane": "agentless"},
    )

    assert missing.status_code == 422
    assert invalid.status_code == 422
    assert created.status_code == 201
    assert created.json()["workflow_lane"] == "agentless"
    assert (
        client.get(f"/projects/{created.json()['id']}").json()["workflow_lane"]
        == "agentless"
    )

    # Read-side compatibility remains Studio for legacy serialized records.
    legacy = ProjectRead(
        id=uuid4(),
        name="Legacy",
        created_at=datetime.utcnow(),
    )
    assert legacy.workflow_lane is ProjectWorkflowLane.cineforge_studio
    assert is_cineforge_studio_workflow_lane("cineforge_studio") is True
    assert is_cineforge_studio_workflow_lane("agentless") is False
    assert is_cineforge_studio_workflow_lane(None) is False
    assert is_cineforge_studio_workflow_lane("future_lane") is False


def test_local_intake_contract_defaults_to_qwen_for_explicit_studio_lane() -> None:
    with pytest.raises(ValidationError):
        SulphurProjectPromptCreate(
            idempotency_key="sulphur-lane-missing-001",
            planning_agent="sulphur",
            prompt="Create a complete studio project from this source prompt.",
        )
    with pytest.raises(ValidationError):
        SulphurProjectPromptCreate(
            idempotency_key="sulphur-lane-agentless-001",
            workflow_lane="agentless",
            planning_agent="sulphur",
            prompt="Create a complete studio project from this source prompt.",
        )

    payload = SulphurProjectPromptCreate(
        idempotency_key="sulphur-lane-studio-001",
        workflow_lane="cineforge_studio",
        prompt="Create a complete studio project from this source prompt.",
    )
    assert payload.workflow_lane == "cineforge_studio"
    assert payload.planning_agent == "qwen"
    assert payload.prompt_artifact_format == "json"


def test_agentless_workspace_persists_deterministic_lane_policy(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def local_qwen(package, payload, *, required=False):
        assert required is True
        result = dict(package)
        result["creative_direction"] = {
            **dict(result.get("creative_direction") or {}),
            "script_provider": "local_lm_studio",
            "planning_agent": payload.planning_agent,
            "prompt_artifact_format": payload.prompt_artifact_format,
        }
        return result

    monkeypatch.setattr(
        production_phases,
        "_apply_sulphur_phase_one_enhancement",
        local_qwen,
    )
    response = client.post("/projects/workspace", json=_workspace_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["project"]["workflow_lane"] == "agentless"
    project = db_session.get(Project, UUID(body["project"]["id"]))
    assert project is not None
    assert project.workflow_lane == "agentless"

    settings = body["settings"]
    assert settings["shot_duration_min_sec"] == 3
    assert settings["shot_duration_max_sec"] == 10
    assert settings["fps"] == 24
    assert settings["prefer_hosted_providers"] is False
    assert settings["prefer_local_providers"] is True
    assert settings["allow_model_download"] is False
    assert settings["allow_rendering"] is False
    assert settings["continuity_policy_json"] | {
        "require_fresh_scene_anchor": True,
        "allow_cross_scene_continuity": False,
        "allow_previous_video_frame_handoff": False,
    } == settings["continuity_policy_json"]

    prompting = settings["prompting_policy_json"]
    assert prompting["workflow_lane"] == "agentless"
    assert prompting["orchestration_mode"] == "deterministic_python"
    assert prompting["planning_agent"] == "qwen"
    assert prompting["planning_mode"] == "local_lm_studio"
    assert prompting["hosted_planning_agents_allowed"] is False
    assert prompting["prompt_artifact_filename"].endswith(".json")
    assert prompting["prompt_artifact_url"].endswith(
        "/planning-prompt.json"
    )
    assert prompting["prompt_artifact"]["artifact_format"] == "json"
    assert prompting["prompt_artifact"]["planning_agent"] == "qwen"
    assert len(prompting["prompt_artifact_sha256"]) == 64
    prompt_download = client.get(prompting["prompt_artifact_url"])
    assert prompt_download.status_code == 200
    assert prompt_download.headers["content-type"].startswith(
        "application/json"
    )
    assert "project-planning-prompt.json" in (
        prompt_download.headers["content-disposition"]
    )
    assert prompt_download.json() == prompting["prompt_artifact"]
    canonical_prompt = json.dumps(
        prompt_download.json(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical_prompt).hexdigest() == (
        prompt_download.headers["x-content-sha256"]
    )
    profile = client.get(
        f"/projects/{project.id}/agentless-workflow"
    )
    assert profile.status_code == 200
    assert profile.json()["selected_planning_agent"] == "qwen"
    policy = prompting["workflow_lane_policy"]
    assert policy["schema_version"] == 2
    assert policy["orchestration"] == "deterministic_python"
    assert policy["planning"]["default_agent"] == "qwen"
    assert policy["planning"]["hosted_agents_allowed"] is False
    assert policy["planning"]["prompt_artifact_extension"] == ".json"
    assert policy["max_scenes"] == 50
    assert policy["production_profile_ref"] == "ltx_base@2"
    assert policy["anchor"] | {
        "model_family": "FLUX.2",
        "fresh_per_scene": True,
        "format": "png",
        "previous_frame_handoff": False,
        "initial_resolution": {"width": 768, "height": 448},
        "candidate_resolution": {"width": 960, "height": 544},
    } == policy["anchor"]
    assert policy["video"] | {
        "model_family": "LTX-2.3",
        "ingredients_reference_sheet": True,
        "first_frame_i2v": True,
        "bypass_i2v": False,
        "fps": 24,
        "frame_count": 241,
        "duration_sec": 10,
    } == policy["video"]
    assert policy["seeds"]["image_and_video_separate"] is True
    assert policy["retries"] == {
        "anchor_max_attempts": 3,
        "video_max_attempts": 3,
    }
    assert policy["queue"]["max_active_gpu_jobs"] == 1
    assert policy["mastering"] == {
        "anchor_format": "png",
        "intermediate_master_formats": ["prores", "ffv1"],
        "final_delivery_encode_count": 1,
    }

    updated = settings_service.put_settings(
        db_session,
        project.id,
        ProjectStoryboardSettingsUpdate(
            expected_settings_version=settings["settings_version"],
            production_profile_key="wan_base@1",
            fps=30,
            prefer_hosted_providers=True,
            prefer_local_providers=True,
            allow_model_download=True,
            allow_rendering=True,
        ),
    )
    assert updated.production_profile_key == "ltx_base@2"
    assert updated.production_profile_snapshot_json["ref"] == "ltx_base@2"
    assert float(updated.fps) == 24
    assert updated.prefer_hosted_providers is False
    assert updated.prefer_local_providers is True
    assert updated.allow_model_download is False
    assert updated.allow_rendering is False


def test_studio_workspace_prompt_policy_reflects_hosted_preference(
    client: TestClient,
) -> None:
    response = client.post(
        "/projects/workspace",
        json=_workspace_payload(
            idempotency_key="studio-hosted-prompt-policy-001",
            workflow_lane="cineforge_studio",
            run_phase_one=False,
            bootstrap_phase_plan=False,
            prefer_hosted_providers=True,
            orchestration_mode="Hybrid",
        ),
    )

    assert response.status_code == 201, response.text
    settings = response.json()["settings"]
    prompting = settings["prompting_policy_json"]
    assert settings["prefer_hosted_providers"] is True
    assert prompting["hosted_planning_agents_allowed"] is True
    assert prompting["local_planning_agent_required"] is False
    assert (
        prompting["prompt_artifact"]["execution_policy"][
            "hosted_agents_allowed"
        ]
        is True
    )


@pytest.mark.parametrize(
    ("field", "value", "required_setting"),
    [
        ("fps", 30, "fps=24"),
        (
            "production_profile_key",
            "wan_2_1_t2v_1_3b@1",
            "production_profile_key='ltx_base@2'",
        ),
        ("prefer_local_providers", False, "local planning provider required"),
        ("prefer_hosted_providers", True, "hosted planning providers disabled"),
        ("allow_model_download", True, "allow_model_download=false"),
        ("allow_rendering", True, "allow_rendering=false"),
        (
            "orchestration_mode",
            "Automatic",
            "orchestration_mode='deterministic_python'",
        ),
    ],
)
def test_agentless_workspace_rejects_noncanonical_creation_settings(
    client: TestClient,
    field: str,
    value: object,
    required_setting: str,
) -> None:
    response = client.post(
        "/projects/workspace",
        json=_workspace_payload(**{field: value}),
    )

    assert response.status_code == 422
    assert "Agentless Workflow requires canonical fail-closed creation settings" in (
        response.text
    )
    assert required_setting in response.text


def test_agentless_workspace_reports_local_agent_failure_and_can_retry(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def flaky_local_agent(package, _payload, *, required=False):
        nonlocal attempts
        attempts += 1
        assert required is True
        if attempts == 1:
            raise production_phases.ProductionPhaseError(
                "The selected local Qwen agent is unavailable."
            )
        return package

    monkeypatch.setattr(
        production_phases,
        "_apply_sulphur_phase_one_enhancement",
        flaky_local_agent,
    )
    first = client.post("/projects/workspace", json=_workspace_payload())

    assert first.status_code == 503
    assert first.json()["detail"] == (
        "The selected local Qwen agent is unavailable."
    )
    assert db_session.scalar(select(func.count()).select_from(Project)) == 0
    assert db_session.scalar(select(func.count()).select_from(Story)) == 0
    assert (
        db_session.scalar(
            select(func.count()).select_from(ProjectWorkspaceCreation)
        )
        == 0
    )

    recovered = client.post(
        "/projects/workspace",
        json=_workspace_payload(),
    )
    assert recovered.status_code == 201, recovered.text
    assert attempts == 2


def test_planning_engine_rejects_mock_fallback_for_agentless_local_planning(
    db_session: Session,
) -> None:
    story = _agentless_story(db_session)
    engine = PlanningEngine(
        db_session,
        providers={"mock": MockPlanningProvider(fixed_latency_ms=0)},
    )

    with pytest.raises(PlanningError) as raised:
        engine.create_run(
            CreateOrchestrationRunRequest(
                story_id=story.id,
                requested_by="agentless-test",
            )
        )

    assert raised.value.code is PlanningErrorCode.ROUTING_FAILED
    assert "forbids fallback to mock or hosted providers" in raised.value.message
    assert (
        db_session.scalar(select(func.count()).select_from(OrchestrationRun))
        == 0
    )


def test_agentless_phase_one_invokes_selected_local_agent(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = _agentless_story(db_session)

    called: dict[str, object] = {}

    def local_qwen(package, payload, *, required=False):
        called.update(
            {
                "planning_agent": payload.planning_agent,
                "required": required,
                "prompt_artifact_format": payload.prompt_artifact_format,
            }
        )
        result = dict(package)
        result["creative_direction"] = {
            **dict(result.get("creative_direction") or {}),
            "script_provider": "local_lm_studio",
            "planning_agent": payload.planning_agent,
        }
        return result

    monkeypatch.setattr(
        production_phases,
        "_apply_sulphur_phase_one_enhancement",
        local_qwen,
    )
    result = production_phases.generate_phase_one(
        db_session,
        story.id,
        PhaseOneGenerationInput(
            original_prompt=story.base_story,
            target_duration_sec=30,
            language="English",
            requested_by="agentless-test",
        ),
    )

    latest = result.phase.latest_version
    assert latest is not None
    assert called == {
        "planning_agent": "qwen",
        "required": True,
        "prompt_artifact_format": "json",
    }
    assert latest.output_json["creative_direction"]["script_provider"] == "local_lm_studio"
    assert latest.output_json["creative_direction"]["planning_agent"] == "qwen"
    assert latest.output_json["creative_direction"]["workflow_lane"] == "agentless"
    assert latest.output_json["creative_direction"]["hosted_planning_agents_allowed"] is False


def test_agentless_phase_one_uses_persisted_sulphur_selection(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = _agentless_story(db_session)
    project_settings = settings_service.get_settings(
        db_session,
        story.project_id,
    )
    project_settings.prompting_policy_json = {
        **dict(project_settings.prompting_policy_json or {}),
        "planning_agent": "sulphur",
    }
    db_session.add(project_settings)
    db_session.commit()

    called: dict[str, object] = {}

    def local_sulphur(package, payload, *, required=False):
        called["planning_agent"] = payload.planning_agent
        called["required"] = required
        return package

    monkeypatch.setattr(
        production_phases,
        "_apply_sulphur_phase_one_enhancement",
        local_sulphur,
    )
    production_phases.generate_phase_one(
        db_session,
        story.id,
        PhaseOneGenerationInput(
            original_prompt=story.base_story,
            planning_agent="qwen",
            target_duration_sec=30,
            requested_by="agentless-sulphur-test",
        ),
    )

    assert called == {
        "planning_agent": "sulphur",
        "required": True,
    }


def test_agentless_automatic_routing_uses_only_persisted_sulphur(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = _agentless_story(db_session)
    project_settings = settings_service.get_settings(
        db_session,
        story.project_id,
    )
    project_settings.prompting_policy_json = {
        **dict(project_settings.prompting_policy_json or {}),
        "planning_agent": "sulphur",
    }
    db_session.add(project_settings)
    db_session.commit()

    descriptors = [
        ProviderDescriptor(
            provider_identifier=identifier,
            display_name=identifier.title(),
            availability_status=ProviderAvailability.available,
            execution_mode="local_http",
            privacy_classification="local",
            capabilities=("planning",),
            detail="Injected local test provider.",
            routing_priority=priority,
        )
        for identifier, priority in (("qwen", 110), ("sulphur", 100))
    ]
    monkeypatch.setattr(
        "backend.app.services.planning.engine.describe_providers",
        lambda: descriptors,
    )
    engine = PlanningEngine(
        db_session,
        providers={
            "qwen": MockPlanningProvider(fixed_latency_ms=0),
            "sulphur": MockPlanningProvider(fixed_latency_ms=0),
        },
    )
    run, created = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            requested_by="agentless-sulphur-routing-test",
        )
    )

    assert created is True
    assert run.routing_snapshot_json["selected_planning_agent"] == "sulphur"
    assert {
        item["provider_identifier"]
        for item in run.routing_snapshot_json["provider_catalog"]
    } == {"sulphur"}


def test_agentless_preflight_matches_persisted_sulphur_and_rejects_mock(
    db_session: Session,
    tmp_path,
) -> None:
    story = _agentless_story(db_session)
    project_settings = settings_service.get_settings(
        db_session,
        story.project_id,
    )
    project_settings.prompting_policy_json = {
        **dict(project_settings.prompting_policy_json or {}),
        "planning_agent": "sulphur",
    }
    db_session.add(project_settings)
    db_session.commit()
    qwen_path = tmp_path / "qwen.gguf"
    sulphur_path = tmp_path / "sulphur.gguf"
    qwen_path.write_bytes(b"qwen")
    sulphur_path.write_bytes(b"sulphur")
    provider_settings = Settings(
        sulphur_planning_enabled=True,
        qwen_model_path=qwen_path,
        qwen_model_id="qwen3-4b",
        sulphur_model_path=sulphur_path,
        sulphur_model_id="sulphur-2-base",
    )

    automatic = validate_story_routing(
        db_session,
        story.id,
        RoutingPreflightRequest(
            routing_mode="automatic",
            prefer_local_providers=True,
            prefer_hosted_providers=False,
            task_types=["story_structure"],
            max_steps=1,
        ),
        provider_settings,
    )
    mock_override = validate_story_routing(
        db_session,
        story.id,
        RoutingPreflightRequest(
            routing_mode="manual",
            manual_routes=[
                {
                    "task_type": "story_structure",
                    "provider_identifier": "mock",
                    "logical_model": "sol",
                }
            ],
            prefer_local_providers=True,
            prefer_hosted_providers=False,
            task_types=["story_structure"],
            max_steps=1,
        ),
        provider_settings,
    )

    assert automatic.valid is True
    assert {
        route.provider_identifier for route in automatic.routes
    } == {"sulphur"}
    assert automatic.metadata["selected_planning_agent"] == "sulphur"
    assert mock_override.valid is False
    assert {
        issue.code for issue in mock_override.errors
    } >= {"agentless_selected_agent_required"}
