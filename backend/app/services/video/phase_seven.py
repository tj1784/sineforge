"""Pure Phase 7 planning and picture-lock domain services.

This module intentionally has no database, ComfyUI, filesystem, or FFmpeg
dependencies.  It defines the contracts those adapters must satisfy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from fractions import Fraction
import hashlib
import json
import math
import re
from typing import Any


PREFERRED_SUBSCENE_DURATION_SEC = 15.0
MAX_SUBSCENE_DURATION_SEC = 90.0
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DomainValidationError(ValueError):
    """Raised when a Phase 7 domain contract is internally inconsistent."""


class StitchStage(StrEnum):
    """The point at which selected picture segments become one timeline."""

    PHASE7_BEFORE_AUDIO = "phase7_before_audio"
    PHASE8_BEFORE_FOLEY = "phase8_before_foley"


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise DomainValidationError(f"{field_name} must not be blank")
    return normalized


def _positive_finite(value: float, field_name: str) -> float:
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise DomainValidationError(f"{field_name} must be a positive finite number")
    return normalized


def _sha256(value: str, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise DomainValidationError(
            f"{field_name} must be a lowercase or uppercase SHA-256 hex digest"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class Subscene:
    """An editorial unit, distinct from a provider inference segment.

    Fifteen seconds is the preferred minimum, not a hard generation-model
    limit.  A deliberately shorter editorial unit is valid only when its
    reason is retained with the plan.
    """

    subscene_id: str
    duration_sec: float
    short_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "subscene_id", _required_text(self.subscene_id, "subscene_id")
        )
        duration = _positive_finite(self.duration_sec, "duration_sec")
        if duration > MAX_SUBSCENE_DURATION_SEC:
            raise DomainValidationError(
                f"duration_sec must not exceed {MAX_SUBSCENE_DURATION_SEC:g} seconds"
            )
        reason = self.short_reason.strip() if self.short_reason is not None else None
        if duration < PREFERRED_SUBSCENE_DURATION_SEC and not reason:
            raise DomainValidationError(
                "subscenes shorter than the preferred 15 seconds require short_reason"
            )
        object.__setattr__(self, "duration_sec", duration)
        object.__setattr__(self, "short_reason", reason or None)

    @property
    def is_short_exception(self) -> bool:
        return self.duration_sec < PREFERRED_SUBSCENE_DURATION_SEC


@dataclass(frozen=True, slots=True)
class ProviderRenderConstraints:
    """Admitted provider frame rules used to compile editorial subscenes."""

    profile_id: str
    fps_numerator: int
    fps_denominator: int = 1
    min_frames: int = 1
    max_frames: int = 81
    frame_stride: int = 4
    frame_offset: int = 1
    duplicate_boundary_frames: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "profile_id", _required_text(self.profile_id, "profile_id")
        )
        for field_name in (
            "fps_numerator",
            "fps_denominator",
            "min_frames",
            "max_frames",
            "frame_stride",
        ):
            if int(getattr(self, field_name)) <= 0:
                raise DomainValidationError(f"{field_name} must be positive")
        if self.min_frames > self.max_frames:
            raise DomainValidationError("min_frames must not exceed max_frames")
        if self.frame_offset < 0 or self.frame_offset >= self.frame_stride:
            raise DomainValidationError(
                "frame_offset must be between zero and frame_stride - 1"
            )
        if self.duplicate_boundary_frames not in (0, 1):
            raise DomainValidationError(
                "duplicate_boundary_frames must be zero or one"
            )
        if not self.valid_frame_counts:
            raise DomainValidationError(
                "provider constraints do not admit any valid frame count"
            )
        if not any(
            frames > self.duplicate_boundary_frames
            for frames in self.valid_frame_counts
        ):
            raise DomainValidationError(
                "at least one valid frame count must exceed duplicate_boundary_frames"
            )

    @property
    def fps(self) -> Fraction:
        return Fraction(self.fps_numerator, self.fps_denominator)

    @property
    def valid_frame_counts(self) -> tuple[int, ...]:
        return tuple(
            frame_count
            for frame_count in range(self.min_frames, self.max_frames + 1)
            if (frame_count - self.frame_offset) % self.frame_stride == 0
        )

    def nearest_valid_frame_count(
        self,
        requested_effective_frames: Fraction,
        *,
        drop_leading_frames: int,
    ) -> int:
        """Return the closest admitted source count after boundary de-duplication."""

        if drop_leading_frames not in (0, self.duplicate_boundary_frames):
            raise DomainValidationError(
                "drop_leading_frames does not match the provider boundary policy"
            )
        candidates = tuple(
            frames
            for frames in self.valid_frame_counts
            if frames > drop_leading_frames
        )
        return min(
            candidates,
            key=lambda frames: (
                abs(Fraction(frames - drop_leading_frames) - requested_effective_frames),
                -frames,
            ),
        )


@dataclass(frozen=True, slots=True)
class RenderSegmentPlan:
    """One provider-valid render invocation compiled from an editorial subscene."""

    segment_id: str
    subscene_id: str
    segment_index: int
    timeline_start_sec: float
    timeline_end_sec: float
    frame_count: int
    drop_leading_frames: int
    provider_profile_id: str
    fps_numerator: int
    fps_denominator: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "segment_id", _required_text(self.segment_id, "segment_id")
        )
        object.__setattr__(
            self, "subscene_id", _required_text(self.subscene_id, "subscene_id")
        )
        object.__setattr__(
            self,
            "provider_profile_id",
            _required_text(self.provider_profile_id, "provider_profile_id"),
        )
        if self.segment_index < 0:
            raise DomainValidationError("segment_index must not be negative")
        if (
            not math.isfinite(self.timeline_start_sec)
            or not math.isfinite(self.timeline_end_sec)
            or self.timeline_start_sec < 0
            or self.timeline_end_sec <= self.timeline_start_sec
        ):
            raise DomainValidationError("segment timeline bounds are invalid")
        if self.frame_count <= 0:
            raise DomainValidationError("frame_count must be positive")
        if self.drop_leading_frames not in (0, 1):
            raise DomainValidationError("drop_leading_frames must be zero or one")
        if self.frame_count <= self.drop_leading_frames:
            raise DomainValidationError(
                "frame_count must exceed drop_leading_frames"
            )
        if self.fps_numerator <= 0 or self.fps_denominator <= 0:
            raise DomainValidationError("segment FPS must be positive")

    @property
    def requested_duration_sec(self) -> float:
        return self.timeline_end_sec - self.timeline_start_sec

    @property
    def effective_frame_count(self) -> int:
        return self.frame_count - self.drop_leading_frames

    @property
    def expected_output_duration_sec(self) -> float:
        return float(
            Fraction(
                self.effective_frame_count * self.fps_denominator,
                self.fps_numerator,
            )
        )


def compile_render_segments(
    subscene: Subscene,
    constraints: ProviderRenderConstraints,
) -> tuple[RenderSegmentPlan, ...]:
    """Compile an editorial subscene into deterministic provider-valid segments.

    The compiler uses the provider's frame ceiling and accounts for the one
    shared boundary frame removed from every continuation.  Editorial timing
    remains exact in the plan; expected generated duration is separately
    exposed so a later picture-lock assembly can trim deterministically.
    """

    requested_frames = (
        Fraction(str(subscene.duration_sec))
        * constraints.fps_numerator
        / constraints.fps_denominator
    )
    maximum_valid_frames = max(constraints.valid_frame_counts)
    first_capacity = maximum_valid_frames
    continuation_capacity = (
        maximum_valid_frames - constraints.duplicate_boundary_frames
    )
    if requested_frames <= first_capacity:
        segment_count = 1
    else:
        remaining = requested_frames - first_capacity
        segment_count = 1 + math.ceil(remaining / continuation_capacity)

    plans: list[RenderSegmentPlan] = []
    exact_segment_duration = Fraction(str(subscene.duration_sec)) / segment_count
    for index in range(segment_count):
        start = exact_segment_duration * index
        end = (
            Fraction(str(subscene.duration_sec))
            if index == segment_count - 1
            else exact_segment_duration * (index + 1)
        )
        drop = 0 if index == 0 else constraints.duplicate_boundary_frames
        desired_effective_frames = (end - start) * constraints.fps
        frame_count = constraints.nearest_valid_frame_count(
            desired_effective_frames,
            drop_leading_frames=drop,
        )
        plans.append(
            RenderSegmentPlan(
                segment_id=f"{subscene.subscene_id}:render:{index + 1:03d}",
                subscene_id=subscene.subscene_id,
                segment_index=index,
                timeline_start_sec=float(start),
                timeline_end_sec=float(end),
                frame_count=frame_count,
                drop_leading_frames=drop,
                provider_profile_id=constraints.profile_id,
                fps_numerator=constraints.fps_numerator,
                fps_denominator=constraints.fps_denominator,
            )
        )
    return tuple(plans)


@dataclass(frozen=True, slots=True)
class EditDecision:
    """A selected source interval placed on the final picture timeline."""

    decision_id: str
    asset_id: str
    asset_sha256: str
    source_start_frame: int
    source_end_frame_exclusive: int
    timeline_start_frame: int
    drop_leading_frames: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision_id", _required_text(self.decision_id, "decision_id")
        )
        object.__setattr__(self, "asset_id", _required_text(self.asset_id, "asset_id"))
        object.__setattr__(
            self,
            "asset_sha256",
            _sha256(self.asset_sha256, "asset_sha256"),
        )
        if self.source_start_frame < 0:
            raise DomainValidationError("source_start_frame must not be negative")
        if self.source_end_frame_exclusive <= self.source_start_frame:
            raise DomainValidationError(
                "source_end_frame_exclusive must exceed source_start_frame"
            )
        if self.timeline_start_frame < 0:
            raise DomainValidationError("timeline_start_frame must not be negative")
        if self.drop_leading_frames not in (0, 1):
            raise DomainValidationError("drop_leading_frames must be zero or one")
        if self.source_frame_count <= self.drop_leading_frames:
            raise DomainValidationError(
                "source interval must exceed drop_leading_frames"
            )

    @property
    def source_frame_count(self) -> int:
        return self.source_end_frame_exclusive - self.source_start_frame

    @property
    def timeline_frame_count(self) -> int:
        return self.source_frame_count - self.drop_leading_frames

    @property
    def timeline_end_frame_exclusive(self) -> int:
        return self.timeline_start_frame + self.timeline_frame_count

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_sha256": self.asset_sha256,
            "decision_id": self.decision_id,
            "drop_leading_frames": self.drop_leading_frames,
            "source_end_frame_exclusive": self.source_end_frame_exclusive,
            "source_start_frame": self.source_start_frame,
            "timeline_start_frame": self.timeline_start_frame,
        }


@dataclass(frozen=True, slots=True)
class EditDecisionList:
    """Immutable, frame-exact assembly decisions for one picture timeline."""

    edl_id: str
    stitch_stage: StitchStage
    fps_numerator: int
    fps_denominator: int
    decisions: tuple[EditDecision, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "edl_id", _required_text(self.edl_id, "edl_id"))
        object.__setattr__(self, "decisions", tuple(self.decisions))
        if not isinstance(self.stitch_stage, StitchStage):
            try:
                object.__setattr__(
                    self, "stitch_stage", StitchStage(self.stitch_stage)
                )
            except ValueError as exc:
                raise DomainValidationError("stitch_stage is invalid") from exc
        if self.fps_numerator <= 0 or self.fps_denominator <= 0:
            raise DomainValidationError("EDL FPS must be positive")
        if not self.decisions:
            raise DomainValidationError("EDL must contain at least one decision")
        expected_start = 0
        seen_ids: set[str] = set()
        for decision in self.decisions:
            if decision.decision_id in seen_ids:
                raise DomainValidationError("EDL decision IDs must be unique")
            seen_ids.add(decision.decision_id)
            if decision.timeline_start_frame != expected_start:
                raise DomainValidationError(
                    "EDL decisions must form a contiguous, zero-based timeline"
                )
            expected_start = decision.timeline_end_frame_exclusive

    @property
    def total_frame_count(self) -> int:
        return self.decisions[-1].timeline_end_frame_exclusive

    @property
    def duration_sec(self) -> float:
        return float(
            Fraction(
                self.total_frame_count * self.fps_denominator,
                self.fps_numerator,
            )
        )

    @property
    def sha256(self) -> str:
        payload = {
            "decisions": [item.canonical_dict() for item in self.decisions],
            "edl_id": self.edl_id,
            "fps_denominator": self.fps_denominator,
            "fps_numerator": self.fps_numerator,
            "stitch_stage": self.stitch_stage.value,
        }
        canonical = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class ContinuityHandoff:
    """Evidence for the exact accepted frame conditioning a successor segment."""

    predecessor_segment_id: str
    successor_segment_id: str
    source_asset_id: str
    source_asset_sha256: str
    frame_index: int
    pts_numerator: int
    pts_denominator: int
    frame_sha256: str
    extraction_template_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "predecessor_segment_id",
            "successor_segment_id",
            "source_asset_id",
            "extraction_template_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "source_asset_sha256",
            _sha256(self.source_asset_sha256, "source_asset_sha256"),
        )
        object.__setattr__(
            self, "frame_sha256", _sha256(self.frame_sha256, "frame_sha256")
        )
        if self.predecessor_segment_id == self.successor_segment_id:
            raise DomainValidationError(
                "handoff predecessor and successor must be different"
            )
        if self.frame_index < 0:
            raise DomainValidationError("frame_index must not be negative")
        if self.pts_numerator < 0 or self.pts_denominator <= 0:
            raise DomainValidationError("handoff PTS must be non-negative and valid")

    @property
    def pts(self) -> Fraction:
        return Fraction(self.pts_numerator, self.pts_denominator)


@dataclass(frozen=True, slots=True)
class PictureLock:
    """Immutable proof that Phase 8 will analyze one exact final picture."""

    picture_lock_id: str
    edl_sha256: str
    final_video_asset_id: str
    final_video_sha256: str
    assembly_manifest_sha256: str
    frame_count: int
    fps_numerator: int
    fps_denominator: int
    width: int
    height: int
    pixel_format: str
    stitch_stage: StitchStage
    selected_asset_ids: tuple[str, ...]
    locked_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "picture_lock_id",
            "final_video_asset_id",
            "pixel_format",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        for field_name in (
            "edl_sha256",
            "final_video_sha256",
            "assembly_manifest_sha256",
        ):
            object.__setattr__(
                self, field_name, _sha256(getattr(self, field_name), field_name)
            )
        object.__setattr__(
            self,
            "selected_asset_ids",
            tuple(
                _required_text(asset_id, "selected_asset_ids item")
                for asset_id in self.selected_asset_ids
            ),
        )
        if not self.selected_asset_ids:
            raise DomainValidationError(
                "picture lock must retain at least one selected asset"
            )
        if self.frame_count <= 0:
            raise DomainValidationError("frame_count must be positive")
        if self.fps_numerator <= 0 or self.fps_denominator <= 0:
            raise DomainValidationError("picture-lock FPS must be positive")
        if self.width <= 0 or self.height <= 0:
            raise DomainValidationError("picture-lock dimensions must be positive")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise DomainValidationError("locked_at must be timezone-aware")
        if not isinstance(self.stitch_stage, StitchStage):
            try:
                object.__setattr__(
                    self, "stitch_stage", StitchStage(self.stitch_stage)
                )
            except ValueError as exc:
                raise DomainValidationError("stitch_stage is invalid") from exc

    @classmethod
    def from_edl(
        cls,
        *,
        picture_lock_id: str,
        edl: EditDecisionList,
        final_video_asset_id: str,
        final_video_sha256: str,
        assembly_manifest_sha256: str,
        width: int,
        height: int,
        pixel_format: str,
        locked_at: datetime,
    ) -> PictureLock:
        """Create a lock whose timeline and source set are derived from the EDL."""

        return cls(
            picture_lock_id=picture_lock_id,
            edl_sha256=edl.sha256,
            final_video_asset_id=final_video_asset_id,
            final_video_sha256=final_video_sha256,
            assembly_manifest_sha256=assembly_manifest_sha256,
            frame_count=edl.total_frame_count,
            fps_numerator=edl.fps_numerator,
            fps_denominator=edl.fps_denominator,
            width=width,
            height=height,
            pixel_format=pixel_format,
            stitch_stage=edl.stitch_stage,
            selected_asset_ids=tuple(
                dict.fromkeys(item.asset_id for item in edl.decisions)
            ),
            locked_at=locked_at,
        )

    @property
    def duration_sec(self) -> float:
        return float(
            Fraction(
                self.frame_count * self.fps_denominator,
                self.fps_numerator,
            )
        )
