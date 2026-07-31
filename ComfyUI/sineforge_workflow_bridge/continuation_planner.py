"""Local-only Qwen planner for reusable Krea 2 -> LTX-2.3 continuations.

This node deliberately shares the podcast planner's trust and GPU-ownership
helpers.  It accepts no endpoint or credential, calls only loopback LM Studio,
releases ComfyUI models before planning, and returns prompts only after every
LM Studio model instance has been confirmed unloaded.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path
from typing import Any

from .podcast_planner import (
    LM_STUDIO_OPENAI_BASE,
    VARIATION_MODES,
    _canonical_json,
    _chat_content,
    _http_json,
    _image_data_url,
    _image_tensor_sha256,
    _load_contract as _load_podcast_contract,
    _release_comfy_models,
    _resolve_model_entry,
    _safe_output_text,
    _unload_all_lm_studio_models,
    _unload_loaded_lm_studio_models,
    _validate_trusted_model_package,
)


CONTRACT_PATH = Path(__file__).with_name(
    "ltx23_krea_continuation_prompt_contract.json"
)
MAX_RECENT_CYCLES = 50


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
        "trusted_planner_models",
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

    # The package allowlist remains owned by the established podcast planner.
    # Requiring an exact match prevents the second contract from widening it.
    trust_contract = _load_podcast_contract()
    trust_keys = (
        "planner_model",
        "trusted_lm_studio_model_root",
        "trusted_planner_models",
    )
    mismatches = [
        key
        for key in trust_keys
        if _canonical_json(contract.get(key))
        != _canonical_json(trust_contract.get(key))
    ]
    if mismatches:
        raise RuntimeError(
            "Krea continuation trust lock differs from the approved Qwen "
            "package for: " + ", ".join(mismatches)
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


def _parse_recent_cycles(raw: str) -> list[Any]:
    try:
        value = json.loads(str(raw or ""))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"recent_cycles_json must be valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(value, list):
        raise ValueError("recent_cycles_json must contain one JSON array.")
    if len(value) > MAX_RECENT_CYCLES:
        raise ValueError(
            f"recent_cycles_json cannot contain more than {MAX_RECENT_CYCLES} cycles."
        )
    for index, cycle in enumerate(value):
        if not isinstance(cycle, (dict, str)):
            raise ValueError(
                "recent_cycles_json entries must be JSON objects or strings; "
                f"entry {index} is invalid."
            )
    return value


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
) -> dict[str, Any]:
    contract = _load_contract()
    user_text = _canonical_json(user_payload)
    user_content: Any = user_text
    if image_data_url:
        user_content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
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
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "sineforge_ltx23_krea_continuation",
                "strict": True,
                "schema": contract["response_schema"],
            },
        },
    }


class SineForgeLTXKreaContinuationPlanner:
    """Generate a strict Krea/LTX continuation plan and release Qwen."""

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
        "Uses the trust-locked local LM Studio Qwen package to plan one general "
        "Krea 2 still-image continuation and its LTX-2.3 animation. The source "
        "may be people, objects, places, products, environments, or styles. "
        "ComfyUI models are released first, every LM Studio model is unloaded "
        "before outputs are returned, and all prompts are embedded in prompt_json."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        contract = _load_contract()
        exact_model = contract["planner_model"]
        return {
            "required": {
                "model": (
                    [exact_model],
                    {"default": exact_model},
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
                "continuation_request_json": (
                    "STRING",
                    {
                        "default": json.dumps(
                            contract["default_request"],
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
        **_: Any,
    ) -> bool | str:
        try:
            contract = _load_contract()
            exact_model = contract["planner_model"]
            if str(model or "").strip() != exact_model:
                return f"model must be the exact trusted Qwen key: {exact_model}"
            if variation_mode not in VARIATION_MODES:
                return "variation_mode is invalid."
            request = _parse_json_object(
                str(continuation_request_json or ""),
                label="continuation_request_json",
            )
            _validate_request(request)
            _parse_recent_cycles(str(recent_cycles_json or ""))
            _validate_trusted_model_package(exact_model)
        except (RuntimeError, ValueError) as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        variation_mode: str,
        seed: int,
        continuation_request_json: str,
        recent_cycles_json: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout_seconds: int,
        image: Any = None,
    ) -> tuple[str, str, str, str, int, int, int, int, str, str]:
        contract = _load_contract()
        model = str(model or "").strip()
        exact_model = contract["planner_model"]
        if model != exact_model:
            raise ValueError(f"model must be the exact trusted Qwen key: {exact_model}")
        if variation_mode == VARIATION_MODES[0]:
            variation_seed = secrets.randbelow(0x7FFFFFFFFFFFFFFF)
        elif variation_mode == VARIATION_MODES[1]:
            variation_seed = int(seed)
        else:
            raise ValueError("variation_mode is invalid.")

        request = _validate_request(
            _parse_json_object(
                continuation_request_json,
                label="continuation_request_json",
            )
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
        image_url: str | None = None
        resolved_model = model
        trusted_package: dict[str, Any] | None = None
        planner_result: dict[str, str] | None = None
        planner_error: Exception | None = None
        unload_error: Exception | None = None
        attempt_errors: list[str] = []
        try:
            image_url = _image_data_url(image)
            source_image_sha256 = _image_tensor_sha256(image)
            trusted_package = _validate_trusted_model_package(model)
            _, resolved_model = _resolve_model_entry(model)
            _release_comfy_models()
            _unload_loaded_lm_studio_models(except_model=resolved_model)

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
            if planner_result is None:
                raise RuntimeError(
                    "Local Qwen did not produce a valid Krea continuation JSON "
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
                "Qwen continuation planning finished, but LM Studio cleanup "
                f"failed: {unload_error} Krea/LTX generation was not started."
            ) from unload_error
        if planner_result is None:
            raise RuntimeError("Local Qwen returned no validated continuation plan.")

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
                "trusted_package": trusted_package,
            },
            "request_sha256": request_sha256,
            "request": request,
            "recent_cycles": recent_cycles,
            "source_image": {
                "attached": image is not None,
                "tensor_sha256": source_image_sha256,
                "role": "last_accepted_frame_and_visual_source_of_truth",
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
                "qwen_unloaded": True,
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


__all__ = [
    "SineForgeLTXKreaContinuationPlanner",
    "_derived_seed",
    "_load_contract",
    "_validate_planner_result",
    "_validate_request",
]
