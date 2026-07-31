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
        "continuation_request_json": json.dumps(_request()),
        "recent_cycles_json": json.dumps(
            [{"topic": "Rain begins", "continuity_summary": "Same courtyard."}]
        ),
        "temperature": 0.8,
        "top_p": 0.95,
        "max_tokens": 2200,
        "timeout_seconds": 60,
        "image": None,
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
        contract["trusted_planner_models"]
        == podcast_contract["trusted_planner_models"]
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
        "_validate_trusted_model_package",
        lambda requested: {
            "model": requested,
            "root": r"C:\trusted\models",
            "files": [{"relative_path": "model.gguf", "size_bytes": 1}],
        },
    )
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda requested: ({"key": requested}, requested),
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

    output = planner.SineForgeLTXKreaContinuationPlanner().generate(
        **_generate_kwargs()
    )
    record = json.loads(output[0])
    status = json.loads(output[9])

    assert events == [
        "release-comfy",
        f"preflight:{model}",
        f"chat:{model}",
        "unload-all",
    ]
    assert record["planner"]["endpoint"] == "loopback"
    assert record["planner"]["all_lm_studio_models_unloaded_before_generation"]
    assert record["request"] == _request()
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
        "_validate_trusted_model_package",
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
