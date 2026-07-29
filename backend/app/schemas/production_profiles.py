"""Public contracts for versioned video production profiles."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.services.production_profiles import ProductionProfile


class VideoCapabilityPolicyRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_to_video: bool
    image_to_video: bool
    video_to_video: bool
    continuation: bool
    native_audio: Literal["supported", "unsupported", "unknown"]
    external_foley: bool
    high_low_noise_pair: bool


class VideoFramePolicyRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_multiple: int
    frame_remainder: int
    nominal_segment_duration_sec: float | None
    min_segment_duration_sec: float | None
    max_segment_duration_sec: float | None
    min_subscene_duration_sec: float
    max_subscene_duration_sec: float
    allow_shorter_subscene_with_reason: bool


class ProductionProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    key: str
    version: int
    display_name: str
    model_family: Literal["ltx", "wan"]
    status: Literal["qualified", "qualification_required"]
    execution_qualified: bool
    approved_video_model_keys: list[str]
    approved_video_models: list[str]
    capabilities: VideoCapabilityPolicyRead
    frame_policy: VideoFramePolicyRead
    qualification_notes: list[str]

    @classmethod
    def from_domain(cls, profile: ProductionProfile) -> "ProductionProfileRead":
        return cls(
            ref=profile.ref,
            key=profile.key,
            version=profile.version,
            display_name=profile.display_name,
            model_family=profile.model_family,
            status=profile.status,
            execution_qualified=profile.execution_qualified,
            approved_video_model_keys=sorted(profile.approved_video_model_keys),
            approved_video_models=sorted(profile.approved_video_models),
            capabilities=VideoCapabilityPolicyRead(
                **profile.capabilities.__dict__
            ),
            frame_policy=VideoFramePolicyRead(**profile.frame_policy.__dict__),
            qualification_notes=list(profile.qualification_notes),
        )


class ProductionProfileCatalogRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_profile_ref: str
    profiles: list[ProductionProfileRead]
