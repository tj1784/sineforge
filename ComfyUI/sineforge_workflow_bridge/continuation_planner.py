"""Local-only selectable-model planner for Krea 2 -> LTX-2.3 continuations.

This node deliberately shares the bridge's local-model and GPU-ownership
helpers. It accepts no endpoint or credential, calls only loopback LM Studio,
releases ComfyUI models before planning, and returns prompts only after every
LM Studio model instance has been confirmed unloaded.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path
from typing import Any

from .character_ingredients_planner import (
    _resolve_local_model_package,
    _selectable_model_keys,
)
from .podcast_planner import (
    LM_STUDIO_OPENAI_BASE,
    VARIATION_MODES,
    _canonical_json,
    _chat_content,
    _ensure_lm_studio_model_loaded,
    _http_json,
    _image_data_url,
    _image_tensor_sha256,
    _load_contract as _load_podcast_contract,
    _release_comfy_models,
    _resolve_model_entry,
    _safe_output_text,
    _unload_all_lm_studio_models,
    _unload_loaded_lm_studio_models,
)


CONTRACT_PATH = Path(__file__).with_name(
    "ltx23_krea_continuation_prompt_contract.json"
)
MAX_RECENT_CYCLES = 50
AUDIO_MODES = (
    "automatic from scene",
    "no dialogue",
    "dialogue JSON",
    "advanced JSON only",
)
CONTINUOUS_LOOP_INTERNAL_TOTAL = 100_000


def _load_contract() -> dict[str, Any]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"SineForge Krea continuation prompt contract is invalid: {exc}"
        ) from exc
    required = {
        "schema_version",
        "planner_model",
        "trusted_lm_studio_model_root",
        "planner_model_selection",
        "preferred_planner_model_package",
        "system_prompt",
        "default_request",
        "request_schema",
        "response_schema",
        "fixed_negative_prompt",
    }
    missing = sorted(required.difference(contract))
    if missing:
        raise RuntimeError(
            "SineForge Krea continuation prompt contract is missing: "
            + ", ".join(missing)
        )

    # The shared contract remains the source of the preferred default and local
    # model root. Other installed GGUF packages are discovered dynamically
    # beneath that same root.
    trust_contract = _load_podcast_contract()
    trust_keys = (
        "planner_model",
        "trusted_lm_studio_model_root",
    )
    mismatches = [
        key
        for key in trust_keys
        if _canonical_json(contract.get(key))
        != _canonical_json(trust_contract.get(key))
    ]
    if mismatches:
        raise RuntimeError(
            "Krea continuation local-model policy differs from the shared "
            "default/root policy for: " + ", ".join(mismatches)
        )
    return contract


def _parse_json_object(raw: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or ""))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object.")
    return value


def _parse_json_values(raw: str, *, label: str) -> list[Any]:
    text = str(raw or "").strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    values: list[Any] = []
    cursor = 0
    while cursor < len(text):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text):
            break
        try:
            value, cursor = decoder.raw_decode(text, cursor)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} must be valid JSON: {exc.msg}") from exc
        values.append(value)
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] not in "[{\"":
            raise ValueError(f"{label} must be valid JSON: unexpected trailing text")
    return values


def _parse_recent_cycles(raw: str) -> list[Any]:
    values = _parse_json_values(raw, label="recent_cycles_json")
    cycles: list[Any] = []
    for value in values:
        if isinstance(value, list):
            cycles.extend(value)
        elif isinstance(value, (dict, str)):
            cycles.append(value)
        else:
            raise ValueError(
                "recent_cycles_json entries must be JSON arrays, objects, or strings."
            )
    if len(cycles) > MAX_RECENT_CYCLES:
        raise ValueError(
            f"recent_cycles_json cannot contain more than {MAX_RECENT_CYCLES} cycles."
        )
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, (dict, str)):
            raise ValueError(
                "recent_cycles_json entries must be JSON objects or strings; "
                f"entry {index} is invalid."
            )
    return cycles


def _validate_bounded_string(
    value: Any,
    *,
    field: str,
    field_schema: dict[str, Any],
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string.")
    cleaned = value.strip()
    min_length = field_schema.get("minLength")
    max_length = field_schema.get("maxLength")
    if isinstance(min_length, int) and len(cleaned) < min_length:
        raise ValueError(f"{field} is shorter than {min_length} characters.")
    if isinstance(max_length, int) and len(cleaned) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters.")
    return cleaned


def _validate_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("continuation_request_json must contain one JSON object.")
    schema = _load_contract()["request_schema"]
    properties = schema.get("properties") or {}
    required = list(schema.get("required") or [])
    missing = [field for field in required if field not in request]
    extra = sorted(set(request).difference(properties))
    if missing:
        raise ValueError(
            "continuation_request_json is missing: " + ", ".join(missing)
        )
    if extra:
        raise ValueError(
            "continuation_request_json has unsupported keys: " + ", ".join(extra)
        )

    normalized: dict[str, Any] = {}
    for field in (
        "project_brief",
        "next_cycle_goal",
        "continuity_mode",
        "dialogue_or_audio_direction",
    ):
        normalized[field] = _validate_bounded_string(
            request[field],
            field=field,
            field_schema=properties[field],
        )

    allowed_modes = properties["continuity_mode"].get("enum") or []
    if normalized["continuity_mode"] not in allowed_modes:
        raise ValueError(
            "continuity_mode must be one of: " + ", ".join(allowed_modes)
        )

    constraints = request.get("visual_constraints")
    constraint_schema = properties["visual_constraints"]
    if not isinstance(constraints, list):
        raise ValueError("visual_constraints must be a JSON array of strings.")
    min_items = int(constraint_schema.get("minItems") or 0)
    max_items = int(constraint_schema.get("maxItems") or len(constraints))
    if len(constraints) < min_items or len(constraints) > max_items:
        raise ValueError(
            f"visual_constraints must contain between {min_items} and "
            f"{max_items} entries."
        )
    item_schema = constraint_schema.get("items") or {}
    normalized["visual_constraints"] = [
        _validate_bounded_string(
            item,
            field=f"visual_constraints[{index}]",
            field_schema=item_schema,
        )
        for index, item in enumerate(constraints)
    ]

    duration = request.get("duration_seconds")
    duration_schema = properties["duration_seconds"]
    minimum = int(duration_schema.get("minimum") or 0)
    maximum = int(duration_schema.get("maximum") or 0)
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise ValueError(
            f"duration_seconds must be an integer between {minimum} and {maximum}."
        )
    if duration < minimum or duration > maximum:
        raise ValueError(
            f"duration_seconds must be an integer between {minimum} and {maximum}."
        )
    normalized["duration_seconds"] = duration
    return normalized


def _line_list(raw: str) -> list[str]:
    return [line.strip() for line in str(raw or "").splitlines() if line.strip()]


def _speaker_clause(name: str, position: str, line: str) -> str:
    cleaned_name = str(name or "").strip() or "Speaker"
    cleaned_position = str(position or "").strip()
    cleaned_line = str(line or "").strip()
    if not cleaned_line:
        return ""
    if cleaned_position:
        return (
            f"{cleaned_name}, {cleaned_position}, says exactly: "
            f"{json.dumps(cleaned_line, ensure_ascii=False)}"
        )
    return (
        f"{cleaned_name} says exactly: "
        f"{json.dumps(cleaned_line, ensure_ascii=False)}"
    )


def _parse_dialogue_turns(raw: str) -> list[dict[str, str]]:
    text = str(raw or "").strip() or "[]"
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"dialogue_json must be valid JSON: {exc.msg}") from exc
    if not isinstance(value, list):
        raise ValueError("dialogue_json must contain one JSON array.")
    if len(value) > 16:
        raise ValueError("dialogue_json cannot contain more than 16 turns.")

    allowed = {"speaker", "position", "line", "delivery", "action"}
    normalized: list[dict[str, str]] = []
    for index, turn in enumerate(value):
        if not isinstance(turn, dict):
            raise ValueError(
                f"dialogue_json turn {index} must be one JSON object."
            )
        extra = sorted(set(turn).difference(allowed))
        if extra:
            raise ValueError(
                f"dialogue_json turn {index} has unsupported keys: "
                + ", ".join(extra)
            )
        speaker = str(turn.get("speaker") or "").strip()
        line = str(turn.get("line") or "").strip()
        if not speaker:
            raise ValueError(
                f"dialogue_json turn {index} requires a non-empty speaker."
            )
        if not line:
            raise ValueError(
                f"dialogue_json turn {index} requires a non-empty line."
            )
        cleaned = {
            "speaker": speaker,
            "position": str(turn.get("position") or "").strip(),
            "line": line,
            "delivery": str(turn.get("delivery") or "").strip(),
            "action": str(turn.get("action") or "").strip(),
        }
        limits = {
            "speaker": 160,
            "position": 240,
            "line": 600,
            "delivery": 400,
            "action": 400,
        }
        for field, maximum in limits.items():
            if len(cleaned[field]) > maximum:
                raise ValueError(
                    f"dialogue_json turn {index} field {field!r} exceeds "
                    f"{maximum} characters."
                )
        normalized.append(cleaned)
    return normalized


def _dialogue_direction(turns: list[dict[str, str]]) -> str:
    if not turns:
        raise ValueError(
            "dialogue_json must contain at least one turn when audio_mode is "
            "'dialogue JSON'."
        )
    clauses: list[str] = []
    for index, turn in enumerate(turns, start=1):
        clause = _speaker_clause(
            turn["speaker"],
            turn["position"],
            turn["line"],
        )
        if turn["delivery"]:
            clause += f" Delivery: {turn['delivery']}."
        if turn["action"]:
            clause += f" Visible action: {turn['action']}."
        clauses.append(f"Turn {index}: {clause}")
    return (
        "Perform these dialogue turns in order and preserve every quoted word "
        "exactly. Do not add, omit, paraphrase, overlap, or reassign speech. "
        + " ".join(clauses)
    )


def _compose_general_request(
    *,
    continuation_request_json: str,
    scene_or_subject: str,
    next_event: str,
    audio_mode: str,
    dialogue_json: str,
    continuity_mode: str,
    visual_constraints_text: str,
    duration_seconds: int,
) -> dict[str, Any]:
    base = _parse_json_object(
        continuation_request_json,
        label="continuation_request_json",
    )
    mode = str(audio_mode or "").strip()
    if mode not in AUDIO_MODES:
        raise ValueError("audio_mode must be one of: " + ", ".join(AUDIO_MODES))
    if mode == "advanced JSON only":
        return _validate_request(base)

    request = dict(base)
    cleaned_scene = str(scene_or_subject or "").strip()
    cleaned_event = str(next_event or "").strip()
    if cleaned_scene:
        request["project_brief"] = (
            "Continue the supplied image as a reusable visual sequence. "
            f"Scene or subject: {cleaned_scene}"
        )
    if cleaned_event:
        request["next_cycle_goal"] = cleaned_event
    if continuity_mode:
        request["continuity_mode"] = str(continuity_mode).strip()
    request["duration_seconds"] = int(duration_seconds)

    constraints = _line_list(visual_constraints_text)
    if constraints:
        request["visual_constraints"] = constraints

    if mode == "automatic from scene":
        request["dialogue_or_audio_direction"] = (
            "Choose audio from the visible scene and the requested next event. "
            "Do not invent spoken dialogue unless the scene_or_subject or "
            "next_event explicitly requests speech or supplies exact quoted "
            "words. Otherwise use coherent ambience and action-matched sound "
            "effects."
        )
    elif mode == "no dialogue":
        request["dialogue_or_audio_direction"] = (
            "No dialogue. Use natural ambience and only sound effects that match "
            "the visible action."
        )
    else:
        request["dialogue_or_audio_direction"] = _dialogue_direction(
            _parse_dialogue_turns(dialogue_json)
        )

    return _validate_request(request)


def _compose_request_from_widgets(
    *,
    continuation_request_json: str,
    topic: str,
    next_action: str,
    speaker_a_name: str,
    speaker_a_position: str,
    speaker_a_line: str,
    speaker_b_name: str,
    speaker_b_position: str,
    speaker_b_line: str,
    dialogue_mode: str,
    continuity_mode: str,
    visual_constraints_text: str,
    duration_seconds: int,
) -> dict[str, Any]:
    base = _parse_json_object(
        continuation_request_json,
        label="continuation_request_json",
    )
    if str(dialogue_mode or "").strip() == "advanced JSON only":
        return _validate_request(base)
    request = dict(base)

    cleaned_topic = str(topic or "").strip()
    cleaned_next_action = str(next_action or "").strip()
    if cleaned_topic:
        request["project_brief"] = (
            "Create a visually continuous sequence from the supplied starting "
            f"image. Main topic or scene: {cleaned_topic}"
        )
    if cleaned_next_action:
        request["next_cycle_goal"] = cleaned_next_action
    if continuity_mode:
        request["continuity_mode"] = str(continuity_mode).strip()
    request["duration_seconds"] = int(duration_seconds)

    constraints = _line_list(visual_constraints_text)
    if constraints:
        request["visual_constraints"] = constraints

    first = _speaker_clause(speaker_a_name, speaker_a_position, speaker_a_line)
    second = _speaker_clause(speaker_b_name, speaker_b_position, speaker_b_line)
    mode = str(dialogue_mode or "").strip()
    if mode == "no dialogue":
        request["dialogue_or_audio_direction"] = (
            "No dialogue. Use natural ambience and only sound effects that match "
            "the visible action."
        )
    elif first or second:
        lines = [line for line in (first, second) if line]
        request["dialogue_or_audio_direction"] = (
            " ".join(lines)
            + " Keep the exchange natural, coherent, and visually consistent. "
            "Preserve speaker identity and seating/position assignment."
        )

    return _validate_request(request)


def _validate_planner_result(result: Any) -> dict[str, str]:
    if not isinstance(result, dict):
        raise ValueError("Planner response must contain one JSON object.")
    schema = _load_contract()["response_schema"]
    properties = schema.get("properties") or {}
    required = list(schema.get("required") or [])
    missing = [field for field in required if field not in result]
    extra = sorted(set(result).difference(properties))
    if missing:
        raise ValueError("Planner response is missing: " + ", ".join(missing))
    if extra:
        raise ValueError(
            "Planner response has unsupported keys: " + ", ".join(extra)
        )

    normalized: dict[str, str] = {}
    for field in required:
        value = _safe_output_text(result[field], field=field)
        field_schema = properties[field]
        min_length = field_schema.get("minLength")
        max_length = field_schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise ValueError(
                f"Planner field {field!r} is shorter than {min_length} characters."
            )
        if isinstance(max_length, int) and len(value) > max_length:
            raise ValueError(
                f"Planner field {field!r} exceeds {max_length} characters."
            )
        normalized[field] = value
    return normalized


def _derived_seed(namespace: str, variation_seed: int) -> int:
    digest = hashlib.sha256(
        f"sineforge-{namespace}:{variation_seed}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _request_hash(request: dict[str, Any], recent_cycles: list[Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "request": request,
                "recent_cycles": recent_cycles,
            }
        ).encode("utf-8")
    ).hexdigest()


def _effective_negative_prompt(generated: str) -> str:
    fixed = str(_load_contract()["fixed_negative_prompt"]).strip().rstrip(",")
    generated = str(generated or "").strip().strip(",")
    return f"{fixed}, {generated}" if generated else fixed


def _planner_payload(
    *,
    model: str,
    seed: int,
    temperature: float,
    top_p: float,
    max_tokens: int,
    user_payload: dict[str, Any],
    image_data_url: str | None,
    reference_image_data_url: str | None,
) -> dict[str, Any]:
    contract = _load_contract()
    user_text = _canonical_json(user_payload)
    user_content: Any = user_text
    image_parts: list[dict[str, Any]] = []
    if image_data_url:
        image_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": image_data_url},
            }
        )
    if reference_image_data_url:
        image_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": reference_image_data_url},
            }
        )
    if image_parts:
        user_content = [{"type": "text", "text": user_text}, *image_parts]
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": _canonical_json(contract["system_prompt"]),
            },
            {"role": "user", "content": user_content},
        ],
        "temperature": float(temperature),
        "top_p": float(top_p),
        "max_tokens": int(max_tokens),
        "seed": int(seed),
        "stream": False,
        # This LM Studio build accepts only json_schema or text, and its schema
        # grammar parser rejects the full contract. JSON and schema correctness
        # are therefore enforced locally with a bounded repair retry.
        "response_format": {"type": "text"},
    }


class SineForgeLTXKreaContinuationPlanner:
    """Generate a strict Krea/LTX continuation plan with a selected local model."""

    CATEGORY = "SineForge/Planning"
    FUNCTION = "generate"
    RETURN_TYPES = (
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "INT",
        "INT",
        "INT",
        "INT",
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "prompt_json",
        "krea_prompt",
        "positive_prompt",
        "negative_prompt",
        "variation_seed",
        "image_seed",
        "video_seed",
        "duration_seconds",
        "output_prefix",
        "status_json",
    )
    DESCRIPTION = (
        "Uses a selectable local LM Studio GGUF package to plan one general "
        "Krea 2 still-image continuation and its LTX-2.3 animation. The source "
        "may be people, objects, places, products, environments, or styles. "
        "Qwen 3.6 40B is the default, not the only choice. ComfyUI models are "
        "released first, every LM Studio model is unloaded before outputs are "
        "returned, and all prompts are embedded in prompt_json."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        contract = _load_contract()
        model_keys = list(_selectable_model_keys())
        preferred_model = contract["planner_model"]
        default_request = contract["default_request"]
        continuity_modes = (
            contract["request_schema"]["properties"]["continuity_mode"]["enum"]
        )
        return {
            "required": {
                "model": (
                    model_keys,
                    {
                        "default": (
                            preferred_model
                            if preferred_model in model_keys
                            else model_keys[0]
                        )
                    },
                ),
                "variation_mode": (
                    list(VARIATION_MODES),
                    {"default": VARIATION_MODES[0]},
                ),
                "seed": (
                    "INT",
                    {
                        "default": 20260731,
                        "min": 0,
                        "max": 0x7FFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                    },
                ),
                "topic": (
                    "STRING",
                    {
                        "default": "Two-person podcast conversation",
                        "multiline": False,
                    },
                ),
                "next_action": (
                    "STRING",
                    {
                        "default": (
                            "Continue the conversation by one clear beat while "
                            "preserving the same speakers, room, camera, and tone."
                        ),
                        "multiline": True,
                    },
                ),
                "dialogue_mode": (
                    ["speaker fields", "no dialogue", "advanced JSON only"],
                    {"default": "speaker fields"},
                ),
                "speaker_a_name": (
                    "STRING",
                    {"default": "Man A", "multiline": False},
                ),
                "speaker_a_position": (
                    "STRING",
                    {"default": "seated camera-left", "multiline": False},
                ),
                "speaker_a_line": (
                    "STRING",
                    {"default": "", "multiline": True},
                ),
                "speaker_b_name": (
                    "STRING",
                    {"default": "Man B", "multiline": False},
                ),
                "speaker_b_position": (
                    "STRING",
                    {"default": "seated camera-right", "multiline": False},
                ),
                "speaker_b_line": (
                    "STRING",
                    {"default": "", "multiline": True},
                ),
                "continuity_mode": (
                    list(continuity_modes),
                    {"default": "lossless_loop"},
                ),
                "duration_seconds": (
                    "INT",
                    {
                        "default": int(default_request["duration_seconds"]),
                        "min": 2,
                        "max": 30,
                        "step": 1,
                    },
                ),
                "visual_constraints_text": (
                    "STRING",
                    {
                        "default": "\n".join(default_request["visual_constraints"]),
                        "multiline": True,
                    },
                ),
                "continuation_request_json": (
                    "STRING",
                    {
                        "default": json.dumps(
                            default_request,
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "multiline": True,
                    },
                ),
                "recent_cycles_json": (
                    "STRING",
                    {
                        "default": "[]",
                        "multiline": True,
                    },
                ),
                "temperature": (
                    "FLOAT",
                    {
                        "default": 0.8,
                        "min": 0.0,
                        "max": 2.0,
                        "step": 0.05,
                    },
                ),
                "top_p": (
                    "FLOAT",
                    {
                        "default": 0.95,
                        "min": 0.05,
                        "max": 1.0,
                        "step": 0.01,
                    },
                ),
                "max_tokens": (
                    "INT",
                    {
                        "default": 2200,
                        "min": 512,
                        "max": 8192,
                        "step": 64,
                    },
                ),
                "timeout_seconds": (
                    "INT",
                    {
                        "default": 900,
                        "min": 60,
                        "max": 3600,
                        "step": 30,
                    },
                ),
            },
            "optional": {
                "image": ("IMAGE",),
                "reference_image": ("IMAGE",),
            },
        }

    @classmethod
    def IS_CHANGED(cls, variation_mode: str, seed: int, **kwargs: Any) -> Any:
        if variation_mode == VARIATION_MODES[0]:
            return float("nan")
        identity = {
            "variation_mode": variation_mode,
            "seed": int(seed),
            "model": kwargs.get("model"),
            "topic": kwargs.get("topic"),
            "next_action": kwargs.get("next_action"),
            "dialogue_mode": kwargs.get("dialogue_mode"),
            "speaker_a_name": kwargs.get("speaker_a_name"),
            "speaker_a_position": kwargs.get("speaker_a_position"),
            "speaker_a_line": kwargs.get("speaker_a_line"),
            "speaker_b_name": kwargs.get("speaker_b_name"),
            "speaker_b_position": kwargs.get("speaker_b_position"),
            "speaker_b_line": kwargs.get("speaker_b_line"),
            "continuity_mode": kwargs.get("continuity_mode"),
            "duration_seconds": kwargs.get("duration_seconds"),
            "visual_constraints_text": kwargs.get("visual_constraints_text"),
            "continuation_request_json": kwargs.get("continuation_request_json"),
            "recent_cycles_json": kwargs.get("recent_cycles_json"),
            "temperature": kwargs.get("temperature"),
            "top_p": kwargs.get("top_p"),
            "max_tokens": kwargs.get("max_tokens"),
        }
        return hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model: str | None = None,
        variation_mode: str | None = None,
        continuation_request_json: str | None = None,
        recent_cycles_json: str | None = None,
        topic: str | None = None,
        next_action: str | None = None,
        speaker_a_name: str | None = None,
        speaker_a_position: str | None = None,
        speaker_a_line: str | None = None,
        speaker_b_name: str | None = None,
        speaker_b_position: str | None = None,
        speaker_b_line: str | None = None,
        dialogue_mode: str | None = None,
        continuity_mode: str | None = None,
        visual_constraints_text: str | None = None,
        duration_seconds: int | None = None,
        **_: Any,
    ) -> bool | str:
        try:
            _load_contract()
            selected_model = str(model or "").strip()
            if not selected_model:
                return "Select one locally installed GGUF model."
            _resolve_local_model_package(selected_model)
            if variation_mode not in VARIATION_MODES:
                return "variation_mode is invalid."
            _compose_request_from_widgets(
                continuation_request_json=str(continuation_request_json or ""),
                topic=str(topic or ""),
                next_action=str(next_action or ""),
                speaker_a_name=str(speaker_a_name or ""),
                speaker_a_position=str(speaker_a_position or ""),
                speaker_a_line=str(speaker_a_line or ""),
                speaker_b_name=str(speaker_b_name or ""),
                speaker_b_position=str(speaker_b_position or ""),
                speaker_b_line=str(speaker_b_line or ""),
                dialogue_mode=str(dialogue_mode or "speaker fields"),
                continuity_mode=str(continuity_mode or "lossless_loop"),
                visual_constraints_text=str(visual_constraints_text or ""),
                duration_seconds=int(duration_seconds or 8),
            )
            _parse_recent_cycles(str(recent_cycles_json or ""))
        except (RuntimeError, ValueError) as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        variation_mode: str,
        seed: int,
        topic: str,
        next_action: str,
        dialogue_mode: str,
        speaker_a_name: str,
        speaker_a_position: str,
        speaker_a_line: str,
        speaker_b_name: str,
        speaker_b_position: str,
        speaker_b_line: str,
        continuity_mode: str,
        duration_seconds: int,
        visual_constraints_text: str,
        continuation_request_json: str,
        recent_cycles_json: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout_seconds: int,
        image: Any = None,
        reference_image: Any = None,
    ) -> tuple[str, str, str, str, int, int, int, int, str, str]:
        contract = _load_contract()
        model = str(model or "").strip()
        local_package = _resolve_local_model_package(model)
        if variation_mode == VARIATION_MODES[0]:
            variation_seed = secrets.randbelow(0x7FFFFFFFFFFFFFFF)
        elif variation_mode == VARIATION_MODES[1]:
            variation_seed = int(seed)
        else:
            raise ValueError("variation_mode is invalid.")

        request = _compose_request_from_widgets(
            continuation_request_json=continuation_request_json,
            topic=topic,
            next_action=next_action,
            speaker_a_name=speaker_a_name,
            speaker_a_position=speaker_a_position,
            speaker_a_line=speaker_a_line,
            speaker_b_name=speaker_b_name,
            speaker_b_position=speaker_b_position,
            speaker_b_line=speaker_b_line,
            dialogue_mode=dialogue_mode,
            continuity_mode=continuity_mode,
            visual_constraints_text=visual_constraints_text,
            duration_seconds=duration_seconds,
        )
        recent_cycles = _parse_recent_cycles(recent_cycles_json)
        duration = request["duration_seconds"]
        image_seed = _derived_seed("krea2-image", variation_seed)
        video_seed = _derived_seed("ltx23-video", variation_seed)
        request_sha256 = _request_hash(request, recent_cycles)
        user_payload = {
            "schema_version": "sineforge.ltx23-krea-continuation-call/v1",
            "variation_seed": variation_seed,
            "image_seed": image_seed,
            "video_seed": video_seed,
            "request": request,
            "recent_cycles": recent_cycles,
            "source": {
                "image_attached": image is not None,
                "reference_image_attached": reference_image is not None,
                "scope": (
                    "The source can contain people, creatures, objects, products, "
                    "places, environments, graphics, or visual styles. Do not "
                    "assume a podcast or conversation."
                ),
                "continuity_instruction": (
                    "Use the attached image as the last accepted frame and visual "
                    "source of truth. Generate a clean successor still; preserve "
                    "stable anchors and change only what next_cycle_goal requires."
                ),
                "reference_instruction": (
                    "If a second reference image is attached, treat it as the "
                    "canonical reference sheet or style/identity reference. Use "
                    "it to preserve character identity, wardrobe, object design, "
                    "studio/set details, palette, and recurring visual motifs. "
                    "Do not copy labels, panel borders, UI, or reference-sheet "
                    "layout into the generated scene."
                ),
            },
            "targets": {
                "image_generator": "Krea 2",
                "video_generator": "LTX-2.3 image-to-video",
                "duration_seconds": duration,
                "instruction": (
                    "Return one standalone Krea 2 image prompt and one standalone "
                    "LTX-2.3 positive prompt that animates the resulting new image."
                ),
            },
        }

        source_image_sha256: str | None = None
        reference_image_sha256: str | None = None
        image_url: str | None = None
        reference_image_url: str | None = None
        resolved_model = model
        catalog_provenance: dict[str, Any] | None = None
        planner_images_forwarded = False
        planner_result: dict[str, str] | None = None
        planner_error: Exception | None = None
        unload_error: Exception | None = None
        attempt_errors: list[str] = []
        try:
            image_url = _image_data_url(image)
            source_image_sha256 = _image_tensor_sha256(image)
            reference_image_url = _image_data_url(reference_image)
            reference_image_sha256 = _image_tensor_sha256(reference_image)
            model_entry, resolved_model = _resolve_model_entry(model)
            if resolved_model != model:
                raise RuntimeError(
                    f"LM Studio resolved local package {model!r} as "
                    f"{resolved_model!r}; aliases are rejected."
                )
            capabilities = model_entry.get("capabilities")
            if not isinstance(capabilities, dict):
                capabilities = {}
            supports_vision = (
                capabilities.get("vision") is True
                or local_package.get("supports_local_vision_files") is True
            )
            planner_images_forwarded = bool(
                supports_vision and (image_url or reference_image_url)
            )
            if not supports_vision:
                image_url = None
                reference_image_url = None
            user_payload["source"]["planner_images_forwarded"] = (
                planner_images_forwarded
            )
            user_payload["source"]["selected_model_supports_vision"] = (
                supports_vision
            )
            catalog_provenance = {
                "key": str(model_entry.get("key") or "").strip(),
                "publisher": str(model_entry.get("publisher") or "").strip(),
                "display_name": str(
                    model_entry.get("display_name") or ""
                ).strip(),
                "architecture": str(
                    model_entry.get("architecture") or ""
                ).strip(),
                "format": str(model_entry.get("format") or "").strip(),
                "size_bytes": model_entry.get("size_bytes"),
                "params_string": model_entry.get("params_string"),
                "quantization": model_entry.get("quantization"),
                "capabilities": capabilities,
            }
            _release_comfy_models()
            _unload_loaded_lm_studio_models(except_model=resolved_model)
            _ensure_lm_studio_model_loaded(resolved_model)

            for attempt in range(2):
                attempt_payload = dict(user_payload)
                if attempt_errors:
                    attempt_payload["repair"] = {
                        "attempt": attempt + 1,
                        "validation_errors": attempt_errors[-1:],
                        "instruction": (
                            "Return a corrected object using exactly the same "
                            "strict schema. Keep Krea and LTX prompts standalone."
                        ),
                    }
                body = _planner_payload(
                    model=resolved_model,
                    seed=(variation_seed + attempt) & 0x7FFFFFFFFFFFFFFF,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    user_payload=attempt_payload,
                    image_data_url=image_url,
                    reference_image_data_url=reference_image_url,
                )
                try:
                    response = _http_json(
                        f"{LM_STUDIO_OPENAI_BASE}/chat/completions",
                        method="POST",
                        payload=body,
                        timeout=float(timeout_seconds),
                    )
                    parsed = json.loads(_chat_content(response))
                    planner_result = _validate_planner_result(parsed)
                    break
                except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                    attempt_errors.append(str(exc))
                    if attempt == 0 and "unload" in str(exc).casefold():
                        _ensure_lm_studio_model_loaded(resolved_model)
            if planner_result is None:
                raise RuntimeError(
                    "The selected local model did not produce a valid Krea "
                    "continuation JSON "
                    "object after two attempts: " + " | ".join(attempt_errors)
                )
        except Exception as exc:
            planner_error = exc
        finally:
            try:
                _unload_all_lm_studio_models()
            except Exception as exc:
                unload_error = exc

        if planner_error is not None:
            if unload_error is not None:
                raise RuntimeError(
                    f"{planner_error} Additionally, LM Studio cleanup failed: "
                    f"{unload_error}"
                ) from planner_error
            raise planner_error
        if unload_error is not None:
            raise RuntimeError(
                "Local continuation planning finished, but LM Studio cleanup "
                f"failed: {unload_error} Krea/LTX generation was not started."
            ) from unload_error
        if planner_result is None:
            raise RuntimeError(
                "The selected local model returned no validated continuation plan."
            )

        krea_prompt = planner_result["krea_prompt"]
        positive_prompt = planner_result["ltx_prompt"]
        negative_prompt = _effective_negative_prompt(
            planner_result["negative_prompt"]
        )
        cycle_id = f"continuation-{variation_seed:016x}"
        record: dict[str, Any] = {
            "schema_version": "sineforge.ltx23-krea-continuation-cycle/v1",
            "cycle_id": cycle_id,
            "variation_seed": variation_seed,
            "image_seed": image_seed,
            "video_seed": video_seed,
            "duration_seconds": duration,
            "planner": {
                "provider": "local_lm_studio",
                "requested_model": model,
                "model": resolved_model,
                "endpoint": "loopback",
                "temperature": float(temperature),
                "top_p": float(top_p),
                "model_unloaded_before_generation": True,
                "all_lm_studio_models_unloaded_before_generation": True,
                "local_package": local_package,
                "lm_studio_catalog": catalog_provenance,
                "planner_images_forwarded": planner_images_forwarded,
            },
            "request_sha256": request_sha256,
            "request": request,
            "recent_cycles": recent_cycles,
            "source_image": {
                "attached": image is not None,
                "tensor_sha256": source_image_sha256,
                "role": "last_accepted_frame_and_visual_source_of_truth",
            },
            "reference_image": {
                "attached": reference_image is not None,
                "tensor_sha256": reference_image_sha256,
                "role": "canonical_reference_sheet_or_style_identity_reference",
            },
            "title": planner_result["title"],
            "topic": planner_result["topic"],
            "continuity_summary": planner_result["continuity_summary"],
            "planner_response": planner_result,
            "krea_prompt": krea_prompt,
            "ltx_prompt": positive_prompt,
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
        }
        record["prompt_sha256"] = hashlib.sha256(
            _canonical_json(record).encode("utf-8")
        ).hexdigest()
        prompt_json = json.dumps(record, ensure_ascii=False, indent=2)
        output_prefix = f"SineForge/LTX23_Krea_Continuation/{cycle_id}"
        status_json = json.dumps(
            {
                "ok": True,
                "cycle_id": cycle_id,
                "variation_seed": variation_seed,
                "image_seed": image_seed,
                "video_seed": video_seed,
                "selected_model_unloaded": True,
                "all_lm_studio_models_unloaded": True,
                "request_sha256": request_sha256,
                "prompt_sha256": record["prompt_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
        return (
            prompt_json,
            krea_prompt,
            positive_prompt,
            negative_prompt,
            variation_seed,
            image_seed,
            video_seed,
            duration,
            output_prefix,
            status_json,
        )


class SineForgeLTXGeneralContinuationPlanner(
    SineForgeLTXKreaContinuationPlanner
):
    """General scene-first adapter over the strict continuation planner."""

    DESCRIPTION = (
        "Plans one general Krea 2 to LTX-2.3 continuation with scene/story "
        "controls first. Dialogue is optional and supplied only as JSON. The "
        "adapter composes the established strict request contract, then runs "
        "the same local-only selectable-GGUF generation and complete unload path."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        contract = _load_contract()
        model_keys = list(_selectable_model_keys())
        preferred_model = contract["planner_model"]
        default_request = contract["default_request"]
        continuity_modes = (
            contract["request_schema"]["properties"]["continuity_mode"]["enum"]
        )
        return {
            "required": {
                "model": (
                    model_keys,
                    {
                        "default": (
                            preferred_model
                            if preferred_model in model_keys
                            else model_keys[0]
                        )
                    },
                ),
                "variation_mode": (
                    list(VARIATION_MODES),
                    {"default": VARIATION_MODES[0]},
                ),
                "seed": (
                    "INT",
                    {
                        "default": 20260731,
                        "min": 0,
                        "max": 0x7FFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                    },
                ),
                "scene_or_subject": (
                    "STRING",
                    {
                        "default": (
                            "The subject and environment shown in the starting "
                            "image, preserved as the visual source of truth."
                        ),
                        "multiline": True,
                    },
                ),
                "next_event": (
                    "STRING",
                    {
                        "default": (
                            "Advance the scene by one clear, visually coherent "
                            "event while preserving everything not explicitly "
                            "changed."
                        ),
                        "multiline": True,
                    },
                ),
                "audio_mode": (
                    list(AUDIO_MODES),
                    {"default": AUDIO_MODES[0]},
                ),
                "dialogue_json": (
                    "STRING",
                    {
                        "default": "[]",
                        "multiline": True,
                    },
                ),
                "continuity_mode": (
                    list(continuity_modes),
                    {"default": "lossless_loop"},
                ),
                "duration_seconds": (
                    "INT",
                    {
                        "default": int(default_request["duration_seconds"]),
                        "min": 2,
                        "max": 30,
                        "step": 1,
                    },
                ),
                "visual_constraints_text": (
                    "STRING",
                    {
                        "default": "\n".join(default_request["visual_constraints"]),
                        "multiline": True,
                    },
                ),
                "continuation_request_json": (
                    "STRING",
                    {
                        "default": json.dumps(
                            default_request,
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "multiline": True,
                    },
                ),
                "recent_cycles_json": (
                    "STRING",
                    {
                        "default": "[]",
                        "multiline": True,
                    },
                ),
                "temperature": (
                    "FLOAT",
                    {
                        "default": 0.8,
                        "min": 0.0,
                        "max": 2.0,
                        "step": 0.05,
                    },
                ),
                "top_p": (
                    "FLOAT",
                    {
                        "default": 0.95,
                        "min": 0.05,
                        "max": 1.0,
                        "step": 0.01,
                    },
                ),
                "max_tokens": (
                    "INT",
                    {
                        "default": 2200,
                        "min": 512,
                        "max": 8192,
                        "step": 64,
                    },
                ),
                "timeout_seconds": (
                    "INT",
                    {
                        "default": 900,
                        "min": 60,
                        "max": 3600,
                        "step": 30,
                    },
                ),
            },
            "optional": {
                "image": ("IMAGE",),
                "reference_image": ("IMAGE",),
            },
        }

    @classmethod
    def IS_CHANGED(cls, variation_mode: str, seed: int, **kwargs: Any) -> Any:
        if variation_mode == VARIATION_MODES[0]:
            return float("nan")
        identity = {
            "variation_mode": variation_mode,
            "seed": int(seed),
            "model": kwargs.get("model"),
            "scene_or_subject": kwargs.get("scene_or_subject"),
            "next_event": kwargs.get("next_event"),
            "audio_mode": kwargs.get("audio_mode"),
            "dialogue_json": kwargs.get("dialogue_json"),
            "continuity_mode": kwargs.get("continuity_mode"),
            "duration_seconds": kwargs.get("duration_seconds"),
            "visual_constraints_text": kwargs.get("visual_constraints_text"),
            "continuation_request_json": kwargs.get("continuation_request_json"),
            "recent_cycles_json": kwargs.get("recent_cycles_json"),
            "temperature": kwargs.get("temperature"),
            "top_p": kwargs.get("top_p"),
            "max_tokens": kwargs.get("max_tokens"),
        }
        return hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model: str | None = None,
        variation_mode: str | None = None,
        scene_or_subject: str | None = None,
        next_event: str | None = None,
        audio_mode: str | None = None,
        dialogue_json: str | None = None,
        continuity_mode: str | None = None,
        duration_seconds: int | None = None,
        visual_constraints_text: str | None = None,
        continuation_request_json: str | None = None,
        recent_cycles_json: str | None = None,
        **_: Any,
    ) -> bool | str:
        try:
            _load_contract()
            selected_model = str(model or "").strip()
            if not selected_model:
                return "Select one locally installed GGUF model."
            _resolve_local_model_package(selected_model)
            if variation_mode not in VARIATION_MODES:
                return "variation_mode is invalid."
            _compose_general_request(
                continuation_request_json=str(continuation_request_json or ""),
                scene_or_subject=str(scene_or_subject or ""),
                next_event=str(next_event or ""),
                audio_mode=str(audio_mode or AUDIO_MODES[0]),
                dialogue_json=str(dialogue_json or "[]"),
                continuity_mode=str(continuity_mode or "lossless_loop"),
                visual_constraints_text=str(visual_constraints_text or ""),
                duration_seconds=int(duration_seconds or 8),
            )
            _parse_recent_cycles(str(recent_cycles_json or ""))
        except (RuntimeError, ValueError) as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        variation_mode: str,
        seed: int,
        scene_or_subject: str,
        next_event: str,
        audio_mode: str,
        dialogue_json: str,
        continuity_mode: str,
        duration_seconds: int,
        visual_constraints_text: str,
        continuation_request_json: str,
        recent_cycles_json: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout_seconds: int,
        image: Any = None,
        reference_image: Any = None,
    ) -> tuple[str, str, str, str, int, int, int, int, str, str]:
        request = _compose_general_request(
            continuation_request_json=continuation_request_json,
            scene_or_subject=scene_or_subject,
            next_event=next_event,
            audio_mode=audio_mode,
            dialogue_json=dialogue_json,
            continuity_mode=continuity_mode,
            visual_constraints_text=visual_constraints_text,
            duration_seconds=duration_seconds,
        )
        return super().generate(
            model=model,
            variation_mode=variation_mode,
            seed=seed,
            topic="",
            next_action="",
            dialogue_mode="advanced JSON only",
            speaker_a_name="",
            speaker_a_position="",
            speaker_a_line="",
            speaker_b_name="",
            speaker_b_position="",
            speaker_b_line="",
            continuity_mode=request["continuity_mode"],
            duration_seconds=request["duration_seconds"],
            visual_constraints_text="",
            continuation_request_json=json.dumps(
                request,
                ensure_ascii=False,
            ),
            recent_cycles_json=recent_cycles_json,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            image=image,
            reference_image=reference_image,
        )


class SineForgeContinuationLoopCount:
    """Convert the user-facing loop count into Easy-Use's required total."""

    CATEGORY = "SineForge/Flow"
    FUNCTION = "resolve"
    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("total",)
    DESCRIPTION = (
        "Sets the exact number of continuation cycles. Values 1 through 100000 "
        "run exactly that many cycles. Zero selects a practical continuous mode "
        "of 100000 cycles, intended to be stopped with ComfyUI Interrupt."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "loop_count": (
                    "INT",
                    {
                        "default": 4,
                        "min": 0,
                        "max": CONTINUOUS_LOOP_INTERNAL_TOTAL,
                        "step": 1,
                    },
                ),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        loop_count: int | None = None,
        **_: Any,
    ) -> bool | str:
        if isinstance(loop_count, bool) or not isinstance(loop_count, int):
            return "loop_count must be an integer from 0 to 100000."
        if loop_count < 0 or loop_count > CONTINUOUS_LOOP_INTERNAL_TOTAL:
            return "loop_count must be an integer from 0 to 100000."
        return True

    def resolve(self, loop_count: int) -> tuple[int]:
        if isinstance(loop_count, bool) or not isinstance(loop_count, int):
            raise ValueError("loop_count must be an integer from 0 to 100000.")
        if loop_count < 0 or loop_count > CONTINUOUS_LOOP_INTERNAL_TOTAL:
            raise ValueError("loop_count must be an integer from 0 to 100000.")
        return (
            CONTINUOUS_LOOP_INTERNAL_TOTAL if loop_count == 0 else loop_count,
        )


__all__ = [
    "AUDIO_MODES",
    "CONTINUOUS_LOOP_INTERNAL_TOTAL",
    "SineForgeContinuationLoopCount",
    "SineForgeLTXGeneralContinuationPlanner",
    "SineForgeLTXKreaContinuationPlanner",
    "_compose_general_request",
    "_derived_seed",
    "_load_contract",
    "_parse_dialogue_turns",
    "_validate_planner_result",
    "_validate_request",
]
