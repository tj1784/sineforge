"""Acceptance coverage for the exact eight-phase contract and Phase 1 boundary."""

from collections.abc import Generator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import (
    AuditLog,
    Base,
    Chapter,
    Character,
    ComfyJob,
    FFmpegJob,
    GeneratedAsset,
    PlanningMediaAsset,
    ProductionPhase,
    ProductionPhaseVersion,
    QAReport,
    Scene,
    Shot,
    Story,
    VoiceProfile,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.services import production_phases


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT = (
    REPO_ROOT
    / "examples"
    / "projects"
    / "transfiguration_5m"
    / "phase_one_test_prompt.txt"
).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def deterministic_phase_one_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep acceptance coverage independent from the workstation LM runtime."""

    monkeypatch.setattr(
        production_phases,
        "_apply_sulphur_phase_one_enhancement",
        lambda package, _payload, **_kwargs: package,
    )


def _workspace_payload(**overrides) -> dict:
    payload = {
        "idempotency_key": "transfiguration-phase-one-acceptance-001",
        "name": "Transfiguration Phase 1 Acceptance",
        "workflow_lane": "cineforge_studio",
        "description": "A fresh one-prompt Phase 1 quality comparison.",
        "source_mode": "story",
        "story_title": "The Transfiguration — Fresh Phase 1",
        "base_story": PROMPT,
        "target_duration_sec": 300,
        "audience": "General audiences",
        "genre": "Sacred cinematic narrative",
        "tone": "Reverent, emotionally truthful, compassionate",
        "point_of_view": "Third person",
        "visual_style": "Ultra-photorealistic live-action sacred realism",
        "production_notes": "Phase 1 only. Do not create media or final shots.",
        "language": "English",
        "narration_dialogue_preference": "Non-diegetic narration with intentional silence; quoted divine speech only.",
        "source_fidelity_constraints": "Combined Synoptic account; Transfiguration, never Ascension.",
        "content_constraints": "Jesus remains physically present on the mountain.",
        "run_phase_one": True,
        "comparison_baseline": "transfiguration_phase_one",
        "aspect_ratio": "16:9",
        "preview_width": 1280,
        "preview_height": 720,
        "final_width": 1920,
        "final_height": 1080,
        "fps": 24,
        "captions_enabled": True,
        "audio_enabled": True,
        "speaking_rate": 1,
        "prefer_hosted_providers": False,
        "prefer_local_providers": True,
        "allow_model_download": False,
        "allow_rendering": False,
        "require_production_plan_approval": True,
        "orchestration_mode": "Automatic",
        "privacy_preference": "Local only",
        "quality_preference": "Quality weighted",
        "cost_sensitivity": "Balanced",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'production.db').as_posix()}",
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


def test_one_prompt_creates_only_complete_phase_one_package(client: TestClient, db_session: Session):
    response = client.post("/projects/workspace", json=_workspace_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    pipeline = body["production_pipeline"]
    assert pipeline["exact_phase_count"] == 8
    assert len(pipeline["phases"]) == 8
    assert [phase["phase_number"] for phase in pipeline["phases"]] == list(range(1, 9))
    assert pipeline["completion_message"] == "Your complete script is ready for review."

    phase_one = pipeline["phases"][0]
    assert phase_one["name"] == "Script and Narrative Development"
    assert phase_one["lifecycle_state"] == "ready_for_review"
    assert phase_one["is_locked"] is False
    assert phase_one["latest_version"]["completed"] is True
    assert phase_one["latest_version"]["lifecycle_state"] == "ready_for_review"
    assert phase_one["latest_qa_report"]["report_json"]["passed"] is True

    package = phase_one["latest_version"]["output_json"]
    assert package["project_title"] == "The Transfiguration — Fresh Phase 1"
    assert package["script_word_count"] >= 330
    assert package["duration_analysis"]["estimated_total_duration_sec"] == 300
    assert package["duration_analysis"]["narration_duration_sec"] > 0
    assert package["duration_analysis"]["dialogue_duration_sec"] > 0
    assert package["duration_analysis"]["planned_silence_visual_duration_sec"] > 0
    assert package["planned_scene_count"] == 38
    assert len(package["scene_duration_plan_sec"]) == 38
    assert sum(package["scene_duration_plan_sec"]) == 300
    assert all(6 <= duration <= 10 for duration in package["scene_duration_plan_sec"])
    assert "Source-required speech" in package["dialogue_script"]
    assert package["baseline_comparison"]["classification"] == "acceptable_variation"
    assert package["baseline_comparison"]["missing_count"] == 0
    assert package["baseline_comparison"]["unsafe_count"] == 0
    assert "scenes" not in package
    assert "shots" not in package
    assert "characters" not in package

    assert all(phase["lifecycle_state"] == "not_started" for phase in pipeline["phases"][1:])
    assert all(phase["is_locked"] is True for phase in pipeline["phases"][1:])
    # Phases 2–8 receive idempotent planning baselines (not executable packages).
    assert all(
        phase["latest_version"] is not None
        and phase["latest_version"]["source"] == "baseline"
        for phase in pipeline["phases"][1:]
    )
    assert phase_one["latest_version"]["source"] in {"generated", "revision"}

    story = db_session.get(Story, UUID(body["story"]["id"]))
    assert story is not None
    assert story.approval_state == "draft"
    assert _count(db_session, ProductionPhase) == 8
    # One Phase 1 generated package + seven planning baselines for phases 2–8.
    assert _count(db_session, ProductionPhaseVersion) == 8
    assert _count(db_session, QAReport) == 1
    assert _count(db_session, AuditLog) >= 3

    # Phase 1 cannot create or invoke any Phase 2–7 entity.
    for model in (
        Chapter,
        Scene,
        Shot,
        Character,
        VoiceProfile,
        PlanningMediaAsset,
        GeneratedAsset,
        ComfyJob,
        FFmpegJob,
    ):
        assert _count(db_session, model) == 0, model.__name__


def test_phase_one_revision_preserves_prior_version_and_remains_unapproved(
    client: TestClient, db_session: Session
):
    created = client.post("/projects/workspace", json=_workspace_payload()).json()
    story_id = created["story"]["id"]
    current = created["production_pipeline"]["phases"][0]["latest_version"]
    package = current["output_json"]

    response = client.put(
        f"/production/stories/{story_id}/phases/1",
        json={
            "expected_version_number": 1,
            "project_title": package["project_title"],
            "logline": package["logline"] + " The disciples must listen.",
            "short_synopsis": package["short_synopsis"],
            "detailed_treatment": package["detailed_treatment"],
            "complete_script": package["complete_script"],
            "narration_script": package["narration_script"],
            "dialogue_script": package["dialogue_script"],
            "non_dialogue_action": package["non_dialogue_action"],
            "silent_visual_beats": package["silent_visual_beats"],
            "emotional_progression": package["emotional_progression"],
            "dramatic_escalation": package["dramatic_escalation"],
            "source_fidelity_notes": package["source_fidelity_notes"],
            "creative_assumptions": package["creative_assumptions"],
            "requested_by": "Phase 1 reviewer",
        },
    )

    assert response.status_code == 200, response.text
    revised = response.json()["phase"]
    assert revised["current_version_number"] == 2
    assert revised["latest_version"]["version_number"] == 2
    assert revised["lifecycle_state"] == "ready_for_review"
    # Two Phase 1 rows + seven planning baselines.
    assert _count(db_session, ProductionPhaseVersion) == 9
    phase_one_id = UUID(revised["id"])
    versions = list(
        db_session.scalars(
            select(ProductionPhaseVersion)
            .where(ProductionPhaseVersion.production_phase_id == phase_one_id)
            .order_by(ProductionPhaseVersion.version_number)
        )
    )
    assert len(versions) == 2
    # Append-only history: prior rows are never mutated (including superseded_at).
    assert versions[0].superseded_at is None
    assert versions[1].previous_version_id == versions[0].id
    assert versions[0].source == "generated"
    assert versions[1].source == "revision"
    assert db_session.get(Story, UUID(story_id)).approval_state == "draft"


def test_phase_one_revision_rejects_stale_editor_version(client: TestClient):
    created = client.post("/projects/workspace", json=_workspace_payload()).json()
    story_id = created["story"]["id"]
    package = created["production_pipeline"]["phases"][0]["latest_version"]["output_json"]
    payload = {
        "expected_version_number": 99,
        "project_title": package["project_title"],
        "logline": package["logline"],
        "short_synopsis": package["short_synopsis"],
        "detailed_treatment": package["detailed_treatment"],
        "complete_script": package["complete_script"],
        "narration_script": package["narration_script"],
        "dialogue_script": package["dialogue_script"],
    }

    response = client.put(f"/production/stories/{story_id}/phases/1", json=payload)

    assert response.status_code == 409
    assert "reload before saving" in response.json()["detail"]


def test_phase_one_generation_fails_closed_without_prompt(client: TestClient):
    payload = _workspace_payload(run_phase_one=False, base_story="A source.")
    created = client.post("/projects/workspace", json=payload).json()

    response = client.post(
        f"/production/stories/{created['story']['id']}/phases/1/generate",
        json={"original_prompt": "", "target_duration_sec": 300},
    )

    assert response.status_code == 422


def test_contract_exposes_exact_canonical_names(client: TestClient):
    created = client.post(
        "/projects/workspace",
        json=_workspace_payload(run_phase_one=False, comparison_baseline=None),
    ).json()
    pipeline = client.get(f"/production/stories/{created['story']['id']}").json()

    assert [phase["name"] for phase in pipeline["phases"]] == [
        "Script and Narrative Development",
        "Scene and Shot Segmentation",
        "Character Development",
        "Location and Key-Asset Development",
        "Production Prompt and Workflow Package",
        "Image and Voice Generation and Mapping",
        "Video Generation, Continuity, Assembly, and Picture Lock",
        "Foley, Audio Mix, Final Mux, and Delivery QA",
    ]
    assert pipeline["phases"][0]["lifecycle_state"] == "not_started"
    assert pipeline["phases"][0]["is_locked"] is False
    assert all(item["is_locked"] for item in pipeline["phases"][1:])


def test_phase_one_package_schema_and_retain_keeps_package_head(
    client: TestClient, db_session: Session
):
    """Manual retain must keep the script package as the pipeline head for UI packageData."""
    created = client.post("/projects/workspace", json=_workspace_payload()).json()
    story_id = created["story"]["id"]
    phase_one = created["production_pipeline"]["phases"][0]
    package = phase_one["latest_version"]["output_json"]

    assert package["schema_name"] == "cineforge.phase_one_script_package"
    assert package["schema_version"] == 1
    for key in (
        "project_title",
        "logline",
        "short_synopsis",
        "detailed_treatment",
        "complete_script",
        "narration_script",
        "dialogue_script",
        "non_dialogue_action",
        "silent_visual_beats",
        "emotional_progression",
        "dramatic_escalation",
        "duration_analysis",
        "script_word_count",
        "generation_boundary",
    ):
        assert key in package, key
    assert set(package["duration_analysis"]) >= {
        "target_duration_sec",
        "narration_duration_sec",
        "dialogue_duration_sec",
        "planned_silence_visual_duration_sec",
        "estimated_total_duration_sec",
    }

    retained = client.post(
        f"/production/stories/{story_id}/phases/1/versions",
        json={"label": "Director freeze", "notes": "Keep package visible", "requested_by": "tester"},
    )
    assert retained.status_code in {200, 201}, retained.text
    body = retained.json()
    head = body["version"]["output_json"]
    assert head["schema_name"] == "cineforge.phase_one_script_package"
    assert head["project_title"] == package["project_title"]
    assert head["complete_script"] == package["complete_script"]
    assert body["pipeline"]["phases"][0]["latest_version"]["output_json"]["schema_name"] == (
        "cineforge.phase_one_script_package"
    )

    # Revision still works against the retained head's version number.
    revised = client.put(
        f"/production/stories/{story_id}/phases/1",
        json={
            "expected_version_number": body["version"]["version_number"],
            "project_title": package["project_title"],
            "logline": package["logline"] + " Review note retained.",
            "short_synopsis": package["short_synopsis"],
            "detailed_treatment": package["detailed_treatment"],
            "complete_script": package["complete_script"],
            "narration_script": package["narration_script"],
            "dialogue_script": package["dialogue_script"],
            "non_dialogue_action": package["non_dialogue_action"],
            "silent_visual_beats": package["silent_visual_beats"],
            "emotional_progression": package["emotional_progression"],
            "dramatic_escalation": package["dramatic_escalation"],
            "source_fidelity_notes": package["source_fidelity_notes"],
            "creative_assumptions": package["creative_assumptions"],
            "requested_by": "tester",
        },
    )
    assert revised.status_code == 200, revised.text
    assert "Review note retained" in revised.json()["phase"]["latest_version"]["output_json"]["logline"]
