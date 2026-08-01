from __future__ import annotations

import importlib.util
import json
import math
import sys
import types
from pathlib import Path

import pytest


BRIDGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "ComfyUI"
    / "sineforge_workflow_bridge"
)
PACKAGE_NAME = "sineforge_character_ingredients_test_package"

if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(BRIDGE_PATH)]
    package.__package__ = PACKAGE_NAME
    sys.modules[PACKAGE_NAME] = package

MODULE_PATH = BRIDGE_PATH / "character_ingredients_planner.py"
SPEC = importlib.util.spec_from_file_location(
    f"{PACKAGE_NAME}.character_ingredients_planner",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
planner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = planner
SPEC.loader.exec_module(planner)


def _profile() -> dict:
    return json.loads(
        json.dumps(planner._load_contract()["default_character_profile"])
    )


def _valid_result() -> dict[str, str]:
    identity = (
        "Alex Rowan, approximately 35, has an oval face, balanced cheekbones, "
        "medium brown eyes, short side-parted dark hair, and a warm complexion."
    )
    common = (
        "Photorealistic studio character reference of Alex Rowan, approximately "
        "35 years old, oval face, balanced cheekbones, straight nose, softly "
        "defined jaw, medium brown eyes, natural brows, short dark brown textured "
        "hair with a neat side part, medium warm complexion, charcoal tailored "
        "jacket over a soft blue open-collar shirt, realistic skin and fabric, "
        "even neutral studio lighting, seamless warm-gray background, exactly one "
        "person, no text, no label, no logo, no watermark."
    )
    return {
        "canonical_identity_summary": identity,
        "face_front_prompt": (
            common
            + " Centered eye-level front facial close-up, neutral expression, "
            "both ears and all facial landmarks unobstructed, 85mm portrait lens."
        ),
        "face_three_quarter_prompt": (
            common
            + " Face-and-shoulders left three-quarter view, both eyes visible, "
            "complete hair silhouette, neutral expression, 85mm portrait lens."
        ),
        "profile_prompt": (
            common
            + " Exact clean left-side profile, ear, nose, chin, hairline, and neck "
            "silhouette fully visible, neutral expression, 85mm portrait lens."
        ),
        "body_turnaround_prompt": (
            common
            + " One orderly four-panel full-body turnaround reference board with "
            "exactly front, three-quarter, side, and back standing views, equal "
            "scale, neutral posture, hands visible, plain trousers and dark shoes, "
            "clean separate panels without captions, borders, or measurement marks."
        ),
    }


def _chat_response(result: dict[str, str] | None = None) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        result if result is not None else {},
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }


def _generate_kwargs() -> dict:
    contract = planner._load_contract()
    return {
        "model": contract["planner_model"],
        "variation_mode": "replay visible seed",
        "seed": 42,
        "character_profile_json": json.dumps(_profile()),
        "temperature": 0.55,
        "top_p": 0.9,
        "max_tokens": 2600,
        "timeout_seconds": 60,
        "reference_image": None,
    }


def _patch_local_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        planner,
        "_resolve_local_model_package",
        lambda model: {
            "model": model,
            "root": r"C:\Users\Blokey\.lmstudio\models",
            "publisher": "DavidAU",
            "package": "Local-GGUF",
            "relative_directory": "DavidAU/Local-GGUF",
            "files": [
                {
                    "relative_path": "DavidAU/Local-GGUF/model.gguf",
                    "role": "model",
                    "size_bytes": 100,
                    "modified_time_ns": 1,
                },
                {
                    "relative_path": "DavidAU/Local-GGUF/mmproj-F32.gguf",
                    "role": "vision_projector",
                    "size_bytes": 10,
                    "modified_time_ns": 1,
                },
            ],
            "supports_local_vision_files": True,
        },
    )


