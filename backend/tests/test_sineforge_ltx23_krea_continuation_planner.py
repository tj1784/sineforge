from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


BRIDGE_DIR = (
    Path(__file__).resolve().parents[2]
    / "ComfyUI"
    / "sineforge_workflow_bridge"
)
PACKAGE_NAME = "sineforge_continuation_planner_test_package"
PACKAGE = types.ModuleType(PACKAGE_NAME)
PACKAGE.__path__ = [str(BRIDGE_DIR)]
sys.modules[PACKAGE_NAME] = PACKAGE


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


podcast_planner = _load_module(
    f"{PACKAGE_NAME}.podcast_planner",
    BRIDGE_DIR / "podcast_planner.py",
)
planner = _load_module(
    f"{PACKAGE_NAME}.continuation_planner",
    BRIDGE_DIR / "continuation_planner.py",
)


def _request() -> dict:
    return planner._load_contract()["default_request"]


def _valid_result() -> dict[str, str]:
    return {
        "title": "Lantern courtyard continuation",
        "topic": "A quiet courtyard changes from rain to clearing mist",
        "continuity_summary": (
            "Keep the same courtyard, lantern, stone layout, palette, lens, and "
            "night lighting while the rain eases and a thin mist moves through."
        ),
        "krea_prompt": (
            "Create the next pristine cinematic still of the exact same stone "
            "courtyard and brass lantern, preserving composition, materials, "
            "blue night palette, soft lens character, and left-side moonlight; "
            "the rain has just eased and a thin mist enters from the archway."
        ),
        "ltx_prompt": (
            "Use the generated image as the exact first frame. Over eight seconds, "
            "move the mist slowly through the archway, let droplets fall from the "
            "lantern, and use a restrained forward camera drift with quiet rain "
            "ambience, no dialogue, no cut, and no change to the courtyard."
        ),
        "negative_prompt": (
            "new buildings, redesigned lantern, daylight, heavy camera shake"
        ),
    }


def _generate_kwargs() -> dict:
    contract = planner._load_contract()
    return {
        "model": contract["planner_model"],
        "variation_mode": "replay visible seed",
        "seed": 42,
        "topic": "Two men discussing a war update in a podcast studio",
        "next_action": "Continue the conversation by one coherent beat.",
        "dialogue_mode": "speaker fields",
        "speaker_a_name": "Man A",
        "speaker_a_position": "seated camera-left",
        "speaker_a_line": "I think the bigger story is how quickly alliances are shifting.",
        "speaker_b_name": "Man B",
        "speaker_b_position": "seated camera-right",
        "speaker_b_line": "Yeah, and people are reacting before the facts settle.",
        "continuity_mode": "lossless_loop",
        "duration_seconds": 8,
        "visual_constraints_text": "\n".join(
            contract["default_request"]["visual_constraints"]
        ),
        "continuation_request_json": json.dumps(_request()),
        "recent_cycles_json": json.dumps(
            [{"topic": "Rain begins", "continuity_summary": "Same courtyard."}]
        ),
        "temperature": 0.8,
        "top_p": 0.95,
        "max_tokens": 2200,
        "timeout_seconds": 60,
        "image": None,
        "reference_image": None,
    }


def _chat_response(result: dict[str, str] | None = None) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(result if result is not None else {}),
                }
            }
        ]
    }


def test_contract_is_general_strict_and_uses_the_existing_qwen_trust_lock() -> None:
    contract = planner._load_contract()
    podcast_contract = podcast_planner._load_contract()

    assert contract["planner_model"] == podcast_contract["planner_model"]
    assert (
        contract["trusted_lm_studio_model_root"]
        == podcast_contract["trusted_lm_studio_model_root"]
    )
    assert (
        contract["planner_model_selection"]["source"]
        == "recursive_local_gguf_package_discovery"
    )
    assert (
        contract["planner_model_selection"]["default_only"]
        == contract["planner_model"]
    )
    assert contract["request_schema"]["additionalProperties"] is False
    assert set(contract["request_schema"]["required"]) == {
        "project_brief",
        "next_cycle_goal",
        "continuity_mode",
        "dialogue_or_audio_direction",
        "visual_constraints",
        "duration_seconds",
    }
    assert contract["response_schema"]["additionalProperties"] is False
    assert set(contract["response_schema"]["required"]) == {
        "title",
        "topic",
        "continuity_summary",
        "krea_prompt",
        "ltx_prompt",
        "negative_prompt",
    }
    system_text = json.dumps(contract["system_prompt"])
    assert "Krea 2" in system_text
    assert "Never assume the source is a podcast" in system_text


