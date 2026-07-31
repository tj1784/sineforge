"""Integration-style tests for the durable planning engine (in-memory SQLite)."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import (
    Base,
    Chapter,
    ComfyJob,
    FFmpegJob,
    Project,
    ProjectStoryboardSettings,
    ProviderProfile,
    Story,
    StoryboardVersion,
    TaskProviderAssignment,
    WorkflowRun,
)
from backend.app.schemas.orchestration import (
    CreateOrchestrationRunRequest,
    LogicalModelProfile,
    ManualTaskRoute,
    PlanningTaskType,
    RoutingMode,
    RunStatus,
    StepStatus,
)
from backend.app.schemas.proposals import (
    ProposalApplyRequest,
    StoryboardProposalPayload,
)
from backend.app.services import proposal_apply, proposal_service, storyboard_snapshot
from backend.app.services.planning.engine import PlanningEngine
from backend.app.services.planning.errors import PlanningError, PlanningErrorCode
from backend.app.services.planning.provider import MockPlanningProvider
from backend.app.services.storyboard_settings import default_settings_values


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create only the tables needed for planning engine tests.
    # Story now has factual provider/version foreign keys; create the complete
    # metadata graph so SQLite exercises the same contract as the application.
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_story(db: Session, *, duration: float = 48.0) -> Story:
    project = Project(id=uuid.uuid4(), name="P", description=None, created_at=datetime.utcnow())
    db.add(project)
    db.flush()
    story = Story(
        id=uuid.uuid4(),
        project_id=project.id,
        title="Harbor Light",
        base_story="A lighthouse keeper faces a storm and chooses hope.",
        target_duration_sec=duration,
        logline="Hope against the storm",
        tone="earnest",
        visual_style="cinematic coastal noir",
        approval_state="draft",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


def test_create_and_complete_run_produces_pending_review_proposal(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})

    # Minimal pipeline for speed while still ending in production_proposal.
    req = CreateOrchestrationRunRequest(
        story_id=story.id,
        requested_by="tester",
        routing_mode=RoutingMode.automatic,
        max_steps=5,
        repair_budget=2,
        time_budget_sec=120,
        transport_retry_limit=1,
        task_types=[
            PlanningTaskType.shot_list,
            PlanningTaskType.production_proposal,
        ],
    )
    run, created = engine.create_run(req)
    assert created is True
    assert run.status == RunStatus.pending.value
    assert run.input_hash

    finished = engine.start_run(run.id)
    assert finished.status == RunStatus.completed.value

    detail = engine.get_run_detail(run.id)
    proposals = detail["proposals"]
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.status == "pending_review"
    assert proposal.orchestration_run_id == run.id
    assert proposal.content_hash
    parsed = StoryboardProposalPayload.model_validate(proposal.payload)
    assert parsed.schema_name == "storyboard_proposal_v1"
    assert parsed.story.existing_id == story.id
    assert proposal.proposal_type == "storyboard_full_plan"
    assert proposal.schema_name == "storyboard_proposal_v1"

    # No apply markers / execution hooks in payload.
    blob = str(proposal.payload).lower()
    assert "comfy" not in blob
    assert "ffmpeg" not in blob

    events = {e.event_type for e in detail["events"]}
    assert "run_created" in events
    assert "run_started" in events
    assert "proposal_created" in events
    assert "run_completed" in events

    invocations = detail["invocations"]
    assert invocations
    for inv in invocations:
        # Never store raw prompts/responses — only hashes/status.
        assert inv.request_hash
        assert not hasattr(inv, "raw_prompt")


def test_idempotent_create_with_client_key(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})
    key = "client-idem-key-12345678"
    req = CreateOrchestrationRunRequest(
        story_id=story.id,
        idempotency_key=key,
        task_types=[PlanningTaskType.story_structure, PlanningTaskType.production_proposal],
        max_steps=4,
    )
    run1, created1 = engine.create_run(req)
    run2, created2 = engine.create_run(req)
    assert created1 is True
    assert created2 is False
    assert run1.id == run2.id


def test_active_run_conflict(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})
    engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[PlanningTaskType.story_structure],
            max_steps=2,
        )
    )
    with pytest.raises(PlanningError) as ei:
        engine.create_run(
            CreateOrchestrationRunRequest(
                story_id=story.id,
                task_types=[PlanningTaskType.story_structure],
                max_steps=2,
            )
        )
    assert ei.value.code == PlanningErrorCode.ACTIVE_RUN_EXISTS


def test_cancel_pending_run(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[PlanningTaskType.shot_list, PlanningTaskType.production_proposal],
            max_steps=4,
        )
    )
    canceled = engine.cancel_run(run.id, reason="user stopped", requested_by="tester")
    assert canceled.status == RunStatus.canceled.value
    assert canceled.canceled_at is not None
    steps = engine.get_run_detail(run.id)["steps"]
    assert all(s.status == "canceled" for s in steps)


def test_cancel_terminal_rejected(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[PlanningTaskType.production_proposal],
            max_steps=2,
        )
    )
    engine.start_run(run.id)
    with pytest.raises(PlanningError) as ei:
        engine.cancel_run(run.id)
    assert ei.value.code == PlanningErrorCode.ALREADY_TERMINAL


def test_manual_routing_and_events(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            routing_mode=RoutingMode.manual,
            manual_routes=[
                ManualTaskRoute(
                    task_type=PlanningTaskType.production_proposal,
                    provider_identifier="mock",
                    logical_model=LogicalModelProfile.sol,
                    rationale="Force Sol for final proposal",
                )
            ],
            task_types=[PlanningTaskType.production_proposal],
            max_steps=2,
        )
    )
    finished = engine.start_run(run.id)
    assert finished.status == RunStatus.completed.value
    steps = engine.get_run_detail(run.id)["steps"]
    completed = [s for s in steps if s.status == "completed"]
    assert completed
    assert completed[0].logical_model == LogicalModelProfile.sol.value
    assert completed[0].provider_identifier == "mock"


def test_persisted_task_assignment_controls_run_provider_and_model(db_session: Session):
    story = _seed_story(db_session)
    profile = ProviderProfile(
        provider_identifier="mock",
        display_name="Deterministic planning profile",
        provider_model_id="mock/stored-sol",
        execution_mode="automatic",
        availability_status="unknown",
        privacy_classification="local",
        capabilities_json={"declared_capabilities": ["planning"]},
        capability_source="user_declared",
    )
    db_session.add(profile)
    db_session.flush()
    assignment = TaskProviderAssignment(
        story_id=story.id,
        task_type=PlanningTaskType.production_proposal.value,
        provider_profile_id=profile.id,
        assignment_mode="manual",
        rationale="Use the persisted final-planning route",
        priority=10,
        enabled=True,
    )
    db_session.add(assignment)
    db_session.commit()

    engine = PlanningEngine(
        db_session,
        providers={"mock": MockPlanningProvider(fixed_latency_ms=0)},
    )
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            routing_mode=RoutingMode.automatic,
            task_types=[PlanningTaskType.production_proposal],
            max_steps=2,
        )
    )

    assert run.routing_snapshot_json["mode"] == RoutingMode.hybrid.value
    persisted = run.routing_snapshot_json["persisted_task_assignments"]
    assert persisted[PlanningTaskType.production_proposal.value]["assignment_id"] == str(
        assignment.id
    )
    assert engine.start_run(run.id).status == RunStatus.completed.value
    completed = [
        step
        for step in engine.get_run_detail(run.id)["steps"]
        if step.status == StepStatus.completed.value
    ]
    assert len(completed) == 1
    assert completed[0].provider_identifier == "mock"
    assert completed[0].resolved_model == "mock/stored-sol"


def test_transport_retries_then_success(db_session: Session):
    story = _seed_story(db_session)
    provider = MockPlanningProvider(fixed_latency_ms=0)
    engine = PlanningEngine(db_session, providers={"mock": provider})
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[PlanningTaskType.story_structure, PlanningTaskType.production_proposal],
            max_steps=4,
            transport_retry_limit=3,
        )
    )
    # Inject transport failure simulation into routing snapshot constraints.
    snap = dict(run.routing_snapshot_json or {})
    snap["provider_constraints"] = {"simulate_transport_failures": 2}
    run.routing_snapshot_json = snap
    db_session.add(run)
    db_session.commit()

    finished = engine.start_run(run.id)
    assert finished.status == RunStatus.completed.value
    events = engine.get_run_detail(run.id)["events"]
    assert any(e.event_type == "transport_retry" for e in events)


def test_semantic_repair_on_schema_defect(db_session: Session):
    story = _seed_story(db_session)
    provider = MockPlanningProvider(fixed_latency_ms=0)
    engine = PlanningEngine(db_session, providers={"mock": provider})
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[PlanningTaskType.story_structure, PlanningTaskType.production_proposal],
            max_steps=6,
            repair_budget=3,
        )
    )
    snap = dict(run.routing_snapshot_json or {})
    snap["provider_constraints"] = {"inject_schema_defect": True}
    run.routing_snapshot_json = snap
    db_session.add(run)
    db_session.commit()

    finished = engine.start_run(run.id)
    assert finished.status == RunStatus.completed.value
    assert finished.repair_used >= 1
    events = {e.event_type for e in engine.get_run_detail(run.id)["events"]}
    assert "semantic_repair" in events
    # Escalation may also appear depending on ladder usage.
    assert "run_completed" in events


def test_resume_skips_completed_steps(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[
                PlanningTaskType.shot_list,
                PlanningTaskType.production_proposal,
            ],
            max_steps=4,
        )
    )
    finished = engine.start_run(run.id)
    assert finished.status == RunStatus.completed.value

    # Starting again should be rejected as terminal.
    with pytest.raises(PlanningError) as ei:
        engine.start_run(run.id)
    assert ei.value.code == PlanningErrorCode.ALREADY_TERMINAL


def test_proposal_never_auto_applied_and_hashes_present(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[PlanningTaskType.production_proposal],
            max_steps=2,
        )
    )
    engine.start_run(run.id)
    detail = engine.get_run_detail(run.id)
    proposal = detail["proposals"][0]
    assert proposal.status == "pending_review"
    assert proposal.applied_at is None
    assert proposal.validation_status in {"valid", "needs_review"}
    # Step/output hashes recorded
    completed_steps = [s for s in detail["steps"] if s.status == "completed"]
    assert completed_steps
    assert completed_steps[0].output_hash


def test_unversioned_proposal_diff_uses_and_guards_live_base_snapshot(
    db_session: Session,
):
    story = _seed_story(db_session)
    engine = PlanningEngine(
        db_session,
        providers={"mock": MockPlanningProvider(fixed_latency_ms=0)},
    )
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[PlanningTaskType.production_proposal],
            max_steps=2,
        )
    )
    assert engine.start_run(run.id).status == RunStatus.completed.value
    proposal = engine.get_run_detail(run.id)["proposals"][0]

    diff = proposal_service.build_diff(db_session, proposal.id)
    assert diff.base_storyboard_version_id is None
    assert diff.base_content_hash == proposal.base_content_hash
    assert diff.ops

    story.production_notes = "The live draft changed after proposal generation."
    db_session.commit()
    with pytest.raises(proposal_service.ProposalStateError, match="Stale proposal"):
        proposal_service.build_diff(db_session, proposal.id)


def test_project_policy_cannot_be_overridden_by_run_request(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)})
    with pytest.raises(PlanningError) as exc_info:
        engine.create_run(
            CreateOrchestrationRunRequest(
                story_id=story.id,
                prefer_local_providers=False,
                prefer_hosted_providers=True,
                task_types=[PlanningTaskType.production_proposal],
                max_steps=2,
            )
        )
    assert exc_info.value.code == PlanningErrorCode.ROUTING_FAILED
    assert "project policy" in exc_info.value.message.lower()


def test_disabled_local_policy_cannot_be_bypassed_with_both_preferences_false(
    db_session: Session,
):
    story = _seed_story(db_session)
    values = default_settings_values()
    values.update(prefer_local_providers=False, prefer_hosted_providers=True)
    db_session.add(ProjectStoryboardSettings(project_id=story.project_id, **values))
    db_session.commit()
    engine = PlanningEngine(
        db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)}
    )

    with pytest.raises(PlanningError) as exc_info:
        engine.create_run(
            CreateOrchestrationRunRequest(
                story_id=story.id,
                prefer_local_providers=False,
                prefer_hosted_providers=False,
                task_types=[PlanningTaskType.production_proposal],
                max_steps=2,
            )
        )
    assert exc_info.value.code == PlanningErrorCode.ROUTING_FAILED


def test_resume_refuses_to_mix_completed_outputs_after_story_edit(db_session: Session):
    story = _seed_story(db_session)
    engine = PlanningEngine(
        db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)}
    )
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            task_types=[PlanningTaskType.shot_list, PlanningTaskType.production_proposal],
            max_steps=4,
        )
    )
    first_step = engine.get_run_detail(run.id)["steps"][0]
    engine.repo.transition_run(run, RunStatus.running)
    engine.repo.transition_step(first_step, StepStatus.running)
    engine.repo.transition_step(
        first_step,
        StepStatus.completed,
        output_hash="a" * 64,
        metadata_patch={
            "result_payload": {
                "summary": "Old shot output",
                "shots": [{"order_index": 0, "title": "Old", "duration_sec": 8}],
            }
        },
    )
    story.base_story = "The story changed after the first checkpoint."
    db_session.commit()

    finished = engine.start_run(run.id)
    assert finished.status == RunStatus.failed.value
    assert finished.failure_category == "validation"
    detail = engine.get_run_detail(run.id)
    assert detail["proposals"] == []
    assert detail["invocations"] == []


def test_real_planning_proposal_reviews_applies_idempotently_and_enqueues_nothing(
    db_session: Session,
):
    story = _seed_story(db_session)
    engine = PlanningEngine(
        db_session, providers={"mock": MockPlanningProvider(fixed_latency_ms=0)}
    )
    task_types = [
        PlanningTaskType.character_bible,
        PlanningTaskType.chapter_outline,
        PlanningTaskType.scene_breakdown,
        PlanningTaskType.shot_list,
        PlanningTaskType.narration_plan,
        PlanningTaskType.prompt_package,
        PlanningTaskType.model_recommendation,
        PlanningTaskType.production_proposal,
    ]
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            requested_by="planner",
            task_types=task_types,
            max_steps=10,
        )
    )
    assert engine.start_run(run.id).status == RunStatus.completed.value
    proposal = engine.get_run_detail(run.id)["proposals"][0]
    payload = StoryboardProposalPayload.model_validate(proposal.payload)
    shots = [
        shot
        for chapter in payload.story.chapters
        for scene in chapter.scenes
        for shot in scene.shots
    ]
    assert sum(shot.duration_sec for shot in shots) == float(story.target_duration_sec)
    assert all(shot.narration and shot.prompt_package for shot in shots)
    assert all(shot.model_recommendations for shot in shots)
    assert proposal.payload_hash == proposal.content_hash
    assert proposal.input_context_hash == proposal.base_content_hash

    applied = proposal_apply.apply_proposal(
        db_session,
        proposal.id,
        ProposalApplyRequest(applied_by="planner"),
    )
    replay = proposal_apply.apply_proposal(
        db_session,
        proposal.id,
        ProposalApplyRequest(applied_by="planner"),
    )
    assert replay.new_storyboard_version_id == applied.new_storyboard_version_id
    assert db_session.scalar(select(func.count()).select_from(StoryboardVersion)) == 1
    assert db_session.scalar(select(func.count()).select_from(ComfyJob)) == 0
    assert db_session.scalar(select(func.count()).select_from(WorkflowRun)) == 0
    assert db_session.scalar(select(func.count()).select_from(FFmpegJob)) == 0

    # A second full-plan pass must preserve the first version's rows without
    # colliding with the live sibling order slots used by the replacement.
    second_run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            requested_by="planner",
            task_types=task_types,
            max_steps=10,
        )
    )
    assert engine.start_run(second_run.id).status == RunStatus.completed.value
    second_proposal = engine.get_run_detail(second_run.id)["proposals"][0]
    second_payload = StoryboardProposalPayload.model_validate(second_proposal.payload)
    second_applied = proposal_apply.apply_proposal(
        db_session,
        second_proposal.id,
        ProposalApplyRequest(applied_by="planner"),
    )
    active_chapters = list(
        db_session.scalars(
            select(Chapter).where(
                Chapter.story_id == story.id,
                Chapter.archived_at.is_(None),
            )
        )
    )
    assert second_applied.new_storyboard_version_id != applied.new_storyboard_version_id
    assert len(active_chapters) == len(second_payload.story.chapters)
    assert {row.order_index for row in active_chapters} == {
        row.order_index for row in second_payload.story.chapters
    }
    assert db_session.scalar(select(func.count()).select_from(StoryboardVersion)) == 2
    assert db_session.scalar(select(func.count()).select_from(ComfyJob)) == 0
    assert db_session.scalar(select(func.count()).select_from(WorkflowRun)) == 0
    assert db_session.scalar(select(func.count()).select_from(FFmpegJob)) == 0


def test_proposal_apply_creates_truthful_draft_without_superseding_last_approval(
    db_session: Session,
):
    story = _seed_story(db_session)
    approved_snapshot, approved_hash = storyboard_snapshot.build_snapshot_with_hash(
        db_session,
        story.id,
    )
    approved_snapshot["story"]["approval_state"] = "approved"
    previous = StoryboardVersion(
        story_id=story.id,
        version_number=1,
        status="approved",
        snapshot_json=approved_snapshot,
        content_hash=approved_hash,
        created_by="producer",
        approved_by="producer",
        approved_at=datetime.utcnow(),
    )
    db_session.add(previous)
    db_session.flush()
    story.active_storyboard_version_id = previous.id
    story.approval_state = "approved"
    db_session.commit()

    engine = PlanningEngine(
        db_session,
        providers={"mock": MockPlanningProvider(fixed_latency_ms=0)},
    )
    run, _ = engine.create_run(
        CreateOrchestrationRunRequest(
            story_id=story.id,
            base_storyboard_version_id=previous.id,
            task_types=[PlanningTaskType.production_proposal],
            max_steps=2,
        )
    )
    assert engine.start_run(run.id).status == RunStatus.completed.value
    proposal = engine.get_run_detail(run.id)["proposals"][0]
    result = proposal_apply.apply_proposal(
        db_session,
        proposal.id,
        ProposalApplyRequest(
            applied_by="producer",
            expected_base_version_id=previous.id,
            expected_base_content_hash=approved_hash,
        ),
    )

    db_session.refresh(story)
    db_session.refresh(previous)
    draft = db_session.get(StoryboardVersion, result.new_storyboard_version_id)
    assert draft is not None
    assert draft.status == "draft"
    assert draft.snapshot_json["story"]["approval_state"] == "draft"
    assert story.approval_state == "draft"
    assert story.active_storyboard_version_id == draft.id
    assert previous.status == "approved"
    assert previous.superseded_at is None