def test_contract_is_strict_json_and_copies_exact_podcast_trust_lock() -> None:
    contract = planner._load_contract()
    podcast_contract = planner._load_podcast_contract()

    assert contract["schema_version"].endswith("/v1")
    assert contract["planner_model"].startswith("qwen3.6-40b-")
    assert contract["planner_model"] == podcast_contract["planner_model"]
    assert (
        contract["trusted_lm_studio_model_root"]
        == podcast_contract["trusted_lm_studio_model_root"]
        == r"C:\Users\Blokey\.lmstudio\models"
    )
    assert "trusted_planner_models" not in contract
    for schema_name in ("character_profile_schema", "response_schema"):
        schema = contract[schema_name]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
    assert "JSON object" in contract["system_prompt"]["output_contract"]


def test_node_surface_has_exact_inputs_outputs_and_one_optional_image() -> None:
    inputs = planner.SineForgeKrea2CharacterIngredientsPlanner.INPUT_TYPES()
    required = inputs["required"]
    optional = inputs["optional"]
    contract = planner._load_contract()

    assert set(required) == {
        "model",
        "variation_mode",
        "seed",
        "character_profile_json",
        "temperature",
        "top_p",
        "max_tokens",
        "timeout_seconds",
    }
    assert set(optional) == {"reference_image"}
    assert required["model"][0][0] == contract["planner_model"]
    assert set(required["model"][0]) == set(planner._selectable_model_keys())
    assert planner.SineForgeKrea2CharacterIngredientsPlanner.RETURN_NAMES == (
        "prompt_json",
        "face_front_prompt",
        "face_three_quarter_prompt",
        "profile_prompt",
        "body_turnaround_prompt",
        "image_seed_1",
        "image_seed_2",
        "image_seed_3",
        "image_seed_4",
        "output_prefix",
        "status_json",
    )
    assert len(planner.SineForgeKrea2CharacterIngredientsPlanner.RETURN_TYPES) == 11


def test_local_inventory_exposes_root_packages_and_excludes_mmproj_files() -> None:
    packages = planner._discover_local_model_packages()
    expected_installed_keys = {
        "qwen3-4b-hivemind-instruct-heretic-abliterated-uncensored-neo-imatrix",
        "qwen3.5-2b-uncensored-hauhaucs-aggressive",
        "qwen3.5-4b-uncensored-hauhaucs-aggressive",
        "qwen3.5-9b-the-defiant-fable-uncensored-heretic-neo-imatrix-max-mtp",
        "qwen3.5-9b-uncensored-hauhaucs-aggressive",
        "qwen3.6-27b-fable-fusion-711-uncensored-heretic-nm-dau-neo-max-mtp",
        (
            "qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-"
            "neo-code-di-imatrix-max"
        ),
        "sulphur-2-base",
    }

    assert expected_installed_keys.issubset(packages)
    assert planner._selectable_model_keys()[0] == (
        planner._load_contract()["planner_model"]
    )
    approved_root = Path(r"C:\Users\Blokey\.lmstudio\models").resolve()
    for package in packages.values():
        assert Path(package["root"]).resolve() == approved_root
        assert any(item["role"] == "model" for item in package["files"])
        assert all(
            (
                approved_root / Path(item["relative_path"])
            ).resolve().is_relative_to(approved_root)
            for item in package["files"]
        )


def test_character_profile_is_strict_and_normalized() -> None:
    profile = _profile()
    profile["character_name"] = "  Alex Rowan  "
    validated = planner._validate_character_profile(profile)
    assert validated["character_name"] == "Alex Rowan"

    missing = _profile()
    missing.pop("face_identity")
    with pytest.raises(ValueError, match="is missing: face_identity"):
        planner._validate_character_profile(missing)

    extra = _profile()
    extra["free_form_prompt"] = "not allowed"
    with pytest.raises(ValueError, match="unsupported keys: free_form_prompt"):
        planner._validate_character_profile(extra)

    wrong_type = _profile()
    wrong_type["wardrobe"] = "charcoal jacket"
    with pytest.raises(ValueError, match="wardrobe must be a JSON array"):
        planner._validate_character_profile(wrong_type)


