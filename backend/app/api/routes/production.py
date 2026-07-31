"""Seven-phase production contract routes for local/private CineForge execution."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.production import (
    PhaseApproveRequest,
    PhaseApproveResponse,
    PhaseHistoryExport,
    PhaseOneGenerationInput,
    PhaseOneMutationResponse,
    PhaseOneRevisionRequest,
    PhaseVersionCreateRequest,
    PhaseVersionCreateResponse,
    PhaseVersionDetail,
    PhaseVersionSummary,
    ProductionPipelineRead,
)
from backend.app.schemas.image_generation import (
    PhaseFiveHandoffGenerateResponse,
    PhaseSixImagePrepareResponse,
    PhaseSixImageStatus,
    StartingImageGenerateRequest,
    StartingImageGenerateResponse,
)
from backend.app.schemas.video_generation import (
    PhaseSevenVideoQueueRequest,
    PhaseSevenVideoQueueResponse,
)
from backend.app.services import production_phases
from backend.app.services import phase_six_images
from backend.app.services import phase_seven_videos


router = APIRouter(prefix="/production", tags=["production"])


def _error(exc: production_phases.ProductionPhaseError) -> HTTPException:
    if str(exc).startswith("workflow_lane_mismatch:"):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, production_phases.ProductionPhaseConflictError):
        code = status.HTTP_409_CONFLICT
    elif str(exc) in {
        "Story not found.",
        "Version not found.",
    } or str(exc).startswith("Phase ") and "missing" in str(exc):
        code = status.HTTP_404_NOT_FOUND
    elif "different" in str(exc).lower() or "integrity" in str(exc).lower() or "tamper" in str(exc).lower() or "failed integrity" in str(exc).lower() or "Unsupported" in str(exc):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif str(exc) == "Version not found.":
        code = status.HTTP_404_NOT_FOUND
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    message = str(exc)
    if message == "Version not found.":
        code = status.HTTP_404_NOT_FOUND
    return HTTPException(status_code=code, detail=message)


@router.get("/stories/{story_id}", response_model=ProductionPipelineRead)
def get_production_pipeline(
    story_id: UUID, db: Session = Depends(get_db)
) -> ProductionPipelineRead:
    try:
        return production_phases.get_pipeline(db, story_id)
    except production_phases.ProductionPhaseError as exc:
        raise _error(exc) from exc


@router.get(
    "/stories/{story_id}/phases/{phase_number}/versions",
    response_model=list[PhaseVersionSummary],
)
def list_phase_versions(
    story_id: UUID,
    phase_number: int,
    db: Session = Depends(get_db),
) -> list[PhaseVersionSummary]:
    try:
        return production_phases.list_phase_versions(db, story_id, phase_number)
    except production_phases.ProductionPhaseError as exc:
        raise _error(exc) from exc


@router.get(
    "/stories/{story_id}/phases/{phase_number}/versions/{version_id}",
    response_model=PhaseVersionDetail,
)
def get_phase_version(
    story_id: UUID,
    phase_number: int,
    version_id: UUID,
    db: Session = Depends(get_db),
) -> PhaseVersionDetail:
    try:
        return production_phases.get_phase_version(
            db, story_id, phase_number, version_id
        )
    except production_phases.ProductionPhaseError as exc:
        raise _error(exc) from exc


@router.post(
    "/stories/{story_id}/phases/{phase_number}/versions",
    response_model=PhaseVersionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_phase_version(
    story_id: UUID,
    phase_number: int,
    payload: PhaseVersionCreateRequest,
    db: Session = Depends(get_db),
) -> PhaseVersionCreateResponse:
    try:
        return production_phases.create_phase_version(
            db, story_id, phase_number, payload
        )
    except production_phases.ProductionPhaseError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get(
    "/stories/{story_id}/versions/export",
    response_model=PhaseHistoryExport,
)
def export_phase_history(
    story_id: UUID, db: Session = Depends(get_db)
) -> PhaseHistoryExport:
    try:
        return production_phases.export_phase_history(db, story_id)
    except production_phases.ProductionPhaseError as exc:
        raise _error(exc) from exc


@router.post(
    "/stories/{story_id}/phases/1/generate",
    response_model=PhaseOneMutationResponse,
)
def generate_phase_one(
    story_id: UUID,
    payload: PhaseOneGenerationInput,
    db: Session = Depends(get_db),
) -> PhaseOneMutationResponse:
    try:
        return production_phases.generate_phase_one(db, story_id, payload)
    except production_phases.ProductionPhaseError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.put(
    "/stories/{story_id}/phases/1",
    response_model=PhaseOneMutationResponse,
)
def revise_phase_one(
    story_id: UUID,
    payload: PhaseOneRevisionRequest,
    db: Session = Depends(get_db),
) -> PhaseOneMutationResponse:
    try:
        return production_phases.revise_phase_one(db, story_id, payload)
    except production_phases.ProductionPhaseError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post(
    "/stories/{story_id}/phases/{phase_number}/approve",
    response_model=PhaseApproveResponse,
)
def approve_phase(
    story_id: UUID,
    phase_number: int,
    payload: PhaseApproveRequest,
    db: Session = Depends(get_db),
) -> PhaseApproveResponse:
    try:
        return production_phases.approve_phase(db, story_id, phase_number, payload)
    except (production_phases.ProductionPhaseError, phase_six_images.PhaseSixImageError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get(
    "/stories/{story_id}/phase6/images/status",
    response_model=PhaseSixImageStatus,
)
def phase_six_image_status(
    story_id: UUID,
    db: Session = Depends(get_db),
) -> PhaseSixImageStatus:
    try:
        return PhaseSixImageStatus(**phase_six_images.status(db, story_id))
    except phase_six_images.PhaseSixImageError as exc:
        raise _error(exc) from exc


@router.post(
    "/stories/{story_id}/phase6/images/prepare",
    response_model=PhaseSixImagePrepareResponse,
)
def prepare_phase_six_images(
    story_id: UUID,
    payload: PhaseApproveRequest,
    db: Session = Depends(get_db),
) -> PhaseSixImagePrepareResponse:
    try:
        state = phase_six_images.prepare(db, story_id, requested_by=payload.approved_by)
        return PhaseSixImagePrepareResponse(
            status=PhaseSixImageStatus(**state),
            message="Phase 6 images are ready for local ComfyUI generation; Phase 7 is not artificially locked.",
        )
    except phase_six_images.PhaseSixImageError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post(
    "/stories/{story_id}/phase6/images/handoff",
    response_model=PhaseFiveHandoffGenerateResponse,
)
def generate_phase_five_image_handoff(
    story_id: UUID,
    payload: StartingImageGenerateRequest | None = None,
    db: Session = Depends(get_db),
) -> PhaseFiveHandoffGenerateResponse:
    request_payload = payload or StartingImageGenerateRequest(
        requested_by="CineForge Phase 5 workflow handoff"
    )
    try:
        result = phase_six_images.generate_phase_five_handoff(
            db,
            story_id,
            requested_by=request_payload.requested_by,
            seed=request_payload.seed,
            model_name=request_payload.model_name or phase_six_images.DEFAULT_FLUX_IMAGE_MODEL,
            workflow_template_id=request_payload.workflow_template_id,
            workflow_label=request_payload.workflow_label,
            workflow_source=request_payload.workflow_source,
            workflow_api_json=request_payload.workflow_api_json,
        )
        return PhaseFiveHandoffGenerateResponse(**result)
    except phase_six_images.PhaseSixImageError as exc:
        db.rollback()
        raise _error(phase_six_images.PhaseSixImageError(str(exc))) from exc
    except Exception as exc:
        db.rollback()
        raise _error(phase_six_images.PhaseSixImageError(str(exc))) from exc


@router.post(
    "/stories/{story_id}/phase6/images/shots/{shot_id}/generate",
    response_model=StartingImageGenerateResponse,
)
def generate_phase_six_starting_image(
    story_id: UUID,
    shot_id: UUID,
    payload: StartingImageGenerateRequest | None = None,
    db: Session = Depends(get_db),
) -> StartingImageGenerateResponse:
    request_payload = payload or StartingImageGenerateRequest()
    try:
        result = phase_six_images.generate_shot(
            db,
            story_id,
            shot_id,
            requested_by=request_payload.requested_by,
            seed=request_payload.seed,
            model_name=request_payload.model_name or phase_six_images.DEFAULT_FLUX_IMAGE_MODEL,
            workflow_template_id=request_payload.workflow_template_id,
            workflow_label=request_payload.workflow_label,
            workflow_source=request_payload.workflow_source,
            workflow_api_json=request_payload.workflow_api_json,
        )
        return StartingImageGenerateResponse(**result)
    except phase_six_images.PhaseSixImageError as exc:
        db.rollback()
        raise _error(phase_six_images.PhaseSixImageError(str(exc))) from exc
    except Exception as exc:
        db.rollback()
        raise _error(phase_six_images.PhaseSixImageError(str(exc))) from exc


@router.post(
    "/stories/{story_id}/phase7/videos/queue",
    response_model=PhaseSevenVideoQueueResponse,
)
def queue_phase_seven_videos(
    story_id: UUID,
    payload: PhaseSevenVideoQueueRequest | None = None,
    db: Session = Depends(get_db),
) -> PhaseSevenVideoQueueResponse:
    request_payload = payload or PhaseSevenVideoQueueRequest()
    try:
        result = phase_seven_videos.queue_story_videos(
            db,
            story_id,
            requested_by=request_payload.requested_by,
            seed=request_payload.seed,
            workflow_label=request_payload.workflow_label,
            workflow_source=request_payload.workflow_source,
            workflow_api_json=request_payload.workflow_api_json,
        )
        return PhaseSevenVideoQueueResponse(**result)
    except phase_seven_videos.PhaseSevenVideoError as exc:
        db.rollback()
        raise _error(production_phases.ProductionPhaseError(str(exc))) from exc
    except Exception as exc:
        db.rollback()
        raise _error(production_phases.ProductionPhaseError(str(exc))) from exc
