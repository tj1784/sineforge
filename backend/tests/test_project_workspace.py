from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import (
    Base,
    Chapter,
    Project,
    ProjectStoryboardSettings,
    ProjectWorkspaceCreation,
    ProductionPhase,
    Scene,
    Shot,
    ShotPromptPackage,
    Story,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.api.routes import projects as project_routes
from backend.app.schemas.api import ProjectWorkspaceCreate
from backend.app.services import project_workspace
from backend.app.services.clip_planning import plan_scenes_for_duration
from backend.app.services.planning.sulphur_project_intake import (
    SulphurProjectBrief,
    SulphurProjectIntakeError,
    SulphurProjectIntakeResult,
)


def _payload(**overrides) -> dict:
    payload = {
        "idempotency_key": "project-workspace-test-key-001",
        "name": "Atomic Project",
        "description": "Created in one transaction",
        "source_mode": "story",
        "story_title": "Atomic Project",
        "base_story": "A complete source story.",
        "target_duration_sec": 315,
        "audience": "Families",
        "genre": "Drama",
        "tone": "Hopeful",
        "point_of_view": "Third person",
        "visual_style": "Naturalistic",
        "production_notes": "Planning only.",
        "aspect_ratio": "2.39:1",
        "preview_width": 1280,
        "preview_height": 536,
        "final_width": 1920,
        "final_height": 804,
        "fps": 30,
        "captions_enabled": False,
        "audio_enabled": True,
        "speaking_rate": 1.15,
        "prefer_hosted_providers": True,
        "prefer_local_providers": True,
        "allow_model_download": True,
        "allow_rendering": True,
        "require_production_plan_approval": True,
        "orchestration_mode": "Hybrid",
        "privacy_preference": "Hosted providers allowed",
        "quality_preference": "Quality weighted",
        "cost_sensitivity": "Balanced",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'workspace.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _count(db: Session, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_workspace_api_creates_and_reloads_all_wizard_values(client: TestClient, db_session: Session):
    response = client.post("/projects/workspace", json=_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["idempotent_replay"] is False
    assert body["project"]["name"] == "Atomic Project"
    assert body["story"] | {
        "audience": "Families",
        "genre": "Drama",
        "tone": "Hopeful",
        "point_of_view": "Third person",
        "visual_style": "Naturalistic",
        "production_notes": "Planning only.",
    } == body["story"]
    assert body["story"]["approval_state"] == "draft"

    project_id = body["project"]["id"]
    settings = client.get(f"/projects/{project_id}/storyboard-settings").json()
    assert settings["aspect_ratio"] == "2.39:1"
    assert (settings["preview_width"], settings["preview_height"]) == (1280, 536)
    assert (settings["final_width"], settings["final_height"]) == (1920, 804)
    assert settings["fps"] == 30
    assert settings["captions_enabled"] is False
    assert settings["audio_enabled"] is True
    assert settings["speaking_rate"] == 1.15
    assert settings["prefer_hosted_providers"] is True
    assert settings["prefer_local_providers"] is True
    assert settings["allow_model_download"] is True
    assert settings["allow_rendering"] is True
    assert settings["require_production_plan_approval"] is True
    assert settings["prompting_policy_json"] | {
        "orchestration_mode": "Hybrid",
        "privacy_preference": "Hosted providers allowed",
        "quality_preference": "Quality weighted",
        "cost_sensitivity": "Balanced",
    } == settings["prompting_policy_json"]
    assert _count(db_session, Project) == 1
    assert _count(db_session, Story) == 1
    assert _count(db_session, ProjectStoryboardSettings) == 1


def test_workspace_preserves_chapter_creation_guidance(client: TestClient):
    response = client.post(
        "/projects/workspace",
        json=_payload(
            requested_chapter_count=2,
            chapter_intake=[
                {
                    "order_index": 0,
                    "title": "Opening Act",
                    "summary": "The discovery changes the routine.",
                    "source_prompt": "Start with the inciting discovery.",
                    "target_duration_sec": 150,
                    "narrative_purpose": "Set stakes and tone.",
                    "dramatic_progression": "Routine becomes obligation.",
                    "production_notes": "Keep the opening quiet.",
                },
                {
                    "order_index": 1,
                    "title": "Final Choice",
                    "target_duration_sec": 165,
                },
            ],
        ),
    )

    assert response.status_code == 201
    body = response.json()
    notes = body["story"]["production_notes"]
    assert "Project creation chapter guidance:" in notes
    assert "Requested chapter count: 2" in notes
    assert "Chapter 1: Opening Act" in notes

    settings = client.get(f"/projects/{body['project']['id']}/storyboard-settings").json()
    policy = settings["prompting_policy_json"]
    assert policy["requested_chapter_count"] == 2
    assert policy["chapter_intake"][0] | {
        "order_index": 0,
        "title": "Opening Act",
        "source_prompt": "Start with the inciting discovery.",
        "target_duration_sec": 150.0,
    } == policy["chapter_intake"][0]
    assert policy["chapter_intake"][1] | {
        "order_index": 1,
        "title": "Final Choice",
        "target_duration_sec": 165.0,
    } == policy["chapter_intake"][1]


def test_workspace_bootstraps_approved_sulphur_phase_plan(
    client: TestClient,
    db_session: Session,
):
    response = client.post(
        "/projects/workspace",
        json=_payload(
            idempotency_key="project-workspace-test-key-bootstrap",
            run_phase_one=True,
            requested_chapter_count=2,
            bootstrap_phase_plan=True,
            auto_approve_phases_through=5,
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["story"]["approval_state"] == "approved"

    phases = list(
        db_session.scalars(
            select(ProductionPhase).order_by(ProductionPhase.phase_number.asc())
        )
    )
    assert [phase.lifecycle_state for phase in phases[:5]] == ["approved"] * 5
    assert all(phase.is_locked is False for phase in phases[:6])
    assert phases[5].lifecycle_state == "drafting"

    planned_scene_count = plan_scenes_for_duration(315).planned_scene_count
    assert _count(db_session, Chapter) == 2
    assert _count(db_session, Scene) == planned_scene_count
    assert _count(db_session, Shot) == planned_scene_count

    prompt_package = db_session.scalar(
        select(ShotPromptPackage).order_by(ShotPromptPackage.created_at.asc())
    )
    assert prompt_package is not None
    assert "Scene label:" in (prompt_package.image_prompt or "")
    assert "Characters: Principal Story Subject" in (prompt_package.image_prompt or "")
    assert "Character assets:" in (prompt_package.image_prompt or "")


def test_workspace_idempotent_replay_reuses_all_rows(client: TestClient, db_session: Session):
    first = client.post("/projects/workspace", json=_payload())
    second = client.post("/projects/workspace", json=_payload())

    assert first.status_code == second.status_code == 201
    assert second.json()["idempotent_replay"] is True
    assert second.json()["project"]["id"] == first.json()["project"]["id"]
    assert second.json()["story"]["id"] == first.json()["story"]["id"]
    assert second.json()["settings"]["id"] == first.json()["settings"]["id"]
    assert _count(db_session, Project) == 1
    assert _count(db_session, Story) == 1
    assert _count(db_session, ProjectStoryboardSettings) == 1
    assert _count(db_session, ProjectWorkspaceCreation) == 1


def test_workspace_rejects_idempotency_key_reuse_for_different_request(client: TestClient):
    assert client.post("/projects/workspace", json=_payload()).status_code == 201
    conflict = client.post("/projects/workspace", json=_payload(name="Different Project"))

    assert conflict.status_code == 409
    assert "different project workspace request" in conflict.json()["detail"]


@pytest.mark.parametrize("failure_helper", ["_new_story", "_new_settings"])
def test_workspace_rolls_back_when_story_or_settings_creation_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, failure_helper: str
):
    def fail(*_args, **_kwargs):
        raise RuntimeError("forced workspace child failure")

    monkeypatch.setattr(project_workspace, failure_helper, fail)

    with pytest.raises(RuntimeError, match="forced workspace child failure"):
        project_workspace.create_project_workspace(
            db_session, ProjectWorkspaceCreate.model_validate(_payload())
        )

    assert _count(db_session, Project) == 0
    assert _count(db_session, Story) == 0
    assert _count(db_session, ProjectStoryboardSettings) == 0
    assert _count(db_session, ProjectWorkspaceCreation) == 0


def test_workspace_safe_defaults_are_persisted(client: TestClient):
    payload = _payload()
    for field in (
        "preview_width",
        "preview_height",
        "final_width",
        "final_height",
        "fps",
        "captions_enabled",
        "audio_enabled",
        "speaking_rate",
        "prefer_hosted_providers",
        "prefer_local_providers",
        "allow_model_download",
        "allow_rendering",
        "require_production_plan_approval",
    ):
        payload.pop(field)

    settings = client.post("/projects/workspace", json=payload).json()["settings"]
    assert (settings["preview_width"], settings["preview_height"]) == (1280, 720)
    assert (settings["final_width"], settings["final_height"]) == (1920, 1080)
    assert settings["fps"] == 24
    assert settings["captions_enabled"] is True
    assert settings["audio_enabled"] is True
    assert settings["speaking_rate"] == 1
    assert settings["prefer_hosted_providers"] is False
    assert settings["prefer_local_providers"] is True
    assert settings["allow_model_download"] is True
    assert settings["allow_rendering"] is True
    assert settings["require_production_plan_approval"] is True


def test_workspace_can_derive_title_from_the_single_prompt(client: TestClient):
    response = client.post(
        "/projects/workspace",
        json=_payload(
            auto_title=True,
            name="CineForge Production",
            story_title="CineForge Production",
            base_story="Create a five-minute cinematic narrative of The Northern Crossing using a grounded style.",
        ),
    )

    assert response.status_code == 201
    assert response.json()["project"]["name"] == "The Northern Crossing"
    assert response.json()["story"]["title"] == "The Northern Crossing"


def test_workspace_derives_an_explicit_named_project_title(client: TestClient):
    response = client.post(
        "/projects/workspace",
        json=_payload(
            auto_title=True,
            name="CineForge Production",
            story_title="CineForge Production",
            base_story=(
                "Please start a new project named gogo power rangers: "
                "use the supplied references as visual anchors."
            ),
        ),
    )

    assert response.status_code == 201
    assert response.json()["project"]["name"] == "Gogo power rangers"
    assert response.json()["story"]["title"] == "Gogo power rangers"


def test_sulphur_intake_route_uses_atomic_workspace_boundary(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    source_prompt = (
        "Create a 125-second noir story about a courier returning a lost letter."
    )

    def fake_intake(request):
        workspace_payload = ProjectWorkspaceCreate.model_validate(
            _payload(
                idempotency_key=request.idempotency_key,
                name="The Lost Letter",
                story_title="The Lost Letter",
                description="A local Sulphur-created project.",
                base_story=request.prompt,
                target_duration_sec=125,
                run_phase_one=False,
            )
        )
        return SulphurProjectIntakeResult(
            brief=SulphurProjectBrief(
                title="The Lost Letter",
                description="A local Sulphur-created project.",
                target_duration_sec=125,
            ),
            workspace_payload=workspace_payload,
            clip_plan=plan_scenes_for_duration(125),
        )

    monkeypatch.setattr(project_routes, "build_sulphur_project_intake", fake_intake)
    response = client.post(
        "/projects/sulphur-intake",
        json={
            "idempotency_key": "sulphur-route-test-001",
            "prompt": source_prompt,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["intake_provider"] == "sulphur"
    assert body["source_prompt_preserved"] is True
    assert body["target_duration_sec"] == 125
    assert body["planned_scene_count"] == 16
    assert body["story"]["base_story"] == source_prompt
    assert _count(db_session, Project) == 1
    assert _count(db_session, ProjectWorkspaceCreation) == 1


def test_sulphur_intake_failure_creates_no_partial_workspace(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    def fail_intake(_request):
        raise SulphurProjectIntakeError("Sulphur returned no project brief")

    monkeypatch.setattr(project_routes, "build_sulphur_project_intake", fail_intake)
    response = client.post(
        "/projects/sulphur-intake",
        json={
            "idempotency_key": "sulphur-route-test-002",
            "prompt": "Create a complete one-minute lighthouse story with a clear ending.",
        },
    )

    assert response.status_code == 503
    assert "no project brief" in response.json()["detail"]
    assert _count(db_session, Project) == 0
    assert _count(db_session, ProjectWorkspaceCreation) == 0
