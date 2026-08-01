import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.errors import not_found
from backend.app.db.base import Project, ProjectStoryboardSettings
from backend.app.db.session import get_db
from backend.app.schemas.api import (
    ProjectCreate,
    ProjectRead,
    ProjectWorkspaceCreate,
    ProjectWorkspaceRead,
    SulphurProjectPromptCreate,
    SulphurProjectWorkspaceRead,
)
from backend.app.schemas.storyboard import StoryRead
from backend.app.schemas.storyboard_settings import ProjectStoryboardSettingsRead
from backend.app.schemas.themes import ProjectThemeUpdate
from backend.app.services.planning.sulphur_project_intake import (
    SulphurProjectIntakeError,
    build_sulphur_project_intake,
)
from backend.app.services.project_workspace import (
    ProjectWorkspaceConflictError,
    ProjectWorkspacePlanningError,
    ProjectWorkspaceResult,
    create_project_workspace,
)
from backend.app.services import production_phases


router = APIRouter(prefix="/projects", tags=["projects"])


def project_to_response(project: Project) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        workflow_lane=project.workflow_lane,
        theme_id=project.theme_id,
        theme_version=project.theme_version,
        theme_context=(project.theme_context_json or None),
        created_at=project.created_at,
        persistence="db",
    )


def workspace_to_response(
    db: Session,
    result: ProjectWorkspaceResult,
) -> ProjectWorkspaceRead:
    return ProjectWorkspaceRead(
        project=project_to_response(result.project),
        story=StoryRead.model_validate(result.story),
        settings=ProjectStoryboardSettingsRead.model_validate(result.settings),
        idempotent_replay=result.idempotent_replay,
        production_pipeline=production_phases.get_pipeline(db, result.story.id),
        initial_planning_run_id=result.initial_planning_run_id,
        completed_planning_phases=list(result.completed_planning_phases),
    )


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    project = Project(
        name=payload.name,
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
    db.commit()
    db.refresh(project)
    return project_to_response(project)


@router.post("/workspace", response_model=ProjectWorkspaceRead, status_code=201)
def create_workspace(
    payload: ProjectWorkspaceCreate, db: Session = Depends(get_db)
) -> ProjectWorkspaceRead:
    try:
        result = create_project_workspace(db, payload)
    except ProjectWorkspaceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectWorkspacePlanningError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except production_phases.ProductionPhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return workspace_to_response(db, result)


@router.post(
    "/sulphur-intake",
    response_model=SulphurProjectWorkspaceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace_from_sulphur(
    payload: SulphurProjectPromptCreate,
    db: Session = Depends(get_db),
) -> SulphurProjectWorkspaceRead:
    """Create a complete local project from one validated Sulphur conversation turn."""

    try:
        intake = build_sulphur_project_intake(payload)
        result = create_project_workspace(db, intake.workspace_payload)
    except SulphurProjectIntakeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ProjectWorkspaceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectWorkspacePlanningError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except production_phases.ProductionPhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    workspace = workspace_to_response(db, result)
    return SulphurProjectWorkspaceRead(
        **workspace.model_dump(),
        intake_provider=intake.planning_agent,
        intake_model=intake.intake_model,
        target_duration_sec=intake.clip_plan.target_duration_sec,
        planned_scene_count=intake.clip_plan.planned_scene_count,
    )


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [project_to_response(project) for project in projects]


@router.get("/{project_id}/planning-prompt.json")
def get_project_planning_prompt(
    project_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    """Download the canonical project-planning prompt as a JSON artifact."""

    project = db.get(Project, project_id)
    project_settings = db.scalar(
        select(ProjectStoryboardSettings).where(
            ProjectStoryboardSettings.project_id == project_id
        )
    )
    if project is None or project_settings is None:
        raise not_found("Project planning prompt not found.")
    policy = dict(project_settings.prompting_policy_json or {})
    artifact = policy.get("prompt_artifact")
    if not isinstance(artifact, dict):
        raise not_found("Project planning prompt not found.")
    content = json.dumps(
        artifact,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    expected_digest = policy.get("prompt_artifact_sha256")
    if expected_digest != digest:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project planning prompt failed its stored SHA-256 check.",
        )
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="project-planning-prompt.json"'
            ),
            "X-Content-SHA256": digest,
        },
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: Session = Depends(get_db)) -> ProjectRead:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project not found.")
    return project_to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: UUID, db: Session = Depends(get_db)) -> Response:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project not found.")
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{project_id}/theme", response_model=ProjectRead)
def update_project_theme(
    project_id: UUID,
    payload: ProjectThemeUpdate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    """Change the theme for future project iterations only."""

    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project not found.")
    project.theme_id = payload.theme_id.value
    project.theme_version = "1.0.0"
    project.theme_context_json = (
        payload.theme_context.model_dump(mode="json", exclude_none=True)
        if payload.theme_context is not None
        else {}
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_to_response(project)
