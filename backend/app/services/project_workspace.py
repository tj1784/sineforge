"""Atomic and idempotent project workspace creation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.base import (
    Project,
    ProjectStoryboardSettings,
    ProjectWorkspaceCreation,
    Story,
)
from backend.app.schemas.api import ProjectWorkspaceCreate
from backend.app.schemas.production import PhaseApproveRequest, PhaseOneGenerationInput
from backend.app.services import production_phases
from backend.app.services.sulphur_storyboard_bootstrap import bootstrap_from_phase_one
from backend.app.services.storyboard_settings import default_settings_values


class ProjectWorkspaceConflictError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectWorkspaceResult:
    project: Project
    story: Story
    settings: ProjectStoryboardSettings
    idempotent_replay: bool


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


def _new_settings(project_id, payload: ProjectWorkspaceCreate) -> ProjectStoryboardSettings:
    values = default_settings_values()
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
    values["prompting_policy_json"] = {
        **values["prompting_policy_json"],
        "orchestration_mode": payload.orchestration_mode,
        "privacy_preference": payload.privacy_preference,
        "quality_preference": payload.quality_preference,
        "cost_sensitivity": payload.cost_sensitivity,
        "requested_chapter_count": payload.requested_chapter_count,
        "chapter_intake": [
            item.model_dump(mode="json") for item in payload.chapter_intake
        ],
        "bootstrap_phase_plan": payload.bootstrap_phase_plan,
        "auto_approve_phases_through": payload.auto_approve_phases_through,
    }
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


def create_project_workspace(db: Session, payload: ProjectWorkspaceCreate) -> ProjectWorkspaceResult:
    request_hash = _request_hash(payload)
    existing = db.scalar(
        select(ProjectWorkspaceCreation).where(
            ProjectWorkspaceCreation.idempotency_key == payload.idempotency_key
        )
    )
    if existing is not None:
        return _load_replay(db, existing, request_hash)

    try:
        workspace_title = _derived_title(payload.base_story) if payload.auto_title else payload.name
        project = Project(name=workspace_title, description=payload.description)
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
            bootstrap_from_phase_one(
                db,
                story,
                phase_one_package,
                requested_chapter_count=payload.requested_chapter_count,
                chapter_intake=[
                    item.model_dump(mode="json") for item in payload.chapter_intake
                ],
                created_by="sulphur_bootstrap",
            )

        if payload.auto_approve_phases_through:
            for phase_number in range(1, payload.auto_approve_phases_through + 1):
                production_phases.approve_phase(
                    db,
                    story.id,
                    phase_number,
                    PhaseApproveRequest(
                        approved_by="Sulphur bootstrap",
                        notes=(
                            f"Auto-approved Phase {phase_number} as an initial local/private "
                            "Sulphur planning baseline. User review and regeneration remain available."
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
        return ProjectWorkspaceResult(project, story, settings, False)
    except IntegrityError:
        db.rollback()
        replay = db.scalar(
            select(ProjectWorkspaceCreation).where(
                ProjectWorkspaceCreation.idempotency_key == payload.idempotency_key
            )
        )
        if replay is None:
            raise
        return _load_replay(db, replay, request_hash)
    except Exception:
        db.rollback()
        raise
