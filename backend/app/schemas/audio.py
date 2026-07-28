"""Strict API contracts for non-rendering Phase 8 audio planning and QA."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    model_validator,
)

from backend.app.services.audio import BoundaryPolicy, DeliveryProfileName


PCM_QA_MAX_SAMPLES = 48_000

BoundedText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]
HashToken = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=256,
        pattern=r"^[^\r\n\\]+$",
    ),
]


class StrictAudioModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RationalValue(StrictAudioModel):
    numerator: int
    denominator: int = Field(gt=0)


class FrameRateContract(StrictAudioModel):
    numerator: int = Field(gt=0, le=240_000)
    denominator: int = Field(default=1, gt=0, le=10_000)


class TimeBaseContract(StrictAudioModel):
    numerator: int = Field(gt=0, le=10_000)
    denominator: int = Field(gt=0, le=10_000_000)


class PictureLockContract(StrictAudioModel):
    content_hash: HashToken
    total_frames: int = Field(gt=0, le=10_000_000)
    frame_rate: FrameRateContract
    time_base: TimeBaseContract
    locked: bool


class TimelineBoundaryContract(StrictAudioModel):
    frame: int = Field(gt=0, le=10_000_000)
    policy: BoundaryPolicy
    transition_frames: int = Field(default=0, ge=0, le=450)


class WindowPlanningConfigContract(StrictAudioModel):
    minimum_seconds: RationalValue = Field(
        default_factory=lambda: RationalValue(numerator=1, denominator=1)
    )
    target_seconds: RationalValue = Field(
        default_factory=lambda: RationalValue(numerator=8, denominator=1)
    )
    maximum_seconds: RationalValue = Field(
        default_factory=lambda: RationalValue(numerator=15, denominator=1)
    )
    maximum_frames: int = Field(default=450, ge=1, le=450)
    ambience_handle_seconds: RationalValue = Field(
        default_factory=lambda: RationalValue(numerator=1, denominator=2)
    )


class FoleyWindowPlanRequest(StrictAudioModel):
    picture_lock: PictureLockContract
    expected_picture_lock_hash: HashToken
    boundaries: list[TimelineBoundaryContract] = Field(
        default_factory=list,
        max_length=10_000,
    )
    config: WindowPlanningConfigContract = Field(
        default_factory=WindowPlanningConfigContract
    )


class IntegerRangeResponse(StrictAudioModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "IntegerRangeResponse":
        if self.end <= self.start or self.count != self.end - self.start:
            raise ValueError("range must be half-open and count must equal end - start")
        return self


class RationalRangeResponse(StrictAudioModel):
    start: RationalValue
    end: RationalValue


class SampleRangeResponse(IntegerRangeResponse):
    sample_rate_hz: Literal[48_000] = 48_000


class FoleyWindowResponse(StrictAudioModel):
    window_id: BoundedText
    ordinal: int = Field(ge=0)
    picture_lock_hash: HashToken
    core_frames: IntegerRangeResponse
    analysis_frames: IntegerRangeResponse
    core_pts: RationalRangeResponse
    analysis_pts: RationalRangeResponse
    output_samples: SampleRangeResponse
    expected_sample_count: int = Field(gt=0)
    left_boundary_policy: BoundaryPolicy | None = None
    right_boundary_policy: BoundaryPolicy | None = None

    @model_validator(mode="after")
    def validate_expected_samples(self) -> "FoleyWindowResponse":
        if self.expected_sample_count != self.output_samples.count:
            raise ValueError("expected sample count must match output sample range")
        return self


class FoleyWindowPlanResponse(StrictAudioModel):
    operation: Literal["planned"] = "planned"
    planning_only: Literal[True] = True
    generated_audio: Literal[False] = False
    picture_lock_hash: HashToken
    sample_rate_hz: Literal[48_000] = 48_000
    window_count: int = Field(ge=1)
    expected_total_samples: int = Field(gt=0)
    windows: list[FoleyWindowResponse]


class LoudnessProfileResponse(StrictAudioModel):
    name: DeliveryProfileName
    integrated_lufs: float | None
    maximum_true_peak_dbtp: float
    loudness_range_lu: float | None


class DeliveryProfilesResponse(StrictAudioModel):
    planning_only: Literal[True] = True
    profiles: list[LoudnessProfileResponse]


class FoleyPolicyResponse(StrictAudioModel):
    planning_only: Literal[True] = True
    performs_rendering: Literal[False] = False
    minimum_window_seconds: int = 1
    target_window_seconds: int = 8
    maximum_window_seconds: int = 15
    maximum_analysis_frames: int = 450
    sample_rate_hz: Literal[48_000] = 48_000
    boundary_policies: list[BoundaryPolicy]
    pcm_qa_max_samples: int = PCM_QA_MAX_SAMPLES
    note: str


class FoleyAttemptRequest(StrictAudioModel):
    window: FoleyWindowResponse
    current_picture_lock_hash: HashToken
    attempt_number: int = Field(ge=1, le=1_000)
    base_seed: int = Field(ge=0, le=(1 << 63) - 1)
    model_id: BoundedText
    model_hash: HashToken
    workflow_hash: HashToken
    prompt_hash: HashToken


class FoleyAttemptResponse(StrictAudioModel):
    operation: Literal["metadata_derived"] = "metadata_derived"
    planning_only: Literal[True] = True
    generation_started: Literal[False] = False
    attempt_id: HashToken
    window_id: BoundedText
    picture_lock_hash: HashToken
    attempt_number: int = Field(ge=1)
    seed: int = Field(ge=0)
    model_id: BoundedText
    model_hash: HashToken
    workflow_hash: HashToken
    prompt_hash: HashToken


class PCMQualityRequest(StrictAudioModel):
    samples: list[FiniteFloat] = Field(
        min_length=1,
        max_length=PCM_QA_MAX_SAMPLES,
    )
    expected_sample_count: int = Field(gt=0, le=100_000_000)
    rms_silence_dbfs: float = Field(default=-60.0, lt=0.0, ge=-200.0)
    peak_silence_dbfs: float = Field(default=-50.0, lt=0.0, ge=-200.0)
    sample_count_tolerance: int = Field(default=0, ge=0, le=48_000)


class PCMQualityResponse(StrictAudioModel):
    operation: Literal["numeric_pcm_qa"] = "numeric_pcm_qa"
    planning_only: Literal[True] = True
    media_read: Literal[False] = False
    passed: bool
    is_silent: bool
    finite: bool
    expected_sample_count: int
    actual_sample_count: int
    peak_dbfs: float | None
    rms_dbfs: float | None
    findings: list[str]

