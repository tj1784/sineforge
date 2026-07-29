"""Pure Phase 8 audio planning, metadata, profiles, and QA services."""

from .attempts import build_attempt_metadata
from .contracts import (
    SAMPLE_RATE_HZ,
    AttemptMetadata,
    AudioDomainError,
    BoundaryPolicy,
    DeliveryProfileName,
    FoleyWindowPlan,
    FrameRange,
    FrameRate,
    LoudnessProfile,
    PictureLock,
    PictureLockError,
    SampleRange,
    SilenceQAConfig,
    SilenceQAResult,
    TimeBase,
    TimelineBoundary,
    WindowPlanningConfig,
    WindowPlanningError,
)
from .planning import plan_foley_windows, validate_picture_lock
from .profiles import DELIVERY_PROFILES, get_delivery_profile
from .qa import evaluate_silence

__all__ = [
    "SAMPLE_RATE_HZ",
    "AttemptMetadata",
    "AudioDomainError",
    "BoundaryPolicy",
    "DELIVERY_PROFILES",
    "DeliveryProfileName",
    "FoleyWindowPlan",
    "FrameRange",
    "FrameRate",
    "LoudnessProfile",
    "PictureLock",
    "PictureLockError",
    "SampleRange",
    "SilenceQAConfig",
    "SilenceQAResult",
    "TimeBase",
    "TimelineBoundary",
    "WindowPlanningConfig",
    "WindowPlanningError",
    "build_attempt_metadata",
    "evaluate_silence",
    "get_delivery_profile",
    "plan_foley_windows",
    "validate_picture_lock",
]