def test_request_validation_is_strict_and_general() -> None:
    request = planner._validate_request(_request())

    assert request["continuity_mode"] == "lossless_loop"
    assert request["duration_seconds"] == 8

    extra = dict(request)
    extra["podcast_speaker"] = "MAN_A"
    with pytest.raises(ValueError, match="unsupported keys"):
        planner._validate_request(extra)

    bad_duration = dict(request)
    bad_duration["duration_seconds"] = 31
    with pytest.raises(ValueError, match="between 2 and 30"):
        planner._validate_request(bad_duration)


def test_visible_dialogue_fields_compose_the_request() -> None:
    request = planner._compose_request_from_widgets(
        continuation_request_json=json.dumps(_request()),
        topic="Two men discussing a breaking news topic in a podcast studio",
        next_action="Continue the conversation without changing seats or identity.",
        speaker_a_name="Alex",
        speaker_a_position="seated camera-left",
        speaker_a_line="I think this is going to affect ordinary people first.",
        speaker_b_name="Marcus",
        speaker_b_position="seated camera-right",
        speaker_b_line="Yeah, I heard the same thing from analysts this morning.",
        dialogue_mode="speaker fields",
        continuity_mode="lossless_loop",
        visual_constraints_text=(
            "Use the supplied image as the visual source of truth.\n"
            "Alex stays camera-left and Marcus stays camera-right."
        ),
        duration_seconds=8,
    )

    assert "breaking news topic" in request["project_brief"]
    assert request["next_cycle_goal"].startswith("Continue the conversation")
    assert request["duration_seconds"] == 8
    assert request["visual_constraints"] == [
        "Use the supplied image as the visual source of truth.",
        "Alex stays camera-left and Marcus stays camera-right.",
    ]
    assert "Alex, seated camera-left, says exactly" in request[
        "dialogue_or_audio_direction"
    ]
    assert "Marcus, seated camera-right, says exactly" in request[
        "dialogue_or_audio_direction"
    ]
    assert "ordinary people first" in request["dialogue_or_audio_direction"]


def test_general_scene_controls_are_primary_and_dialogue_is_optional_json() -> None:
    request = planner._compose_general_request(
        continuation_request_json=json.dumps(_request()),
        scene_or_subject=(
            "A ginger cat sleeping on a blue armchair beside a rainy window."
        ),
        next_event=(
            "The cat wakes, stretches, jumps down, and investigates a paper bag."
        ),
        audio_mode="no dialogue",
        dialogue_json="[]",
        continuity_mode="lossless_loop",
        visual_constraints_text=(
            "Keep the same cat, chair, window, room, lens, and lighting.\n"
            "Do not add people."
        ),
        duration_seconds=8,
    )

    assert "ginger cat" in request["project_brief"]
    assert request["next_cycle_goal"].startswith("The cat wakes")
    assert request["dialogue_or_audio_direction"].startswith("No dialogue")
    assert "podcast" not in json.dumps(request).casefold()

    dialogue = planner._compose_general_request(
        continuation_request_json=json.dumps(_request()),
        scene_or_subject="Two characters sharing a table in an interior scene.",
        next_event="Character A asks a question and Character B answers.",
        audio_mode="dialogue JSON",
        dialogue_json=json.dumps(
            [
                {
                    "speaker": "Character A",
                    "position": "camera-left",
                    "line": "Did you hear the update?",
                },
                {
                    "speaker": "Character B",
                    "position": "camera-right",
                    "line": "Yes, and I want to check the details.",
                    "delivery": "calm and conversational",
                },
            ]
        ),
        continuity_mode="preserve_subjects",
        visual_constraints_text=(
            "Keep both character identities and positions unchanged."
        ),
        duration_seconds=8,
    )
    audio = dialogue["dialogue_or_audio_direction"]
    assert "Character A, camera-left, says exactly" in audio
    assert "Character B, camera-right, says exactly" in audio
    assert "Did you hear the update?" in audio
    assert "Do not add, omit, paraphrase" in audio


