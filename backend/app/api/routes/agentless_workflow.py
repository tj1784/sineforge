"""Project-scoped read-only routes for the Agentless scene-reset lane."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import Project, ProjectStoryboardSettings
from backend.app.db.session import get_db
from backend.app.schemas.agentless_workflow import (
    AgentlessDryRunRead,
    AgentlessDryRunRequest,
    AgentlessWorkflowProfileRead,
)
from backend.app.schemas.project_workflows import (
    ProjectWorkflowLane,
    is_agentless_workflow_lane,
)
from backend.app.services.agentless_workflow import (
    AgentlessCompilationError,
    build_agentless_profile,
    dry_run_agentless_workflow,
)


router = APIRouter(prefix="/projects", tags=["agentless-workflow"])


def _require_agentless_project(db: Session, project_id: UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "project_not_found",
                "message": "Project not found.",
            },
        )
    actual_lane = getattr(
        project,
        "workflow_lane",
        ProjectWorkflowLane.cineforge_studio.value,
    )
    if not is_agentless_workflow_lane(actual_lane):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "workflow_lane_mismatch",
                "message": (
                    "Agentless Workflow routes are only available to projects "
                    "created in the agentless lane."
                ),
                "required_workflow_lane": (
                    ProjectWorkflowLane.agentless.value
                ),
                "actual_workflow_lane": actual_lane,
            },
        )
    return project


@router.get(
    "/{project_id}/agentless-workflow",
    response_model=AgentlessWorkflowProfileRead,
)
def get_agentless_workflow_profile(
    project_id: UUID,
    db: Session = Depends(get_db),
) -> AgentlessWorkflowProfileRead:
    """Return the immutable planning policy for one Agentless project."""

    _require_agentless_project(db, project_id)
    project_settings = db.scalar(
        select(ProjectStoryboardSettings).where(
            ProjectStoryboardSettings.project_id == project_id
        )
    )
    selected_agent = str(
        (
            project_settings.prompting_policy_json
            if project_settings is not None
            else {}
        ).get("planning_agent", "grok")
    )
    if selected_agent not in {"qwen", "sulphur", "grok"}:
        selected_agent = "grok"
    return build_agentless_profile(
        project_id=project_id,
        selected_planning_agent=selected_agent,
    )


@router.post(
    "/{project_id}/agentless-workflow/dry-run",
    response_model=AgentlessDryRunRead,
)
def dry_run_agentless_project(
    project_id: UUID,
    payload: AgentlessDryRunRequest,
    db: Session = Depends(get_db),
) -> AgentlessDryRunRead:
    """Compile an isolated scene-reset DAG without writing or submitting work."""

    _require_agentless_project(db, project_id)
    if payload.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "project_scope_mismatch",
                "message": (
                    "Request project_id must match the project ID in the route."
                ),
            },
        )
    try:
        return dry_run_agentless_workflow(db, payload)
    except AgentlessCompilationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "agentless_compilation_failed",
                "message": str(exc),
            },
        ) from exc
