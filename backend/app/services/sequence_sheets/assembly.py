"""Pure, file-based audiovisual assembly planning for LTX Sequence Sheets.

This module accepts already-probed managed clip references and produces an
exact EDL, a bounded-memory assembly strategy, an immutable synchronized
native-audio plan, and a planned final mux identity. LTX audio is generated
with each segment and remains attached through assembly; it is never routed
through WAN Phase 8. This module intentionally does not construct shell
commands, invoke FFmpeg, or read media files.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Iterable

from backend.app.services.sequence_sheets.continuity import (
    DuplicateBoundaryDecision,
)


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_FORBIDDEN_MANAGED_PATH_CHARACTERS = frozenset("\x00\r\n")


class AssemblyValidationError(ValueError):
    """Raised when selected media cannot produce an exact, safe assembly plan."""


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise AssemblyValidationError(f"{field_name} must not be blank")
    return normalized


def _sha256(value: str, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise AssemblyValidationError(
            f"{field_name} must be a SHA-256 hexadecimal digest"
        )
    return normalized


def _positive_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AssemblyValidationError(f"{field_name} must be a positive integer")
    return value


def _non_negative_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AssemblyValidationError(
            f"{field_name} must be a non-negative integer"
        )
    return value


def _managed_relative_path(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise AssemblyValidationError("managed_path must not be blank")
    if any(character in normalized for character in _FORBIDDEN_MANAGED_PATH_CHARACTERS):
        raise AssemblyValidationError("managed_path contains a forbidden character")
    if "\\" in normalized or ":" in normalized:
        raise AssemblyValidationError(
            "managed_path must be a relative POSIX managed-asset reference"
        )
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise AssemblyValidationError(
            "managed_path must remain inside managed project storage"
        )
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class ManagedAssetReference:
    """A content-addressed project asset, never a caller-supplied command path."""

    asset_id: str
    managed_path: str
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _required_text(self.asset_id, "asset_id"))
        object.__setattr__(
            self, "managed_path", _managed_relative_path(self.managed_path)
        )
        object.__setattr__(self, "sha256", _sha256(self.sha256, "sha256"))


@dataclass(frozen=True, slots=True)
class VideoStreamSignature:
    """Fields that must match exactly for safe concat-demuxer stream copy."""

    codec_name: str
    codec_profile: str
    codec_level: int
    width: int
    height: int
    pixel_format: str
    fps_numerator: int
    fps_denominator: int
    time_base_numerator: int
    time_base_denominator: int
    sample_aspect_ratio_numerator: int = 1
    sample_aspect_ratio_denominator: int = 1
    color_range: str = "unknown"
    color_space: str = "unknown"
    color_transfer: str = "unknown"
    color_primaries: str = "unknown"
    field_order: str = "progressive"

    def __post_init__(self) -> None:
        for field_name in (
            "codec_name",
            "codec_profile",
            "pixel_format",
            "color_range",
            "color_space",
            "color_transfer",
            "color_primaries",
            "field_order",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name).lower(),
            )
        _non_negative_integer(self.codec_level, "codec_level")
        for field_name in (
            "width",
            "height",
            "fps_numerator",
            "fps_denominator",
            "time_base_numerator",
            "time_base_denominator",
            "sample_aspect_ratio_numerator",
            "sample_aspect_ratio_denominator",
        ):
            _positive_integer(getattr(self, field_name), field_name)

    @property
    def fps(self) -> Fraction:
        return Fraction(self.fps_numerator, self.fps_denominator)

    @property
    def time_base(self) -> Fraction:
        return Fraction(self.time_base_numerator, self.time_base_denominator)

    @property
    def frame_duration_pts(self) -> int:
        ticks = Fraction(1, 1) / self.fps / self.time_base
        if ticks.denominator != 1:
            raise AssemblyValidationError(
                "stream FPS is not frame-exact in the declared time base"
            )
        return ticks.numerator

    def differences(self, other: VideoStreamSignature) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in self.__dataclass_fields__
            if getattr(self, field_name) != getattr(other, field_name)
        )


class NativeAudioRole(StrEnum):
    SYNCHRONIZED_NATIVE = "synchronized_native"


@dataclass(frozen=True, slots=True)
class NativeAudioStem:
    """Required row-scoped LTX audio synchronized to its generated video."""

    asset: ManagedAssetReference
    role: NativeAudioRole
    sample_rate: int
    channels: int
    sample_count: int
    workflow_identity: str
    seed: int | None = None

    def __post_init__(self) -> None:
        _positive_integer(self.sample_rate, "sample_rate")
        _positive_integer(self.channels, "channels")
        _positive_integer(self.sample_count, "sample_count")
        object.__setattr__(
            self,
            "workflow_identity",
            _required_text(self.workflow_identity, "workflow_identity"),
        )
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise AssemblyValidationError("seed must be an integer or null")

    @property
    def duration(self) -> Fraction:
        return Fraction(self.sample_count, self.sample_rate)


@dataclass(frozen=True, slots=True)
class SelectedClipProbe:
    """Full-decode evidence for one selected row clip."""

    row_id: str
    asset: ManagedAssetReference
    stream: VideoStreamSignature
    frame_count: int
    start_pts: int
    duration_pts: int
    fully_decodable: bool = True
    probe_version: str = "ffprobe_contract_v1"
    native_audio_stem: NativeAudioStem | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", _required_text(self.row_id, "row_id"))
        _positive_integer(self.frame_count, "frame_count")
        _non_negative_integer(self.start_pts, "start_pts")
        _positive_integer(self.duration_pts, "duration_pts")
        object.__setattr__(
            self,
            "probe_version",
            _required_text(self.probe_version, "probe_version"),
        )
        expected_duration_pts = self.frame_count * self.stream.frame_duration_pts
        if self.duration_pts != expected_duration_pts:
            raise AssemblyValidationError(
                "duration_pts must exactly equal frame_count times frame duration"
            )

    @property
    def duration(self) -> Fraction:
        return self.duration_pts * self.stream.time_base


@dataclass(frozen=True, slots=True)
class ClipBoundaryEdit:
    """An explicit decision for a single adjacent clip boundary."""

    predecessor_row_id: str
    successor_row_id: str
    decision: DuplicateBoundaryDecision

    def __post_init__(self) -> None:
        predecessor = _required_text(self.predecessor_row_id, "predecessor_row_id")
        successor = _required_text(self.successor_row_id, "successor_row_id")
        if predecessor == successor:
            raise AssemblyValidationError(
                "a clip boundary must connect two different rows"
            )
        object.__setattr__(self, "predecessor_row_id", predecessor)
        object.__setattr__(self, "successor_row_id", successor)


class VisualTransformKind(StrEnum):
    RETIME = "retime"
    INTERPOLATE = "interpolate"
    UPSCALE = "upscale"
    CROP = "crop"


@dataclass(frozen=True, slots=True)
class VisualTransformRequest:
    row_id: str
    kind: VisualTransformKind
    output_frame_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", _required_text(self.row_id, "row_id"))
        changes_timing = self.kind in (
            VisualTransformKind.RETIME,
            VisualTransformKind.INTERPOLATE,
        )
        if changes_timing:
            if self.output_frame_count is None:
                raise AssemblyValidationError(
                    f"{self.kind.value} requires an explicit output_frame_count"
                )
            _positive_integer(self.output_frame_count, "output_frame_count")
        elif self.output_frame_count is not None:
            raise AssemblyValidationError(
                "output_frame_count is valid only for a timing transform"
            )


class VisualTransitionKind(StrEnum):
    CROSSFADE = "crossfade"
    DISSOLVE = "dissolve"


@dataclass(frozen=True, slots=True)
class VisualTransitionRequest:
    predecessor_row_id: str
    successor_row_id: str
    kind: VisualTransitionKind
    overlap_frames: int

    def __post_init__(self) -> None:
        predecessor = _required_text(self.predecessor_row_id, "predecessor_row_id")
        successor = _required_text(self.successor_row_id, "successor_row_id")
        if predecessor == successor:
            raise AssemblyValidationError(
                "a transition must connect two different rows"
            )
        object.__setattr__(self, "predecessor_row_id", predecessor)
        object.__setattr__(self, "successor_row_id", successor)
        _positive_integer(self.overlap_frames, "overlap_frames")


class AssemblyStrategy(StrEnum):
    CONCAT_STREAM_COPY = "concat_stream_copy"
    CONTROLLED_MEZZANINE = "controlled_mezzanine"


@dataclass(frozen=True, slots=True)
class EditDecision:
    row_id: str
    asset: ManagedAssetReference
    source_start_frame: int
    source_end_frame_exclusive: int
    source_start_pts: int
    source_end_pts_exclusive: int
    output_frame_count: int
    timeline_start_frame: int
    timeline_end_frame_exclusive: int
    timeline_start_pts: int
    timeline_end_pts_exclusive: int
    boundary_trim_leading_frames: int
    boundary_reason: str
    native_audio_stem: NativeAudioStem | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", _required_text(self.row_id, "row_id"))
        for field_name in (
            "source_start_frame",
            "source_start_pts",
            "timeline_start_frame",
            "timeline_start_pts",
            "boundary_trim_leading_frames",
        ):
            _non_negative_integer(getattr(self, field_name), field_name)
        for field_name in (
            "source_end_frame_exclusive",
            "source_end_pts_exclusive",
            "output_frame_count",
            "timeline_end_frame_exclusive",
            "timeline_end_pts_exclusive",
        ):
            _positive_integer(getattr(self, field_name), field_name)
        if self.boundary_trim_leading_frames not in (0, 1):
            raise AssemblyValidationError(
                "boundary_trim_leading_frames must be zero or one"
            )
        if self.source_end_frame_exclusive <= self.source_start_frame:
            raise AssemblyValidationError("source frame range must not be empty")
        if self.source_end_pts_exclusive <= self.source_start_pts:
            raise AssemblyValidationError("source PTS range must not be empty")
        if (
            self.timeline_end_frame_exclusive - self.timeline_start_frame
            != self.output_frame_count
        ):
            raise AssemblyValidationError(
                "timeline frame range must equal output_frame_count"
            )
        if self.timeline_end_pts_exclusive <= self.timeline_start_pts:
            raise AssemblyValidationError("timeline PTS range must not be empty")
        object.__setattr__(
            self,
            "boundary_reason",
            _required_text(self.boundary_reason, "boundary_reason"),
        )


@dataclass(frozen=True, slots=True)
class ControlledMezzaninePlan:
    """One normalization pass; adapters map the profile to fixed arguments."""

    profile_id: str
    target_stream: VideoStreamSignature
    source_row_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    transforms: tuple[VisualTransformRequest, ...]
    transitions: tuple[VisualTransitionRequest, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _required_text(self.profile_id, "profile_id"))
        if not self.source_row_ids:
            raise AssemblyValidationError(
                "a controlled mezzanine plan requires source rows"
            )
        if not self.reason_codes:
            raise AssemblyValidationError(
                "a controlled mezzanine plan requires a deterministic reason"
            )


@dataclass(frozen=True, slots=True)
class PictureLockPlan:
    """Exact LTX delivery timing identity for synchronized video and audio."""

    picture_lock_id: str
    edl_sha256: str
    native_audio_manifest_sha256: str
    manifest_sha256: str
    strategy: AssemblyStrategy
    target_stream: VideoStreamSignature
    total_frame_count: int
    timeline_start_pts: int
    timeline_end_pts_exclusive: int
    source_asset_ids: tuple[str, ...]
    source_asset_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "picture_lock_id",
            _required_text(self.picture_lock_id, "picture_lock_id"),
        )
        object.__setattr__(self, "edl_sha256", _sha256(self.edl_sha256, "edl_sha256"))
        object.__setattr__(
            self,
            "native_audio_manifest_sha256",
            _sha256(
                self.native_audio_manifest_sha256,
                "native_audio_manifest_sha256",
            ),
        )
        object.__setattr__(
            self,
            "manifest_sha256",
            _sha256(self.manifest_sha256, "manifest_sha256"),
        )
        _positive_integer(self.total_frame_count, "total_frame_count")
        _non_negative_integer(self.timeline_start_pts, "timeline_start_pts")
        _positive_integer(
            self.timeline_end_pts_exclusive, "timeline_end_pts_exclusive"
        )
        if self.timeline_end_pts_exclusive <= self.timeline_start_pts:
            raise AssemblyValidationError("picture-lock PTS range must not be empty")
        if (
            self.timeline_end_pts_exclusive - self.timeline_start_pts
            != self.total_frame_count * self.target_stream.frame_duration_pts
        ):
            raise AssemblyValidationError(
                "picture-lock frame and PTS totals must agree exactly"
            )
        if not self.source_asset_ids:
            raise AssemblyValidationError("picture lock requires source assets")
        if len(self.source_asset_ids) != len(self.source_asset_sha256s):
            raise AssemblyValidationError(
                "picture-lock asset IDs and hashes must have equal length"
            )
        for asset_id in self.source_asset_ids:
            _required_text(asset_id, "source_asset_id")
        for digest in self.source_asset_sha256s:
            _sha256(digest, "source_asset_sha256")

    @property
    def duration(self) -> Fraction:
        return (
            self.timeline_end_pts_exclusive - self.timeline_start_pts
        ) * self.target_stream.time_base


@dataclass(frozen=True, slots=True)
class LtxNativeAudioEdit:
    row_id: str
    asset: ManagedAssetReference
    sample_rate: int
    channels: int
    source_start_sample: int
    source_end_sample_exclusive: int
    output_sample_count: int
    timeline_start_sample: int
    timeline_end_sample_exclusive: int
    timeline_start_frame: int
    timeline_end_frame_exclusive: int
    requires_time_stretch: bool
    transition_overlap_samples: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", _required_text(self.row_id, "row_id"))
        _positive_integer(self.sample_rate, "sample_rate")
        _positive_integer(self.channels, "channels")
        for field_name in (
            "source_start_sample",
            "timeline_start_sample",
            "timeline_start_frame",
            "transition_overlap_samples",
        ):
            _non_negative_integer(getattr(self, field_name), field_name)
        for field_name in (
            "source_end_sample_exclusive",
            "output_sample_count",
            "timeline_end_sample_exclusive",
            "timeline_end_frame_exclusive",
        ):
            _positive_integer(getattr(self, field_name), field_name)
        if self.source_end_sample_exclusive <= self.source_start_sample:
            raise AssemblyValidationError("native-audio source range must not be empty")
        if (
            self.timeline_end_sample_exclusive - self.timeline_start_sample
            != self.output_sample_count
        ):
            raise AssemblyValidationError(
                "native-audio timeline range must equal output_sample_count"
            )
        if self.timeline_end_frame_exclusive <= self.timeline_start_frame:
            raise AssemblyValidationError(
                "native-audio frame range must not be empty"
            )
        source_sample_count = (
            self.source_end_sample_exclusive - self.source_start_sample
        )
        if self.requires_time_stretch != (
            source_sample_count != self.output_sample_count
        ):
            raise AssemblyValidationError(
                "requires_time_stretch must match the source/output sample counts"
            )


@dataclass(frozen=True, slots=True)
class LtxNativeAudioAssemblyPlan:
    schema_version: str
    strategy: str
    sample_rate: int
    channels: int
    total_sample_count: int
    manifest_sha256: str
    native_audio_required: bool
    mux_with_video: bool
    edits: tuple[LtxNativeAudioEdit, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _required_text(self.schema_version, "schema_version"),
        )
        object.__setattr__(
            self,
            "strategy",
            _required_text(self.strategy, "strategy"),
        )
        object.__setattr__(
            self,
            "manifest_sha256",
            _sha256(self.manifest_sha256, "manifest_sha256"),
        )
        _positive_integer(self.sample_rate, "sample_rate")
        _positive_integer(self.channels, "channels")
        _positive_integer(self.total_sample_count, "total_sample_count")
        if self.native_audio_required is not True:
            raise AssemblyValidationError(
                "LTX assembly requires synchronized native audio"
            )
        if self.mux_with_video is not True:
            raise AssemblyValidationError(
                "LTX native audio must be muxed with the assembled video"
            )
        if not self.edits:
            raise AssemblyValidationError(
                "LTX native-audio assembly requires row edits"
            )
        if any(edit.sample_rate != self.sample_rate for edit in self.edits):
            raise AssemblyValidationError(
                "all LTX native-audio edits must use the declared sample rate"
            )
        if any(edit.channels != self.channels for edit in self.edits):
            raise AssemblyValidationError(
                "all LTX native-audio edits must use the declared channel count"
            )
        if max(edit.timeline_end_sample_exclusive for edit in self.edits) != (
            self.total_sample_count
        ):
            raise AssemblyValidationError(
                "LTX native audio must reach the exact final video duration"
            )

    @property
    def duration(self) -> Fraction:
        return Fraction(self.total_sample_count, self.sample_rate)


@dataclass(frozen=True, slots=True)
class AssemblyPlan:
    strategy: AssemblyStrategy
    target_stream: VideoStreamSignature
    edl: tuple[EditDecision, ...]
    edl_sha256: str
    concat_assets: tuple[ManagedAssetReference, ...]
    mezzanine: ControlledMezzaninePlan | None
    picture_lock: PictureLockPlan
    native_audio: LtxNativeAudioAssemblyPlan


def _stream_payload(stream: VideoStreamSignature) -> dict[str, int | str]:
    return {
        field_name: getattr(stream, field_name)
        for field_name in stream.__dataclass_fields__
    }


def _asset_payload(asset: ManagedAssetReference) -> dict[str, str]:
    return {
        "asset_id": asset.asset_id,
        "managed_path": asset.managed_path,
        "sha256": asset.sha256,
    }


def _audio_payload(stem: NativeAudioStem | None) -> dict[str, object] | None:
    if stem is None:
        return None
    return {
        "asset": _asset_payload(stem.asset),
        "role": stem.role.value,
        "sample_rate": stem.sample_rate,
        "channels": stem.channels,
        "sample_count": stem.sample_count,
        "workflow_identity": stem.workflow_identity,
        "seed": stem.seed,
    }


def _edl_payload(edl: tuple[EditDecision, ...]) -> list[dict[str, object]]:
    return [
        {
            "row_id": decision.row_id,
            "asset": _asset_payload(decision.asset),
            "source_start_frame": decision.source_start_frame,
            "source_end_frame_exclusive": decision.source_end_frame_exclusive,
            "source_start_pts": decision.source_start_pts,
            "source_end_pts_exclusive": decision.source_end_pts_exclusive,
            "output_frame_count": decision.output_frame_count,
            "timeline_start_frame": decision.timeline_start_frame,
            "timeline_end_frame_exclusive": decision.timeline_end_frame_exclusive,
            "timeline_start_pts": decision.timeline_start_pts,
            "timeline_end_pts_exclusive": decision.timeline_end_pts_exclusive,
            "boundary_trim_leading_frames": decision.boundary_trim_leading_frames,
            "boundary_reason": decision.boundary_reason,
            "native_audio_stem": _audio_payload(decision.native_audio_stem),
        }
        for decision in edl
    ]


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _frames_to_samples_exact(
    frame_count: int,
    fps: Fraction,
    sample_rate: int,
    *,
    field_name: str,
) -> int:
    exact = Fraction(frame_count * sample_rate, 1) / fps
    if exact.denominator != 1:
        raise AssemblyValidationError(
            f"{field_name} is not sample-exact at {sample_rate} Hz"
        )
    return exact.numerator


def _exact_target_frame_count(
    source_frame_count: int,
    source_stream: VideoStreamSignature,
    target_stream: VideoStreamSignature,
) -> int:
    exact = Fraction(source_frame_count, 1) / source_stream.fps * target_stream.fps
    if exact.denominator != 1:
        raise AssemblyValidationError(
            "normalization does not yield an exact target frame count; add an "
            "explicit timing transform"
        )
    return exact.numerator


def plan_ltx_av_assembly(
    clips: Iterable[SelectedClipProbe],
    *,
    boundary_edits: Iterable[ClipBoundaryEdit] = (),
    transforms: Iterable[VisualTransformRequest] = (),
    transitions: Iterable[VisualTransitionRequest] = (),
    target_stream: VideoStreamSignature | None = None,
    mezzanine_profile_id: str = "sineforge_visual_mezzanine_v1",
) -> AssemblyPlan:
    """Compile selected LTX clips and native audio into one exact mux plan."""

    selected = tuple(clips)
    if not selected:
        raise AssemblyValidationError("at least one selected clip is required")
    row_ids = tuple(clip.row_id for clip in selected)
    if len(set(row_ids)) != len(row_ids):
        raise AssemblyValidationError("selected clip row IDs must be unique")
    if any(not clip.fully_decodable for clip in selected):
        raise AssemblyValidationError(
            "every selected clip must have full-decode evidence"
        )
    if any(clip.native_audio_stem is None for clip in selected):
        raise AssemblyValidationError(
            "every LTX segment requires synchronized native audio before assembly"
        )

    first_audio = selected[0].native_audio_stem
    assert first_audio is not None
    audio_sample_rate = first_audio.sample_rate
    audio_channels = first_audio.channels
    for clip in selected:
        stem = clip.native_audio_stem
        assert stem is not None
        if (
            stem.sample_rate != audio_sample_rate
            or stem.channels != audio_channels
        ):
            raise AssemblyValidationError(
                "all LTX native-audio streams must share sample rate and channels"
            )
        expected_sample_count = _frames_to_samples_exact(
            clip.frame_count,
            clip.stream.fps,
            stem.sample_rate,
            field_name=f"{clip.row_id} native audio",
        )
        if stem.sample_count != expected_sample_count:
            raise AssemblyValidationError(
                f"{clip.row_id} native audio does not match its video duration"
            )

    index_by_row = {row_id: index for index, row_id in enumerate(row_ids)}
    boundaries = tuple(boundary_edits)
    boundary_by_successor: dict[str, ClipBoundaryEdit] = {}
    for boundary in boundaries:
        if boundary.successor_row_id in boundary_by_successor:
            raise AssemblyValidationError(
                "each successor may have only one boundary edit"
            )
        successor_index = index_by_row.get(boundary.successor_row_id)
        predecessor_index = index_by_row.get(boundary.predecessor_row_id)
        if (
            successor_index is None
            or predecessor_index is None
            or successor_index != predecessor_index + 1
        ):
            raise AssemblyValidationError(
                "boundary edits must connect adjacent selected rows"
            )
        boundary_by_successor[boundary.successor_row_id] = boundary

    requested_transforms = tuple(transforms)
    transform_by_row: dict[str, VisualTransformRequest] = {}
    for transform in requested_transforms:
        if transform.row_id not in index_by_row:
            raise AssemblyValidationError("transform references an unknown row")
        if transform.row_id in transform_by_row:
            raise AssemblyValidationError(
                "V1 permits at most one explicit transform per row"
            )
        transform_by_row[transform.row_id] = transform

    requested_transitions = tuple(transitions)
    transition_by_successor: dict[str, VisualTransitionRequest] = {}
    for transition in requested_transitions:
        successor_index = index_by_row.get(transition.successor_row_id)
        predecessor_index = index_by_row.get(transition.predecessor_row_id)
        if (
            successor_index is None
            or predecessor_index is None
            or successor_index != predecessor_index + 1
        ):
            raise AssemblyValidationError(
                "transitions must connect adjacent selected rows"
            )
        if transition.successor_row_id in transition_by_successor:
            raise AssemblyValidationError(
                "each boundary may have at most one transition"
            )
        transition_by_successor[transition.successor_row_id] = transition

    target = target_stream or selected[0].stream
    target_frame_duration_pts = target.frame_duration_pts
    signature_differences = tuple(
        (clip.row_id, clip.stream.differences(target))
        for clip in selected
        if clip.stream != target
    )
    has_boundary_trim = any(
        boundary.decision.trim_successor_leading_frames
        for boundary in boundaries
    )
    stream_copy_safe = (
        not signature_differences
        and not requested_transforms
        and not requested_transitions
        and not has_boundary_trim
    )
    strategy = (
        AssemblyStrategy.CONCAT_STREAM_COPY
        if stream_copy_safe
        else AssemblyStrategy.CONTROLLED_MEZZANINE
    )

    timeline_cursor_frames = 0
    decisions: list[EditDecision] = []
    for clip in selected:
        boundary = boundary_by_successor.get(clip.row_id)
        trim = (
            boundary.decision.trim_successor_leading_frames
            if boundary is not None
            else 0
        )
        if trim >= clip.frame_count:
            raise AssemblyValidationError(
                "a boundary trim cannot remove the entire successor clip"
            )
        effective_source_frames = clip.frame_count - trim
        transform = transform_by_row.get(clip.row_id)
        if transform is not None and transform.output_frame_count is not None:
            output_frames = transform.output_frame_count
        else:
            output_frames = _exact_target_frame_count(
                effective_source_frames,
                clip.stream,
                target,
            )

        transition = transition_by_successor.get(clip.row_id)
        overlap_frames = transition.overlap_frames if transition is not None else 0
        if overlap_frames:
            if not decisions or overlap_frames >= output_frames:
                raise AssemblyValidationError(
                    "transition overlap must be smaller than the successor clip"
                )
            if overlap_frames >= decisions[-1].output_frame_count:
                raise AssemblyValidationError(
                    "transition overlap must be smaller than the predecessor clip"
                )
        timeline_start_frame = timeline_cursor_frames - overlap_frames
        timeline_end_frame = timeline_start_frame + output_frames

        source_frame_duration_pts = clip.stream.frame_duration_pts
        source_start_frame = trim
        source_start_pts = clip.start_pts + trim * source_frame_duration_pts
        source_end_pts = clip.start_pts + clip.duration_pts
        boundary_reason = (
            boundary.decision.reason
            if boundary is not None
            else "No duplicate-boundary trim was requested."
        )
        decision = EditDecision(
            row_id=clip.row_id,
            asset=clip.asset,
            source_start_frame=source_start_frame,
            source_end_frame_exclusive=clip.frame_count,
            source_start_pts=source_start_pts,
            source_end_pts_exclusive=source_end_pts,
            output_frame_count=output_frames,
            timeline_start_frame=timeline_start_frame,
            timeline_end_frame_exclusive=timeline_end_frame,
            timeline_start_pts=timeline_start_frame * target_frame_duration_pts,
            timeline_end_pts_exclusive=timeline_end_frame
            * target_frame_duration_pts,
            boundary_trim_leading_frames=trim,
            boundary_reason=boundary_reason,
            native_audio_stem=clip.native_audio_stem,
        )
        decisions.append(decision)
        timeline_cursor_frames = timeline_end_frame

    edl = tuple(decisions)
    edl_payload = {
        "schema_version": "sineforge.sequence-edl/v1",
        "target_stream": _stream_payload(target),
        "decisions": _edl_payload(edl),
    }
    edl_sha256 = _canonical_sha256(edl_payload)

    mezzanine: ControlledMezzaninePlan | None = None
    if strategy is AssemblyStrategy.CONTROLLED_MEZZANINE:
        reasons: list[str] = []
        for row_id, fields in signature_differences:
            reasons.extend(f"stream_mismatch:{row_id}:{field}" for field in fields)
        if requested_transforms:
            reasons.append("explicit_visual_transform")
        if requested_transitions:
            reasons.append("explicit_visual_transition")
        if has_boundary_trim:
            reasons.append("frame_exact_boundary_trim")
        mezzanine = ControlledMezzaninePlan(
            profile_id=mezzanine_profile_id,
            target_stream=target,
            source_row_ids=row_ids,
            reason_codes=tuple(dict.fromkeys(reasons)),
            transforms=requested_transforms,
            transitions=requested_transitions,
        )

    clip_by_row = {clip.row_id: clip for clip in selected}
    audio_edits: list[LtxNativeAudioEdit] = []
    for decision in edl:
        clip = clip_by_row[decision.row_id]
        stem = clip.native_audio_stem
        assert stem is not None
        source_start_sample = _frames_to_samples_exact(
            decision.source_start_frame,
            clip.stream.fps,
            audio_sample_rate,
            field_name=f"{decision.row_id} audio source start",
        )
        source_end_sample = _frames_to_samples_exact(
            decision.source_end_frame_exclusive,
            clip.stream.fps,
            audio_sample_rate,
            field_name=f"{decision.row_id} audio source end",
        )
        output_sample_count = _frames_to_samples_exact(
            decision.output_frame_count,
            target.fps,
            audio_sample_rate,
            field_name=f"{decision.row_id} audio output duration",
        )
        timeline_start_sample = _frames_to_samples_exact(
            decision.timeline_start_frame,
            target.fps,
            audio_sample_rate,
            field_name=f"{decision.row_id} audio timeline start",
        )
        timeline_end_sample = timeline_start_sample + output_sample_count
        transition_overlap_samples = 0
        if audio_edits:
            transition_overlap_samples = max(
                0,
                audio_edits[-1].timeline_end_sample_exclusive
                - timeline_start_sample,
            )
        audio_edits.append(
            LtxNativeAudioEdit(
                row_id=decision.row_id,
                asset=stem.asset,
                sample_rate=stem.sample_rate,
                channels=stem.channels,
                source_start_sample=source_start_sample,
                source_end_sample_exclusive=source_end_sample,
                output_sample_count=output_sample_count,
                timeline_start_sample=timeline_start_sample,
                timeline_end_sample_exclusive=timeline_end_sample,
                timeline_start_frame=decision.timeline_start_frame,
                timeline_end_frame_exclusive=decision.timeline_end_frame_exclusive,
                requires_time_stretch=(
                    source_end_sample - source_start_sample
                    != output_sample_count
                ),
                transition_overlap_samples=transition_overlap_samples,
            )
        )

    total_frames = timeline_cursor_frames
    timeline_end_pts = total_frames * target_frame_duration_pts
    total_audio_samples = _frames_to_samples_exact(
        total_frames,
        target.fps,
        audio_sample_rate,
        field_name="assembled LTX native audio",
    )
    native_audio_strategy = (
        "concat_native_stream_copy"
        if strategy is AssemblyStrategy.CONCAT_STREAM_COPY
        else "controlled_native_audio_remux"
    )
    native_audio_payload = {
        "schema_version": "sineforge.ltx-native-audio-assembly/v1",
        "strategy": native_audio_strategy,
        "sample_rate": audio_sample_rate,
        "channels": audio_channels,
        "total_sample_count": total_audio_samples,
        "edits": [
            {
                "row_id": edit.row_id,
                "asset": _asset_payload(edit.asset),
                "source_start_sample": edit.source_start_sample,
                "source_end_sample_exclusive": edit.source_end_sample_exclusive,
                "output_sample_count": edit.output_sample_count,
                "timeline_start_sample": edit.timeline_start_sample,
                "timeline_end_sample_exclusive": edit.timeline_end_sample_exclusive,
                "requires_time_stretch": edit.requires_time_stretch,
                "transition_overlap_samples": edit.transition_overlap_samples,
            }
            for edit in audio_edits
        ],
    }
    native_audio_manifest_sha256 = _canonical_sha256(native_audio_payload)
    native_audio = LtxNativeAudioAssemblyPlan(
        schema_version="sineforge.ltx-native-audio-assembly/v1",
        strategy=native_audio_strategy,
        sample_rate=audio_sample_rate,
        channels=audio_channels,
        total_sample_count=total_audio_samples,
        manifest_sha256=native_audio_manifest_sha256,
        native_audio_required=True,
        mux_with_video=True,
        edits=tuple(audio_edits),
    )
    manifest_payload = {
        "schema_version": "sineforge.picture-lock-plan/v1",
        "strategy": strategy.value,
        "edl_sha256": edl_sha256,
        "native_audio_manifest_sha256": native_audio.manifest_sha256,
        "target_stream": _stream_payload(target),
        "total_frame_count": total_frames,
        "timeline_start_pts": 0,
        "timeline_end_pts_exclusive": timeline_end_pts,
        "sources": [_asset_payload(clip.asset) for clip in selected],
        "mezzanine_profile_id": mezzanine.profile_id if mezzanine else None,
    }
    manifest_sha256 = _canonical_sha256(manifest_payload)
    picture_lock = PictureLockPlan(
        picture_lock_id=f"picture-lock:{manifest_sha256}",
        edl_sha256=edl_sha256,
        native_audio_manifest_sha256=native_audio.manifest_sha256,
        manifest_sha256=manifest_sha256,
        strategy=strategy,
        target_stream=target,
        total_frame_count=total_frames,
        timeline_start_pts=0,
        timeline_end_pts_exclusive=timeline_end_pts,
        source_asset_ids=tuple(clip.asset.asset_id for clip in selected),
        source_asset_sha256s=tuple(clip.asset.sha256 for clip in selected),
    )
    return AssemblyPlan(
        strategy=strategy,
        target_stream=target,
        edl=edl,
        edl_sha256=edl_sha256,
        concat_assets=tuple(clip.asset for clip in selected),
        mezzanine=mezzanine,
        picture_lock=picture_lock,
        native_audio=native_audio,
    )
