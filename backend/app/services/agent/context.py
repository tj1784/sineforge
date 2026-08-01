"""Server-verified page context packaging for the contextual Operator."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.db.base import (
    AgentContextSnapshot,
    Character,
    Project,
    Shot,
    Story,
)
from backend.app.schemas.agent import PageContextEnvelope


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _compact_text(value: str | None, limit: int = 240) -> str | None:
    if not value:
        return None
    return " ".join(value.split())[:limit]


def _uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


@dataclass(frozen=True)
class HydratedContext:
    context_hash: str
    context_json: dict[str, Any]
    hydrated_summary: dict[str, Any]
    source_refs: list[dict[str, Any]]
    verified_capabilities: list[str]


def _story_version(story: Story) -> str:
    return story.updated_at.isoformat()


def _target_summary(db: Session, context: PageContextEnvelope) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    refs: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "routeId": context.routeId,
        "pathname": context.pathname,
        "pageTitle": context.pageTitle,
        "domain": context.domain,
        "activeTab": context.activeTab,
        "activePanel": context.activePanel,
        "mode": context.mode,
        "dirty": context.dirty,
        "specificRecordAttached": False,
    }

    project: Project | None = None
    if context.projectId:
        project = db.get(Project, context.projectId)
        if project is not None:
            summary["project"] = {
                "id": str(project.id),
                "name": project.name,
                "description": _compact_text(project.description),
                "workflow_lane": project.workflow_lane,
                "theme_id": project.theme_id,
                "version": str(project.created_at.isoformat()),
            }
            refs.append({"type": "project", "id": str(project.id), "version": project.created_at.isoformat()})
        else:
            summary["projectMissing"] = str(context.projectId)

    record_type = (context.recordType or "").strip().lower() or None
    record_id = _uuid(context.recordId)
    if not record_type or record_id is None:
        return summary, refs

    if record_type == "story":
        story = db.get(Story, record_id)
        if story and (project is None or story.project_id == project.id):
            version = _story_version(story)
            summary["specificRecordAttached"] = True
            summary["record"] = {
                "type": "story",
                "id": str(story.id),
                "title": story.title,
                "version": version,
                "target_duration_sec": float(story.target_duration_sec),
                "logline": _compact_text(story.logline),
            }
            refs.append({"type": "story", "id": str(story.id), "version": version})
        return summary, refs

    if record_type == "shot":
        shot = db.get(Shot, record_id)
        if shot is not None:
            summary["specificRecordAttached"] = True
            summary["record"] = {
                "type": "shot",
                "id": str(shot.id),
                "title": shot.title,
                "version": shot.updated_at.isoformat(),
                "duration_sec": float(shot.duration_sec),
                "approval_state": shot.approval_state,
                "production_status": shot.production_status,
            }
            refs.append({"type": "shot", "id": str(shot.id), "version": shot.updated_at.isoformat()})
        return summary, refs

    if record_type == "character":
        character = db.get(Character, record_id)
        if character is not None:
            summary["specificRecordAttached"] = True
            summary["record"] = {
                "type": "character",
                "id": str(character.id),
                "name": character.name,
                "version": character.updated_at.isoformat(),
                "role": _compact_text(character.role),
            }
            refs.append({"type": "character", "id": str(character.id), "version": character.updated_at.isoformat()})
        return summary, refs

    summary["unsupportedRecordType"] = record_type
    return summary, refs


def hydrate_page_context(
    db: Session,
    *,
    context: PageContextEnvelope,
    actor_id: str,
) -> HydratedContext:
    summary, refs = _target_summary(db, context)
    capabilities = ["context.get_current", "context.refresh", "project.search"]
    if summary.get("project"):
        capabilities.extend(["project.get", "record.get", "review.add_note"])

    raw_context = context.model_dump(mode="json")
    context_json = {
        "raw_envelope": raw_context,
        "verified_capabilities": capabilities,
        "client_capabilities_ignored": raw_context.get("capabilities", []),
    }
    package = {
        "context": context_json,
        "hydrated_summary": summary,
        "source_refs": refs,
        "actor_id": actor_id,
    }
    return HydratedContext(
        context_hash=stable_hash(package),
        context_json=context_json,
        hydrated_summary=summary,
        source_refs=refs,
        verified_capabilities=capabilities,
    )


def create_context_snapshot(
    db: Session,
    *,
    session_id: UUID,
    actor_id: str,
    hydrated: HydratedContext,
) -> AgentContextSnapshot:
    record = AgentContextSnapshot(
        session_id=session_id,
        actor_id=actor_id,
        context_hash=hydrated.context_hash,
        context_json=hydrated.context_json,
        hydrated_summary_json=hydrated.hydrated_summary,
        source_refs_json=hydrated.source_refs,
        redaction_report_json={
            "client_capabilities_trusted": False,
            "full_project_included": False,
            "full_workflow_json_included": False,
            "secrets_included": False,
        },
    )
    db.add(record)
    db.flush()
    return record
