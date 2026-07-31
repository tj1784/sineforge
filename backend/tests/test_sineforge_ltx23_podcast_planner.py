from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "ComfyUI"
    / "sineforge_workflow_bridge"
    / "podcast_planner.py"
)
GEOPOLITICS_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "Workflows"
    / "LTX23"
    / "SineForge_LTX23_Podcast_Geopolitics_To_Everyday.prompt.json"
)
SPEC = importlib.util.spec_from_file_location(
    "sineforge_podcast_planner_test_module",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


def _request() -> dict:
    return planner._load_contract()["default_request"]


def _valid_result() -> dict[str, str]:
    return {
        "variation_title": "Shipping lanes to bread starters",
        "primary_topic": "changing shipping routes",
        "pivot_topic": "maintaining a sourdough starter",
        "factuality_mode": "fictional_opinion_dialogue",
        "visual_style": "natural cinematic broadcast realism",
        "setting_description": "A quiet premium podcast studio",
        "camera_motion": "a restrained slow push in",
        "man_a_dialogue": "Routes may reshape trade sooner.",
        "man_a_action": "leans slightly toward his microphone",
        "man_b_dialogue": "Insurance could slow that shift.",
        "man_b_action": "answers with one small hand gesture",
        "pivot_dialogue": "Anyway, how is your starter?",
        "pivot_action": "smiles and relaxes his shoulders",
        "ambient_audio": "quiet treated studio room tone",
        "negative_prompt": "harsh flicker, exaggerated gestures",
    }


def _generate_kwargs() -> dict:
    return {
        "model": "requested-qwen",
        "variation_mode": "replay visible seed",
        "seed": 42,
        "topic_request_json": planner._canonical_json(_request()),
        "recent_topics_json": '["old topic"]',
        "temperature": 0.9,
        "top_p": 0.95,
        "max_tokens": 1600,
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


def _patch_trusted_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        planner,
        "_validate_trusted_model_package",
        lambda model: {
            "model": model,
            "root": r"C:\trusted\models",
            "files": [{"relative_path": "model.gguf", "size_bytes": 1}],
        },
    )


def test_prompt_contract_is_strict_json_and_uses_requested_qwen_model() -> None:
    contract = planner._load_contract()

    assert contract["schema_version"].endswith("/v1")
    assert contract["planner_model"].startswith("qwen3.6-40b-")
    assert contract["trusted_lm_studio_model_root"] == (
        r"C:\Users\Blokey\.lmstudio\models"
    )
    assert contract["planner_model"] in contract["trusted_planner_models"]
    assert contract["response_schema"]["additionalProperties"] is False
    assert set(contract["response_schema"]["required"]) == set(
        contract["response_schema"]["properties"]
    )
    assert contract["default_request"]["duration_seconds"] == 8


def test_geopolitics_example_is_json_and_requires_fictional_opinion() -> None:
    request = json.loads(GEOPOLITICS_EXAMPLE_PATH.read_text(encoding="utf-8"))

    assert request["schema_version"].endswith("/v1")
    assert "Iran" in request["primary_topic_brief"]
    assert "Russia" in request["primary_topic_brief"]
    assert "unrelated" in request["pivot_topic_brief"]
    assert "fictional opinion" in request["factuality_policy"]
    assert request["source_notes"] == []


def test_validated_result_builds_timed_prompt_with_exact_dialogue() -> None:
    request = _request()
    result = planner._validate_planner_result(
        _valid_result(),
        request=request,
    )

    positive = planner._build_positive_prompt(
        result,
        request=request,
        duration=8,
    )

    assert "MAN_A at camera-left" in positive
    assert "MAN_B at camera-right" in positive
    assert '"Routes may reshape trade sooner."' in positive
    assert '"Insurance could slow that shift."' in positive
    assert '"Anyway, how is your starter?"' in positive
    assert "one continuous shot" in positive
    assert "no overlapping speech" in positive


def test_planner_rejects_duplicate_topics_and_overlong_dialogue() -> None:
    duplicate = _valid_result()
    duplicate["pivot_topic"] = duplicate["primary_topic"]
    with pytest.raises(ValueError, match="must be different"):
        planner._validate_planner_result(duplicate, request=_request())

    overlong = _valid_result()
    overlong["man_a_dialogue"] = (
        "one two three four five six seven"
    )
    with pytest.raises(ValueError, match="max_words_per_line"):
        planner._validate_planner_result(overlong, request=_request())


def test_planner_enforces_schema_lengths_and_source_bound_notes() -> None:
    too_short = _valid_result()
    too_short["visual_style"] = "x"
    with pytest.raises(ValueError, match="shorter than"):
        planner._validate_planner_result(too_short, request=_request())

    source_bound = _valid_result()
    source_bound["factuality_mode"] = "source_bound"
    with pytest.raises(ValueError, match="source_bound requires"):
        planner._validate_planner_result(source_bound, request=_request())

    request = _request()
    request["source_notes"] = ["Approved production note."]
    assert planner._validate_planner_result(
        source_bound,
        request=request,
    )["factuality_mode"] == "source_bound"


def test_recent_topics_accepts_array_jsonl_and_rejects_trailing_text() -> None:
    assert planner._parse_json_list("", label="recent_topics_json") == []
    assert planner._parse_json_list(
        '["one"]\n["two", "three"]\n{"topic": "four"}',
        label="recent_topics_json",
    ) == ["one", "two", "three", {"topic": "four"}]

    with pytest.raises(ValueError, match="recent_topics_json must be valid JSON"):
        planner._parse_json_list(
            '["one"]\nnot-json',
            label="recent_topics_json",
        )


def test_variation_mode_controls_cache_identity() -> None:
    fresh = planner.SineForgeLTXPodcastPlanner.IS_CHANGED(
        variation_mode="new variation every run",
        seed=42,
    )
    assert math.isnan(fresh)

    replay_one = planner.SineForgeLTXPodcastPlanner.IS_CHANGED(
        variation_mode="replay visible seed",
        seed=42,
        model="qwen",
        topic_request_json="{}",
        recent_topics_json="[]",
        temperature=0.9,
        top_p=0.95,
        max_tokens=1600,
    )
    replay_two = planner.SineForgeLTXPodcastPlanner.IS_CHANGED(
        variation_mode="replay visible seed",
        seed=42,
        model="qwen",
        topic_request_json="{}",
        recent_topics_json="[]",
        temperature=0.9,
        top_p=0.95,
        max_tokens=1600,
    )
    assert replay_one == replay_two


def test_duration_and_speaker_assignment_fail_closed() -> None:
    request = _request()
    request["duration_seconds"] = 20
    with pytest.raises(ValueError, match="between 6 and 12"):
        planner._duration_seconds(request)

    request = _request()
    request["speaker_assignment"] = {
        "MAN_A": "camera-left",
        "MAN_B": "camera-left",
    }
    validation = planner.SineForgeLTXPodcastPlanner.VALIDATE_INPUTS(
        model="qwen",
        variation_mode="new variation every run",
        topic_request_json=planner._canonical_json(request),
        recent_topics_json="[]",
    )
    assert validation == (
        "speaker_assignment must give MAN_A and MAN_B different positions."
    )


def test_generate_resolves_exact_model_and_cleans_all_lm_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _patch_trusted_package(monkeypatch)
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda model: ({"key": "resolved-qwen"}, "resolved-qwen"),
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

    output = planner.SineForgeLTXPodcastPlanner().generate(**_generate_kwargs())
    record = json.loads(output[0])

    assert events == [
        "release-comfy",
        "preflight:resolved-qwen",
        "chat:resolved-qwen",
        "unload-all",
    ]
    assert record["planner"]["requested_model"] == "requested-qwen"
    assert record["planner"]["model"] == "resolved-qwen"
    assert record["planner"]["all_lm_studio_models_unloaded_before_ltx"] is True
    assert record["request"] == _request()
    assert record["recent_topics"] == ["old topic"]
    assert record["source_image"] == {
        "attached": False,
        "tensor_sha256": None,
    }


def test_generate_retries_invalid_json_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[dict] = []
    responses = iter([_chat_response(), _chat_response(_valid_result())])
    _patch_trusted_package(monkeypatch)
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda model: ({"key": model}, model),
    )
    monkeypatch.setattr(planner, "_release_comfy_models", lambda: None)
    monkeypatch.setattr(
        planner,
        "_unload_loaded_lm_studio_models",
        lambda *, except_model=None: None,
    )

    def fake_http(*args, **kwargs):
        payloads.append(kwargs["payload"])
        return next(responses)

    monkeypatch.setattr(planner, "_http_json", fake_http)
    monkeypatch.setattr(planner, "_unload_all_lm_studio_models", lambda: None)

    output = planner.SineForgeLTXPodcastPlanner().generate(**_generate_kwargs())

    assert json.loads(output[0])["primary_topic"] == (
        _valid_result()["primary_topic"]
    )
    assert len(payloads) == 2
    repaired_request = json.loads(payloads[1]["messages"][1]["content"])
    assert repaired_request["repair"]["attempt"] == 2
    assert repaired_request["repair"]["validation_errors"]


