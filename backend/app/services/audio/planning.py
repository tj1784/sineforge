"""Frame-accurate, deterministic Foley window planning."""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction

from .contracts import (
    SAMPLE_RATE_HZ,
    BoundaryPolicy,
    FoleyWindowPlan,
    FrameRange,
    PictureLock,
    PictureLockError,
    SampleRange,
    TimelineBoundary,
    WindowPlanningConfig,
    WindowPlanningError,
)


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _floor_fraction(value: Fraction) -> int:
    return value.numerator // value.denominator


def _round_half_up(value: Fraction) -> int:
    return _floor_fraction(value + Fraction(1, 2))


def validate_picture_lock(
    picture_lock: PictureLock,
    *,
    expected_hash: str,
) -> None:
    """Refuse unlocked or stale picture timing before any audio work is planned."""

    if not picture_lock.locked:
        raise PictureLockError("Phase 8 requires an immutable picture lock")
    if not expected_hash.strip():
        raise PictureLockError("expected picture-lock hash must be non-empty")
    if picture_lock.content_hash != expected_hash:
        raise PictureLockError(
            "picture-lock hash mismatch; picture changed after audio planning"
        )


def _frame_to_sample(frame: int, picture_lock: PictureLock) -> int:
    exact = (
        Fraction(frame, 1)
        / picture_lock.frame_rate.fraction
        * SAMPLE_RATE_HZ
    )
    return _round_half_up(exact)


def _boundary_context_frames(
    boundary: TimelineBoundary | None,
    *,
    picture_lock: PictureLock,
    config: WindowPlanningConfig,
) -> int:
    if boundary is None or boundary.policy is BoundaryPolicy.HARD_CUT:
        return 0
    if boundary.policy is BoundaryPolicy.VISUAL_CROSSFADE:
        return boundary.transition_frames
    return _round_half_up(
        picture_lock.frame_rate.fraction * config.ambience_handle_seconds
    )


def _choose_core_ranges(
    picture_lock: PictureLock,
    *,
    boundaries: tuple[TimelineBoundary, ...],
    config: WindowPlanningConfig,
) -> list[FrameRange]:
    fps = picture_lock.frame_rate.fraction
    minimum_frames = max(1, _ceil_fraction(fps * config.minimum_seconds))
    target_frames = max(minimum_frames, _round_half_up(fps * config.target_seconds))
    maximum_frames = min(
        config.maximum_frames,
        _floor_fraction(fps * config.maximum_seconds),
    )
    if maximum_frames < minimum_frames:
        raise WindowPlanningError(
            "frame rate and limits cannot produce a valid 1–15 second window"
        )
    if picture_lock.total_frames < minimum_frames:
        raise WindowPlanningError(
            "picture duration is shorter than the one-second Foley minimum"
        )

    boundary_frames = tuple(boundary.frame for boundary in boundaries)
    ranges: list[FrameRange] = []
    start = 0
    total = picture_lock.total_frames

    while start < total:
        remaining = total - start
        if remaining <= maximum_frames:
            if remaining < minimum_frames:
                raise WindowPlanningError("final Foley window is shorter than one second")
            ranges.append(FrameRange(start, total))
            break

        minimum_end = start + minimum_frames
        maximum_end = min(start + maximum_frames, total - minimum_frames)
        desired_end = min(start + target_frames, maximum_end)
        candidates = [
            frame
            for frame in boundary_frames
            if minimum_end <= frame <= maximum_end
        ]
        if candidates:
            end = min(candidates, key=lambda frame: (abs(frame - desired_end), frame))
        else:
            end = max(minimum_end, desired_end)
        ranges.append(FrameRange(start, end))
        start = end

    return ranges


