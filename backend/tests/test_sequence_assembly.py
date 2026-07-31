"""Tests for exact, file-based LTX Sequence Sheet assembly planning."""

from __future__ import annotations

from fractions import Fraction

import pytest

from backend.app.services.sequence_sheets.assembly import (
    AssemblyStrategy,
    AssemblyValidationError,
    ClipBoundaryEdit,
    ManagedAssetReference,
    NativeAudioRole,
    NativeAudioStem,
    SelectedClipProbe,
    VideoStreamSignature,
    plan_ltx_av_assembly,
)
from backend.app.services.sequence_sheets.continuity import (
    decide_duplicate_boundary,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _stream(*, width: int = 1280, fps: int = 24) -> VideoStreamSignature:
    return VideoStreamSignature(
        codec_name="h264",
        codec_profile="high",
        codec_level=41,
        width=width,
        height=704,
        pixel_format="yuv420p",
        fps_numerator=fps,
        fps_denominator=1,
        time_base_numerator=1,
        time_base_denominator=24000,
        color_range="tv",
        color_space="bt709",
        color_transfer="bt709",
        color_primaries="bt709",
    )


def _asset(name: str, digest: str) -> ManagedAssetReference:
    return ManagedAssetReference(
        asset_id=f"asset-{name}",
        managed_path=f"projects/project-1/sequence/{name}.mp4",
        sha256=digest,
    )


def _audio_stem(
    row_id: str,
    *,
    stream: VideoStreamSignature,
    frame_count: int,
    digest: str = SHA_C,
) -> NativeAudioStem:
    sample_rate = 48_000
    sample_count = Fraction(frame_count * sample_rate, 1) / stream.fps
    assert sample_count.denominator == 1
    return NativeAudioStem(
        asset=ManagedAssetReference(
            asset_id=f"audio-{row_id}",
            managed_path=f"projects/project-1/sequence/{row_id}-native.wav",
            sha256=digest,
        ),
        role=NativeAudioRole.SYNCHRONIZED_NATIVE,
        sample_rate=sample_rate,
        channels=2,
        sample_count=sample_count.numerator,
        workflow_identity="ltx-i2v-api@sha256:fixture",
        seed=42,
    )


def _clip(
    row_id: str,
    digest: str,
    *,
    stream: VideoStreamSignature | None = None,
    frame_count: int = 193,
    native_audio_stem: NativeAudioStem | None = None,
) -> SelectedClipProbe:
    signature = stream or _stream()
    stem = native_audio_stem or _audio_stem(
        row_id,
        stream=signature,
        frame_count=frame_count,
    )
    return SelectedClipProbe(
        row_id=row_id,
        asset=_asset(row_id, digest),
        stream=signature,
        frame_count=frame_count,
        start_pts=0,
        duration_pts=frame_count * signature.frame_duration_pts,
        native_audio_stem=stem,
    )


def test_identical_stream_signatures_use_concat_stream_copy():
    plan = plan_ltx_av_assembly(
        (_clip("row-1", SHA_A), _clip("row-2", SHA_B))
    )

    assert plan.strategy is AssemblyStrategy.CONCAT_STREAM_COPY
    assert plan.mezzanine is None
    assert plan.concat_assets == (
        _asset("row-1", SHA_A),
        _asset("row-2", SHA_B),
    )
    assert plan.edl[0].timeline_start_frame == 0
    assert plan.edl[0].timeline_end_frame_exclusive == 193
    assert plan.edl[1].timeline_start_frame == 193
    assert plan.edl[1].timeline_end_frame_exclusive == 386
    assert plan.picture_lock.total_frame_count == 386
    assert plan.picture_lock.timeline_end_pts_exclusive == 386_000
    assert plan.picture_lock.duration == Fraction(386, 24)
    assert plan.native_audio.duration == plan.picture_lock.duration
    assert plan.native_audio.strategy == "concat_native_stream_copy"
    assert plan.picture_lock.native_audio_manifest_sha256 == (
        plan.native_audio.manifest_sha256
    )


def test_different_stream_signature_uses_exactly_one_controlled_mezzanine():
    plan = plan_ltx_av_assembly(
        (
            _clip("row-1", SHA_A),
            _clip("row-2", SHA_B, stream=_stream(width=1024)),
        )
    )

    assert plan.strategy is AssemblyStrategy.CONTROLLED_MEZZANINE
    assert plan.mezzanine is not None
    assert plan.mezzanine.profile_id == "sineforge_visual_mezzanine_v1"
    assert plan.mezzanine.source_row_ids == ("row-1", "row-2")
    assert plan.mezzanine.reason_codes == ("stream_mismatch:row-2:width",)
    assert plan.picture_lock.total_frame_count == 386


def test_one_explicit_duplicate_boundary_frame_is_removed_exactly():
    duplicate = decide_duplicate_boundary(
        SHA_C,
        SHA_C,
        remove_exact_duplicate=True,
    )
    plan = plan_ltx_av_assembly(
        (_clip("row-1", SHA_A), _clip("row-2", SHA_B)),
        boundary_edits=(
            ClipBoundaryEdit(
                predecessor_row_id="row-1",
                successor_row_id="row-2",
                decision=duplicate,
            ),
        ),
    )

    assert plan.strategy is AssemblyStrategy.CONTROLLED_MEZZANINE
    assert plan.mezzanine is not None
    assert "frame_exact_boundary_trim" in plan.mezzanine.reason_codes
    assert plan.edl[1].boundary_trim_leading_frames == 1
    assert plan.edl[1].source_start_frame == 1
    assert plan.edl[1].source_start_pts == 1000
    assert plan.edl[1].output_frame_count == 192
    assert plan.picture_lock.total_frame_count == 385
    assert plan.picture_lock.timeline_end_pts_exclusive == 385_000


def test_native_audio_is_required_and_stays_synchronized_with_picture_timing():
    audio_asset = ManagedAssetReference(
        asset_id="audio-row-1",
        managed_path="projects/project-1/sequence/row-1-native.wav",
        sha256=SHA_C,
    )
    stem = NativeAudioStem(
        asset=audio_asset,
        role=NativeAudioRole.SYNCHRONIZED_NATIVE,
        sample_rate=48000,
        channels=2,
        sample_count=386000,
        workflow_identity="ltx-i2v-api@sha256:fixture",
        seed=42,
    )
    plan = plan_ltx_av_assembly(
        (
            _clip("row-1", SHA_A, native_audio_stem=stem),
            _clip("row-2", SHA_B),
        )
    )

    edits = plan.native_audio.edits
    assert plan.native_audio.native_audio_required is True
    assert plan.native_audio.mux_with_video is True
    assert edits[0].asset is stem.asset
    assert edits[0].output_sample_count == 386_000
    assert edits[0].timeline_start_sample == 0
    assert edits[1].timeline_start_sample == 386_000
    assert plan.picture_lock.total_frame_count == 386
    assert plan.native_audio.total_sample_count == 772_000
    assert plan.native_audio.duration == plan.picture_lock.duration


def test_missing_or_mistimed_ltx_native_audio_fails_closed():
    no_audio = SelectedClipProbe(
        row_id="row-no-audio",
        asset=_asset("row-no-audio", SHA_A),
        stream=_stream(),
        frame_count=193,
        start_pts=0,
        duration_pts=193_000,
        native_audio_stem=None,
    )
    with pytest.raises(AssemblyValidationError, match="synchronized native audio"):
        plan_ltx_av_assembly((no_audio,))

    wrong_length = NativeAudioStem(
        asset=ManagedAssetReference(
            asset_id="audio-wrong-length",
            managed_path="projects/project-1/sequence/wrong-length.wav",
            sha256=SHA_C,
        ),
        role=NativeAudioRole.SYNCHRONIZED_NATIVE,
        sample_rate=48_000,
        channels=2,
        sample_count=385_999,
        workflow_identity="ltx-i2v-api@sha256:fixture",
    )
    with pytest.raises(AssemblyValidationError, match="does not match its video"):
        plan_ltx_av_assembly(
            (_clip("row-wrong-length", SHA_A, native_audio_stem=wrong_length),)
        )


def test_unmanaged_paths_and_inexact_probe_durations_fail_closed():
    with pytest.raises(AssemblyValidationError, match="relative POSIX"):
        ManagedAssetReference(
            asset_id="bad",
            managed_path=r"C:\Users\someone\clip.mp4",
            sha256=SHA_A,
        )
    with pytest.raises(AssemblyValidationError, match="inside managed"):
        ManagedAssetReference(
            asset_id="bad",
            managed_path="../outside.mp4",
            sha256=SHA_A,
        )

    with pytest.raises(AssemblyValidationError, match="duration_pts"):
        SelectedClipProbe(
            row_id="row-bad",
            asset=_asset("row-bad", SHA_A),
            stream=_stream(),
            frame_count=193,
            start_pts=0,
            duration_pts=192_000,
        )


def test_boundary_edits_must_be_adjacent_and_clips_must_fully_decode():
    edit = ClipBoundaryEdit(
        predecessor_row_id="row-1",
        successor_row_id="row-3",
        decision=decide_duplicate_boundary(
            SHA_A,
            SHA_A,
            remove_exact_duplicate=True,
        ),
    )
    with pytest.raises(AssemblyValidationError, match="adjacent"):
        plan_ltx_av_assembly(
            (
                _clip("row-1", SHA_A),
                _clip("row-2", SHA_B),
                _clip("row-3", SHA_C),
            ),
            boundary_edits=(edit,),
        )

    bad = SelectedClipProbe(
        row_id="row-bad",
        asset=_asset("row-bad", SHA_A),
        stream=_stream(),
        frame_count=193,
        start_pts=0,
        duration_pts=193_000,
        fully_decodable=False,
    )
    with pytest.raises(AssemblyValidationError, match="full-decode"):
        plan_ltx_av_assembly((bad,))
