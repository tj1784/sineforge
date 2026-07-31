"""Versioned production-profile contracts for local video generation.

Profiles are product policy, not runtime discovery.  A profile may describe a
planned lane before its exact workflow, model artifacts, and benchmarks have
been admitted.  Such a profile remains resolvable for planning and UI display,
but selection for execution fails closed until it is qualified.

The current unscoped video contract is preserved as ``ltx_base@1``.  Legacy
callers that do not supply a profile therefore continue to select the exact
LTX 2.3 Distilled 1.1 FP8 model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


ProductionProfileStatus = Literal[
    "qualified",
    "qualification_required",
    "on_hold",
]
VideoModelFamily = Literal["ltx", "wan"]

DEFAULT_PRODUCTION_PROFILE_REF = "ltx_base@1"
LTX_BASE_PROFILE_REF = DEFAULT_PRODUCTION_PROFILE_REF
LTX_SEQUENCE_PROFILE_REF = "ltx_base@2"
WAN_BASE_PROFILE_REF = "wan_base@1"

LEGACY_LTX_VIDEO_MODEL_KEY = "ltx2_3_22b_distilled_1_1_fp8"
LEGACY_LTX_VIDEO_MODEL = "ltx-2.3-22b-distilled-1.1-fp8.safetensors"
LTX_SEQUENCE_VIDEO_MODEL_KEY = "sulphur2_base_quants_dev"
LTX_SEQUENCE_VIDEO_MODEL = "sulphur2BaseQuants_dev.safetensors"


class ProductionProfileError(ValueError):
    """Base error for an invalid or unusable production-profile selection."""


class UnknownProductionProfileError(ProductionProfileError):
    """The requested profile reference or legacy alias is not registered."""


class ProductionProfileQualificationRequired(ProductionProfileError):
    """The profile is known but has not passed runtime qualification."""


class ProductionProfileOnHold(ProductionProfileQualificationRequired):
    """The profile is intentionally unavailable after an unsuccessful gate."""


@dataclass(frozen=True)
class VideoCapabilityPolicy:
    text_to_video: bool
    image_to_video: bool
    video_to_video: bool
    continuation: bool
    native_audio: Literal["supported", "unsupported", "unknown"]
    external_foley: bool
    high_low_noise_pair: bool = False


@dataclass(frozen=True)
class VideoFramePolicy:
    """Frame geometry plus separate logical and render-segment duration bounds."""

    frame_multiple: int
    frame_remainder: int
    nominal_segment_duration_sec: float | None
    min_segment_duration_sec: float | None
    max_segment_duration_sec: float | None
    min_subscene_duration_sec: float
    max_subscene_duration_sec: float
    allow_shorter_subscene_with_reason: bool

    def accepts_frame_count(self, frame_count: int) -> bool:
        return (
            isinstance(frame_count, int)
            and not isinstance(frame_count, bool)
            and frame_count > 0
            and frame_count % self.frame_multiple == self.frame_remainder
        )

    def require_frame_count(self, frame_count: int) -> None:
        if not self.accepts_frame_count(frame_count):
            raise ProductionProfileError(
                f"Frame count must be positive and satisfy "
                f"{self.frame_multiple}n+{self.frame_remainder}; got {frame_count}."
            )

    def require_subscene_duration(
        self,
        duration_sec: float,
        *,
        shorter_reason: str | None = None,
    ) -> None:
        duration = float(duration_sec)
        if not math.isfinite(duration) or duration <= 0:
            raise ProductionProfileError(
                "Subscene duration must be a positive finite number."
            )
        if duration > self.max_subscene_duration_sec:
            raise ProductionProfileError(
                f"Subscene duration exceeds {self.max_subscene_duration_sec:g} seconds."
            )
        if duration < self.min_subscene_duration_sec and not (
            self.allow_shorter_subscene_with_reason
            and isinstance(shorter_reason, str)
            and shorter_reason.strip()
        ):
            raise ProductionProfileError(
                f"Subscenes shorter than {self.min_subscene_duration_sec:g} seconds "
                "require a scene-specific reason."
            )


@dataclass(frozen=True)
class ProductionProfile:
    key: str
    version: int
    display_name: str
    model_family: VideoModelFamily
    status: ProductionProfileStatus
    approved_video_model_keys: frozenset[str]
    approved_video_models: frozenset[str]
    capabilities: VideoCapabilityPolicy
    frame_policy: VideoFramePolicy
    qualification_notes: tuple[str, ...] = ()
    hold_reason: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.key}@{self.version}"

    @property
    def execution_qualified(self) -> bool:
        return self.status == "qualified"

    @property
    def selectable_for_execution(self) -> bool:
        return self.execution_qualified

    def require_execution_qualified(self) -> None:
        if not self.execution_qualified:
            if self.status == "on_hold":
                reason = self.hold_reason or (
                    "The profile is intentionally unavailable pending a new "
                    "qualification decision."
                )
                raise ProductionProfileOnHold(
                    f"Production profile {self.ref} is on hold and cannot execute. "
                    f"{reason}"
                )
            detail = (
                f" {' '.join(self.qualification_notes)}"
                if self.qualification_notes
                else ""
            )
            raise ProductionProfileQualificationRequired(
                f"Production profile {self.ref} requires runtime qualification "
                f"before execution.{detail}"
            )

    def require_video_model(self, model_name: str) -> None:
        self.require_execution_qualified()
        if model_name not in self.approved_video_models:
            expected = ", ".join(sorted(self.approved_video_models)) or "no admitted model"
            raise ProductionProfileError(
                f"Video generation under {self.ref} requires {expected}; "
                f"got {model_name}."
            )


LTX_BASE_PROFILE = ProductionProfile(
    key="ltx_base",
    version=1,
    display_name="LTX Base",
    model_family="ltx",
    status="qualified",
    approved_video_model_keys=frozenset({LEGACY_LTX_VIDEO_MODEL_KEY}),
    approved_video_models=frozenset({LEGACY_LTX_VIDEO_MODEL}),
    capabilities=VideoCapabilityPolicy(
        text_to_video=True,
        image_to_video=True,
        video_to_video=True,
        continuation=True,
        native_audio="unknown",
        external_foley=True,
    ),
    frame_policy=VideoFramePolicy(
        frame_multiple=8,
        frame_remainder=1,
        nominal_segment_duration_sec=8.0,
        min_segment_duration_sec=6.0,
        max_segment_duration_sec=10.0,
        min_subscene_duration_sec=6.0,
        max_subscene_duration_sec=10.0,
        allow_shorter_subscene_with_reason=False,
    ),
)

LTX_SEQUENCE_PROFILE = ProductionProfile(
    key="ltx_base",
    version=2,
    display_name="LTX Base · Sequence Sheet",
    model_family="ltx",
    # The exact static Sulphur 2 API workflow passed the local 8 s, 15 s, and
    # two-row last-frame continuation gate with synchronized native audio.
    status="qualified",
    approved_video_model_keys=frozenset({LTX_SEQUENCE_VIDEO_MODEL_KEY}),
    approved_video_models=frozenset({LTX_SEQUENCE_VIDEO_MODEL}),
    capabilities=VideoCapabilityPolicy(
        text_to_video=True,
        image_to_video=True,
        video_to_video=False,
        continuation=True,
        native_audio="supported",
        external_foley=False,
    ),
    frame_policy=VideoFramePolicy(
        frame_multiple=8,
        frame_remainder=1,
        nominal_segment_duration_sec=None,
        min_segment_duration_sec=8.0,
        max_segment_duration_sec=15.0,
        min_subscene_duration_sec=8.0,
        max_subscene_duration_sec=15.0,
        allow_shorter_subscene_with_reason=False,
    ),
    qualification_notes=(
        "Qualified locally on 2026-07-29 with Sulphur 2 base quants dev.",
        "Passed 8-second, 15-second, and two-row last-frame continuation renders.",
        "Pinned API workflow SHA-256 c928366ccf42a2d47a81a51c478079c385d1d6e72fe50ed8ff96d51c4dbb68bc.",
        "Native audio is preserved through LTX assembly; WAN Phase 8 is not used.",
    ),
)

WAN_BASE_PROFILE = ProductionProfile(
    key="wan_base",
    version=1,
    display_name="WAN Base",
    model_family="wan",
    status="on_hold",
    # The WAN lane is intentionally non-executable until exact model artifacts,
    # workflow manifests, custom nodes, and 24 GB benchmarks are admitted.
    approved_video_model_keys=frozenset(),
    approved_video_models=frozenset(),
    capabilities=VideoCapabilityPolicy(
        text_to_video=True,
        image_to_video=True,
        video_to_video=True,
        continuation=True,
        native_audio="unknown",
        external_foley=True,
        high_low_noise_pair=True,
    ),
    frame_policy=VideoFramePolicy(
        frame_multiple=4,
        frame_remainder=1,
        nominal_segment_duration_sec=None,
        min_segment_duration_sec=None,
        max_segment_duration_sec=None,
        min_subscene_duration_sec=15.0,
        max_subscene_duration_sec=90.0,
        allow_shorter_subscene_with_reason=True,
    ),
    qualification_notes=(
        "WAN evidence is preserved, but the production lane is not executable.",
    ),
    hold_reason="Local WAN dry run did not complete successfully.",
)

PRODUCTION_PROFILES: Mapping[str, ProductionProfile] = MappingProxyType(
    {
        LTX_BASE_PROFILE.ref: LTX_BASE_PROFILE,
        LTX_SEQUENCE_PROFILE.ref: LTX_SEQUENCE_PROFILE,
        WAN_BASE_PROFILE.ref: WAN_BASE_PROFILE,
    }
)

_PROFILE_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "ltx": LTX_BASE_PROFILE_REF,
        "ltx_base": LTX_BASE_PROFILE_REF,
        "ltx_sequence": LTX_SEQUENCE_PROFILE_REF,
        "ltx_sequence_sheet": LTX_SEQUENCE_PROFILE_REF,
        LEGACY_LTX_VIDEO_MODEL_KEY: LTX_BASE_PROFILE_REF,
        LEGACY_LTX_VIDEO_MODEL: LTX_BASE_PROFILE_REF,
        "wan": WAN_BASE_PROFILE_REF,
        "wan_base": WAN_BASE_PROFILE_REF,
    }
)


def canonical_production_profile_ref(profile_ref: str | None = None) -> str:
    """Resolve a canonical versioned reference without checking qualification."""

    if profile_ref is None:
        return DEFAULT_PRODUCTION_PROFILE_REF
    normalized = profile_ref.strip().casefold()
    if not normalized:
        raise UnknownProductionProfileError("Production profile cannot be empty.")
    canonical = _PROFILE_ALIASES.get(normalized, normalized)
    if canonical not in PRODUCTION_PROFILES:
        raise UnknownProductionProfileError(
            f"Unknown production profile {profile_ref!r}."
        )
    return canonical


def resolve_production_profile(
    profile_ref: str | ProductionProfile | None = None,
) -> ProductionProfile:
    """Resolve qualified and draft profiles for inspection or planning."""

    if isinstance(profile_ref, ProductionProfile):
        registered = PRODUCTION_PROFILES.get(profile_ref.ref)
        if registered != profile_ref:
            raise UnknownProductionProfileError(
                f"Unregistered production profile {profile_ref.ref!r}."
            )
        return registered
    return PRODUCTION_PROFILES[canonical_production_profile_ref(profile_ref)]


def select_production_profile(
    profile_ref: str | ProductionProfile | None = None,
    *,
    allow_unqualified: bool = False,
) -> ProductionProfile:
    """Resolve a selection, failing closed for draft profiles by default."""

    profile = resolve_production_profile(profile_ref)
    if not allow_unqualified:
        profile.require_execution_qualified()
    return profile


def list_production_profiles(
    *,
    include_unqualified: bool = True,
) -> tuple[ProductionProfile, ...]:
    profiles = tuple(PRODUCTION_PROFILES.values())
    if include_unqualified:
        return profiles
    return tuple(profile for profile in profiles if profile.execution_qualified)