def test_planner_result_rejects_extra_missing_short_and_duplicate_prompts() -> None:
    assert (
        planner._validate_planner_result(_valid_result())["face_front_prompt"]
        == _valid_result()["face_front_prompt"]
    )

    extra = _valid_result()
    extra["negative_prompt"] = "not in contract"
    with pytest.raises(ValueError, match="unsupported keys: negative_prompt"):
        planner._validate_planner_result(extra)

    missing = _valid_result()
    missing.pop("profile_prompt")
    with pytest.raises(ValueError, match="is missing: profile_prompt"):
        planner._validate_planner_result(missing)

    short = _valid_result()
    short["face_front_prompt"] = "too short"
    with pytest.raises(ValueError, match="shorter than"):
        planner._validate_planner_result(short)

    duplicate = _valid_result()
    duplicate["profile_prompt"] = duplicate["face_front_prompt"]
    with pytest.raises(ValueError, match="four different"):
        planner._validate_planner_result(duplicate)


def test_planner_payload_is_json_only_and_orders_four_references() -> None:
    contract = planner._load_contract()
    user_payload = {
        "schema_version": "test/v1",
        "character_profile": _profile(),
    }
    payload = planner._planner_payload(
        model=contract["planner_model"],
        seed=42,
        temperature=0.55,
        top_p=0.9,
        max_tokens=2600,
        user_payload=user_payload,
        reference_image_data_urls=[
            "data:image/jpeg;base64,one",
            "data:image/jpeg;base64,two",
            "data:image/jpeg;base64,three",
            "data:image/jpeg;base64,four",
        ],
    )

    assert json.loads(payload["messages"][0]["content"]) == (
        contract["system_prompt"]
    )
    content = payload["messages"][1]["content"]
    assert isinstance(content, list)
    assert json.loads(content[0]["text"]) == user_payload
    assert [
        item["image_url"]["url"] for item in content[1:]
    ] == [
        "data:image/jpeg;base64,one",
        "data:image/jpeg;base64,two",
        "data:image/jpeg;base64,three",
        "data:image/jpeg;base64,four",
    ]
    assert payload["response_format"] == {"type": "text"}


def test_variation_mode_controls_cache_and_seeds_are_stable_and_distinct() -> None:
    fresh = planner.SineForgeKrea2CharacterIngredientsPlanner.IS_CHANGED(
        variation_mode="new variation every run",
        seed=42,
    )
    assert math.isnan(fresh)

    kwargs = _generate_kwargs()
    replay_one = planner.SineForgeKrea2CharacterIngredientsPlanner.IS_CHANGED(
        **kwargs
    )
    replay_two = planner.SineForgeKrea2CharacterIngredientsPlanner.IS_CHANGED(
        **kwargs
    )
    assert replay_one == replay_two

    seeds = [planner._derive_image_seed(42, index) for index in range(1, 5)]
    assert seeds == [
        planner._derive_image_seed(42, index) for index in range(1, 5)
    ]
    assert len(set(seeds)) == 4
    assert all(0 <= value <= planner.MAX_SEED for value in seeds)


def test_validate_inputs_rejects_nonlocal_model_and_invalid_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = planner._load_contract()
    validation = planner.SineForgeKrea2CharacterIngredientsPlanner.VALIDATE_INPUTS(
        model="some-other-model",
        variation_mode="replay visible seed",
        character_profile_json=json.dumps(_profile()),
    )
    assert "is not an installed GGUF package beneath" in str(validation)

    invalid = _profile()
    invalid["unexpected"] = True
    validation = planner.SineForgeKrea2CharacterIngredientsPlanner.VALIDATE_INPUTS(
        model=contract["planner_model"],
        variation_mode="replay visible seed",
        character_profile_json=json.dumps(invalid),
    )
    assert "unsupported keys: unexpected" in str(validation)

    _patch_local_package(monkeypatch)
    assert (
        planner.SineForgeKrea2CharacterIngredientsPlanner.VALIDATE_INPUTS(
            model=contract["planner_model"],
            variation_mode="replay visible seed",
            character_profile_json=json.dumps(_profile()),
            temperature=0.55,
            top_p=0.9,
            max_tokens=2600,
            timeout_seconds=60,
        )
        is True
    )


