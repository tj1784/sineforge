"""Focused contracts for deterministic Agentless scene-reset planning."""

from __future__ import annotations

import copy
import json
from uuid import uuid4

from pydantic import ValidationError
import pytest

from backend.app.schemas.agentless_workflow import (
    AgentlessDryRunRequest,
    AgentlessStageKind,
)
from backend.app.services.agentless_workflow import (
    AgentlessCompilationError,
    compile_agentless_plan,
)


def _scene(
    *,
    scene_id: str = "S001",
    duration_sec: float = 10.0,
    output_prefix: str | None = None,
) -> dict:
    return {
        "scene_id": scene_id,
        "duration_sec": duration_sec,
        "visible_character_ids": ["SARAH", "MARK"],
        "character_reference_asset_ids": {
            "SARAH": ["asset-sarah-front", "asset-sarah-seated"],
            "MARK": ["asset-mark-front", "asset-mark-seated"],
        },
        "flux_reference_assets": {
            "set_studio_asset_ids": ["asset-studio-main"],
            "composition_asset_ids": ["asset-composition-twoshot"],
            "pose_asset_ids": ["asset-pose-seated"],
            "prop_asset_ids": ["asset-prop-microphone"],
        },
        "ingredients_reference_asset_id": "sheet-sarah-mark-v1",
        "character_description_block": (
            "Preserve Sarah and Mark's canonical facial identity, age, hair, "
            "wardrobe, complexion, and accessories from the supplied references."
        ),
        "anchor_prompt": "Sarah and Mark in a broadcast podcast two-shot.",
        "video_prompt": "Sarah turns toward Mark while Mark listens.",
        "negative_prompt": "identity drift, merged faces",
        "image_seed": 318700421,
        "video_seed": 791420508,
        "width": 768,
        "height": 448,
        "ingredients_lora_strength": 1.0,
        "distilled_lora_strength": 0.5,
        "bypass_i2v": False,
        "output_prefix": output_prefix or scene_id,
        "audio_asset_id": "audio-scene-master",
        "anchor_max_attempts": 3,
        "video_max_attempts": 3,
    }


def _payload(
    *,
    duration_sec: float = 10.0,
    scene_count: int = 1,
) -> dict:
    project_id = uuid4()
    return {
        "schema_version": "sineforge.agentless-scene-reset-request/v1",
        "project_id": str(project_id),
        "workflow_templates": {
            "anchor": {
                "template_id": "flux2-multi-reference-anchor",
                "version": "1.0",
                "sha256": "a" * 64,
            },
            "video": {
                "template_id": "ltx23-ingredients-i2v",
                "version": "1.0",
                "sha256": "b" * 64,
            },
        },
        "master_policy": {
            "intermediate_codec": "prores_422_hq",
            "delivery_codec": "h264",
            "delivery_encode_count": 1,
            "intermediate_reencoding_allowed": False,
            "anchor_format": "png",
        },
        "scenes": [
            _scene(
                scene_id=f"S{index + 1:03d}",
                duration_sec=duration_sec,
            )
            for index in range(scene_count)
        ],
    }


def _request(payload: dict) -> AgentlessDryRunRequest:
    return AgentlessDryRunRequest.model_validate_json(json.dumps(payload))


