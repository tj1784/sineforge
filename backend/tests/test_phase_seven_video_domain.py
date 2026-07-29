"""Focused tests for the pure Phase 7 video domain."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from backend.app.services.video import (
    ContinuityHandoff,
    DomainValidationError,
    EditDecision,
    EditDecisionList,
    PictureLock,
    ProviderRenderConstraints,
    StitchStage,
    Subscene,
    compile_render_segments,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _wan_constraints() -> ProviderRenderConstraints:
    return ProviderRenderConstraints(
        profile_id="wan-base-quality",
        fps_numerator=16,
        min_frames=1,
        max_frames=81,
        frame_stride=4,
        frame_offset=1,
        duplicate_boundary_frames=1,
    )


def _edl(
    stitch_stage: StitchStage = StitchStage.PHASE7_BEFORE_AUDIO,
) -> EditDecisionList:
    first = EditDecision(
        decision_id="decision-1",
        asset_id="asset-a",
        asset_sha256=SHA_A,
        source_start_frame=0,
        source_end_frame_exclusive=81,
        timeline_start_frame=0,
    )
    second = EditDecision(
        decision_id="decision-2",
        asset_id="asset-b",
        asset_sha256=SHA_B,
        source_start_frame=0,
        source_end_frame_exclusive=81,
        timeline_start_frame=81,
        drop_leading_frames=1,
    )
    return EditDecisionList(
        edl_id="edl-1",
        stitch_stage=stitch_stage,
        fps_numerator=16,
        fps_denominator=1,
        decisions=(first, second),
    )


@pytest.mark.parametrize("duration", [15, 30.5, 90])
def test_editorial_subscene_accepts_preferred_to_maximum_duration(duration):
    subscene = Subscene(subscene_id="subscene-1", duration_sec=duration)

    assert subscene.duration_sec == duration
    assert subscene.short_reason is None
    assert subscene.is_short_exception is False


def test_short_subscene_requires_and_retains_a_reason():
    with pytest.raises(DomainValidationError, match="require short_reason"):
        Subscene(subscene_id="short", duration_sec=14.99)

    short = Subscene(
        subscene_id="short",
        duration_sec=4.5,
        short_reason="  Intentional reaction cut.  ",
    )
    assert short.is_short_exception is True
    assert short.short_reason == "Intentional reaction cut."


@pytest.mark.parametrize("duration", [0, -1, float("inf"), 90.001])
def test_subscene_rejects_invalid_or_overlong_duration(duration):
    with pytest.raises(DomainValidationError):
        Subscene(
            subscene_id="bad",
            duration_sec=duration,
            short_reason="Required for values below 15.",
        )


def test_wan_compiler_turns_15_second_subscene_into_provider_valid_segments():
    plans = compile_render_segments(
        Subscene(subscene_id="scene-a", duration_sec=15),
        _wan_constraints(),
    )

    assert len(plans) == 3
    assert plans[0].timeline_start_sec == 0
    assert plans[-1].timeline_end_sec == 15
    assert [plan.segment_index for plan in plans] == [0, 1, 2]
    assert [plan.frame_count for plan in plans] == [81, 81, 81]
    assert [plan.drop_leading_frames for plan in plans] == [0, 1, 1]
    assert all((plan.frame_count - 1) % 4 == 0 for plan in plans)
    assert sum(plan.effective_frame_count for plan in plans) == 241


def test_wan_compiler_caps_90_second_subscene_without_one_giant_inference():
    constraints = _wan_constraints()
    plans = compile_render_segments(
        Subscene(subscene_id="scene-long", duration_sec=90),
        constraints,
    )

    assert len(plans) == 18
    assert all(plan.frame_count <= constraints.max_frames for plan in plans)
    assert all(plan.provider_profile_id == constraints.profile_id for plan in plans)
    assert plans[-1].timeline_end_sec == 90
    assert sum(plan.requested_duration_sec for plan in plans) == pytest.approx(90)


def test_edl_validates_contiguous_frame_exact_timeline_and_hashes_it():
    edl = _edl()

    assert edl.total_frame_count == 161
    assert edl.duration_sec == pytest.approx(10.0625)
    assert len(edl.sha256) == 64
    assert edl.sha256 == _edl().sha256

    with pytest.raises(DomainValidationError, match="contiguous"):
        EditDecisionList(
            edl_id="gapped",
            stitch_stage=StitchStage.PHASE7_BEFORE_AUDIO,
            fps_numerator=16,
            fps_denominator=1,
            decisions=(
                edl.decisions[0],
                EditDecision(
                    decision_id="decision-gap",
                    asset_id="asset-b",
                    asset_sha256=SHA_B,
                    source_start_frame=0,
                    source_end_frame_exclusive=81,
                    timeline_start_frame=82,
                ),
            ),
        )


def test_edl_supports_both_explicit_stitch_stages():
    assert (
        _edl(StitchStage.PHASE7_BEFORE_AUDIO).stitch_stage.value
        == "phase7_before_audio"
    )
    assert (
        _edl(StitchStage.PHASE8_BEFORE_FOLEY).stitch_stage.value
        == "phase8_before_foley"
    )


def test_continuity_handoff_retains_exact_frame_pts_and_hash_evidence():
    handoff = ContinuityHandoff(
        predecessor_segment_id="segment-1",
        successor_segment_id="segment-2",
        source_asset_id="asset-a",
        source_asset_sha256=SHA_A,
        frame_index=80,
        pts_numerator=5,
        pts_denominator=1,
        frame_sha256=SHA_C,
        extraction_template_version="extract_handoff_frame_v1",
    )

    assert float(handoff.pts) == 5
    assert handoff.frame_index == 80
    with pytest.raises(DomainValidationError, match="must be different"):
        ContinuityHandoff(
            predecessor_segment_id="same",
            successor_segment_id="same",
            source_asset_id="asset-a",
            source_asset_sha256=SHA_A,
            frame_index=0,
            pts_numerator=0,
            pts_denominator=1,
            frame_sha256=SHA_C,
            extraction_template_version="extract_handoff_frame_v1",
        )


def test_picture_lock_is_immutable_and_derived_from_validated_edl():
    edl = _edl(StitchStage.PHASE8_BEFORE_FOLEY)
    lock = PictureLock.from_edl(
        picture_lock_id="lock-1",
        edl=edl,
        final_video_asset_id="final-video",
        final_video_sha256=SHA_C,
        assembly_manifest_sha256=SHA_B,
        width=1280,
        height=704,
        pixel_format="yuv420p",
        locked_at=datetime(2026, 7, 28, tzinfo=UTC),
    )

    assert lock.edl_sha256 == edl.sha256
    assert lock.frame_count == edl.total_frame_count
    assert lock.selected_asset_ids == ("asset-a", "asset-b")
    assert lock.stitch_stage is StitchStage.PHASE8_BEFORE_FOLEY
    assert lock.duration_sec == edl.duration_sec
    with pytest.raises(FrozenInstanceError):
        lock.frame_count = 1


def test_picture_lock_rejects_naive_timestamp_and_invalid_hash():
    with pytest.raises(DomainValidationError, match="SHA-256"):
        PictureLock.from_edl(
            picture_lock_id="lock-1",
            edl=_edl(),
            final_video_asset_id="final-video",
            final_video_sha256="not-a-hash",
            assembly_manifest_sha256=SHA_B,
            width=1280,
            height=704,
            pixel_format="yuv420p",
            locked_at=datetime(2026, 7, 28, tzinfo=UTC),
        )

    with pytest.raises(DomainValidationError, match="timezone-aware"):
        PictureLock.from_edl(
            picture_lock_id="lock-1",
            edl=_edl(),
            final_video_asset_id="final-video",
            final_video_sha256=SHA_C,
            assembly_manifest_sha256=SHA_B,
            width=1280,
            height=704,
            pixel_format="yuv420p",
            locked_at=datetime(2026, 7, 28),
        )
