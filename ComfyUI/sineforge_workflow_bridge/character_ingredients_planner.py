"""Local-only model planner for Krea 2 character Ingredients assets.

The node creates four strict, self-contained image prompts for one canonical
character: front face, three-quarter face, profile, and body turnaround.  Its
model dropdown is built only from GGUF packages physically installed beneath
the established podcast planner's exact LM Studio model root.  No endpoint,
credential, free-form prompt source, hosted model, or path outside that root
can be supplied by the workflow.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path
from typing import Any

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
    "krea2_character_ingredients_prompt_contract.json"
)
REFERENCE_ROLES = (
    "single canonical identity / character image",
)
MAX_SEED = 0x7FFFFFFFFFFFFFFF
GGUF_SUFFIX = re.compile(r"-gguf$", flags=re.IGNORECASE)


def _load_contract() -> dict[str, Any]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"SineForge character Ingredients prompt contract is invalid: {exc}"
        ) from exc

    required = {
        "schema_version",
        "planner_model",
        "trusted_lm_studio_model_root",
        "system_prompt",
        "default_character_profile",
        "character_profile_schema",
        "response_schema",
    }
    missing = sorted(required.difference(contract))
    if missing:
        raise RuntimeError(
            "SineForge character Ingredients prompt contract is missing: "
            + ", ".join(missing)
        )

    # The podcast planner owns the local model root and preferred model default.
    # This contract can discover other packages beneath that root, but cannot
    # redirect discovery elsewhere or silently replace the preferred default.
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
            "Character Ingredients trust lock differs from the approved local "
            "planner "
            "package for: " + ", ".join(mismatches)
        )

    for schema_name in ("character_profile_schema", "response_schema"):
        schema = contract.get(schema_name)
        if not isinstance(schema, dict):
            raise RuntimeError(f"{schema_name} must be one JSON Schema object.")
        if schema.get("type") != "object":
            raise RuntimeError(f"{schema_name} must describe one JSON object.")
        if schema.get("additionalProperties") is not False:
            raise RuntimeError(f"{schema_name} must reject additional properties.")
        properties = schema.get("properties")
        required_fields = schema.get("required")
        if not isinstance(properties, dict) or not isinstance(required_fields, list):
            raise RuntimeError(f"{schema_name} has an invalid property contract.")
        if set(properties) != set(required_fields):
            raise RuntimeError(
                f"{schema_name} must require every declared property."
            )
    return contract


def _local_model_root() -> Path:
    configured = Path(
        str(_load_contract()["trusted_lm_studio_model_root"]).strip()
    )
    if not configured.is_absolute():
        raise RuntimeError("The local LM Studio model root must be absolute.")
    try:
        root = configured.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(
            f"The local LM Studio model root is unavailable: {configured}"
        ) from exc
    if not root.is_dir():
        raise RuntimeError(f"The local LM Studio model root is not a directory: {root}")
    return root


def _package_key(directory_name: str) -> str:
    key = GGUF_SUFFIX.sub("", str(directory_name or "").strip()).casefold()
    if not key or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", key):
        raise RuntimeError(
            f"Cannot derive a safe LM Studio model key from package "
            f"{directory_name!r}."
        )
    return key


def _discover_local_model_packages() -> dict[str, dict[str, Any]]:
    """Inventory executable GGUF packages strictly below the configured root."""

    root = _local_model_root()
    package_directories: dict[Path, list[Path]] = {}
    for raw_path in root.rglob("*.gguf"):
        try:
            path = raw_path.resolve(strict=True)
            path.relative_to(root)
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"Local GGUF path escaped the approved model root: {raw_path}"
            ) from exc
        if not path.is_file():
            continue
        if path.name.casefold().startswith("mmproj"):
            continue
        package_directories.setdefault(path.parent, []).append(path)

    packages: dict[str, dict[str, Any]] = {}
    for directory, model_files in sorted(
        package_directories.items(),
        key=lambda item: item[0].as_posix().casefold(),
    ):
        try:
            relative_directory = directory.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(
                f"Local model package escaped the approved root: {directory}"
            ) from exc
        if not relative_directory.parts:
            raise RuntimeError(
                "GGUF model files must be contained in a named package directory."
            )
        key = _package_key(relative_directory.name)
        if key in packages:
            raise RuntimeError(
                f"Local LM Studio model key {key!r} is ambiguous across packages."
            )

        all_gguf_files: list[Path] = []
        for raw_file in directory.glob("*.gguf"):
            try:
                file_path = raw_file.resolve(strict=True)
                file_path.relative_to(root)
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    f"Local package file escaped the approved root: {raw_file}"
                ) from exc
            if file_path.is_file():
                all_gguf_files.append(file_path)

        file_records = []
        for file_path in sorted(
            all_gguf_files,
            key=lambda item: item.name.casefold(),
        ):
            stat = file_path.stat()
            file_records.append(
                {
                    "relative_path": file_path.relative_to(root).as_posix(),
                    "role": (
                        "vision_projector"
                        if file_path.name.casefold().startswith("mmproj")
                        else "model"
                    ),
                    "size_bytes": stat.st_size,
                    "modified_time_ns": stat.st_mtime_ns,
                }
            )
        packages[key] = {
            "model": key,
            "root": str(root),
            "publisher": (
                relative_directory.parts[0]
                if len(relative_directory.parts) > 1
                else ""
            ),
            "package": relative_directory.name,
            "relative_directory": relative_directory.as_posix(),
            "files": file_records,
            "supports_local_vision_files": any(
                item["role"] == "vision_projector" for item in file_records
            ),
        }
    if not packages:
        raise RuntimeError(
            f"No local GGUF model packages were found beneath {root}."
        )
    return packages


def _selectable_model_keys() -> tuple[str, ...]:
    packages = _discover_local_model_packages()
    preferred = str(_load_contract()["planner_model"]).strip()
    keys = sorted(packages, key=str.casefold)
    if preferred in packages:
        keys.remove(preferred)
        keys.insert(0, preferred)
    return tuple(keys)


def _resolve_local_model_package(model: str) -> dict[str, Any]:
    model = str(model or "").strip()
    packages = _discover_local_model_packages()
    package = packages.get(model)
    if package is None:
        raise RuntimeError(
            f"Planner model {model!r} is not an installed GGUF package beneath "
            f"{_local_model_root()}. Select one of: {', '.join(sorted(packages))}."
        )
    return package


def _parse_json_object(raw: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or ""))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object.")
    return value


def _validate_schema_object(
    value: Any,
    *,
    schema: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object.")

    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise RuntimeError(f"{label} schema is invalid.")

    missing = [field for field in required if field not in value]
    extra = sorted(set(value).difference(properties))
    if missing:
        raise ValueError(f"{label} is missing: " + ", ".join(missing))
    if extra:
        raise ValueError(
            f"{label} has unsupported keys: " + ", ".join(extra)
        )

    normalized: dict[str, Any] = {}
    for field, field_schema in properties.items():
        item = value[field]
        expected_type = field_schema.get("type")
        if expected_type == "string":
            if not isinstance(item, str):
                raise ValueError(f"{label}.{field} must be a string.")
            item = item.strip()
            min_length = field_schema.get("minLength")
            max_length = field_schema.get("maxLength")
            if isinstance(min_length, int) and len(item) < min_length:
                raise ValueError(
                    f"{label}.{field} is shorter than {min_length} characters."
                )
            if isinstance(max_length, int) and len(item) > max_length:
                raise ValueError(
                    f"{label}.{field} exceeds {max_length} characters."
                )
            allowed = field_schema.get("enum")
            if isinstance(allowed, list) and item not in allowed:
                raise ValueError(f"{label}.{field} is not an allowed value.")
            normalized[field] = item
            continue

        if expected_type == "array":
            if not isinstance(item, list):
                raise ValueError(f"{label}.{field} must be a JSON array.")
            min_items = field_schema.get("minItems")
            max_items = field_schema.get("maxItems")
            if isinstance(min_items, int) and len(item) < min_items:
                raise ValueError(
                    f"{label}.{field} needs at least {min_items} items."
                )
            if isinstance(max_items, int) and len(item) > max_items:
                raise ValueError(
                    f"{label}.{field} exceeds {max_items} items."
                )
            item_schema = field_schema.get("items") or {}
            if item_schema.get("type") != "string":
                raise RuntimeError(
                    f"{label}.{field} array schema must contain strings."
                )
            cleaned_items: list[str] = []
            for index, raw_item in enumerate(item):
                if not isinstance(raw_item, str):
                    raise ValueError(
                        f"{label}.{field}[{index}] must be a string."
                    )
                cleaned = raw_item.strip()
                item_min = item_schema.get("minLength")
                item_max = item_schema.get("maxLength")
                if isinstance(item_min, int) and len(cleaned) < item_min:
                    raise ValueError(
                        f"{label}.{field}[{index}] is shorter than "
                        f"{item_min} characters."
                    )
                if isinstance(item_max, int) and len(cleaned) > item_max:
                    raise ValueError(
                        f"{label}.{field}[{index}] exceeds "
                        f"{item_max} characters."
                    )
                cleaned_items.append(cleaned)
            normalized[field] = cleaned_items
            continue

        raise RuntimeError(
            f"{label}.{field} uses unsupported schema type {expected_type!r}."
        )
    return normalized


def _validate_character_profile(profile: Any) -> dict[str, Any]:
    return _validate_schema_object(
        profile,
        schema=_load_contract()["character_profile_schema"],
        label="character_profile_json",
    )


def _validate_planner_result(result: Any) -> dict[str, str]:
    validated = _validate_schema_object(
        result,
        schema=_load_contract()["response_schema"],
        label="Planner response",
    )
    normalized = {
        field: _safe_output_text(value, field=field)
        for field, value in validated.items()
    }
    prompt_fields = (
        "face_front_prompt",
        "face_three_quarter_prompt",
        "profile_prompt",
        "body_turnaround_prompt",
    )
    if len({normalized[field].casefold() for field in prompt_fields}) != 4:
        raise ValueError("Planner response must contain four different view prompts.")
    return normalized


def _derive_image_seed(variation_seed: int, index: int) -> int:
    digest = hashlib.sha256(
        (
            "sineforge-krea2-character-ingredients/v1:"
            f"{int(variation_seed)}:{int(index)}"
        ).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") & MAX_SEED


def _reference_manifest(images: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "role": REFERENCE_ROLES[index - 1],
            "attached": image is not None,
            "tensor_sha256": _image_tensor_sha256(image),
        }
        for index, image in enumerate(images, start=1)
    ]


def _planner_payload(
    *,
    model: str,
    seed: int,
    temperature: float,
    top_p: float,
    max_tokens: int,
    user_payload: dict[str, Any],
    reference_image_data_urls: list[str],
) -> dict[str, Any]:
    contract = _load_contract()
    user_text = _canonical_json(user_payload)
    user_content: Any = user_text
    if reference_image_data_urls:
        user_content = [
            {"type": "text", "text": user_text},
            *[
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                }
                for data_url in reference_image_data_urls
            ],
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
        # This LM Studio build accepts only json_schema or text. Its schema
        # grammar parser rejects this otherwise valid contract, so use text and
        # enforce JSON plus the full schema locally with a bounded repair retry.
        "response_format": {"type": "text"},
    }


def _safe_prefix_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:80] or "character"


class SineForgeKrea2CharacterIngredientsPlanner:
    """Create four strict Krea 2 character-reference prompts locally."""

    CATEGORY = "SineForge/Planning"
    FUNCTION = "generate"
    RETURN_TYPES = (
        "STRING",
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
    DESCRIPTION = (
        "Uses a selectable, locally installed LM Studio GGUF package to turn one "
        "strict character-profile JSON object and one identity image "
        "into four Krea 2 prompts for a clean Ingredients identity set. The "
        "dropdown is bounded to the approved local model root; the existing "
        "Qwen 3.6 40B is preferred by default. Every prompt source and provenance "
        "hash is saved in prompt_json. ComfyUI models are released before "
        "planning, and all LM Studio models are unloaded before the image prompts "
        "are returned."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        contract = _load_contract()
        model_keys = list(_selectable_model_keys())
        preferred_model = contract["planner_model"]
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
                        "max": MAX_SEED,
                        "control_after_generate": True,
                    },
                ),
                "character_profile_json": (
                    "STRING",
                    {
                        "default": json.dumps(
                            contract["default_character_profile"],
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "multiline": True,
                    },
                ),
                "temperature": (
                    "FLOAT",
                    {
                        "default": 0.55,
                        "min": 0.0,
                        "max": 2.0,
                        "step": 0.05,
                    },
                ),
                "top_p": (
                    "FLOAT",
                    {
                        "default": 0.9,
                        "min": 0.05,
                        "max": 1.0,
                        "step": 0.01,
                    },
                ),
                "max_tokens": (
                    "INT",
                    {
                        "default": 2600,
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
            "character_profile_json": kwargs.get("character_profile_json"),
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
        character_profile_json: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        timeout_seconds: int | None = None,
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
            profile = _parse_json_object(
                str(character_profile_json or ""),
                label="character_profile_json",
            )
            _validate_character_profile(profile)
            if temperature is not None and not 0.0 <= float(temperature) <= 2.0:
                return "temperature must be between 0.0 and 2.0."
            if top_p is not None and not 0.05 <= float(top_p) <= 1.0:
                return "top_p must be between 0.05 and 1.0."
            if max_tokens is not None and not 512 <= int(max_tokens) <= 8192:
                return "max_tokens must be between 512 and 8192."
            if timeout_seconds is not None and not 60 <= int(timeout_seconds) <= 3600:
                return "timeout_seconds must be between 60 and 3600."
        except (RuntimeError, ValueError, TypeError) as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        variation_mode: str,
        seed: int,
        character_profile_json: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout_seconds: int,
        reference_image: Any = None,
    ) -> tuple[
        str,
        str,
        str,
        str,
        str,
        int,
        int,
        int,
        int,
        str,
        str,
    ]:
        contract = _load_contract()
        model = str(model or "").strip()
        local_package = _resolve_local_model_package(model)
        if variation_mode == VARIATION_MODES[0]:
            variation_seed = secrets.randbelow(MAX_SEED)
        elif variation_mode == VARIATION_MODES[1]:
            variation_seed = int(seed)
        else:
            raise ValueError("variation_mode is invalid.")

        profile = _validate_character_profile(
            _parse_json_object(
                character_profile_json,
                label="character_profile_json",
            )
        )
        references = (reference_image,)
        image_seeds = tuple(
            _derive_image_seed(variation_seed, index)
            for index in range(1, 5)
        )
        reference_records: list[dict[str, Any]] = []
        reference_urls: list[str] = []
        resolved_model = model
        catalog_provenance: dict[str, Any] | None = None
        planner_result: dict[str, str] | None = None
        planner_error: Exception | None = None
        unload_error: Exception | None = None
        attempt_records: list[dict[str, Any]] = []
        user_payload: dict[str, Any] | None = None
        reference_delivery: dict[str, Any] | None = None

        try:
            reference_records = _reference_manifest(references)
            for image in references:
                data_url = _image_data_url(image)
                if data_url is not None:
                    reference_urls.append(data_url)

            user_payload = {
                "schema_version": (
                    "sineforge.krea2-character-ingredients-planner-call/v1"
                ),
                "variation_seed": variation_seed,
                "character_profile": profile,
                "reference_images": [
                    {
                        "index": item["index"],
                        "role": item["role"],
                        "attached": item["attached"],
                    }
                    for item in reference_records
                ],
                "generation_target": {
                    "image_model": "Krea 2",
                    "asset_type": "LTX-2.3 Ingredients character references",
                    "outputs": [
                        "face front",
                        "face three-quarter",
                        "profile",
                        "body turnaround",
                    ],
                    "instruction": (
                        "Write four self-contained prompts for the same canonical "
                        "character. Use the identity image delivered to the "
                        "selected model only in their declared order, preserve "
                        "identity and wardrobe, and never copy labels, borders, "
                        "watermarks, or unrelated people. When references were "
                        "omitted because the selected model is text-only, use the "
                        "strict character profile as the complete source."
                    ),
                },
            }

            model_entry, resolved_model = _resolve_model_entry(model)
            if resolved_model != model:
                raise RuntimeError(
                    f"LM Studio resolved local package {model!r} as "
                    f"{resolved_model!r}; aliases are rejected."
                )
            capabilities = model_entry.get("capabilities")
            if not isinstance(capabilities, dict):
                capabilities = {}
            model_supports_vision = capabilities.get("vision") is True
            planner_reference_urls = (
                reference_urls if model_supports_vision else []
            )
            attached_reference_count = len(reference_urls)
            sent_reference_count = len(planner_reference_urls)
            reference_delivery = {
                "selected_model_advertises_vision": model_supports_vision,
                "attached_reference_count": attached_reference_count,
                "sent_to_planner_count": sent_reference_count,
                "omitted_from_planner_count": (
                    attached_reference_count - sent_reference_count
                ),
                "omission_reason": (
                    None
                    if sent_reference_count == attached_reference_count
                    else "selected_local_model_does_not_advertise_vision"
                ),
            }
            for item in reference_records:
                item["sent_to_planner"] = bool(
                    item["attached"] and model_supports_vision
                )
            user_payload["reference_delivery"] = dict(reference_delivery)
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

            validation_errors: list[str] = []
            for attempt in range(2):
                attempt_payload = dict(user_payload)
                if validation_errors:
                    attempt_payload["repair"] = {
                        "attempt": attempt + 1,
                        "validation_errors": validation_errors[-1:],
                        "instruction": (
                            "Return a corrected object in the same strict JSON "
                            "schema. Do not omit, add, or rename keys."
                        ),
                    }
                attempt_seed = (variation_seed + attempt) & MAX_SEED
                request_sha256 = hashlib.sha256(
                    _canonical_json(attempt_payload).encode("utf-8")
                ).hexdigest()
                attempt_record = {
                    "attempt": attempt + 1,
                    "seed": attempt_seed,
                    "request_sha256": request_sha256,
                }
                try:
                    response = _http_json(
                        f"{LM_STUDIO_OPENAI_BASE}/chat/completions",
                        method="POST",
                        payload=_planner_payload(
                            model=resolved_model,
                            seed=attempt_seed,
                            temperature=temperature,
                            top_p=top_p,
                            max_tokens=max_tokens,
                            user_payload=attempt_payload,
                            reference_image_data_urls=planner_reference_urls,
                        ),
                        timeout=float(timeout_seconds),
                    )
                    raw_content = _chat_content(response)
                    attempt_record["response_sha256"] = hashlib.sha256(
                        raw_content.encode("utf-8")
                    ).hexdigest()
                    planner_result = _validate_planner_result(
                        json.loads(raw_content)
                    )
                    attempt_record["valid"] = True
                    attempt_records.append(attempt_record)
                    break
                except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                    validation_errors.append(str(exc))
                    if attempt == 0 and "unload" in str(exc).casefold():
                        _ensure_lm_studio_model_loaded(resolved_model)
                    attempt_record["valid"] = False
                    attempt_record["validation_error"] = str(exc)
                    attempt_records.append(attempt_record)
            if planner_result is None:
                raise RuntimeError(
                    "The selected local model did not produce valid character "
                    "Ingredients JSON after two attempts: "
                    + " | ".join(validation_errors)
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
                "Character planning finished, but LM Studio cleanup failed: "
                f"{unload_error} Krea 2 was not started."
            ) from unload_error
        if (
            planner_result is None
            or user_payload is None
            or reference_delivery is None
        ):
            raise RuntimeError(
                "The selected local model returned no character Ingredients plan."
            )

        contract_canonical = _canonical_json(contract)
        profile_canonical = _canonical_json(profile)
        request_canonical = _canonical_json(user_payload)
        contract_sha256 = hashlib.sha256(
            contract_canonical.encode("utf-8")
        ).hexdigest()
        profile_sha256 = hashlib.sha256(
            profile_canonical.encode("utf-8")
        ).hexdigest()
        request_sha256 = hashlib.sha256(
            request_canonical.encode("utf-8")
        ).hexdigest()
        character_slug = _safe_prefix_component(profile["character_id"])
        ingredients_id = (
            f"{character_slug}-{variation_seed:016x}"
        )
        record: dict[str, Any] = {
            "schema_version": "sineforge.krea2-character-ingredients/v1",
            "ingredients_id": ingredients_id,
            "variation_seed": variation_seed,
            "image_seeds": {
                "face_front": image_seeds[0],
                "face_three_quarter": image_seeds[1],
                "profile": image_seeds[2],
                "body_turnaround": image_seeds[3],
            },
            "planner": {
                "provider": "local_lm_studio",
                "requested_model": model,
                "model": resolved_model,
                "endpoint": "loopback",
                "temperature": float(temperature),
                "top_p": float(top_p),
                "max_tokens": int(max_tokens),
                "timeout_seconds": int(timeout_seconds),
                "all_lm_studio_models_unloaded_before_krea": True,
                "local_package": local_package,
                "lm_studio_catalog": catalog_provenance,
                "attempts": attempt_records,
            },
            "provenance": {
                "contract_path": CONTRACT_PATH.name,
                "contract_sha256": contract_sha256,
                "character_profile_sha256": profile_sha256,
                "planner_request_sha256": request_sha256,
                "reference_images": reference_records,
                "reference_delivery": reference_delivery,
            },
            "prompt_sources": {
                "system_json": contract["system_prompt"],
                "user_json": user_payload,
                "response_schema_json": contract["response_schema"],
            },
            "character_profile": profile,
            **planner_result,
        }
        record["prompt_sha256"] = hashlib.sha256(
            _canonical_json(record).encode("utf-8")
        ).hexdigest()
        output_prefix = (
            f"SineForge/Krea2_Character_Ingredients/{ingredients_id}"
        )
        prompt_json = json.dumps(record, ensure_ascii=False, indent=2)
        status_json = json.dumps(
            {
                "ok": True,
                "ingredients_id": ingredients_id,
                "variation_seed": variation_seed,
                "image_seeds": list(image_seeds),
                "attached_reference_count": sum(
                    1 for item in reference_records if item["attached"]
                ),
                "all_lm_studio_models_unloaded": True,
                "contract_sha256": contract_sha256,
                "character_profile_sha256": profile_sha256,
                "planner_request_sha256": request_sha256,
                "prompt_sha256": record["prompt_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
        return (
            prompt_json,
            planner_result["face_front_prompt"],
            planner_result["face_three_quarter_prompt"],
            planner_result["profile_prompt"],
            planner_result["body_turnaround_prompt"],
            image_seeds[0],
            image_seeds[1],
            image_seeds[2],
            image_seeds[3],
            output_prefix,
            status_json,
        )


__all__ = [
    "SineForgeKrea2CharacterIngredientsPlanner",
    "VARIATION_MODES",
    "_derive_image_seed",
    "_discover_local_model_packages",
    "_load_contract",
    "_planner_payload",
    "_resolve_local_model_package",
    "_selectable_model_keys",
    "_validate_character_profile",
    "_validate_planner_result",
]