def test_twenty_second_scene_compiles_two_isolated_ten_second_segments() -> None:
    request = _request(_payload(duration_sec=20.0))

    first = compile_agentless_plan(request)
    replay = compile_agentless_plan(request)

    assert first.plan_sha256 == replay.plan_sha256
    assert first.logical_scene_count == 1
    assert first.segment_count == 2
    assert first.batch_size == 1
    assert first.max_active_gpu_jobs == 1
    assert first.previous_clip_dependency_allowed is False
    assert first.previous_frame_dependency_allowed is False
    assert first.submission_enabled is False
    assert first.master_policy.intermediate_codec == "prores_422_hq"
    assert first.master_policy.delivery_codec == "h264"
    assert first.master_policy.delivery_encode_count == 1

    assert [segment.segment_id for segment in first.segments] == [
        "S001-A",
        "S001-B",
    ]
    assert [segment.requested_duration_sec for segment in first.segments] == [
        10.0,
        10.0,
    ]
    assert [segment.frame_count for segment in first.segments] == [241, 241]
    assert [
        segment.playback_duration_sec for segment in first.segments
    ] == pytest.approx([241 / 24, 241 / 24])
    assert first.segments[0].image_seed == request.scenes[0].image_seed
    assert first.segments[0].video_seed == request.scenes[0].video_seed
    assert first.segments[1].image_seed != first.segments[0].image_seed
    assert first.segments[1].video_seed != first.segments[0].video_seed

    for segment in first.segments:
        assert segment.independently_anchored is True
        assert segment.anchor.fresh_anchor is True
        assert segment.anchor.anchor_format == "png"
        assert segment.anchor.previous_clip_asset_id is None
        assert segment.anchor.previous_frame_asset_id is None
        assert segment.anchor.prompt.startswith(
            request.scenes[0].character_description_block
        )
        assert segment.anchor.scene_prompt == request.scenes[0].anchor_prompt
        assert segment.anchor.flux_reference_assets.set_studio_asset_ids == (
            "asset-studio-main",
        )
        assert segment.anchor.flux_reference_assets.composition_asset_ids == (
            "asset-composition-twoshot",
        )
        assert segment.video.first_frame_i2v is True
        assert segment.video.bypass_i2v is False
        assert segment.video.previous_clip_asset_id is None
        assert segment.video.previous_frame_asset_id is None
        assert segment.video.prompt.startswith(
            request.scenes[0].character_description_block
        )
        assert segment.video.scene_prompt == request.scenes[0].video_prompt
        assert segment.video.ingredients_reference_asset_id == (
            "sheet-sarah-mark-v1"
        )
        assert segment.video.batch_size == 1
        assert segment.image_seed != segment.video_seed
    assert [
        segment.video.audio_source_offset_sec for segment in first.segments
    ] == [0.0, 10.0]
    assert [
        segment.video.audio_segment_duration_sec for segment in first.segments
    ] == [10.0, 10.0]

    by_id = {stage.stage_id: stage for stage in first.stages}
    for segment in first.segments:
        segment_stages = [
            stage for stage in first.stages if stage.segment_id == segment.segment_id
        ]
        assert [stage.kind for stage in segment_stages] == [
            AgentlessStageKind.ANCHOR,
            AgentlessStageKind.ANCHOR_QA,
            AgentlessStageKind.VIDEO,
            AgentlessStageKind.VIDEO_QA,
            AgentlessStageKind.MASTER,
        ]
        for stage in segment_stages:
            assert stage.max_attempts <= 3
            for dependency_id in stage.depends_on_stage_ids:
                assert by_id[dependency_id].segment_id == segment.segment_id


@pytest.mark.parametrize(
    ("duration_sec", "segment_durations", "frame_counts"),
    [
        (3.0, [3.0], [73]),
        (3.5, [3.5], [81]),
        (10.0, [10.0], [241]),
        (12.0, [9.0, 3.0], [217, 73]),
        (15.0, [10.0, 5.0], [241, 121]),
    ],
)
def test_compiler_preserves_requested_timing_with_safe_ltx_frames(
    duration_sec: float,
    segment_durations: list[float],
    frame_counts: list[int],
) -> None:
    plan = compile_agentless_plan(
        _request(_payload(duration_sec=duration_sec))
    )

    assert [
        segment.requested_duration_sec for segment in plan.segments
    ] == segment_durations
    assert [segment.frame_count for segment in plan.segments] == frame_counts
    assert all(
        segment.frame_count % 8 == 1 for segment in plan.segments
    )
    assert sum(
        segment.requested_duration_sec for segment in plan.segments
    ) == duration_sec
    for segment in plan.segments:
        assert segment.playback_duration_sec == pytest.approx(
            segment.frame_count / 24
        )
        assert segment.duration_delta_sec == pytest.approx(
            segment.playback_duration_sec
            - segment.requested_duration_sec
        )


