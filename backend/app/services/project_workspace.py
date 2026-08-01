"""Atomic and idempotent project workspace creation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.base import (
    AIProposalRecord,
    Project,
    ProjectStoryboardSettings,
    ProjectWorkspaceCreation,
    ProductionPhase,
    ProductionPhaseVersion,
    Story,
)
from backend.app.schemas.api import ProjectWorkspaceCreate
from backend.app.schemas.orchestration import (
    CreateOrchestrationRunRequest,
    LogicalModelProfile,
    ManualTaskRoute,
    PlanningTaskType,
    RoutingMode,
)
from backend.app.schemas.production import PhaseApproveRequest, PhaseOneGenerationInput
from backend.app.schemas.proposals import ProposalApplyRequest
from backend.app.services import production_phases
from backend.app.services import proposal_apply
from backend.app.services.planning.engine import PlanningEngine
from backend.app.services.planning.errors import PlanningError
from backend.app.services.sulphur_storyboard_bootstrap import (
    approve_generated_planning_records,
    bootstrap_from_phase_one,
)
from backend.app.services.storyboard_settings import (
    apply_workflow_lane_policy,
    default_settings_values,
    production_profile_settings_values,
)


class ProjectWorkspaceConflictError(ValueError):
    pass


class ProjectWorkspacePlanningError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectWorkspaceResult:
    project: Project
    story: Story
    settings: ProjectStoryboardSettings
    idempotent_replay: bool
    initial_planning_run_id: UUID | None = None
    completed_planning_phases: tuple[int, ...] = ()


_PHASE_TWO_THROUGH_FIVE_TASKS = (
    PlanningTaskType.character_bible,
    PlanningTaskType.scene_breakdown,
    PlanningTaskType.shot_list,
    PlanningTaskType.prompt_package,
    PlanningTaskType.production_proposal,
)

_TASK_QUALITY = {
    PlanningTaskType.character_bible: LogicalModelProfile.terra,
    PlanningTaskType.scene_breakdown: LogicalModelProfile.terra,
    PlanningTaskType.shot_list: LogicalModelProfile.luna,
    PlanningTaskType.prompt_package: LogicalModelProfile.luna,
    PlanningTaskType.production_proposal: LogicalModelProfile.sol,
}


def _local_agent_label(agent: str) -> str:
    return {
        "qwen": "Qwen3 4B Hivemind",
        "sulphur": "Sulphur 2 Base",
        "grok": "Grok",
    }.get(agent, agent)


def _request_hash(payload: ProjectWorkspaceCreate) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json", exclude={"idempotency_key"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _new_story(project_id, payload: ProjectWorkspaceCreate) -> Story:
    chapter_guidance = _chapter_guidance_text(payload)
    production_notes = payload.production_notes
    if chapter_guidance:
        production_notes = "\n\n".join(
            part for part in (production_notes, chapter_guidance) if part
        )
    return Story(
        project_id=project_id,
        title=payload.story_title,
        base_story=payload.base_story,
        target_duration_sec=payload.target_duration_sec,
        audience=payload.audience,
        genre=payload.genre,
        tone=payload.tone,
        point_of_view=payload.point_of_view,
        visual_style=payload.visual_style,
        production_notes=production_notes,
        approval_state="draft",
    )


def _derived_title(prompt: str) -> str:
    """Derive a reviewable working title without assuming any story domain."""
    first = next(
        (line.strip() for line in re.split(r"[\r\n]+", prompt) if line.strip()),
        "Untitled CineForge Production",
    )
    named_project_match = re.search(
        r"\b(?:project|film|story|production)\s+(?:named|called|titled)\s+"
        r"[\"'“”]?([^:;.\r\n\"'“”]+)",
        first,
        flags=re.IGNORECASE,
    )
    subject_match = re.search(
        r"\b(?:story|film|narrative|sequence|documentary)\s+(?:about|of)\s+(.+?)(?:\s+using\b|\s+with\b|[.;]|$)",
        first,
        flags=re.IGNORECASE,
    )
    candidate = (
        named_project_match.group(1)
        if named_project_match
        else subject_match.group(1)
        if subject_match
        else first
    )
    candidate = re.sub(
        r"^(?:create|develop|write|make)\s+(?:an?\s+)?(?:\d+[\s-]*(?:minute|min)\s+)?",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip(" .,:;–—-")
    words = candidate.split()
    if len(words) > 10:
        candidate = " ".join(words[:10]).rstrip(" ,;:")
    if not candidate:
        return "Untitled CineForge Production"
    titled = candidate[0].upper() + candidate[1:]
    return titled[:200]


def _chapter_guidance_text(payload: ProjectWorkspaceCreate) -> str:
    if payload.requested_chapter_count <= 1 and not payload.chapter_intake:
        return ""
    lines = [
        "Project creation chapter guidance:",
        f"- Requested chapter count: {payload.requested_chapter_count}",
    ]
    for chapter in payload.chapter_intake:
        details = [
            f"Chapter {chapter.order_index + 1}: {chapter.title}",
        ]
        if chapter.target_duration_sec:
            details.append(f"target {chapter.target_duration_sec:g}s")
        if chapter.summary:
            details.append(f"summary: {chapter.summary.strip()}")
        if chapter.source_prompt:
            details.append(f"source prompt: {chapter.source_prompt.strip()}")
        if chapter.narrative_purpose:
            details.append(f"purpose: {chapter.narrative_purpose.strip()}")
        if chapter.dramatic_progression:
            details.append(f"progression: {chapter.dramatic_progression.strip()}")
        if chapter.production_notes:
            details.append(f"notes: {chapter.production_notes.strip()}")
        lines.append("- " + " | ".join(details))
    return "\n".join(lines)


def _planning_prompt_artifact(payload: ProjectWorkspaceCreate) -> dict:
    """Build the canonical JSON prompt artifact retained with project policy."""

    agentless = payload.workflow_lane.value == "agentless"
    artifact = {
        "schema_version": payload.prompt_schema_version,
        "artifact_format": payload.prompt_artifact_format,
        "artifact_filename": "project-planning-prompt.json",
        "workflow_lane": payload.workflow_lane.value,
        "planning_agent": payload.planning_agent,
        "planning_model_id": payload.planning_model_id,
        "source": {
            "mode": payload.source_mode,
            "user_text": payload.base_story,
        },
        "project": {
            "title": payload.name,
            "description": payload.description,
            "target_duration_sec": payload.target_duration_sec,
            "audience": payload.audience,
            "genre": payload.genre,
            "tone": payload.tone,
            "point_of_view": payload.point_of_view,
            "visual_style": payload.visual_style,
            "language": payload.language,
        },
        "chapters": [
            item.model_dump(mode="json") for item in payload.chapter_intake
        ],
        "execution_policy": {
            "hosted_agents_allowed": (
                False if agentless else payload.prefer_hosted_providers
            ),
            "local_planning_runtime": "lm_studio",
            "production_orchestrator": (
                "deterministic_python"
                if agentless
                else payload.orchestration_mode
            ),
            "rendering_during_creation": False,
        },
    }
    if payload.theme_id.value != "default":
        artifact["creative_theme"] = {
            "theme_id": payload.theme_id.value,
            "theme_version": "1.0.0",
            "theme_context": (
                payload.theme_context.model_dump(mode="json", exclude_none=True)
                if payload.theme_context is not None
                else None
            ),
        }
    return artifact


def _new_settings(project_id, payload: ProjectWorkspaceCreate) -> ProjectStoryboardSettings:
    agentless = payload.workflow_lane.value == "agentless"
    values = default_settings_values(payload.workflow_lane)
    values.update(
        {
            "aspect_ratio": payload.aspect_ratio,
            "preview_width": payload.preview_width,
            "preview_height": payload.preview_height,
            "final_width": payload.final_width,
            "final_height": payload.final_height,
            "fps": payload.fps,
            "captions_enabled": payload.captions_enabled,
            "audio_enabled": payload.audio_enabled,
            "production_profile_key": payload.production_profile_key,
            "stitch_stage": payload.stitch_stage,
            "speaking_rate": payload.speaking_rate,
            "prefer_hosted_providers": payload.prefer_hosted_providers,
            "prefer_local_providers": payload.prefer_local_providers,
            "allow_model_download": bool(payload.allow_model_download),
            "allow_rendering": bool(payload.allow_rendering),
            "require_production_plan_approval": bool(
                payload.require_production_plan_approval
            ),
        }
    )
    prompt_artifact = _planning_prompt_artifact(payload)
    prompt_artifact_bytes = json.dumps(
        prompt_artifact,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    values["prompting_policy_json"] = {
        **values["prompting_policy_json"],
        "orchestration_mode": payload.orchestration_mode,
        "planning_agent": payload.planning_agent,
        "planning_model_id": payload.planning_model_id,
        "planning_mode": "local_lm_studio",
        "local_planning_agent_required": agentless,
        "hosted_planning_agents_allowed": (
            False if agentless else payload.prefer_hosted_providers
        ),
        "prompt_artifact_format": payload.prompt_artifact_format,
        "prompt_schema_version": payload.prompt_schema_version,
        "prompt_artifact_filename": "project-planning-prompt.json",
        "prompt_artifact_url": (
            f"/projects/{project_id}/planning-prompt.json"
        ),
        "prompt_artifact_sha256": hashlib.sha256(
            prompt_artifact_bytes
        ).hexdigest(),
        "prompt_artifact": prompt_artifact,
        "privacy_preference": payload.privacy_preference,
        "quality_preference": payload.quality_preference,
        "cost_sensitivity": payload.cost_sensitivity,
        "requested_chapter_count": payload.requested_chapter_count,
        "chapter_intake": [
            item.model_dump(mode="json") for item in payload.chapter_intake
        ],
        "bootstrap_phase_plan": payload.bootstrap_phase_plan,
        "auto_approve_phases_through": payload.auto_approve_phases_through,
        "run_phases_two_through_five": payload.run_phases_two_through_five,
    }
    values.update(production_profile_settings_values(payload.production_profile_key))
    values = apply_workflow_lane_policy(values, payload.workflow_lane)
    return ProjectStoryboardSettings(project_id=project_id, **values)


def _load_replay(
    db: Session, record: ProjectWorkspaceCreation, request_hash: str
) -> ProjectWorkspaceResult:
    if record.request_hash != request_hash:
        raise ProjectWorkspaceConflictError(
            "That idempotency key was already used for a different project workspace request."
        )
    project = db.get(Project, record.project_id)
    story = db.get(Story, record.story_id)
    settings = db.get(ProjectStoryboardSettings, record.settings_id)
    if project is None or story is None or settings is None:
        raise RuntimeError("The project workspace replay record is incomplete.")
    return ProjectWorkspaceResult(project, story, settings, True)


def _completed_initial_planning_phases(
    db: Session,
    story_id: UUID,
    run_id: UUID,
) -> tuple[int, ...]:
    phases = list(
        db.scalars(
            select(ProductionPhase)
            .where(
                ProductionPhase.story_id == story_id,
                ProductionPhase.phase_number.in_([2, 3, 4, 5]),
            )
            .order_by(ProductionPhase.phase_number)
        )
    )
    completed: list[int] = []
    for phase in phases:
        versions = list(
            db.scalars(
                select(ProductionPhaseVersion).where(
                    ProductionPhaseVersion.production_phase_id == phase.id
                )
            )
        )
        if any(
            str((version.input_snapshot_json or {}).get("orchestration_run_id") or "")
            == str(run_id)
            for version in versions
        ):
            completed.append(phase.phase_number)
    return tuple(completed)


def _run_initial_phases_two_through_five(
    db: Session,
    *,
    payload: ProjectWorkspaceCreate,
    result: ProjectWorkspaceResult,
) -> ProjectWorkspaceResult:
    """Run, apply, retain, and approve the selected local Phase 2-5 plan.

    The former implementation called the local model only for Phase 1 and
    approved deterministic baselines for the remaining planning phases.  This
    path performs five provider-neutral local planning tasks, applies the
    validated proposal, then retains one generated version for each phase.
    """

    run_key = "workspace-p2-p5-" + hashlib.sha256(
        f"{payload.idempotency_key}|{result.story.id}".encode("utf-8")
    ).hexdigest()
    manual_routes = [
        ManualTaskRoute(
            task_type=task,
            provider_identifier=payload.planning_agent,
            logical_model=_TASK_QUALITY[task],
            resolved_model=payload.planning_model_id,
            rationale=(
                "New-project Phase 2-5 execution through the explicitly selected "
                "local planning agent."
            ),
        )
        for task in _PHASE_TWO_THROUGH_FIVE_TASKS
    ]
    engine = PlanningEngine(db)
    try:
        run, _created = engine.create_run(
            CreateOrchestrationRunRequest(
                story_id=result.story.id,
                base_storyboard_version_id=result.story.active_storyboard_version_id,
                requested_by="project_creation:phases_2_5",
                routing_mode=RoutingMode.manual,
                manual_routes=manual_routes,
                prefer_local_providers=True,
                prefer_hosted_providers=False,
                max_steps=len(_PHASE_TWO_THROUGH_FIVE_TASKS),
                repair_budget=5,
                time_budget_sec=3600,
                transport_retry_limit=2,
                idempotency_key=run_key,
                task_types=list(_PHASE_TWO_THROUGH_FIVE_TASKS),
            )
        )
        if run.status in {"pending", "running"}:
            run = engine.start_run(run.id)
        if run.status != "completed":
            raise ProjectWorkspacePlanningError(
                f"Local Phase 2-5 planning ended with status={run.status}."
            )

        detail = engine.get_run_detail(run.id)
        proposals = [
            proposal
            for proposal in detail["proposals"]
            if isinstance(proposal, AIProposalRecord)
        ]
        if len(proposals) != 1:
            raise ProjectWorkspacePlanningError(
                "Local Phase 2-5 planning did not produce exactly one validated proposal."
            )
        proposal = proposals[0]
        completed = _completed_initial_planning_phases(
            db, result.story.id, run.id
        )
        if completed == (2, 3, 4, 5):
            return ProjectWorkspaceResult(
                result.project,
                result.story,
                result.settings,
                result.idempotent_replay,
                run.id,
                completed,
            )

        if proposal.status != "applied":
            proposal_apply.apply_proposal(
                db,
                proposal.id,
                ProposalApplyRequest(
                    applied_by=f"{payload.planning_agent}:project_creation",
                    expected_base_version_id=proposal.base_storyboard_version_id,
                    expected_base_content_hash=proposal.base_content_hash,
                ),
            )
        db.refresh(result.story)
        approve_generated_planning_records(
            db,
            result.story,
            created_by=f"{payload.planning_agent}:project_creation",
        )

        for phase_number in range(2, 6):
            if phase_number not in completed:
                production_phases.retain_generated_planning_phase(
                    db,
                    result.story.id,
                    phase_number,
                    orchestration_run_id=run.id,
                    proposal_id=proposal.id,
                    created_by=f"{payload.planning_agent}:project_creation",
                    commit=False,
                )
            production_phases.approve_phase(
                db,
                result.story.id,
                phase_number,
                PhaseApproveRequest(
                    approved_by=f"{payload.planning_agent} local project planner",
                    notes=(
                        f"Phase {phase_number} completed by local orchestration run "
                        f"{run.id}; validated proposal {proposal.id} was applied."
                    ),
                ),
                commit=False,
            )
        db.commit()
        db.refresh(result.project)
        db.refresh(result.story)
        db.refresh(result.settings)
        return ProjectWorkspaceResult(
            result.project,
            result.story,
            result.settings,
            result.idempotent_replay,
            run.id,
            (2, 3, 4, 5),
        )
    except ProjectWorkspacePlanningError:
        db.rollback()
        raise
    except PlanningError as exc:
        db.rollback()
        raise ProjectWorkspacePlanningError(
            f"Local Phase 2-5 planning failed: {exc.message}"
        ) from exc
    except Exception as exc:
        db.rollback()
        raise ProjectWorkspacePlanningError(
            f"Local Phase 2-5 planning failed: {exc}"
        ) from exc


def create_project_workspace(db: Session, payload: ProjectWorkspaceCreate) -> ProjectWorkspaceResult:
    request_hash = _request_hash(payload)
    existing = db.scalar(
        select(ProjectWorkspaceCreation).where(
            ProjectWorkspaceCreation.idempotency_key == payload.idempotency_key
        )
    )
    if existing is not None:
        replay = _load_replay(db, existing, request_hash)
        return (
            _run_initial_phases_two_through_five(
                db,
                payload=payload,
                result=replay,
            )
            if payload.run_phases_two_through_five
            else replay
        )

    try:
        workspace_title = _derived_title(payload.base_story) if payload.auto_title else payload.name
        project = Project(
            name=workspace_title,
            description=payload.description,
            workflow_lane=payload.workflow_lane.value,
            theme_id=payload.theme_id.value,
            theme_version="1.0.0",
            theme_context_json=(
                payload.theme_context.model_dump(mode="json", exclude_none=True)
                if payload.theme_context is not None
                else {}
            ),
        )
        db.add(project)
        db.flush()

        story = _new_story(project.id, payload)
        if payload.auto_title:
            story.title = workspace_title
        settings = _new_settings(project.id, payload)
        db.add_all((story, settings))
        db.flush()

        production_phases.ensure_contract(db, story, commit=False)
        phase_one_package: dict | None = None
        if payload.run_phase_one:
            phase_one_response = production_phases.generate_phase_one(
                db,
                story.id,
                PhaseOneGenerationInput(
                    original_prompt=payload.base_story,
                    planning_agent=payload.planning_agent,
                    planning_model_id=payload.planning_model_id,
                    prompt_artifact_format=payload.prompt_artifact_format,
                    prompt_schema_version=payload.prompt_schema_version,
                    target_duration_sec=payload.target_duration_sec,
                    audience=payload.audience,
                    genre=payload.genre,
                    tone=payload.tone,
                    language=payload.language,
                    visual_style=payload.visual_style,
                    narration_dialogue_preference=payload.narration_dialogue_preference,
                    source_fidelity_constraints=payload.source_fidelity_constraints,
                    content_constraints=payload.content_constraints,
                    requested_chapter_count=payload.requested_chapter_count,
                    chapter_intake=[
                        item.model_dump(mode="json") for item in payload.chapter_intake
                    ],
                    comparison_baseline=payload.comparison_baseline,
                    requested_by="project_creation",
                ),
                commit=False,
            )
            latest = phase_one_response.phase.latest_version
            phase_one_package = latest.output_json if latest is not None else None

        if payload.bootstrap_phase_plan:
            if not isinstance(phase_one_package, dict):
                raise RuntimeError("Phase plan bootstrap requires a generated Phase 1 package.")
            agent_label = _local_agent_label(payload.planning_agent)
            bootstrap_from_phase_one(
                db,
                story,
                phase_one_package,
                requested_chapter_count=payload.requested_chapter_count,
                chapter_intake=[
                    item.model_dump(mode="json") for item in payload.chapter_intake
                ],
                created_by=f"{payload.planning_agent}_bootstrap",
                approve_records=not payload.run_phases_two_through_five,
            )

        if payload.auto_approve_phases_through:
            agent_label = _local_agent_label(payload.planning_agent)
            for phase_number in range(1, payload.auto_approve_phases_through + 1):
                production_phases.approve_phase(
                    db,
                    story.id,
                    phase_number,
                    PhaseApproveRequest(
                        approved_by=f"{agent_label} local bootstrap",
                        notes=(
                            f"Auto-approved Phase {phase_number} as an initial local/private "
                            f"{agent_label} planning baseline. User review and regeneration "
                            "remain available."
                        ),
                    ),
                    commit=False,
                )

        db.add(
            ProjectWorkspaceCreation(
                idempotency_key=payload.idempotency_key,
                request_hash=request_hash,
                project_id=project.id,
                story_id=story.id,
                settings_id=settings.id,
            )
        )
        db.commit()
        db.refresh(project)
        db.refresh(story)
        db.refresh(settings)
        result = ProjectWorkspaceResult(project, story, settings, False)
        return (
            _run_initial_phases_two_through_five(
                db,
                payload=payload,
                result=result,
            )
            if payload.run_phases_two_through_five
            else result
        )
    except IntegrityError:
        db.rollback()
        replay = db.scalar(
            select(ProjectWorkspaceCreation).where(
                ProjectWorkspaceCreation.idempotency_key == payload.idempotency_key
            )
        )
        if replay is None:
            raise
        result = _load_replay(db, replay, request_hash)
        return (
            _run_initial_phases_two_through_five(
                db,
                payload=payload,
                result=result,
            )
            if payload.run_phases_two_through_five
            else result
        )
    except Exception:
        db.rollback()
        raise