@pytest.mark.parametrize("failure_stage", ["chat", "preflight"])
def test_generate_failure_still_cleans_all_lm_models(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    cleanup_calls: list[str] = []
    _patch_trusted_package(monkeypatch)
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda model: ({"key": model}, model),
    )
    monkeypatch.setattr(planner, "_release_comfy_models", lambda: None)

    if failure_stage == "preflight":
        monkeypatch.setattr(
            planner,
            "_unload_loaded_lm_studio_models",
            lambda *, except_model=None: (_ for _ in ()).throw(
                RuntimeError("preflight failed")
            ),
        )
    else:
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

    with pytest.raises(RuntimeError, match=f"{failure_stage} failed"):
        planner.SineForgeLTXPodcastPlanner().generate(**_generate_kwargs())
    assert cleanup_calls == ["cleanup"]


def test_generate_fails_closed_for_unknown_model_or_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_calls: list[str] = []
    _patch_trusted_package(monkeypatch)
    monkeypatch.setattr(planner, "_model_entries", lambda: [])
    monkeypatch.setattr(
        planner,
        "_unload_all_lm_studio_models",
        lambda: cleanup_calls.append("unknown-model-cleanup"),
    )

    with pytest.raises(RuntimeError, match="exact requested model key"):
        planner.SineForgeLTXPodcastPlanner().generate(**_generate_kwargs())
    assert cleanup_calls == ["unknown-model-cleanup"]

    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda model: ({"key": model}, model),
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
        lambda *args, **kwargs: _chat_response(_valid_result()),
    )
    monkeypatch.setattr(
        planner,
        "_unload_all_lm_studio_models",
        lambda: (_ for _ in ()).throw(RuntimeError("still loaded")),
    )

    with pytest.raises(RuntimeError, match="cleanup failed.*still loaded"):
        planner.SineForgeLTXPodcastPlanner().generate(**_generate_kwargs())


def test_validate_inputs_rejects_untrusted_planner_model() -> None:
    validation = planner.SineForgeLTXPodcastPlanner.VALIDATE_INPUTS(
        model="some-model-outside-the-trust-contract",
        variation_mode="new variation every run",
        topic_request_json=planner._canonical_json(_request()),
        recent_topics_json="[]",
    )

    assert validation == (
        "Planner model 'some-model-outside-the-trust-contract' is not approved "
        "by the JSON trust contract."
    )
