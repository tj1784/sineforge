"""Server-owned typed tool registry for the CineForge Operator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import Character, Project, Shot, Story
from backend.app.schemas.agent import AgentRiskClass, AgentToolDescriptor


class ToolValidationError(ValueError):
    pass


class ToolPolicyError(PermissionError):
    pass


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArgs(ToolArgs):
    pass


class ProjectGetArgs(ToolArgs):
    project_id: UUID | None = None


class ProjectSearchArgs(ToolArgs):
    query: str = Field(default="", max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class RecordGetArgs(ToolArgs):
    record_type: str = Field(min_length=1, max_length=80)
    record_id: UUID


class ReviewAddNoteArgs(ToolArgs):
    target_type: str = Field(min_length=1, max_length=80)
    target_id: UUID
    target_version: str | None = Field(default=None, max_length=128)
    note: str = Field(min_length=1, max_length=4000)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    args_model: type[ToolArgs]
    output_schema: dict[str, Any]
    required_permission: str
    allowed_resource_scopes: list[str]
    risk_class: AgentRiskClass
    approval_required: bool
    idempotent: bool
    timeout_seconds: int = 30
    result_size_limit: int = 65536

    def descriptor(self) -> AgentToolDescriptor:
        return AgentToolDescriptor(
            name=self.name,
            version=self.version,
            description=self.description,
            input_schema=self.args_model.model_json_schema(),
            output_schema=self.output_schema,
            required_permission=self.required_permission,
            allowed_resource_scopes=self.allowed_resource_scopes,
            risk_class=self.risk_class,
            approval_required=self.approval_required,
            idempotent=self.idempotent,
            timeout_seconds=self.timeout_seconds,
            result_size_limit=self.result_size_limit,
        )


READ_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "resource": {"type": "object"},
    },
    "required": ["status"],
    "additionalProperties": True,
}

PROPOSAL_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "proposal_id": {"type": "string"},
    },
    "required": ["status"],
    "additionalProperties": True,
}


TOOL_SPECS: dict[str, ToolSpec] = {
    "context.get_current": ToolSpec(
        name="context.get_current",
        version="1",
        description="Return the verified page context snapshot for this message.",
        args_model=EmptyArgs,
        output_schema=READ_RESULT_SCHEMA,
        required_permission="context:read",
        allowed_resource_scopes=["current_context"],
        risk_class=AgentRiskClass.read,
        approval_required=False,
        idempotent=True,
    ),
    "context.refresh": ToolSpec(
        name="context.refresh",
        version="1",
        description="Return the latest server-hydrated context for the captured page envelope.",
        args_model=EmptyArgs,
        output_schema=READ_RESULT_SCHEMA,
        required_permission="context:read",
        allowed_resource_scopes=["current_context"],
        risk_class=AgentRiskClass.read,
        approval_required=False,
        idempotent=True,
    ),
    "project.get": ToolSpec(
        name="project.get",
        version="1",
        description="Read the current project summary or a project explicitly in scope.",
        args_model=ProjectGetArgs,
        output_schema=READ_RESULT_SCHEMA,
        required_permission="project:read",
        allowed_resource_scopes=["current_project"],
        risk_class=AgentRiskClass.read,
        approval_required=False,
        idempotent=True,
    ),
    "project.search": ToolSpec(
        name="project.search",
        version="1",
        description="Search accessible local CineForge projects by name.",
        args_model=ProjectSearchArgs,
        output_schema=READ_RESULT_SCHEMA,
        required_permission="project:read",
        allowed_resource_scopes=["workspace_projects"],
        risk_class=AgentRiskClass.read,
        approval_required=False,
        idempotent=True,
    ),
    "record.get": ToolSpec(
        name="record.get",
        version="1",
        description="Read a compact server-verified project, story, shot, or character record.",
        args_model=RecordGetArgs,
        output_schema=READ_RESULT_SCHEMA,
        required_permission="record:read",
        allowed_resource_scopes=["current_project_records"],
        risk_class=AgentRiskClass.read,
        approval_required=False,
        idempotent=True,
    ),
    "review.add_note": ToolSpec(
        name="review.add_note",
        version="1",
        description="Propose adding a human-readable review note to the resolved project or record.",
        args_model=ReviewAddNoteArgs,
        output_schema=PROPOSAL_RESULT_SCHEMA,
        required_permission="review:write",
        allowed_resource_scopes=["current_project_records"],
        risk_class=AgentRiskClass.low,
        approval_required=True,
        idempotent=True,
    ),
}


def list_tool_descriptors(capabilities: list[str] | None = None) -> list[AgentToolDescriptor]:
    allowed = set(capabilities or TOOL_SPECS)
    return [
        spec.descriptor()
        for name, spec in sorted(TOOL_SPECS.items())
        if name in allowed or spec.risk_class == AgentRiskClass.read
    ]


def get_tool(name: str) -> ToolSpec:
    try:
        return TOOL_SPECS[name]
    except KeyError as exc:
        raise ToolValidationError(f"Unknown tool: {name}") from exc


def validate_tool_args(name: str, arguments: dict[str, Any]) -> ToolArgs:
    spec = get_tool(name)
    try:
        return spec.args_model.model_validate(arguments)
    except ValidationError as exc:
        raise ToolValidationError(str(exc)) from exc


def _project_summary(project: Project) -> dict[str, Any]:
    return {
        "type": "project",
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "workflow_lane": project.workflow_lane,
        "theme_id": project.theme_id,
        "version": project.created_at.isoformat(),
    }


def _story_summary(story: Story) -> dict[str, Any]:
    return {
        "type": "story",
        "id": str(story.id),
        "project_id": str(story.project_id),
        "title": story.title,
        "version": story.updated_at.isoformat(),
        "target_duration_sec": float(story.target_duration_sec),
        "approval_state": story.approval_state,
        "logline": story.logline,
    }


def _shot_summary(shot: Shot) -> dict[str, Any]:
    return {
        "type": "shot",
        "id": str(shot.id),
        "scene_id": str(shot.scene_id),
        "title": shot.title,
        "version": shot.updated_at.isoformat(),
        "duration_sec": float(shot.duration_sec),
        "approval_state": shot.approval_state,
        "production_status": shot.production_status,
    }


def _character_summary(character: Character) -> dict[str, Any]:
    return {
        "type": "character",
        "id": str(character.id),
        "story_id": str(character.story_id),
        "name": character.name,
        "role": character.role,
        "version": character.updated_at.isoformat(),
    }


def current_project_id_from_summary(hydrated_summary: dict[str, Any]) -> UUID | None:
    project = hydrated_summary.get("project")
    if not isinstance(project, dict):
        return None
    raw = project.get("id")
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def target_version(db: Session, target_type: str, target_id: UUID | None) -> str | None:
    if target_id is None:
        return None
    normalized = target_type.lower()
    if normalized == "project":
        project = db.get(Project, target_id)
        return project.created_at.isoformat() if project else None
    if normalized == "story":
        story = db.get(Story, target_id)
        return story.updated_at.isoformat() if story else None
    if normalized == "shot":
        shot = db.get(Shot, target_id)
        return shot.updated_at.isoformat() if shot else None
    if normalized == "character":
        character = db.get(Character, target_id)
        return character.updated_at.isoformat() if character else None
    return None


def execute_read_tool(
    db: Session,
    *,
    name: str,
    args: ToolArgs,
    hydrated_summary: dict[str, Any],
) -> dict[str, Any]:
    if name in {"context.get_current", "context.refresh"}:
        return {"status": "ok", "resource": hydrated_summary}

    if name == "project.search":
        typed = args if isinstance(args, ProjectSearchArgs) else ProjectSearchArgs()
        query = f"%{typed.query.casefold()}%"
        statement = select(Project).order_by(Project.created_at.desc()).limit(typed.limit)
        if typed.query.strip():
            statement = (
                select(Project)
                .where(Project.name.ilike(query))
                .order_by(Project.created_at.desc())
                .limit(typed.limit)
            )
        return {
            "status": "ok",
            "resource": {
                "projects": [_project_summary(project) for project in db.scalars(statement).all()]
            },
        }

    if name == "project.get":
        typed = args if isinstance(args, ProjectGetArgs) else ProjectGetArgs()
        project_id = typed.project_id or current_project_id_from_summary(hydrated_summary)
        if project_id is None:
            raise ToolPolicyError("No verified project is attached to this context")
        project = db.get(Project, project_id)
        if project is None:
            raise ToolPolicyError("Project was not found")
        stories = db.scalars(select(Story).where(Story.project_id == project.id).limit(10)).all()
        return {
            "status": "ok",
            "resource": {
                **_project_summary(project),
                "stories": [_story_summary(story) for story in stories],
            },
        }

    if name == "record.get":
        typed = args
        if not isinstance(typed, RecordGetArgs):
            raise ToolValidationError("record.get requires record_type and record_id")
        record_type = typed.record_type.lower()
        if record_type == "project":
            project = db.get(Project, typed.record_id)
            if project is None:
                raise ToolPolicyError("Project was not found")
            return {"status": "ok", "resource": _project_summary(project)}
        if record_type == "story":
            story = db.get(Story, typed.record_id)
            if story is None:
                raise ToolPolicyError("Story was not found")
            return {"status": "ok", "resource": _story_summary(story)}
        if record_type == "shot":
            shot = db.get(Shot, typed.record_id)
            if shot is None:
                raise ToolPolicyError("Shot was not found")
            return {"status": "ok", "resource": _shot_summary(shot)}
        if record_type == "character":
            character = db.get(Character, typed.record_id)
            if character is None:
                raise ToolPolicyError("Character was not found")
            return {"status": "ok", "resource": _character_summary(character)}
        raise ToolPolicyError(f"record.get does not support {typed.record_type}")

    raise ToolValidationError(f"{name} is not a read tool")

