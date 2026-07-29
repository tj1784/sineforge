"""Strict API contracts for non-rendering Phase 7 video operations."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.app.services.video import StitchStage


OpaqueId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]
Sha256Hex = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[0-9a-fA-F]{64}$",
    ),
]


class StrictVideoModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PhaseSevenPolicyRead(StrictVideoModel):
    schema_name: Literal["video.phase7.policy.v1"] = "video.phase7.policy.v1"
    preferred_subscene_min_sec: Literal[15] = 15
    short_subscene_allowed_with_reason: Literal[True] = True
    subscene_max_sec: Literal[90] = 90
    stitch_stages: tuple[StitchStage, StitchStage] = (
        StitchStage.PHASE7_BEFORE_AUDIO,
        StitchStage.PHASE8_BEFORE_FOLEY,
    )
    default_stitch_stage: Literal[StitchStage.PHASE7_BEFORE_AUDIO] = (
        StitchStage.PHASE7_BEFORE_AUDIO
    )
    rendering_performed: Literal[False] = False


class PhaseSevenCapabilitiesRead(StrictVideoModel):
    schema_name: Literal["video.phase7.capabilities.v1"] = (
        "video.phase7.capabilities.v1"
    )
    capabilities: tuple[
        Literal["validate_subscene"],
        Literal["compile_provider_segments"],
        Literal["validate_edl"],
        Literal["construct_picture_lock"],
    ] = (
        "validate_subscene",
        "compile_provider_segments",
        "validate_edl",
        "construct_picture_lock",
    )
    accepts_local_paths: Literal[False] = False
    executes_comfyui: Literal[False] = False
    executes_ffmpeg: Literal[False] = False
    persists_state: Literal[False] = False
    rendering_performed: Literal[False] = False


class SubsceneInput(StrictVideoModel):
    subscene_id: OpaqueId
    duration_sec: float = Field(gt=0, le=90, allow_inf_nan=False)
    short_reason: str | None = Field(default=None, min_length=1, max_length=500)


class ProviderRenderConstraintsInput(StrictVideoModel):
    profile_id: OpaqueId
    fps_numerator: int = Field(gt=0, le=1000)
    fps_denominator: int = Field(default=1, gt=0, le=1001)
    min_frames: int = Field(default=1, gt=0, le=1_000_000)
    max_frames: int = Field(default=81, gt=0, le=1_000_000)
    frame_stride: int = Field(default=4, gt=0, le=10_000)
    frame_offset: int = Field(default=1, ge=0, le=9_999)
    duplicate_boundary_frames: Literal[0, 1] = 1


class CompileSubsceneRequest(StrictVideoModel):
    subscene: SubsceneInput
    provider: ProviderRenderConstraintsInput


class RenderSegmentRead(StrictVideoModel):
    segment_id: str
    subscene_id: OpaqueId
    segment_index: int = Field(ge=0)
    timeline_start_sec: float = Field(ge=0)
    timeline_end_sec: float = Field(gt=0)
    requested_duration_sec: float = Field(gt=0)
    frame_count: int = Field(gt=0)
    drop_leading_frames: Literal[0, 1]
    effective_frame_count: int = Field(gt=0)
    expected_output_duration_sec: float = Field(gt=0)
    provider_profile_id: OpaqueId
    fps_numerator: int = Field(gt=0)
    fps_denominator: int = Field(gt=0)


class CompileSubsceneResponse(StrictVideoModel):
    schema_name: Literal["video.phase7.compilation.v1"] = (
        "video.phase7.compilation.v1"
    )
    operation: Literal["plan_only"] = "plan_only"
    rendering_performed: Literal[False] = False
    subscene_id: OpaqueId
    editorial_duration_sec: float = Field(gt=0, le=90)
    short_exception: bool
    segment_count: int = Field(gt=0)
    expected_effective_frame_count: int = Field(gt=0)
    segments: tuple[RenderSegmentRead, ...]


class EditDecisionInput(StrictVideoModel):
    decision_id: OpaqueId
    asset_id: OpaqueId
    asset_sha256: Sha256Hex
    source_start_frame: int = Field(ge=0)
    source_end_frame_exclusive: int = Field(gt=0)
    timeline_start_frame: int = Field(ge=0)
    drop_leading_frames: Literal[0, 1] = 0


class ValidateEdlRequest(StrictVideoModel):
    edl_id: OpaqueId
    stitch_stage: StitchStage
    fps_numerator: int = Field(gt=0, le=1000)
    fps_denominator: int = Field(default=1, gt=0, le=1001)
    decisions: tuple[EditDecisionInput, ...] = Field(min_length=1, max_length=10_000)


class EditDecisionRead(EditDecisionInput):
    source_frame_count: int = Field(gt=0)
    timeline_frame_count: int = Field(gt=0)
    timeline_end_frame_exclusive: int = Field(gt=0)


class ValidateEdlResponse(StrictVideoModel):
    schema_name: Literal["video.phase7.edl-validation.v1"] = (
        "video.phase7.edl-validation.v1"
    )
    valid: Literal[True] = True
    rendering_performed: Literal[False] = False
    edl_id: OpaqueId
    stitch_stage: StitchStage
    fps_numerator: int = Field(gt=0)
    fps_denominator: int = Field(gt=0)
    total_frame_count: int = Field(gt=0)
    duration_sec: float = Field(gt=0)
    edl_sha256: Sha256Hex
    decisions: tuple[EditDecisionRead, ...]


class ConstructPictureLockRequest(StrictVideoModel):
    edl: ValidateEdlRequest
    picture_lock_id: OpaqueId
    final_video_asset_id: OpaqueId
    final_video_sha256: Sha256Hex
    assembly_manifest_sha256: Sha256Hex
    width: int = Field(gt=0, le=32_768)
    height: int = Field(gt=0, le=32_768)
    pixel_format: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=64,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        ),
    ]
    locked_at: datetime


class PictureLockRead(StrictVideoModel):
    schema_name: Literal["video.phase7.picture-lock.v1"] = (
        "video.phase7.picture-lock.v1"
    )
    contract_only: Literal[True] = True
    rendering_performed: Literal[False] = False
    picture_lock_id: OpaqueId
    edl_sha256: Sha256Hex
    final_video_asset_id: OpaqueId
    final_video_sha256: Sha256Hex
    assembly_manifest_sha256: Sha256Hex
    frame_count: int = Field(gt=0)
    fps_numerator: int = Field(gt=0)
    fps_denominator: int = Field(gt=0)
    duration_sec: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    pixel_format: str
    stitch_stage: StitchStage
    selected_asset_ids: tuple[OpaqueId, ...] = Field(min_length=1)
    locked_at: datetime
