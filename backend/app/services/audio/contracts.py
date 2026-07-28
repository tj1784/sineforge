"""Pure domain contracts for picture-locked Phase 8 audio work.

All timeline ranges are half-open: ``start`` is inclusive and ``end`` is
exclusive.  Fractions are used for frame/time conversions so 24000/1001 and
30000/1001 timelines do not accumulate floating-point drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction


SAMPLE_RATE_HZ = 48_000


class AudioDomainError(ValueError):
    """Base exception for invalid Phase 8 domain inputs."""


class PictureLockError(AudioDomainError):
    """The requested picture is not immutable or no longer matches its lock."""


class WindowPlanningError(AudioDomainError):
    """A timeline cannot be represented by valid Foley inference windows."""


class BoundaryPolicy(StrEnum):
    """How audio context is handled at a picture edit."""

    HARD_CUT = "hard_cut"
    CONTINUOUS_AMBIENCE = "continuous_ambience"
    VISUAL_CROSSFADE = "visual_crossfade"


class DeliveryProfileName(StrEnum):
    WEB = "web"
    BROADCAST = "broadcast"
    PRESERVE_DYNAMICS = "preserve_dynamics"


@dataclass(frozen=True, slots=True)
class FrameRate:
    numerator: int
    denominator: int = 1

    def __post_init__(self) -> None:
        if self.numerator <= 0 or self.denominator <= 0:
            raise AudioDomainError("frame rate numerator and denominator must be positive")

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)


@dataclass(frozen=True, slots=True)
class TimeBase:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.numerator <= 0 or self.denominator <= 0:
            raise AudioDomainError("time base numerator and denominator must be positive")

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)


@dataclass(frozen=True, slots=True)
class FrameRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise AudioDomainError("frame range start must be non-negative")
        if self.end <= self.start:
            raise AudioDomainError("frame range end must be greater than start")

    @property
    def count(self) -> int:
        return self.end - self.start

    def seconds(self, frame_rate: FrameRate) -> tuple[Fraction, Fraction]:
        fps = frame_rate.fraction
        return Fraction(self.start, 1) / fps, Fraction(self.end, 1) / fps

    def pts(
        self,
        *,
        frame_rate: FrameRate,
        time_base: TimeBase,
    ) -> tuple[Fraction, Fraction]:
        start_sec, end_sec = self.seconds(frame_rate)
        return start_sec / time_base.fraction, end_sec / time_base.fraction


@dataclass(frozen=True, slots=True)
class SampleRange:
    start: int
    end: int
    sample_rate_hz: int = SAMPLE_RATE_HZ

    def __post_init__(self) -> None:
        if self.start < 0:
            raise AudioDomainError("sample range start must be non-negative")
        if self.end <= self.start:
            raise AudioDomainError("sample range end must be greater than start")
        if self.sample_rate_hz <= 0:
            raise AudioDomainError("sample rate must be positive")

    @property
    def count(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class PictureLock:
    """Immutable picture timing accepted by the Phase 8 planner."""

    content_hash: str
    total_frames: int
    frame_rate: FrameRate
    time_base: TimeBase
    locked: bool = True

    def __post_init__(self) -> None:
        if not self.content_hash.strip():
            raise PictureLockError("picture-lock hash must be non-empty")
        if self.total_frames <= 0:
            raise AudioDomainError("picture lock must contain at least one frame")


@dataclass(frozen=True, slots=True)
class TimelineBoundary:
    """An edit boundary, expressed as the first frame after the edit."""

    frame: int
    policy: BoundaryPolicy
    transition_frames: int = 0

    def __post_init__(self) -> None:
        if self.frame <= 0:
            raise AudioDomainError("boundary frame must be positive")
        if self.transition_frames < 0:
            raise AudioDomainError("transition frames must be non-negative")
        if (
            self.policy is BoundaryPolicy.VISUAL_CROSSFADE
            and self.transition_frames <= 0
        ):
            raise AudioDomainError("visual crossfade boundaries require transition frames")
        if (
            self.policy is not BoundaryPolicy.VISUAL_CROSSFADE
            and self.transition_frames
        ):
            raise AudioDomainError(
                "transition frames are only valid for visual crossfade boundaries"
            )


@dataclass(frozen=True, slots=True)
class FoleyWindowPlan:
    window_id: str
    ordinal: int
    picture_lock_hash: str
    core_frames: FrameRange
    analysis_frames: FrameRange
    core_pts: tuple[Fraction, Fraction]
    analysis_pts: tuple[Fraction, Fraction]
    output_samples: SampleRange
    left_boundary_policy: BoundaryPolicy | None
    right_boundary_policy: BoundaryPolicy | None

    @property
    def expected_sample_count(self) -> int:
        return self.output_samples.count


@dataclass(frozen=True, slots=True)
class WindowPlanningConfig:
    minimum_seconds: Fraction = Fraction(1, 1)
    target_seconds: Fraction = Fraction(8, 1)
    maximum_seconds: Fraction = Fraction(15, 1)
    maximum_frames: int = 450
    ambience_handle_seconds: Fraction = Fraction(1, 2)

    def __post_init__(self) -> None:
        if self.minimum_seconds <= 0:
            raise WindowPlanningError("minimum window duration must be positive")
        if not self.minimum_seconds <= self.target_seconds <= self.maximum_seconds:
            raise WindowPlanningError(
                "target duration must be between minimum and maximum"
            )
        if self.maximum_seconds > 15:
            raise WindowPlanningError("Foley windows may not exceed 15 seconds")
        if self.maximum_frames <= 0 or self.maximum_frames > 450:
            raise WindowPlanningError("maximum_frames must be between 1 and 450")
        if self.ambience_handle_seconds < 0:
            raise WindowPlanningError("ambience handles cannot be negative")


@dataclass(frozen=True, slots=True)
class LoudnessProfile:
    name: DeliveryProfileName
    integrated_lufs: float | None
    maximum_true_peak_dbtp: float
    loudness_range_lu: float | None

    def __post_init__(self) -> None:
        if self.integrated_lufs is not None and not -70.0 <= self.integrated_lufs <= -5.0:
            raise AudioDomainError("integrated loudness must be between -70 and -5 LUFS")
        if not -9.0 <= self.maximum_true_peak_dbtp <= 0.0:
            raise AudioDomainError("true peak must be between -9 and 0 dBTP")
        if self.loudness_range_lu is not None and self.loudness_range_lu <= 0:
            raise AudioDomainError("loudness range must be positive")
        if (
            self.name is DeliveryProfileName.PRESERVE_DYNAMICS
            and self.integrated_lufs is not None
        ):
            raise AudioDomainError("preserve-dynamics profile cannot target integrated loudness")


@dataclass(frozen=True, slots=True)
class AttemptMetadata:
    attempt_id: str
    window_id: str
    picture_lock_hash: str
    attempt_number: int
    seed: int
    model_id: str
    model_hash: str
    workflow_hash: str
    prompt_hash: str


@dataclass(frozen=True, slots=True)
class SilenceQAConfig:
    rms_silence_dbfs: float = -60.0
    peak_silence_dbfs: float = -50.0
    sample_count_tolerance: int = 0

    def __post_init__(self) -> None:
        if self.rms_silence_dbfs >= 0 or self.peak_silence_dbfs >= 0:
            raise AudioDomainError("silence thresholds must be below 0 dBFS")
        if self.sample_count_tolerance < 0:
            raise AudioDomainError("sample-count tolerance cannot be negative")


@dataclass(frozen=True, slots=True)
class SilenceQAResult:
    passed: bool
    is_silent: bool
    finite: bool
    expected_sample_count: int
    actual_sample_count: int
    peak_dbfs: float
    rms_dbfs: float
    findings: tuple[str, ...]