def test_unsplit_scene_preserves_scene_and_output_identity() -> None:
    plan = compile_agentless_plan(_request(_payload(duration_sec=8.0)))

    assert plan.segment_count == 1
    segment = plan.segments[0]
    assert segment.segment_id == "S001"
    assert segment.segment_label == "single"
    assert segment.output_prefix == "S001"
    assert segment.anchor.output_prefix == "S001-anchor"
    assert segment.video.audio_source_offset_sec == 0


def test_compiler_rejects_collisions_created_by_segment_suffixes() -> None:
    payload = _payload(duration_sec=20.0, scene_count=2)
    payload["scenes"][1]["duration_sec"] = 8.0
    payload["scenes"][1]["output_prefix"] = "S001-A"

    with pytest.raises(AgentlessCompilationError):
        compile_agentless_plan(_request(payload))

    payload = _payload(duration_sec=20.0, scene_count=2)
    payload["scenes"][1]["duration_sec"] = 8.0
    payload["scenes"][1]["scene_id"] = "S001-A"

    with pytest.raises(AgentlessCompilationError):
        compile_agentless_plan(_request(payload))


def test_manifest_is_strict_and_rejects_unsafe_or_unbounded_inputs() -> None:
    payload = _payload()
    payload["scenes"][0]["ingredients_reference_asset_id"] = (
        "references/sarah.png"
    )
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["scenes"][0]["bypass_i2v"] = True
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["scenes"][0]["anchor_max_attempts"] = 4
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["scenes"][0]["width"] = 1920
    payload["scenes"][0]["height"] = 1080
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["scenes"][0]["unexpected"] = "not allowed"
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["scenes"][0]["scene_id"] = "S" * 97
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["scenes"][0]["output_prefix"] = "S001."
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["master_policy"]["intermediate_codec"] = "h264"
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["master_policy"]["delivery_encode_count"] = 2
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload(scene_count=50)
    extra_scene = copy.deepcopy(payload["scenes"][-1])
    extra_scene["scene_id"] = "S051"
    extra_scene["output_prefix"] = "S051"
    payload["scenes"].append(extra_scene)
    with pytest.raises(ValidationError):
        _request(payload)


def test_scene_requires_separate_seed_channels_and_complete_character_refs() -> None:
    payload = _payload()
    payload["scenes"][0]["video_seed"] = payload["scenes"][0]["image_seed"]
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    del payload["scenes"][0]["character_reference_asset_ids"]["MARK"]
    with pytest.raises(ValidationError):
        _request(payload)


def test_reference_lists_have_per_character_and_conservative_total_caps() -> None:
    payload = _payload()
    payload["scenes"][0]["visible_character_ids"] = ["SARAH"]
    payload["scenes"][0]["character_reference_asset_ids"] = {
        "SARAH": [f"sarah-ref-{index}" for index in range(9)]
    }
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    character_ids = ["SARAH", "MARK", "RIVERA", "GUEST"]
    payload["scenes"][0]["visible_character_ids"] = character_ids
    payload["scenes"][0]["character_reference_asset_ids"] = {
        character_id: [
            f"{character_id.lower()}-ref-{index}" for index in range(7)
        ]
        for character_id in character_ids
    }
    with pytest.raises(ValidationError):
        _request(payload)


def test_flux_reference_categories_are_required_and_bounded() -> None:
    payload = _payload()
    del payload["scenes"][0]["flux_reference_assets"]
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["scenes"][0]["flux_reference_assets"][
        "set_studio_asset_ids"
    ] = []
    with pytest.raises(ValidationError):
        _request(payload)

    payload = _payload()
    payload["scenes"][0]["flux_reference_assets"] = {
        "set_studio_asset_ids": [f"set-{index}" for index in range(4)],
        "composition_asset_ids": [f"composition-{index}" for index in range(4)],
        "pose_asset_ids": [f"pose-{index}" for index in range(4)],
        "prop_asset_ids": [f"prop-{index}" for index in range(5)],
    }
    with pytest.raises(ValidationError):
        _request(payload)
