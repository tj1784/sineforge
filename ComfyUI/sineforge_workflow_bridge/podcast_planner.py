"""Local-only Qwen JSON planner for the SineForge LTX-2.3 podcast workflow.

The node deliberately sequences GPU ownership:

1. release cached ComfyUI models;
2. call the selected LM Studio model with a strict JSON Schema;
3. unload and verify the complete LM Studio model-instance set; and
4. return prompt text only after unload has been confirmed.

No cloud endpoint, API key, or remote host is accepted.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


LM_STUDIO_ROOT = "http://127.0.0.1:1234"
LM_STUDIO_OPENAI_BASE = f"{LM_STUDIO_ROOT}/v1"
CONTRACT_PATH = Path(__file__).with_name("ltx23_podcast_prompt_contract.json")
VARIATION_MODES = (
    "new variation every run",
    "replay visible seed",
)
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
WORD_PATTERN = re.compile(r"[\w'’-]+", flags=re.UNICODE)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _load_contract() -> dict[str, Any]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"SineForge podcast prompt contract is invalid: {exc}") from exc
    required = {
        "schema_version",
        "planner_model",
        "trusted_lm_studio_model_root",
        "trusted_planner_models",
        "system_prompt",
        "default_request",
        "category_hints",
        "response_schema",
        "fixed_negative_prompt",
    }
    missing = sorted(required.difference(contract))
    if missing:
        raise RuntimeError(
            "SineForge podcast prompt contract is missing: " + ", ".join(missing)
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


def _parse_json_list(raw: str, *, label: str) -> list[Any]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        if exc.msg != "Extra data":
            raise ValueError(f"{label} must be valid JSON: {exc.msg}") from exc

        decoder = json.JSONDecoder()
        values: list[Any] = []
        cursor = 0
        try:
            while cursor < len(text):
                value, cursor = decoder.raw_decode(text, cursor)
                if isinstance(value, list):
                    values.extend(value)
                else:
                    values.append(value)
                while cursor < len(text) and text[cursor].isspace():
                    cursor += 1
        except json.JSONDecodeError as sequence_exc:
            raise ValueError(
                f"{label} must be valid JSON: {sequence_exc.msg}"
            ) from sequence_exc
        return values
    if not isinstance(value, list):
        raise ValueError(f"{label} must contain one JSON array.")
    return value


def _word_count(value: str) -> int:
    return len(WORD_PATTERN.findall(str(value or "")))


def _safe_output_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Planner field {field!r} must be a string.")
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        raise ValueError(f"Planner field {field!r} cannot be empty.")
    return cleaned


def _validate_planner_result(
    result: Any,
    *,
    request: dict[str, Any],
) -> dict[str, str]:
    if not isinstance(result, dict):
        raise ValueError("Planner response must contain one JSON object.")
    contract = _load_contract()
    schema = contract["response_schema"]
    required = list(schema.get("required") or [])
    allowed = set((schema.get("properties") or {}).keys())
    missing = [field for field in required if field not in result]
    extra = sorted(set(result).difference(allowed))
    if missing:
        raise ValueError("Planner response is missing: " + ", ".join(missing))
    if extra:
        raise ValueError("Planner response has unsupported keys: " + ", ".join(extra))

    normalized = {
        field: _safe_output_text(result[field], field=field)
        for field in required
    }
    properties = schema.get("properties") or {}
    for field, value in normalized.items():
        field_schema = properties.get(field) or {}
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
    if normalized["primary_topic"].casefold() == normalized["pivot_topic"].casefold():
        raise ValueError("Primary and pivot topics must be different.")

    source_notes = request.get("source_notes")
    if normalized["factuality_mode"] == "source_bound" and (
        not isinstance(source_notes, list)
        or not any(str(item or "").strip() for item in source_notes)
    ):
        raise ValueError("source_bound requires at least one approved source note.")
    if normalized["factuality_mode"] not in {
        "fictional_opinion_dialogue",
        "source_bound",
    }:
        raise ValueError("Unsupported factuality_mode.")

    limits = request.get("dialogue_limits")
    if not isinstance(limits, dict):
        limits = {}
    max_per_line = int(limits.get("max_words_per_line") or 6)
    max_total = int(limits.get("max_total_words") or max_per_line * 3)
    dialogue_fields = ("man_a_dialogue", "man_b_dialogue", "pivot_dialogue")
    counts = {field: _word_count(normalized[field]) for field in dialogue_fields}
    too_long = [field for field, count in counts.items() if count > max_per_line]
    if too_long:
        raise ValueError(
            "Dialogue exceeds max_words_per_line for: " + ", ".join(too_long)
        )
    if sum(counts.values()) > max_total:
        raise ValueError("Combined dialogue exceeds max_total_words.")
    return normalized


def _speaker_positions(request: dict[str, Any]) -> tuple[str, str]:
    assignment = request.get("speaker_assignment")
    if not isinstance(assignment, dict):
        assignment = {}
    man_a = str(assignment.get("MAN_A") or "camera-left").strip()
    man_b = str(assignment.get("MAN_B") or "camera-right").strip()
    if not man_a or not man_b or man_a.casefold() == man_b.casefold():
        raise ValueError(
            "speaker_assignment must give MAN_A and MAN_B different positions."
        )
    return man_a, man_b


def _duration_seconds(request: dict[str, Any]) -> int:
    raw = request.get("duration_seconds", 8)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError("duration_seconds must be an integer between 6 and 12.")
    duration = int(raw)
    if duration != raw or duration < 6 or duration > 12:
        raise ValueError("duration_seconds must be an integer between 6 and 12.")
    return duration


def _build_positive_prompt(
    result: dict[str, str],
    *,
    request: dict[str, Any],
    duration: int,
) -> str:
    man_a_position, man_b_position = _speaker_positions(request)
    first_end = duration * 0.34
    second_end = duration * 0.69
    return " ".join(
        [
            f"Style: {result['visual_style']}.",
            (
                "Use the supplied source image as the exact first frame and preserve "
                "both men's facial identity, age, hair, wardrobe, seating positions, "
                "microphones, furniture, studio layout, lighting, and composition."
            ),
            result["setting_description"].rstrip(".") + ".",
            (
                f"From 0.0 to {first_end:.1f} seconds, MAN_A at {man_a_position} "
                f"{result['man_a_action'].rstrip('.')} and says in a measured natural "
                f"male broadcast voice, \"{result['man_a_dialogue']}\" MAN_B at "
                f"{man_b_position} keeps his mouth closed, listens, and gives one "
                "subtle reaction."
            ),
            (
                f"From {first_end:.1f} to {second_end:.1f} seconds, MAN_B at "
                f"{man_b_position} {result['man_b_action'].rstrip('.')} and replies "
                f"in a distinct calm male conversational voice, "
                f"\"{result['man_b_dialogue']}\" MAN_A keeps his mouth closed and "
                "listens naturally."
            ),
            (
                f"From {second_end:.1f} to {duration:.1f} seconds, MAN_A at "
                f"{man_a_position} pivots to {result['pivot_topic']}, "
                f"{result['pivot_action'].rstrip('.')}, and says, "
                f"\"{result['pivot_dialogue']}\" MAN_B remains silent and attentive."
            ),
            (
                f"The camera uses {result['camera_motion'].rstrip('.')}, remains one "
                "continuous shot, and never cuts or changes the set."
            ),
            (
                f"Audio: {result['ambient_audio'].rstrip('.')}; clean close-microphone "
                "dialogue, quiet treated-room ambience, no music, no narrator, no "
                "overlapping speech."
            ),
        ]
    )


def _build_negative_prompt(result: dict[str, str]) -> str:
    fixed = str(_load_contract()["fixed_negative_prompt"]).strip().rstrip(",")
    generated = result["negative_prompt"].strip().strip(",")
    return f"{fixed}, {generated}" if generated else fixed


def _image_data_url(image: Any) -> str | None:
    if image is None:
        return None
    try:
        import numpy as np
        from PIL import Image

        tensor = image[0] if getattr(image, "ndim", 0) >= 4 else image
        array = tensor.detach().cpu().numpy()
        array = np.clip(array, 0.0, 1.0)
        array = (array * 255.0).round().astype(np.uint8)
        pil = Image.fromarray(array)
        if pil.mode not in {"RGB", "L"}:
            pil = pil.convert("RGB")
        if max(pil.size) > 1024:
            pil.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        pil.save(buffer, format="JPEG", quality=88, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception as exc:
        raise RuntimeError(f"Unable to prepare the planner image: {exc}") from exc


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = _canonical_json(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(
            f"LM Studio returned HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"LM Studio is unavailable at 127.0.0.1:1234: {exc}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("LM Studio response exceeded the safety limit.")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("LM Studio returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("LM Studio returned an invalid response envelope.")
    return decoded


def _model_entries() -> list[dict[str, Any]]:
    response = _http_json(f"{LM_STUDIO_ROOT}/api/v1/models", timeout=20.0)
    models = response.get("models")
    return [item for item in models or [] if isinstance(item, dict)]


def _entry_matches_model(entry: dict[str, Any], model: str) -> bool:
    variants = entry.get("variants")
    if not isinstance(variants, list):
        variants = []
    identities = {
        str(entry.get("key") or "").strip(),
        str(entry.get("id") or "").strip(),
        *(str(item or "").strip() for item in variants),
    }
    return model in identities


def _resolve_model_entry(model: str) -> tuple[dict[str, Any], str]:
    matches = [entry for entry in _model_entries() if _entry_matches_model(entry, model)]
    if not matches:
        raise RuntimeError(
            f"LM Studio does not contain the exact requested model key {model!r}. "
            "Aliases and loaded-instance IDs are rejected because their VRAM "
            "unload cannot be proven safely."
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"LM Studio model identifier {model!r} is ambiguous; use one exact "
            "catalog key."
        )
    entry = matches[0]
    canonical_key = str(entry.get("key") or entry.get("id") or "").strip()
    if not canonical_key:
        raise RuntimeError("The matched LM Studio model has no stable catalog key.")
    return entry, canonical_key


def _validate_trusted_model_package(model: str) -> dict[str, Any]:
    contract = _load_contract()
    trusted_models = contract.get("trusted_planner_models")
    if not isinstance(trusted_models, dict) or model not in trusted_models:
        raise RuntimeError(
            f"Planner model {model!r} is not approved by the JSON trust contract."
        )
    package = trusted_models[model]
    if not isinstance(package, dict):
        raise RuntimeError(f"Trusted planner package for {model!r} is invalid.")

    root_value = str(contract.get("trusted_lm_studio_model_root") or "").strip()
    root = Path(root_value)
    if not root.is_absolute():
        raise RuntimeError("The trusted LM Studio model root must be absolute.")
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(
            f"Trusted LM Studio model root is unavailable: {root}"
        ) from exc
    if not resolved_root.is_dir():
        raise RuntimeError(
            f"Trusted LM Studio model root is not a directory: {resolved_root}"
        )

    relative_files = package.get("required_relative_files")
    if not isinstance(relative_files, list) or not relative_files:
        raise RuntimeError(
            f"Trusted planner package for {model!r} has no required files."
        )
    verified_files: list[dict[str, Any]] = []
    for relative_value in relative_files:
        relative_path = Path(str(relative_value or "").strip())
        if not str(relative_path) or relative_path.is_absolute():
            raise RuntimeError(
                f"Trusted planner file path {relative_value!r} must be relative."
            )
        try:
            candidate = (resolved_root / relative_path).resolve(strict=True)
            candidate.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"Trusted planner file is unavailable inside {resolved_root}: "
                f"{relative_value}"
            ) from exc
        if not candidate.is_file():
            raise RuntimeError(f"Trusted planner model file is missing: {candidate}")
        verified_files.append(
            {
                "relative_path": relative_path.as_posix(),
                "size_bytes": candidate.stat().st_size,
            }
        )
    return {
        "model": model,
        "root": str(resolved_root),
        "files": verified_files,
    }


def _loaded_instance_ids(
    *,
    model: str | None = None,
    except_model: str | None = None,
) -> list[str]:
    if model and except_model:
        raise ValueError("model and except_model cannot be combined.")
    found: list[str] = []
    for entry in _model_entries():
        if model and not _entry_matches_model(entry, model):
            continue
        if except_model and _entry_matches_model(entry, except_model):
            continue
        for instance in entry.get("loaded_instances") or []:
            if not isinstance(instance, dict):
                continue
            instance_id = str(instance.get("id") or "").strip()
            if instance_id and instance_id not in found:
                found.append(instance_id)
    return found


def _unload_instance(instance_id: str) -> None:
    _http_json(
        f"{LM_STUDIO_ROOT}/api/v1/models/unload",
        method="POST",
        payload={"instance_id": instance_id},
        timeout=60.0,
    )


def _unload_loaded_lm_studio_models(*, except_model: str | None = None) -> None:
    unload_errors: list[str] = []
    try:
        instance_ids = _loaded_instance_ids(except_model=except_model)
    except Exception as exc:
        raise RuntimeError(f"Could not inspect LM Studio before unload: {exc}") from exc
    for instance_id in instance_ids:
        try:
            _unload_instance(instance_id)
        except Exception as exc:
            unload_errors.append(f"{instance_id}: {exc}")
    if unload_errors:
        raise RuntimeError(
            "LM Studio model unload failed: " + " | ".join(unload_errors)
        )

    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        remaining = _loaded_instance_ids(except_model=except_model)
        if not remaining:
            return
        time.sleep(0.5)
    raise RuntimeError(
        "LM Studio still reports model instances that should have been unloaded; "
        "generation was stopped to prevent a VRAM collision."
    )


def _unload_all_lm_studio_models() -> None:
    _unload_loaded_lm_studio_models()


def _release_comfy_models() -> None:
    try:
        import comfy.model_management as model_management

        model_management.unload_all_models()
        model_management.soft_empty_cache()
    except Exception as exc:
        raise RuntimeError(
            "Could not release ComfyUI models before loading local Qwen; "
            "generation was stopped to protect VRAM."
        ) from exc


def _image_tensor_sha256(image: Any) -> str | None:
    if image is None:
        return None
    try:
        tensor = image.detach().cpu().contiguous()
        array = tensor.numpy()
        digest = hashlib.sha256()
        digest.update(_canonical_json(list(array.shape)).encode("utf-8"))
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(array.tobytes(order="C"))
        return digest.hexdigest()
    except Exception as exc:
        raise RuntimeError(f"Unable to hash the source image tensor: {exc}") from exc


def _chat_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LM Studio response has no choices.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise ValueError("LM Studio response has no final JSON content.")


def _video_seed(variation_seed: int) -> int:
    digest = hashlib.sha256(f"sineforge-ltx-video:{variation_seed}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _request_hash(request: dict[str, Any], recent_topics: list[Any]) -> str:
    return hashlib.sha256(
        _canonical_json({"request": request, "recent_topics": recent_topics}).encode(
            "utf-8"
        )
    ).hexdigest()


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
                "name": "sineforge_ltx23_podcast_variation",
                "strict": True,
                "schema": contract["response_schema"],
            },
        },
    }


class SineForgeLTXPodcastPlanner:
    """Generate strict podcast JSON locally, then unload Qwen before LTX."""

    CATEGORY = "SineForge/Planning"
    FUNCTION = "generate"
    RETURN_TYPES = (
        "STRING",
        "STRING",
        "STRING",
        "INT",
        "INT",
        "INT",
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "prompt_json",
        "positive_prompt",
        "negative_prompt",
        "variation_seed",
        "video_seed",
        "duration_seconds",
        "output_prefix",
        "status_json",
    )
    DESCRIPTION = (
        "Uses local LM Studio Qwen 3.6 40B to create a fresh strict-JSON "
        "two-person podcast variation from an image. It releases ComfyUI "
        "models first and refuses to return until every LM Studio model is "
        "unloaded, preventing local-LLM/LTX VRAM overlap. The JSON contract "
        "also verifies the exact package beneath the trusted LM Studio model "
        "root. No cloud or API key is used."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        contract = _load_contract()
        return {
            "required": {
                "model": (
                    "STRING",
                    {
                        "default": contract["planner_model"],
                        "multiline": False,
                    },
                ),
                "variation_mode": (
                    list(VARIATION_MODES),
                    {"default": VARIATION_MODES[0]},
                ),
                "seed": (
                    "INT",
                    {
                        "default": 20260730,
                        "min": 0,
                        "max": 0x7FFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                    },
                ),
                "topic_request_json": (
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
                "recent_topics_json": (
                    "STRING",
                    {
                        "default": "[]",
                        "multiline": True,
                    },
                ),
                "temperature": (
                    "FLOAT",
                    {
                        "default": 0.9,
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
                        "default": 1600,
                        "min": 256,
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
            "topic_request_json": kwargs.get("topic_request_json"),
            "recent_topics_json": kwargs.get("recent_topics_json"),
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
        topic_request_json: str | None = None,
        recent_topics_json: str | None = None,
        **_: Any,
    ) -> bool | str:
        if not str(model or "").strip():
            return "Select the installed local Qwen model."
        if variation_mode not in VARIATION_MODES:
            return "variation_mode is invalid."
        try:
            request = _parse_json_object(
                str(topic_request_json or ""),
                label="topic_request_json",
            )
            _speaker_positions(request)
            _duration_seconds(request)
            _parse_json_list(
                str(recent_topics_json or ""),
                label="recent_topics_json",
            )
            _validate_trusted_model_package(str(model or "").strip())
        except ValueError as exc:
            return str(exc)
        except RuntimeError as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        variation_mode: str,
        seed: int,
        topic_request_json: str,
        recent_topics_json: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout_seconds: int,
        image: Any = None,
    ) -> tuple[str, str, str, int, int, int, str, str]:
        model = str(model or "").strip()
        request = _parse_json_object(
            topic_request_json,
            label="topic_request_json",
        )
        recent_topics = _parse_json_list(
            recent_topics_json,
            label="recent_topics_json",
        )
        duration = _duration_seconds(request)
        _speaker_positions(request)
        contract = _load_contract()
        categories = list(contract["category_hints"])
        if len(categories) < 2:
            raise RuntimeError("Podcast prompt contract needs at least two categories.")

        if variation_mode == VARIATION_MODES[0]:
            variation_seed = secrets.randbelow(0x7FFFFFFFFFFFFFFF)
        elif variation_mode == VARIATION_MODES[1]:
            variation_seed = int(seed)
        else:
            raise ValueError("variation_mode is invalid.")
        video_seed = _video_seed(variation_seed)
        primary_index = variation_seed % len(categories)
        pivot_index = (variation_seed // len(categories) + 7) % len(categories)
        if pivot_index == primary_index:
            pivot_index = (pivot_index + 1) % len(categories)

        user_payload = {
            "schema_version": "sineforge.ltx23-podcast-planner-call/v1",
            "variation_seed": variation_seed,
            "request": request,
            "novelty": {
                "primary_category_hint": categories[primary_index],
                "pivot_category_hint": categories[pivot_index],
                "recent_topics_to_avoid": recent_topics[-50:],
                "instruction": (
                    "Choose specific topics and wording that do not repeat the "
                    "recent topics. The two new topics must be unrelated."
                ),
            },
            "image": {
                "attached": image is not None,
                "instruction": (
                    "Inspect the image for stable visual details, but do not infer "
                    "names, ethnicity, religion, politics, health, or other "
                    "sensitive traits from appearance."
                ),
            },
        }
        request_sha256 = _request_hash(request, recent_topics)
        source_image_sha256: str | None = None
        image_url: str | None = None
        resolved_model = model
        planner_result: dict[str, str] | None = None
        planner_error: Exception | None = None
        unload_error: Exception | None = None
        attempt_errors: list[str] = []
        trusted_package: dict[str, Any] | None = None
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
                            "Return a corrected object within the same strict "
                            "schema and dialogue word limits."
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
                    planner_result = _validate_planner_result(
                        parsed,
                        request=request,
                    )
                    break
                except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                    attempt_errors.append(str(exc))
            if planner_result is None:
                raise RuntimeError(
                    "Local Qwen did not produce a valid podcast JSON object after "
                    "two attempts: " + " | ".join(attempt_errors)
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
                f"Qwen planning finished, but LM Studio cleanup failed: "
                f"{unload_error} LTX was not started."
            ) from unload_error
        if planner_result is None:
            raise RuntimeError("Local Qwen returned no validated podcast plan.")

        positive_prompt = _build_positive_prompt(
            planner_result,
            request=request,
            duration=duration,
        )
        negative_prompt = _build_negative_prompt(planner_result)
        record: dict[str, Any] = {
            "schema_version": "sineforge.ltx23-podcast-variation/v1",
            "variation_id": f"podcast-{variation_seed:016x}",
            "variation_seed": variation_seed,
            "video_seed": video_seed,
            "planner": {
                "provider": "local_lm_studio",
                "requested_model": model,
                "model": resolved_model,
                "endpoint": "loopback",
                "temperature": float(temperature),
                "top_p": float(top_p),
                "model_unloaded_before_ltx": True,
                "all_lm_studio_models_unloaded_before_ltx": True,
                "trusted_package": trusted_package,
            },
            "request_sha256": request_sha256,
            "request": request,
            "recent_topics": recent_topics,
            "source_image": {
                "attached": image is not None,
                "tensor_sha256": source_image_sha256,
            },
            "novelty": user_payload["novelty"],
            "speaker_assignment": request.get("speaker_assignment"),
            "duration_seconds": duration,
            "frame_rate": 24,
            "batch_size": 1,
            "render_mode": "image_to_video_native_audio",
            **planner_result,
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
        }
        hash_source = _canonical_json(record)
        record["prompt_sha256"] = hashlib.sha256(
            hash_source.encode("utf-8")
        ).hexdigest()
        prompt_json = json.dumps(record, ensure_ascii=False, indent=2)
        output_prefix = (
            f"SineForge/LTX23_Podcast/{record['variation_id']}"
        )
        status_json = json.dumps(
            {
                "ok": True,
                "variation_id": record["variation_id"],
                "variation_seed": variation_seed,
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
            positive_prompt,
            negative_prompt,
            variation_seed,
            video_seed,
            duration,
            output_prefix,
            status_json,
        )


__all__ = [
    "SineForgeLTXPodcastPlanner",
    "VARIATION_MODES",
    "_build_positive_prompt",
    "_duration_seconds",
    "_load_contract",
    "_validate_planner_result",
]
