from fractions import Fraction

import pytest

from backend.app.services.audio import (
    BoundaryPolicy,
    FrameRange,
    FrameRate,
    PictureLock,
    PictureLockError,
    TimeBase,
    TimelineBoundary,
    WindowPlanningConfig,
    WindowPlanningError,
    plan_foley_windows,
)


def picture_lock(
    *,
    total_frames: int = 2_700,
    frame_rate: FrameRate | None = None,
    locked: bool = True,
    content_hash: str = "picture-sha256",
) -> PictureLock:
    return PictureLock(
        content_hash=content_hash,
        total_frames=total_frames,
        frame_rate=frame_rate or FrameRate(30),
        time_base=TimeBase(1, 90_000),
        locked=locked,
    )


def test_plans_ninety_seconds_as_exact_bounded_windows() -> None:
    lock = picture_lock()

    windows = plan_foley_windows(
        lock,
        expected_picture_lock_hash=lock.content_hash,
    )

    assert windows[0].core_frames.start == 0
    assert windows[-1].core_frames.end == 2_700
    assert windows[0].core_frames.count == 8 * 30
    assert all(window.analysis_frames.count <= 450 for window in windows)
    assert all(30 <= window.core_frames.count <= 450 for window in windows)
    assert all(
        left.core_frames.end == right.core_frames.start
        for left, right in zip(windows, windows[1:], strict=False)
    )
    assert sum(window.expected_sample_count for window in windows) == 90 * 48_000


def test_exact_fractional_fps_pts_and_sample_ranges_do_not_drift() -> None:
    lock = picture_lock(
        total_frames=300,
        frame_rate=FrameRate(30_000, 1_001),
    )

    windows = plan_foley_windows(
        lock,
        expected_picture_lock_hash=lock.content_hash,
    )

    assert windows[-1].core_pts[1] == Fraction(900_900, 1)
    assert windows[-1].output_samples.end == 480_480
    assert sum(window.expected_sample_count for window in windows) == 480_480


def test_explicit_hard_cut_is_preferred_and_has_no_context_handle() -> None:
    lock = picture_lock(total_frames=480)
    cut = TimelineBoundary(frame=210, policy=BoundaryPolicy.HARD_CUT)

    windows = plan_foley_windows(
        lock,
        expected_picture_lock_hash=lock.content_hash,
        boundaries=(cut,),
    )

    assert windows[0].core_frames.end == 210
    assert windows[0].analysis_frames.end == 210
    assert windows[1].analysis_frames.start == 210
    assert windows[0].right_boundary_policy is BoundaryPolicy.HARD_CUT
    assert windows[1].left_boundary_policy is BoundaryPolicy.HARD_CUT


def test_continuous_boundary_adds_handles_without_exceeding_model_limit() -> None:
    lock = picture_lock(total_frames=480)
    boundary = TimelineBoundary(
        frame=240,
        policy=BoundaryPolicy.CONTINUOUS_AMBIENCE,
    )

    windows = plan_foley_windows(
        lock,
        expected_picture_lock_hash=lock.content_hash,
        boundaries=(boundary,),
    )

    assert windows[0].analysis_frames == FrameRange(0, 255)
    assert windows[1].analysis_frames == FrameRange(225, 480)
    assert all(window.analysis_frames.count <= 450 for window in windows)


def test_visual_crossfade_requires_transition_frames() -> None:
    with pytest.raises(ValueError, match="require transition frames"):
        TimelineBoundary(frame=120, policy=BoundaryPolicy.VISUAL_CROSSFADE)


@pytest.mark.parametrize(
    ("lock", "expected", "message"),
    [
        (picture_lock(locked=False), "picture-sha256", "immutable"),
        (picture_lock(), "different-sha256", "hash mismatch"),
    ],
)
def test_refuses_mutable_or_stale_picture_lock(
    lock: PictureLock,
    expected: str,
    message: str,
) -> None:
    with pytest.raises(PictureLockError, match=message):
        plan_foley_windows(lock, expected_picture_lock_hash=expected)


def test_refuses_picture_shorter_than_one_second() -> None:
    lock = picture_lock(total_frames=29)

    with pytest.raises(WindowPlanningError, match="one-second"):
        plan_foley_windows(
            lock,
            expected_picture_lock_hash=lock.content_hash,
        )


def test_configuration_enforces_public_foley_limits() -> None:
    with pytest.raises(WindowPlanningError, match="15 seconds"):
        WindowPlanningConfig(maximum_seconds=Fraction(16, 1))
    with pytest.raises(WindowPlanningError, match="450"):
        WindowPlanningConfig(maximum_frames=451)
