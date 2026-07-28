from pydantic import BaseModel
from typing import Any
from uuid import UUID

from backend.app.schemas.assets import PlanningMediaAssetRead


class PhaseSixImageStatus(BaseModel):
    shot_count: int
    required_count: int
    assigned_count: int
    approved_count: int
    in_review_count: int = 0
    missing_count: int
    complete: bool
    phase_7_locked: bool | None = None
    runtime_reachable: bool | None = None


class PhaseSixImagePrepareResponse(BaseModel):
    status: PhaseSixImageStatus
    message: str


class StartingImageGenerateRequest(BaseModel):
    requested_by: str = "CineForge local operator"
    seed: int | None = None
    model_name: str | None = None
    workflow_template_id: UUID | None = None
    workflow_label: str | None = None
    workflow_source: str | None = None
    workflow_api_json: dict[str, Any] | None = None


class StartingImageGenerateResponse(BaseModel):
    asset: PlanningMediaAssetRead
    created: bool
    duplicate_of_existing: bool = False
    shot_id: UUID
    previous_asset_id: UUID | None = None
    status: PhaseSixImageStatus
    prompt_id: str | None = None
    model_name: str
    seed: int
