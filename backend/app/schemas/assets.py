"""Schemas for managed Storyboard Phase 1 planning media / reference assets."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssetKind(StrEnum):
    character_reference = "character_reference"
    art_direction_reference = "art_direction_reference"
    starting_image = "starting_image"
    video_source = "video_source"
    voice_source = "voice_source"
    story_document = "story_document"


class AssetSourceType(StrEnum):
    user_upload = "user_upload"
    system_generated = "system_generated"
    imported = "imported"


class AssetApprovalState(StrEnum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    blocked = "blocked"
    archived = "archived"


class ActiveAssetApprovalState(StrEnum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    blocked = "blocked"


class CharacterReferenceRole(StrEnum):
    primary = "primary"
    alternate = "alternate"
    expression = "expression"
    costume = "costume"
    detail = "detail"


class PlanningMediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    kind: str
    source_type: str
    managed_uri: str
    sha256: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_sec: float | None = None
    approval_state: str
    metadata_json: dict = Field(default_factory=dict)
    original_filename: str | None = None
    size_bytes: int | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    is_duplicate: bool = False


class AssetUploadResponse(BaseModel):
    asset: PlanningMediaAssetRead
    created: bool
    duplicate_of_existing: bool = False


class AssetArchiveRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class StartingImageApprovalUpdate(BaseModel):
    """Explicit optimistic transition for one active managed starting image."""

    model_config = ConfigDict(extra="forbid")

    approval_state: ActiveAssetApprovalState
    expected_approval_state: ActiveAssetApprovalState
    reason: str | None = Field(default=None, max_length=500)
    changed_by: str | None = Field(default=None, min_length=1, max_length=200)


class AssetDeleteRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    force: bool = False


class CharacterReferenceLinkCreate(BaseModel):
    asset_id: UUID
    reference_role: CharacterReferenceRole = CharacterReferenceRole.primary
    approved: bool = False
    order_index: int = Field(default=0, ge=0)


class CharacterReferenceLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    character_id: UUID
    asset_id: UUID
    reference_role: str
    approved: bool
    order_index: int
    created_at: datetime
    updated_at: datetime
    asset: PlanningMediaAssetRead | None = None


class AssetListResponse(BaseModel):
    items: list[PlanningMediaAssetRead]
    total: int