def test_loop_count_zero_means_continuous_until_interrupted() -> None:
    node = planner.SineForgeContinuationLoopCount()

    assert node.resolve(0) == (100000,)
    assert node.resolve(1) == (1,)
    assert node.resolve(27) == (27,)
    assert node.VALIDATE_INPUTS(loop_count=-1) != True


def test_model_dropdown_discovers_local_gguf_packages_with_qwen_default() -> None:
    preferred = planner._load_contract()["planner_model"]
    for node_class in (
        planner.SineForgeLTXGeneralContinuationPlanner,
        planner.SineForgeLTXKreaContinuationPlanner,
    ):
        input_types = node_class.INPUT_TYPES()
        choices, options = input_types["required"]["model"]

        assert choices[0] == preferred
        assert options["default"] == preferred
        assert len(choices) > 1
        assert all("mmproj" not in choice.casefold() for choice in choices)


def test_recent_cycles_accepts_empty_arrays_and_jsonl_entries() -> None:
    assert planner._parse_recent_cycles("") == []
    assert planner._parse_recent_cycles("[]") == []
    assert planner._parse_recent_cycles('["old"]\n{"topic":"next"}') == [
        "old",
        {"topic": "next"},
    ]
    with pytest.raises(ValueError, match="unexpected trailing text"):
        planner._parse_recent_cycles('["old"] trailing text')


def test_result_validation_and_seed_derivation_are_deterministic() -> None:
    result = planner._validate_planner_result(_valid_result())

    assert result["krea_prompt"].startswith("Create the next")
    assert result["ltx_prompt"].startswith("Use the generated image")
    assert planner._derived_seed("krea2-image", 42) == planner._derived_seed(
        "krea2-image", 42
    )
    assert planner._derived_seed("krea2-image", 42) != planner._derived_seed(
        "ltx23-video", 42
    )

    extra = _valid_result()
    extra["podcast_dialogue"] = "not part of this contract"
    with pytest.raises(ValueError, match="unsupported keys"):
        planner._validate_planner_result(extra)


def test_generate_releases_comfy_calls_exact_qwen_and_unloads_every_lm_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    model = planner._load_contract()["planner_model"]
    monkeypatch.setattr(
        planner,
        "_resolve_local_model_package",
        lambda requested: {
            "model": requested,
            "root": r"C:\trusted\models",
            "files": [{"relative_path": "model.gguf", "size_bytes": 1}],
            "supports_local_vision_files": True,
        },
    )
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda requested: (
            {"key": requested, "capabilities": {"vision": True}},
            requested,
        ),
    )
    monkeypatch.setattr(
        planner,
        "_release_comfy_models",
        lambda: events.append("release-comfy"),
    )
    monkeypatch.setattr(
        planner,
        "_unload_loaded_lm_studio_models",
        lambda *, except_model=None: events.append(f"preflight:{except_model}"),
    )
    monkeypatch.setattr(
        planner,
        "_http_json",
        lambda *args, **kwargs: (
            events.append(f"chat:{kwargs['payload']['model']}")
            or _chat_response(_valid_result())
        ),
    )
    monkeypatch.setattr(
        planner,
        "_unload_all_lm_studio_models",
        lambda: events.append("unload-all"),
    )

    kwargs = _generate_kwargs()
    output = planner.SineForgeLTXKreaContinuationPlanner().generate(**kwargs)
    record = json.loads(output[0])
    status = json.loads(output[9])
    expected_request = planner._compose_request_from_widgets(
        continuation_request_json=kwargs["continuation_request_json"],
        topic=kwargs["topic"],
        next_action=kwargs["next_action"],
        speaker_a_name=kwargs["speaker_a_name"],
        speaker_a_position=kwargs["speaker_a_position"],
        speaker_a_line=kwargs["speaker_a_line"],
        speaker_b_name=kwargs["speaker_b_name"],
        speaker_b_position=kwargs["speaker_b_position"],
        speaker_b_line=kwargs["speaker_b_line"],
        dialogue_mode=kwargs["dialogue_mode"],
        continuity_mode=kwargs["continuity_mode"],
        visual_constraints_text=kwargs["visual_constraints_text"],
        duration_seconds=kwargs["duration_seconds"],
    )

    assert events == [
        "release-comfy",
        f"preflight:{model}",
        f"chat:{model}",
        "unload-all",
    ]
    assert record["planner"]["endpoint"] == "loopback"
    assert record["planner"]["all_lm_studio_models_unloaded_before_generation"]
    assert record["request"] == expected_request
    assert record["source_image"]["attached"] is False
    assert record["reference_image"]["attached"] is False
    assert "Man A" in record["request"]["dialogue_or_audio_direction"]
    assert "Man B" in record["request"]["dialogue_or_audio_direction"]
    assert record["krea_prompt"] == _valid_result()["krea_prompt"]
    assert record["positive_prompt"] == _valid_result()["ltx_prompt"]
    assert record["planner_response"]["negative_prompt"] == (
        _valid_result()["negative_prompt"]
    )
    assert _valid_result()["negative_prompt"] in record["negative_prompt"]
    assert output[1] == record["krea_prompt"]
    assert output[2] == record["positive_prompt"]
    assert output[4] == 42
    assert output[5] == record["image_seed"]
    assert output[6] == record["video_seed"]
    assert output[7] == 8
    assert status["all_lm_studio_models_unloaded"] is True


