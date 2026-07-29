"""Non-rendering Phase 8 audio policy, planning, metadata, and numeric QA API.

This router is intentionally not registered here.  It performs no file access,
model execution, workflow submission, transcoding, database mutation, or media
generation.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from fractions import Fraction

from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.audio import (
    DeliveryProfilesResponse,
    FoleyAttemptRequest,
    FoleyAttemptResponse,
    FoleyPolicyResponse,
    FoleyWindowPlanRequest,
    FoleyWindowPlanResponse,
    FoleyWindowResponse,
    IntegerRangeResponse,
    LoudnessProfileResponse,
    PCMQualityRequest,
    PCMQualityResponse,
    RationalRangeResponse,
    RationalValue,
    SampleRangeResponse,
)
from backend.app.services.audio import (
    DELIVERY_PROFILES,
    AudioDomainError,
    BoundaryPolicy,
    FoleyWindowPlan,
    FrameRange,
    FrameRate,
    PictureLock,
    PictureLockError,
    SampleRange,
    SilenceQAConfig,
    TimeBase,
    TimelineBoundary,
    WindowPlanningConfig,
    build_attempt_metadata,
    evaluate_silence,
    plan_foley_windows,
)


router = APIRouter(prefix="/audio", tags=["audio"])


def _fraction(value: RationalValue) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _rational(value: Fraction) -> RationalValue:
    return RationalValue(numerator=value.numerator, denominator=value.denominator)


def _rational_range(values: tuple[Fraction, Fraction]) -> RationalRangeResponse:
    return RationalRangeResponse(start=_rational(values[0]), end=_rational(values[1]))


def _integer_range(value: FrameRange) -> IntegerRangeResponse:
    return IntegerRangeResponse(start=value.start, end=value.end, count=value.count)


def _sample_range(value: SampleRange) -> SampleRangeResponse:
    return SampleRangeResponse(
        start=value.start,
        end=value.end,
        count=value.count,
        sample_rate_hz=value.sample_rate_hz,
    )


def _window_response(value: FoleyWindowPlan) -> FoleyWindowResponse:
    return FoleyWindowResponse(
        window_id=value.window_id,
        ordinal=value.ordinal,
        picture_lock_hash=value.picture_lock_hash,
        core_frames=_integer_range(value.core_frames),
        analysis_frames=_integer_range(value.analysis_frames),
        core_pts=_rational_range(value.core_pts),
        analysis_pts=_rational_range(value.analysis_pts),
        output_samples=_sample_range(value.output_samples),
        expected_sample_count=value.expected_sample_count,
        left_boundary_policy=value.left_boundary_policy,
        right_boundary_policy=value.right_boundary_policy,
    )


def _window_contract(value: FoleyWindowResponse) -> FoleyWindowPlan:
    return FoleyWindowPlan(
        window_id=value.window_id,
        ordinal=value.ordinal,
        picture_lock_hash=value.picture_lock_hash,
        core_frames=FrameRange(value.core_frames.start, value.core_frames.end),
        analysis_frames=FrameRange(
            value.analysis_frames.start,
            value.analysis_frames.end,
        ),
        core_pts=(
            _fraction(value.core_pts.start),
            _fraction(value.core_pts.end),
        ),
        analysis_pts=(
            _fraction(value.analysis_pts.start),
            _fraction(value.analysis_pts.end),
        ),
        output_samples=SampleRange(
            value.output_samples.start,
            value.output_samples.end,
            value.output_samples.sample_rate_hz,
        ),
        left_boundary_policy=value.left_boundary_policy,
        right_boundary_policy=value.right_boundary_policy,
    )


def _domain_error(error: AudioDomainError) -> HTTPException:
    code = (
        status.HTTP_409_CONFLICT
        if isinstance(error, PictureLockError)
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return HTTPException(status_code=code, detail=str(error))


@router.get("/foley-policy", response_model=FoleyPolicyResponse)
def get_foley_policy() -> FoleyPolicyResponse:
    return FoleyPolicyResponse(
        boundary_policies=list(BoundaryPolicy),
        note=(
            "Policy and timing only. This endpoint does not read media, execute "
            "models or workflows, write files, or claim that audio was generated."
        ),
    )


@router.get("/delivery-profiles", response_model=DeliveryProfilesResponse)
def get_delivery_profiles() -> DeliveryProfilesResponse:
    return DeliveryProfilesResponse(
        profiles=[
            LoudnessProfileResponse(
                name=profile.name,
                integrated_lufs=profile.integrated_lufs,
                maximum_true_peak_dbtp=profile.maximum_true_peak_dbtp,
                loudness_range_lu=profile.loudness_range_lu,
            )
            for profile in DELIVERY_PROFILES.values()
        ]
    )


@router.post("/foley-windows/plan", response_model=FoleyWindowPlanResponse)
def plan_windows(payload: FoleyWindowPlanRequest) -> FoleyWindowPlanResponse:
    try:
        lock = PictureLock(
            content_hash=payload.picture_lock.content_hash,
            total_frames=payload.picture_lock.total_frames,
            frame_rate=FrameRate(
                payload.picture_lock.frame_rate.numerator,
                payload.picture_lock.frame_rate.denominator,
            ),
            time_base=TimeBase(
                payload.picture_lock.time_base.numerator,
                payload.picture_lock.time_base.denominator,
            ),
            locked=payload.picture_lock.locked,
        )
        boundaries = tuple(
            TimelineBoundary(
                frame=item.frame,
                policy=item.policy,
                transition_frames=item.transition_frames,
            )
            for item in payload.boundaries
        )
        config = WindowPlanningConfig(
            minimum_seconds=_fraction(payload.config.minimum_seconds),
            target_seconds=_fraction(payload.config.target_seconds),
            maximum_seconds=_fraction(payload.config.maximum_seconds),
            maximum_frames=payload.config.maximum_frames,
            ambience_handle_seconds=_fraction(
                payload.config.ambience_handle_seconds
            ),
        )
        windows = plan_foley_windows(
            lock,
            expected_picture_lock_hash=payload.expected_picture_lock_hash,
            boundaries=boundaries,
            config=config,
        )
    except AudioDomainError as error:
        raise _domain_error(error) from error
    response_windows = [_window_response(window) for window in windows]
    return FoleyWindowPlanResponse(
        picture_lock_hash=lock.content_hash,
        window_count=len(response_windows),
        expected_total_samples=sum(
            window.expected_sample_count for window in response_windows
        ),
        windows=response_windows,
    )


@router.post("/foley-attempts/derive", response_model=FoleyAttemptResponse)
def derive_attempt_metadata(payload: FoleyAttemptRequest) -> FoleyAttemptResponse:
    try:
        metadata = build_attempt_metadata(
            _window_contract(payload.window),
            current_picture_lock_hash=payload.current_picture_lock_hash,
            attempt_number=payload.attempt_number,
            base_seed=payload.base_seed,
            model_id=payload.model_id,
            model_hash=payload.model_hash,
            workflow_hash=payload.workflow_hash,
            prompt_hash=payload.prompt_hash,
        )
    except (AudioDomainError, ValueError) as error:
        if isinstance(error, AudioDomainError):
            raise _domain_error(error) from error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    return FoleyAttemptResponse(**asdict(metadata))


@router.post("/pcm/qa", response_model=PCMQualityResponse)
def run_numeric_pcm_qa(payload: PCMQualityRequest) -> PCMQualityResponse:
    result = evaluate_silence(
        payload.samples,
        expected_sample_count=payload.expected_sample_count,
        config=SilenceQAConfig(
            rms_silence_dbfs=payload.rms_silence_dbfs,
            peak_silence_dbfs=payload.peak_silence_dbfs,
            sample_count_tolerance=payload.sample_count_tolerance,
        ),
    )
    return PCMQualityResponse(
        passed=result.passed,
        is_silent=result.is_silent,
        finite=result.finite,
        expected_sample_count=result.expected_sample_count,
        actual_sample_count=result.actual_sample_count,
        peak_dbfs=result.peak_dbfs if math.isfinite(result.peak_dbfs) else None,
        rms_dbfs=result.rms_dbfs if math.isfinite(result.rms_dbfs) else None,
        findings=list(result.findings),
    )