def test_generate_uses_exact_model_and_saves_full_json_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    reference = object()
    kwargs = _generate_kwargs()
    kwargs["reference_image"] = reference

    _patch_local_package(monkeypatch)
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda model: (
            {
                "key": model,
                "publisher": "DavidAU",
                "display_name": "Local vision model",
                "architecture": "qwen35",
                "format": "gguf",
                "size_bytes": 100,
                "params_string": "40B",
                "quantization": {"name": "Q4_K_S"},
                "capabilities": {"vision": True},
            },
            model,
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
        "_image_data_url",
        lambda image: (
            None
            if image is None
            else "data:image/jpeg;base64,ref-1"
        ),
    )
    monkeypatch.setattr(
        planner,
        "_image_tensor_sha256",
        lambda image: (
            None if image is None else "sha256-ref-1"
        ),
    )

    captured_payloads: list[dict] = []

    def fake_http(*args, **call_kwargs):
        payload = call_kwargs["payload"]
        captured_payloads.append(payload)
        events.append(f"chat:{payload['model']}")
        return _chat_response(_valid_result())

    monkeypatch.setattr(planner, "_http_json", fake_http)
    monkeypatch.setattr(
        planner,
        "_unload_all_lm_studio_models",
        lambda: events.append("unload-all"),
    )

    output = planner.SineForgeKrea2CharacterIngredientsPlanner().generate(**kwargs)
    record = json.loads(output[0])
    status = json.loads(output[-1])

    assert events == [
        "release-comfy",
        f"preflight:{kwargs['model']}",
        f"chat:{kwargs['model']}",
        "unload-all",
    ]
    assert tuple(output[1:5]) == tuple(
        _valid_result()[field]
        for field in (
            "face_front_prompt",
            "face_three_quarter_prompt",
            "profile_prompt",
            "body_turnaround_prompt",
        )
    )
    assert tuple(output[5:9]) == tuple(
        planner._derive_image_seed(42, index) for index in range(1, 5)
    )
    assert output[9].startswith(
        "SineForge/Krea2_Character_Ingredients/character_001-"
    )
    assert record["planner"]["provider"] == "local_lm_studio"
    assert record["planner"]["requested_model"] == kwargs["model"]
    assert record["planner"]["model"] == kwargs["model"]
    assert record["planner"]["local_package"]["root"] == (
        r"C:\Users\Blokey\.lmstudio\models"
    )
    assert record["planner"]["lm_studio_catalog"]["key"] == kwargs["model"]
    assert record["planner"]["lm_studio_catalog"]["capabilities"]["vision"] is True
    assert record["planner"]["all_lm_studio_models_unloaded_before_krea"] is True
    references_record = record["provenance"]["reference_images"]
    assert [item["tensor_sha256"] for item in references_record] == [
        "sha256-ref-1"
    ]
    assert all(item["attached"] for item in references_record)
    assert len(record["provenance"]["contract_sha256"]) == 64
    assert len(record["provenance"]["character_profile_sha256"]) == 64
    assert len(record["provenance"]["planner_request_sha256"]) == 64
    assert len(record["prompt_sha256"]) == 64
    assert record["prompt_sources"]["system_json"] == (
        planner._load_contract()["system_prompt"]
    )
    assert record["prompt_sources"]["user_json"]["character_profile"] == _profile()
    assert record["prompt_sources"]["response_schema_json"] == (
        planner._load_contract()["response_schema"]
    )
    user_message = captured_payloads[0]["messages"][1]["content"]
    assert isinstance(user_message, list)
    assert len(user_message) == 2
    assert status["attached_reference_count"] == 1
    assert status["all_lm_studio_models_unloaded"] is True


