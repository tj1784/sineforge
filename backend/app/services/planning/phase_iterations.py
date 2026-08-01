"""Real local-agent generation for individual planning-phase iterations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import (
    AIProposalRecord,
    ProductionPhase,
    ProductionPhaseVersion,
    ProjectStoryboardSettings,
    Story,
)
from backend.app.schemas.orchestration import (
    CreateOrchestrationRunRequest,
    LogicalModelProfile,
    ManualTaskRoute,
    PlanningTaskType,
    RoutingMode,
)
from backend.app.schemas.production import (
    PlanningPhaseIterationRequest,
    PlanningPhaseIterationResponse,
)
from backend.app.schemas.proposals import ProposalApplyRequest
from backend.app.services import production_phases, proposal_apply
from backend.app.services.planning.engine import PlanningEngine
from backend.app.services.planning.errors import PlanningError


class PhaseIterationPlanningError(RuntimeError):
    pass


class PhaseIterationActiveRunError(PhaseIterationPlanningError):
    pass


_PHASE_TASKS: dict[int, tuple[PlanningTaskType, ...]] = {
    2: (PlanningTaskType.scene_breakdown, PlanningTaskType.shot_list),
    3: (PlanningTaskType.character_bible,),
    4: (PlanningTaskType.continuity_plan, PlanningTaskType.prompt_package),
    5: (PlanningTaskType.prompt_package, PlanningTaskType.model_recommendation),
}

_TASK_QUALITY: dict[PlanningTaskType, LogicalModelProfile] = {
    PlanningTaskType.scene_breakdown: LogicalModelProfile.terra,
    PlanningTaskType.shot_list: LogicalModelProfile.terra,
    PlanningTaskType.character_bible: LogicalModelProfile.terra,
    PlanningTaskType.continuity_plan: LogicalModelProfile.terra,
    PlanningTaskType.prompt_package: LogicalModelProfile.sol,
    PlanningTaskType.model_recommendation: LogicalModelProfile.luna,
}


def _existing_version_for_run(
    db: Session,
    *,
    phase_id: UUID,
    run_id: UUID,
) -> ProductionPhaseVersion | None:
    rows = list(
        db.scalars(
            select(ProductionPhaseVersion)
            .where(ProductionPhaseVersion.production_phase_id == phase_id)
            .order_by(ProductionPhaseVersion.version_number.desc())
        )
    )
    return next(
        (
            row
            for row in rows
            if str((row.input_snapshot_json or {}).get("orchestration_run_id") or "")
            == str(run_id)
        ),
        None,
    )


def generate_planning_phase_iteration(
    db: Session,
    *,
    story_id: UUID,
    phase_number: int,
    payload: PlanningPhaseIterationRequest,
) -> PlanningPhaseIterationResponse:
    """Generate and apply one local planning iteration for Phase 2, 3, 4, or 5."""

    tasks = _PHASE_TASKS.get(phase_number)
    if tasks is None:
        raise PhaseIterationPlanningError(
            "Local-agent phase generation is available for planning Phases 2-5. "
            "Phase 1 uses script generation; Phases 6-8 use their media actions."
        )
    story = db.get(Story, story_id)
    if story is None:
        raise PhaseIterationPlanningError("Story not found.")
    phase = db.scalar(
        select(ProductionPhase).where(
            ProductionPhase.story_id == story.id,
            ProductionPhase.phase_number == phase_number,
        )
    )
    if phase is None:
        raise PhaseIterationPlanningError(f"Phase {phase_number} is missing.")
    if phase.is_locked:
        raise PhaseIterationPlanningError(
            phase.locked_reason or f"Phase {phase_number} is locked."
        )

    settings = db.scalar(
        select(ProjectStoryboardSettings).where(
            ProjectStoryboardSettings.project_id == story.project_id
        )
    )
    policy = dict(settings.prompting_policy_json or {}) if settings is not None else {}
    agent = str(policy.get("planning_agent") or "qwen")
    model_id = policy.get("planning_model_id")
    if agent not in {"qwen", "sulphur", "grok"}:
        raise PhaseIterationPlanningError(
            "The project does not have a valid local planning agent selected."
        )

    routes = [
        ManualTaskRoute(
            task_type=task,
            provider_identifier=agent,
            logical_model=_TASK_QUALITY[task],
            resolved_model=str(model_id) if model_id else None,
            rationale=f"Phase {phase_number} user-requested local iteration.",
        )
        for task in tasks
    ]
    instruction = "\n\n".join(
        part
        for part in (
            f"Generate a new iteration specifically for Phase {phase_number}: {phase.name}.",
            f"Iteration label: {payload.label.strip()}",
            payload.notes.strip() or None,
            "Preserve approved facts outside this phase and return strict JSON only.",
        )
        if part
    )
    engine = PlanningEngine(db)
    try:
        run, created = engine.create_run(
            CreateOrchestrationRunRequest(
                story_id=story.id,
                base_storyboard_version_id=story.active_storyboard_version_id,
                requested_by=payload.requested_by or "CineForge phase iteration",
                routing_mode=RoutingMode.manual,
                manual_routes=routes,
                prefer_local_providers=True,
                prefer_hosted_providers=False,
                max_steps=len(tasks),
                repair_budget=max(3, len(tasks) * 2),
                time_budget_sec=3600,
                transport_retry_limit=2,
                idempotency_key=(
                    f"phase-{phase_number}-iteration-{payload.idempotency_key}"
                )[:128],
                planning_instruction=instruction,
                proposal_type="storyboard_revision",
                task_types=list(tasks),
            )
        )
        existing = _existing_version_for_run(db, phase_id=phase.id, run_id=run.id)
        if existing is not None:
            return PlanningPhaseIterationResponse(
                version=production_phases.get_phase_version(
                    db, story.id, phase_number, existing.id
                ),
                pipeline=production_phases.get_pipeline(db, story.id, ensure=False),
                orchestration_run_id=run.id,
                proposal_id=UUID(
                    str((existing.input_snapshot_json or {})["proposal_id"])
                ),
                idempotent_replay=True,
                message=f"Phase {phase_number} iteration already generated; reused it.",
            )
        if run.status in {"pending", "running"}:
            run = engine.start_run(run.id)
        if run.status != "completed":
            raise PhaseIterationPlanningError(
                f"Phase {phase_number} local generation ended with status={run.status}."
            )

        proposal = db.scalar(
            select(AIProposalRecord).where(
                AIProposalRecord.orchestration_run_id == run.id
            )
        )
        if proposal is None:
            raise PhaseIterationPlanningError(
                f"Phase {phase_number} generation produced no validated proposal."
            )
        if proposal.status != "applied":
            proposal_apply.apply_proposal(
                db,
                proposal.id,
                ProposalApplyRequest(
                    applied_by=payload.requested_by or "CineForge phase iteration",
                    expected_base_version_id=proposal.base_storyboard_version_id,
                    expected_base_content_hash=proposal.base_content_hash,
                ),
            )
        db.refresh(story)
        version = production_phases.retain_generated_planning_phase(
            db,
            story.id,
            phase_number,
            orchestration_run_id=run.id,
            proposal_id=proposal.id,
            created_by=payload.requested_by or f"{agent}:phase_iteration",
            label=payload.label,
            notes=payload.notes,
            invalidate_downstream=True,
            commit=True,
        )
        return PlanningPhaseIterationResponse(
            version=production_phases.get_phase_version(
                db, story.id, phase_number, version.id
            ),
            pipeline=production_phases.get_pipeline(db, story.id, ensure=False),
            orchestration_run_id=run.id,
            proposal_id=proposal.id,
            idempotent_replay=not created,
            message=(
                f"Phase {phase_number} generated by the selected local agent and "
                "saved as a new reviewable iteration."
            ),
        )
    except PhaseIterationPlanningError:
        db.rollback()
        raise
    except PlanningError as exc:
        db.rollback()
        if exc.code.value == "active_run_exists":
            raise PhaseIterationActiveRunError(exc.message) from exc
        raise PhaseIterationPlanningError(exc.message) from exc
    except Exception as exc:
        db.rollback()
        raise PhaseIterationPlanningError(
            f"Phase {phase_number} local generation failed: {exc}"
        ) from exc
