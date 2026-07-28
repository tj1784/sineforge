"""Schemas for per-project storyboard Phase 1 settings."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_SHOT_DURATION_MIN_SEC = 6.0
DEFAULT_SHOT_DURATION_MAX_SEC = 12.0
DEFAULT_SPEAKING_RATE = 1.0
DEFAULT_ASPECT_RATIO = "16:9"
DEFAULT_PREVIEW_WIDTH = 1280
DEFAULT_PREVIEW_HEIGHT = 720
DEFAULT_FINAL_WIDTH = 1920
DEFAULT_FINAL_HEIGHT = 1080
DEFAULT_FPS = 24.0
DEFAULT_PRODUCTION_PROFILE_KEY = "ltx_base@1"
DEFAULT_STITCH_STAGE = "phase7_before_audio"

ProductionProfileKey = Literal["ltx_base@1", "wan_base@1"]
StitchStage = Literal["phase7_before_audio", "phase8_before_foley"]

DEFAULT_CONTINUITY_POLICY: dict = {
    "require_starting_image_when_flagged": True,
    "allow_cross_scene_continuity": True,
}

DEFAULT_PROMPTING_POLICY: dict = {
    "require_visual_description": False,
    "require_story_purpose": False,
}

DEFAULT_VOICE_POLICY: dict = {
    "allow_placeholder_for_approval": True,
    "allow_manual_for_approval": True,
    "require_consent_when_required": True,
    "block_unresolved_provider_voices": False,
}

DEFAULT_APPROVAL_POLICY: dict = {
    "require_exact_duration": True,
    "require_at_least_one_chapter": True,
    "require_at_least_one_scene": True,
    "require_at_least_one_shot": True,
    "require_narration_or_exception": True,
    "require_prompt_package_or_exception": True,
    "require_model_recommendation_or_exception": True,
    "prompt_package_exceptions": {},
    "model_recommendation_exceptions": {},
    "block_on_shot_blocked": True,
}


class ProjectStoryboardSettingsBase(BaseModel):
    shot_duration_min_sec: float = Field(default=DEFAULT_SHOT_DURATION_MIN_SEC, gt=0)
    shot_duration_max_sec: float = Field(default=DEFAULT_SHOT_DURATION_MAX_SEC, gt=0)
    continuity_policy_json: dict = Field(default_factory=lambda: dict(DEFAULT_CONTINUITY_POLICY))
    prompting_policy_json: dict = Field(default_factory=lambda: dict(DEFAULT_PROMPTING_POLICY))
    voice_policy_json: dict = Field(default_factory=lambda: dict(DEFAULT_VOICE_POLICY))
    approval_policy_json: dict = Field(default_factory=lambda: dict(DEFAULT_APPROVAL_POLICY))
    speaking_rate: float = Field(default=DEFAULT_SPEAKING_RATE, gt=0)
    aspect_ratio: str = Field(default=DEFAULT_ASPECT_RATIO, min_length=1, max_length=32)
    preview_width: int = Field(default=DEFAULT_PREVIEW_WIDTH, gt=0)
    preview_height: int = Field(default=DEFAULT_PREVIEW_HEIGHT, gt=0)
    final_width: int = Field(default=DEFAULT_FINAL_WIDTH, gt=0)
    final_height: int = Field(default=DEFAULT_FINAL_HEIGHT, gt=0)
    fps: float = Field(default=DEFAULT_FPS, gt=0)
    captions_enabled: bool = True
    audio_enabled: bool = True
    production_profile_key: ProductionProfileKey = DEFAULT_PRODUCTION_PROFILE_KEY
    production_profile_snapshot_json: dict = Field(default_factory=dict)
    stitch_stage: StitchStage = DEFAULT_STITCH_STAGE
    prefer_hosted_providers: bool = False
    prefer_local_providers: bool = True
    allow_model_download: bool = False
    allow_rendering: bool = False
    require_voice_consent: bool = True
    require_production_plan_approval: bool = True

    @model_validator(mode="after")
    def validate_duration_bounds(self):
        if self.shot_duration_min_sec > self.shot_duration_max_sec:
            raise ValueError("shot_duration_min_sec must be <= shot_duration_max_sec.")
        return self


class ProjectStoryboardSettingsUpdate(ProjectStoryboardSettingsBase):
    """Full PUT body for project storyboard settings."""

    expected_settings_version: int | None = Field(
        default=None,
        gt=0,
        description="When set, must match the current settings_version or the update conflicts.",
    )


class ProjectStoryboardSettingsRead(ProjectStoryboardSettingsBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    project_id: UUID
    settings_version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