def test_generate_retries_invalid_json_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[dict] = []
    responses = iter([_chat_response(), _chat_response(_valid_result())])
    _patch_local_package(monkeypatch)
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda model: ({"key": model, "capabilities": {"vision": True}}, model),
    )
    monkeypatch.setattr(planner, "_release_comfy_models", lambda: None)
    monkeypatch.setattr(
        planner,
        "_unload_loaded_lm_studio_models",
        lambda *, except_model=None: None,
    )
    monkeypatch.setattr(planner, "_image_data_url", lambda image: None)
    monkeypatch.setattr(planner, "_image_tensor_sha256", lambda image: None)

    def fake_http(*args, **kwargs):
        payloads.append(kwargs["payload"])
        return next(responses)

    monkeypatch.setattr(planner, "_http_json", fake_http)
    monkeypatch.setattr(planner, "_unload_all_lm_studio_models", lambda: None)

    output = planner.SineForgeKrea2CharacterIngredientsPlanner().generate(
        **_generate_kwargs()
    )
    record = json.loads(output[0])

    assert len(payloads) == 2
    repaired_content = payloads[1]["messages"][1]["content"]
    repaired_request = json.loads(repaired_content)
    assert repaired_request["repair"]["attempt"] == 2
    assert repaired_request["repair"]["validation_errors"]
    assert [attempt["valid"] for attempt in record["planner"]["attempts"]] == [
        False,
        True,
    ]


def test_nonvision_local_model_omits_images_but_preserves_reference_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = object()
    kwargs = _generate_kwargs()
    kwargs["model"] = "local-text-only-model"
    kwargs["reference_image"] = reference
    _patch_local_package(monkeypatch)
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda model: (
            {
                "key": model,
                "publisher": "Local",
                "display_name": "Text-only local model",
                "architecture": "qwen3",
                "format": "gguf",
                "capabilities": {"vision": False},
            },
            model,
        ),
    )
    monkeypatch.setattr(planner, "_release_comfy_models", lambda: None)
    monkeypatch.setattr(
        planner,
        "_unload_loaded_lm_studio_models",
        lambda *, except_model=None: None,
    )
    monkeypatch.setattr(
        planner,
        "_image_data_url",
        lambda image: (
            None if image is None else "data:image/jpeg;base64,reference"
        ),
    )
    monkeypatch.setattr(
        planner,
        "_image_tensor_sha256",
        lambda image: None if image is None else "reference-sha256",
    )
    payloads: list[dict] = []

    def fake_http(*args, **call_kwargs):
        payloads.append(call_kwargs["payload"])
        return _chat_response(_valid_result())

    monkeypatch.setattr(planner, "_http_json", fake_http)
    monkeypatch.setattr(planner, "_unload_all_lm_studio_models", lambda: None)

    output = planner.SineForgeKrea2CharacterIngredientsPlanner().generate(**kwargs)
    record = json.loads(output[0])

    assert isinstance(payloads[0]["messages"][1]["content"], str)
    delivery = record["provenance"]["reference_delivery"]
    assert delivery == {
        "selected_model_advertises_vision": False,
        "attached_reference_count": 1,
        "sent_to_planner_count": 0,
        "omitted_from_planner_count": 1,
        "omission_reason": "selected_local_model_does_not_advertise_vision",
    }
    reference_record = record["provenance"]["reference_images"][0]
    assert reference_record["attached"] is True
    assert reference_record["tensor_sha256"] == "reference-sha256"
    assert reference_record["sent_to_planner"] is False
    assert (
        record["planner"]["lm_studio_catalog"]["capabilities"]["vision"]
        is False
    )


@pytest.mark.parametrize("failure_stage", ["preflight", "chat"])
def test_generate_failure_always_unloads_every_lm_model(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    cleanup_calls: list[str] = []
    _patch_local_package(monkeypatch)
    monkeypatch.setattr(
        planner,
        "_resolve_model_entry",
        lambda model: ({"key": model, "capabilities": {"vision": True}}, model),
    )
    monkeypatch.setattr(planner, "_release_comfy_models", lambda: None)
    monkeypatch.setattr(planner, "_image_data_url", lambda image: None)
    monkeypatch.setattr(planner, "_image_tensor_sha256", lambda image: None)
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
        planner.SineForgeKrea2CharacterIngredientsPlanner().generate(
            **_generate_kwargs()
        )
    assert cleanup_calls == ["cleanup"]
