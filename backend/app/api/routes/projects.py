from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.errors import not_found
from backend.app.db.base import Project
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
from backend.app.services.planning.sulphur_project_intake import (
    SulphurProjectIntakeError,
    build_sulphur_project_intake,
)
from backend.app.services.project_workspace import (
    ProjectWorkspaceConflictError,
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
    )


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    project = Project(name=payload.name, description=payload.description)
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

    workspace = workspace_to_response(db, result)
    return SulphurProjectWorkspaceRead(
        **workspace.model_dump(),
        intake_model=get_settings().sulphur_model_id,
        target_duration_sec=intake.clip_plan.target_duration_sec,
        planned_scene_count=intake.clip_plan.planned_scene_count,
    )


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [project_to_response(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: Session = Depends(get_db)) -> ProjectRead:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("Project not found.")
    return project_to_response(project)
