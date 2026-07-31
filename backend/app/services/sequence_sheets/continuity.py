"""Pure continuity decisions for LTX Sequence Sheet handoffs.

The functions in this module consume probe results supplied by a media adapter.
They never open media, touch the filesystem, or execute extraction tools.  This
keeps tail-frame selection deterministic and makes the QA policy independently
testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
import math
import re
from typing import Iterable


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class ContinuityValidationError(ValueError):
    """Raised when continuity probe evidence is incomplete or inconsistent."""


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ContinuityValidationError(f"{field_name} must not be blank")
    return normalized


def _sha256(value: str, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ContinuityValidationError(
            f"{field_name} must be a SHA-256 hexadecimal digest"
        )
    return normalized


def _unit_interval(value: float, field_name: str) -> float:
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 1:
        raise ContinuityValidationError(
            f"{field_name} must be a finite number between zero and one"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class TailFrameProbe:
    """Metrics for one decoded frame near the end of a selected clip.

    ``sharpness_score`` is deliberately unitless.  The media adapter and the
    policy must use the same versioned metric (for example variance of
    Laplacian); this domain layer only applies the admitted threshold.
    """

    frame_index: int
    pts_numerator: int
    pts_denominator: int
    frame_sha256: str | None
    decode_ok: bool = True
    grossly_malformed: bool = False
    mean_luma: float = 0.5
    blank_fraction: float = 0.0
    sharpness_score: float = 100.0
    frozen: bool = False
    duplicate_run_length: int = 1
    identity_distance: float | None = None
    geography_distance: float | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.frame_index, bool)
            or not isinstance(self.frame_index, int)
            or self.frame_index < 0
        ):
            raise ContinuityValidationError("frame_index must be a non-negative integer")
        if isinstance(self.pts_numerator, bool) or not isinstance(
            self.pts_numerator, int
        ):
            raise ContinuityValidationError("pts_numerator must be an integer")
        if (
            isinstance(self.pts_denominator, bool)
            or not isinstance(self.pts_denominator, int)
            or self.pts_denominator <= 0
        ):
            raise ContinuityValidationError("pts_denominator must be a positive integer")
        for field_name in (
            "decode_ok",
            "grossly_malformed",
            "frozen",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ContinuityValidationError(f"{field_name} must be a boolean")

        if self.frame_sha256 is not None:
            object.__setattr__(
                self,
                "frame_sha256",
                _sha256(self.frame_sha256, "frame_sha256"),
            )

        object.__setattr__(self, "mean_luma", _unit_interval(self.mean_luma, "mean_luma"))
        object.__setattr__(
            self,
            "blank_fraction",
            _unit_interval(self.blank_fraction, "blank_fraction"),
        )
        sharpness = float(self.sharpness_score)
        if not math.isfinite(sharpness) or sharpness < 0:
            raise ContinuityValidationError(
                "sharpness_score must be a non-negative finite number"
            )
        object.__setattr__(self, "sharpness_score", sharpness)

        if (
            isinstance(self.duplicate_run_length, bool)
            or not isinstance(self.duplicate_run_length, int)
            or self.duplicate_run_length < 1
        ):
            raise ContinuityValidationError(
                "duplicate_run_length must be a positive integer"
            )
        for field_name in ("identity_distance", "geography_distance"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _unit_interval(value, field_name))

    @property
    def pts(self) -> Fraction:
        return Fraction(self.pts_numerator, self.pts_denominator)


@dataclass(frozen=True, slots=True)
class TailFramePolicy:
    """Explicit, versioned admission policy for a bounded tail window."""

    policy_id: str = "ltx_tail_frame_qa_v1"
    tail_window_frames: int = 12
    minimum_mean_luma: float = 0.02
    maximum_blank_fraction: float = 0.98
    minimum_sharpness_score: float = 10.0
    maximum_duplicate_run_length: int = 1
    reject_frozen: bool = True
    maximum_identity_distance: float | None = None
    maximum_geography_distance: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _required_text(self.policy_id, "policy_id"))
        if (
            isinstance(self.tail_window_frames, bool)
            or not isinstance(self.tail_window_frames, int)
            or not 1 <= self.tail_window_frames <= 240
        ):
            raise ContinuityValidationError(
                "tail_window_frames must be between 1 and 240"
            )
        object.__setattr__(
            self,
            "minimum_mean_luma",
            _unit_interval(self.minimum_mean_luma, "minimum_mean_luma"),
        )
        object.__setattr__(
            self,
            "maximum_blank_fraction",
            _unit_interval(self.maximum_blank_fraction, "maximum_blank_fraction"),
        )
        sharpness = float(self.minimum_sharpness_score)
        if not math.isfinite(sharpness) or sharpness < 0:
            raise ContinuityValidationError(
                "minimum_sharpness_score must be a non-negative finite number"
            )
        object.__setattr__(self, "minimum_sharpness_score", sharpness)
        if (
            isinstance(self.maximum_duplicate_run_length, bool)
            or not isinstance(self.maximum_duplicate_run_length, int)
            or self.maximum_duplicate_run_length < 1
        ):
            raise ContinuityValidationError(
                "maximum_duplicate_run_length must be a positive integer"
            )
        if not isinstance(self.reject_frozen, bool):
            raise ContinuityValidationError("reject_frozen must be a boolean")
        for field_name in (
            "maximum_identity_distance",
            "maximum_geography_distance",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _unit_interval(value, field_name))


class TailFrameRejectionReason(StrEnum):
    CORRUPT_OR_UNDECODABLE = "corrupt_or_undecodable"
    MISSING_FRAME_HASH = "missing_frame_hash"
    BLACK_OR_NEARLY_BLANK = "black_or_nearly_blank"
    DUPLICATED_BEYOND_POLICY = "duplicated_beyond_policy"
    FROZEN = "frozen"
    SEVERELY_BLURRED = "severely_blurred"
    GROSSLY_MALFORMED = "grossly_malformed"
    IDENTITY_DISCONTINUITY = "identity_discontinuity"
    GEOGRAPHY_DISCONTINUITY = "geography_discontinuity"


@dataclass(frozen=True, slots=True)
class TailFrameEvaluation:
    probe: TailFrameProbe
    accepted: bool
    rejection_reasons: tuple[TailFrameRejectionReason, ...]

    def __post_init__(self) -> None:
        if self.accepted == bool(self.rejection_reasons):
            raise ContinuityValidationError(
                "accepted must be true exactly when rejection_reasons is empty"
            )


class ReanchorAction(StrEnum):
    USE_HANDOFF = "use_handoff"
    USE_APPROVED_CANONICAL_ASSET = "use_approved_canonical_asset"
    OPERATOR_REANCHOR_REQUIRED = "operator_reanchor_required"


@dataclass(frozen=True, slots=True)
class ReanchorDecision:
    action: ReanchorAction
    blocks_successor: bool
    reason: str
    canonical_asset_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.blocks_successor, bool):
            raise ContinuityValidationError("blocks_successor must be a boolean")
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        if self.action is ReanchorAction.USE_APPROVED_CANONICAL_ASSET:
            object.__setattr__(
                self,
                "canonical_asset_id",
                _required_text(self.canonical_asset_id or "", "canonical_asset_id"),
            )
        elif self.canonical_asset_id is not None:
            raise ContinuityValidationError(
                "canonical_asset_id is only valid for an approved canonical re-anchor"
            )
        expected_block = self.action is ReanchorAction.OPERATOR_REANCHOR_REQUIRED
        if self.blocks_successor is not expected_block:
            raise ContinuityValidationError(
                "blocks_successor does not match the re-anchor action"
            )


@dataclass(frozen=True, slots=True)
class TailFrameSelection:
    policy_id: str
    window_start_frame_index: int
    window_end_frame_index: int
    evaluations: tuple[TailFrameEvaluation, ...]
    selected: TailFrameProbe | None

    def __post_init__(self) -> None:
        if not self.evaluations:
            raise ContinuityValidationError("tail-frame selection requires a window")
        accepted = tuple(item.probe for item in self.evaluations if item.accepted)
        if self.selected is None:
            if accepted:
                raise ContinuityValidationError(
                    "selected must contain the latest accepted frame"
                )
        elif not accepted or self.selected != accepted[-1]:
            raise ContinuityValidationError(
                "selected must be the latest accepted frame in the window"
            )


def _evaluate_probe(
    probe: TailFrameProbe,
    policy: TailFramePolicy,
) -> TailFrameEvaluation:
    reasons: list[TailFrameRejectionReason] = []
    if not probe.decode_ok:
        reasons.append(TailFrameRejectionReason.CORRUPT_OR_UNDECODABLE)
    if probe.frame_sha256 is None:
        reasons.append(TailFrameRejectionReason.MISSING_FRAME_HASH)
    if (
        probe.mean_luma <= policy.minimum_mean_luma
        or probe.blank_fraction >= policy.maximum_blank_fraction
    ):
        reasons.append(TailFrameRejectionReason.BLACK_OR_NEARLY_BLANK)
    if probe.duplicate_run_length > policy.maximum_duplicate_run_length:
        reasons.append(TailFrameRejectionReason.DUPLICATED_BEYOND_POLICY)
    if policy.reject_frozen and probe.frozen:
        reasons.append(TailFrameRejectionReason.FROZEN)
    if probe.sharpness_score < policy.minimum_sharpness_score:
        reasons.append(TailFrameRejectionReason.SEVERELY_BLURRED)
    if probe.grossly_malformed:
        reasons.append(TailFrameRejectionReason.GROSSLY_MALFORMED)
    if (
        policy.maximum_identity_distance is not None
        and probe.identity_distance is not None
        and probe.identity_distance > policy.maximum_identity_distance
    ):
        reasons.append(TailFrameRejectionReason.IDENTITY_DISCONTINUITY)
    if (
        policy.maximum_geography_distance is not None
        and probe.geography_distance is not None
        and probe.geography_distance > policy.maximum_geography_distance
    ):
        reasons.append(TailFrameRejectionReason.GEOGRAPHY_DISCONTINUITY)
    return TailFrameEvaluation(
        probe=probe,
        accepted=not reasons,
        rejection_reasons=tuple(reasons),
    )


def select_latest_usable_tail_frame(
    probes: Iterable[TailFrameProbe],
    policy: TailFramePolicy = TailFramePolicy(),
) -> TailFrameSelection:
    """Select the latest acceptable frame from the configured tail window.

    The input may arrive in any order.  Duplicate frame indexes are rejected,
    and frames outside the bounded window are not used as a fallback.
    """

    ordered = tuple(sorted(probes, key=lambda probe: probe.frame_index))
    if not ordered:
        raise ContinuityValidationError("at least one tail-frame probe is required")
    indexes = tuple(probe.frame_index for probe in ordered)
    if len(set(indexes)) != len(indexes):
        raise ContinuityValidationError("tail-frame probe indexes must be unique")
    window = ordered[-policy.tail_window_frames :]
    evaluations = tuple(_evaluate_probe(probe, policy) for probe in window)
    accepted = tuple(item.probe for item in evaluations if item.accepted)
    return TailFrameSelection(
        policy_id=policy.policy_id,
        window_start_frame_index=window[0].frame_index,
        window_end_frame_index=window[-1].frame_index,
        evaluations=evaluations,
        selected=accepted[-1] if accepted else None,
    )


def decide_reanchor(
    selection: TailFrameSelection,
    *,
    force_reanchor: bool = False,
    approved_canonical_asset_id: str | None = None,
) -> ReanchorDecision:
    """Return an explicit successor gate for handoff or canonical re-anchoring."""

    needs_reanchor = force_reanchor or selection.selected is None
    if not needs_reanchor:
        return ReanchorDecision(
            action=ReanchorAction.USE_HANDOFF,
            blocks_successor=False,
            reason="The bounded tail window contains an approved handoff frame.",
        )
    if approved_canonical_asset_id is not None:
        return ReanchorDecision(
            action=ReanchorAction.USE_APPROVED_CANONICAL_ASSET,
            blocks_successor=False,
            reason=(
                "An operator-approved canonical asset replaces the rejected or "
                "explicitly bypassed tail handoff."
            ),
            canonical_asset_id=approved_canonical_asset_id,
        )
    return ReanchorDecision(
        action=ReanchorAction.OPERATOR_REANCHOR_REQUIRED,
        blocks_successor=True,
        reason=(
            "No usable handoff frame is approved; an operator must approve a "
            "canonical anchor before successors can run."
        ),
    )


@dataclass(frozen=True, slots=True)
class DuplicateBoundaryDecision:
    """Evidence and explicit choice for at most one successor-frame trim."""

    predecessor_frame_sha256: str
    successor_opening_frame_sha256: str
    exact_duplicate: bool
    trim_successor_leading_frames: int
    reason: str

    def __post_init__(self) -> None:
        predecessor = _sha256(
            self.predecessor_frame_sha256, "predecessor_frame_sha256"
        )
        successor = _sha256(
            self.successor_opening_frame_sha256,
            "successor_opening_frame_sha256",
        )
        object.__setattr__(self, "predecessor_frame_sha256", predecessor)
        object.__setattr__(self, "successor_opening_frame_sha256", successor)
        if not isinstance(self.exact_duplicate, bool):
            raise ContinuityValidationError("exact_duplicate must be a boolean")
        if self.exact_duplicate != (predecessor == successor):
            raise ContinuityValidationError(
                "exact_duplicate must match the supplied frame hashes"
            )
        if (
            isinstance(self.trim_successor_leading_frames, bool)
            or not isinstance(self.trim_successor_leading_frames, int)
            or self.trim_successor_leading_frames not in (0, 1)
        ):
            raise ContinuityValidationError(
                "trim_successor_leading_frames must be zero or one"
            )
        if self.trim_successor_leading_frames and not self.exact_duplicate:
            raise ContinuityValidationError(
                "a boundary frame may be trimmed only with exact-duplicate evidence"
            )
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))


def decide_duplicate_boundary(
    predecessor_frame_sha256: str,
    successor_opening_frame_sha256: str,
    *,
    remove_exact_duplicate: bool,
) -> DuplicateBoundaryDecision:
    """Record duplicate evidence without silently deleting an opening frame."""

    if not isinstance(remove_exact_duplicate, bool):
        raise ContinuityValidationError("remove_exact_duplicate must be a boolean")
    predecessor = _sha256(
        predecessor_frame_sha256, "predecessor_frame_sha256"
    )
    successor = _sha256(
        successor_opening_frame_sha256, "successor_opening_frame_sha256"
    )
    exact_duplicate = predecessor == successor
    trim = int(exact_duplicate and remove_exact_duplicate)
    if trim:
        reason = (
            "The operator elected to remove one opening frame after an exact "
            "boundary-frame hash match."
        )
    elif exact_duplicate:
        reason = (
            "The boundary frames match exactly, but the explicit edit decision "
            "keeps the successor opening frame."
        )
    else:
        reason = "The boundary frame hashes differ, so no frame is removed."
    return DuplicateBoundaryDecision(
        predecessor_frame_sha256=predecessor,
        successor_opening_frame_sha256=successor,
        exact_duplicate=exact_duplicate,
        trim_successor_leading_frames=trim,
        reason=reason,
    )