def plan_foley_windows(
    picture_lock: PictureLock,
    *,
    expected_picture_lock_hash: str,
    boundaries: tuple[TimelineBoundary, ...] = (),
    config: WindowPlanningConfig | None = None,
) -> tuple[FoleyWindowPlan, ...]:
    """Plan model-sized inference windows from immutable picture timing.

    Core ranges tile the picture exactly. Analysis ranges may include contextual
    handles, but are trimmed as necessary so every model input remains within
    both the duration and 450-frame limits.
    """

    config = config or WindowPlanningConfig()
    validate_picture_lock(picture_lock, expected_hash=expected_picture_lock_hash)

    by_frame: dict[int, TimelineBoundary] = {}
    for boundary in boundaries:
        if boundary.frame >= picture_lock.total_frames:
            raise WindowPlanningError("boundary must fall inside the picture lock")
        if boundary.frame in by_frame:
            raise WindowPlanningError("duplicate timeline boundary")
        by_frame[boundary.frame] = boundary

    core_ranges = _choose_core_ranges(
        picture_lock,
        boundaries=boundaries,
        config=config,
    )
    maximum_analysis_frames = min(
        config.maximum_frames,
        _floor_fraction(
            picture_lock.frame_rate.fraction * config.maximum_seconds
        ),
    )
    plans: list[FoleyWindowPlan] = []

    for ordinal, core in enumerate(core_ranges):
        left_boundary = by_frame.get(core.start)
        right_boundary = by_frame.get(core.end)
        left_handle = _boundary_context_frames(
            left_boundary,
            picture_lock=picture_lock,
            config=config,
        )
        right_handle = _boundary_context_frames(
            right_boundary,
            picture_lock=picture_lock,
            config=config,
        )

        available_extra = maximum_analysis_frames - core.count
        if available_extra < 0:
            raise WindowPlanningError("core window exceeds model analysis limit")
        requested_extra = left_handle + right_handle
        if requested_extra > available_extra:
            # Trim proportionally and deterministically; favor the left handle on
            # an odd remainder because it provides pre-roll for synchronization.
            left_handle = min(left_handle, (available_extra + 1) // 2)
            right_handle = min(right_handle, available_extra - left_handle)
        analysis_start = max(0, core.start - left_handle)
        analysis_end = min(picture_lock.total_frames, core.end + right_handle)

        analysis = FrameRange(analysis_start, analysis_end)
        if analysis.count > maximum_analysis_frames:
            raise WindowPlanningError("analysis window exceeds Foley model limits")

        core_pts = core.pts(
            frame_rate=picture_lock.frame_rate,
            time_base=picture_lock.time_base,
        )
        analysis_pts = analysis.pts(
            frame_rate=picture_lock.frame_rate,
            time_base=picture_lock.time_base,
        )
        output_samples = SampleRange(
            _frame_to_sample(core.start, picture_lock),
            _frame_to_sample(core.end, picture_lock),
        )
        window_identity = {
            "picture_lock_hash": picture_lock.content_hash,
            "ordinal": ordinal,
            "core_start": core.start,
            "core_end": core.end,
            "analysis_start": analysis.start,
            "analysis_end": analysis.end,
        }
        window_id = hashlib.sha256(
            json.dumps(
                window_identity,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24]
        plans.append(
            FoleyWindowPlan(
                window_id=window_id,
                ordinal=ordinal,
                picture_lock_hash=picture_lock.content_hash,
                core_frames=core,
                analysis_frames=analysis,
                core_pts=core_pts,
                analysis_pts=analysis_pts,
                output_samples=output_samples,
                left_boundary_policy=(
                    left_boundary.policy if left_boundary is not None else None
                ),
                right_boundary_policy=(
                    right_boundary.policy if right_boundary is not None else None
                ),
            )
        )

    if plans[0].core_frames.start != 0:
        raise WindowPlanningError("planned windows do not start at picture origin")
    if plans[-1].core_frames.end != picture_lock.total_frames:
        raise WindowPlanningError("planned windows do not cover the full picture")
    if any(
        left.core_frames.end != right.core_frames.start
        for left, right in zip(plans, plans[1:], strict=False)
    ):
        raise WindowPlanningError("planned core windows overlap or contain gaps")
    expected_total_samples = _frame_to_sample(
        picture_lock.total_frames,
        picture_lock,
    )
    if sum(plan.expected_sample_count for plan in plans) != expected_total_samples:
        raise WindowPlanningError("window sample ranges do not tile the soundtrack")
    return tuple(plans)
