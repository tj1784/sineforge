"""Tests for pure LTX Sequence Sheet continuity decisions."""

from __future__ import annotations

from fractions import Fraction

import pytest

from backend.app.services.sequence_sheets.continuity import (
    ContinuityValidationError,
    ReanchorAction,
    TailFramePolicy,
    TailFrameProbe,
    TailFrameRejectionReason,
    decide_duplicate_boundary,
    decide_reanchor,
    select_latest_usable_tail_frame,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _probe(
    frame_index: int,
    *,
    frame_sha256: str | None = SHA_A,
    **overrides,
) -> TailFrameProbe:
    values = {
        "frame_index": frame_index,
        "pts_numerator": frame_index,
        "pts_denominator": 24,
        "frame_sha256": frame_sha256,
    }
    values.update(overrides)
    return TailFrameProbe(**values)


def test_latest_usable_frame_is_selected_deterministically():
    probes = (
        _probe(99, mean_luma=0.0, frame_sha256=SHA_C),
        _probe(97, frame_sha256=SHA_A),
        _probe(98, sharpness_score=2.0, frame_sha256=SHA_B),
    )

    selection = select_latest_usable_tail_frame(
        probes,
        TailFramePolicy(tail_window_frames=3, minimum_sharpness_score=10),
    )

    assert [item.probe.frame_index for item in selection.evaluations] == [97, 98, 99]
    assert selection.selected is not None
    assert selection.selected.frame_index == 97
    assert selection.selected.pts == Fraction(97, 24)
    assert selection.selected.frame_sha256 == SHA_A
    assert selection.evaluations[1].rejection_reasons == (
        TailFrameRejectionReason.SEVERELY_BLURRED,
    )
    assert selection.evaluations[2].rejection_reasons == (
        TailFrameRejectionReason.BLACK_OR_NEARLY_BLANK,
    )


def test_all_rejected_frames_require_an_operator_reanchor():
    selection = select_latest_usable_tail_frame(
        (
            _probe(10, decode_ok=False, frame_sha256=None),
            _probe(11, frozen=True),
            _probe(12, duplicate_run_length=3),
        ),
        TailFramePolicy(tail_window_frames=3),
    )

    assert selection.selected is None
    assert TailFrameRejectionReason.CORRUPT_OR_UNDECODABLE in (
        selection.evaluations[0].rejection_reasons
    )
    assert TailFrameRejectionReason.MISSING_FRAME_HASH in (
        selection.evaluations[0].rejection_reasons
    )
    decision = decide_reanchor(selection)
    assert decision.action is ReanchorAction.OPERATOR_REANCHOR_REQUIRED
    assert decision.blocks_successor is True

    resolved = decide_reanchor(
        selection,
        approved_canonical_asset_id="canonical-character-anchor",
    )
    assert resolved.action is ReanchorAction.USE_APPROVED_CANONICAL_ASSET
    assert resolved.canonical_asset_id == "canonical-character-anchor"
    assert resolved.blocks_successor is False


def test_tail_window_is_a_hard_bound_and_does_not_fall_back_farther():
    probes = [_probe(index) for index in range(17)]
    probes.extend(
        [
            _probe(17, frozen=True),
            _probe(18, sharpness_score=0),
            _probe(19, mean_luma=0),
        ]
    )

    selection = select_latest_usable_tail_frame(
        probes,
        TailFramePolicy(tail_window_frames=3),
    )

    assert selection.window_start_frame_index == 17
    assert selection.window_end_frame_index == 19
    assert len(selection.evaluations) == 3
    assert selection.selected is None


def test_probe_reasons_preserve_every_explicit_policy_failure():
    selection = select_latest_usable_tail_frame(
        (
            _probe(
                8,
                grossly_malformed=True,
                blank_fraction=0.99,
                sharpness_score=1,
                frozen=True,
                duplicate_run_length=4,
                identity_distance=0.9,
                geography_distance=0.8,
            ),
        ),
        TailFramePolicy(
            maximum_identity_distance=0.2,
            maximum_geography_distance=0.3,
        ),
    )

    assert selection.evaluations[0].rejection_reasons == (
        TailFrameRejectionReason.BLACK_OR_NEARLY_BLANK,
        TailFrameRejectionReason.DUPLICATED_BEYOND_POLICY,
        TailFrameRejectionReason.FROZEN,
        TailFrameRejectionReason.SEVERELY_BLURRED,
        TailFrameRejectionReason.GROSSLY_MALFORMED,
        TailFrameRejectionReason.IDENTITY_DISCONTINUITY,
        TailFrameRejectionReason.GEOGRAPHY_DISCONTINUITY,
    )


def test_duplicate_boundary_trim_requires_exact_hash_and_explicit_choice():
    remove = decide_duplicate_boundary(
        SHA_A,
        SHA_A.upper(),
        remove_exact_duplicate=True,
    )
    assert remove.exact_duplicate is True
    assert remove.trim_successor_leading_frames == 1

    keep = decide_duplicate_boundary(
        SHA_A,
        SHA_A,
        remove_exact_duplicate=False,
    )
    assert keep.exact_duplicate is True
    assert keep.trim_successor_leading_frames == 0

    mismatch = decide_duplicate_boundary(
        SHA_A,
        SHA_B,
        remove_exact_duplicate=True,
    )
    assert mismatch.exact_duplicate is False
    assert mismatch.trim_successor_leading_frames == 0


def test_invalid_policy_and_duplicate_probe_indexes_fail_closed():
    with pytest.raises(ContinuityValidationError, match="between 1 and 240"):
        TailFramePolicy(tail_window_frames=241)

    with pytest.raises(ContinuityValidationError, match="indexes must be unique"):
        select_latest_usable_tail_frame((_probe(1), _probe(1)))