def test_generate_failure_still_runs_the_outer_lm_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_calls: list[str] = []
    monkeypatch.setattr(
        planner,
        "_resolve_local_model_package",
        lambda requested: {"model": requested, "root": "trusted", "files": []},
    )
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda requested: ({"key": requested}, requested),
    )
    monkeypatch.setattr(planner, "_release_comfy_models", lambda: None)
    monkeypatch.setattr(
        planner,
        "_unload_loaded_lm_studio_models",
        lambda *, except_model=None: None,
    )
    monkeypatch.setattr(
        planner,
        "_http_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("chat failed")
        ),
    )
    monkeypatch.setattr(
        planner,
        "_unload_all_lm_studio_models",
        lambda: cleanup_calls.append("cleanup"),
    )

    with pytest.raises(RuntimeError, match="chat failed"):
        planner.SineForgeLTXKreaContinuationPlanner().generate(
            **_generate_kwargs()
        )
    assert cleanup_calls == ["cleanup"]


def test_text_only_local_model_omits_images_but_still_plans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    kwargs = _generate_kwargs()
    kwargs["model"] = "local-text-model"
    kwargs["image"] = object()
    kwargs["reference_image"] = object()

    monkeypatch.setattr(
        planner,
        "_resolve_local_model_package",
        lambda requested: {
            "model": requested,
            "root": r"C:\trusted\models",
            "files": [{"relative_path": "text.gguf", "size_bytes": 1}],
            "supports_local_vision_files": False,
        },
    )
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda requested: (
            {"key": requested, "capabilities": {"vision": False}},
            requested,
        ),
    )
    monkeypatch.setattr(planner, "_release_comfy_models", lambda: None)
    monkeypatch.setattr(
        planner,
        "_unload_loaded_lm_studio_models",
        lambda *, except_model=None: None,
    )
    monkeypatch.setattr(planner, "_unload_all_lm_studio_models", lambda: None)
    monkeypatch.setattr(
        planner,
        "_image_data_url",
        lambda image: "data:image/png;base64,abc" if image is not None else None,
    )
    monkeypatch.setattr(
        planner,
        "_image_tensor_sha256",
        lambda image: "hash" if image is not None else None,
    )

    def fake_http(*args, **kwargs):
        captured["payload"] = kwargs["payload"]
        return _chat_response(_valid_result())

    monkeypatch.setattr(planner, "_http_json", fake_http)

    output = planner.SineForgeLTXKreaContinuationPlanner().generate(**kwargs)
    record = json.loads(output[0])
    user_content = captured["payload"]["messages"][1]["content"]

    assert isinstance(user_content, str)
    assert record["source_image"]["attached"] is True
    assert record["reference_image"]["attached"] is True
    assert record["planner"]["planner_images_forwarded"] is False
