"""Structured Phase 1 script enrichment with the local Sulphur model."""

from __future__ import annotations

import json
from typing import Any

import httpx

from backend.app.core.config import Settings, get_settings
from backend.app.services.lm_studio_models import get_active_lm_studio_model_id
from backend.app.services.clip_planning import (
    MAX_CLIP_DURATION_SEC,
    MIN_CLIP_DURATION_SEC,
    NOMINAL_CLIP_DURATION_SEC,
    plan_scenes_for_duration,
)


_ENHANCEMENT_FIELDS = (
    "logline",
    "short_synopsis",
    "detailed_treatment",
    "complete_script",
    "narration_script",
    "dialogue_script",
    "non_dialogue_action",
    "silent_visual_beats",
    "emotional_progression",
    "dramatic_escalation",
    "narrative_structure",
)

_SYSTEM_PROMPT = (
    "You are Sulphur, CineForge's local script and prompt enhancer. "
    "Return only one JSON object. Enrich cinematic language and production usefulness "
    "without adding unsupported characters, locations, objects, events, claims, or side effects. "
    "Preserve every source event, the four-movement structure, explicit ACTION/NARRATION/DIALOGUE "
    "labels, intentional silent beats, the requested target duration, and the supplied short-clip "
    "scene plan. Do not return analysis, "
    "markdown fences, shell commands, file paths, ComfyUI payloads, or hidden reasoning."
)


def _schema() -> dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "logline": {"type": "string"},
            "short_synopsis": {"type": "string"},
            "detailed_treatment": {"type": "string"},
            "complete_script": {"type": "string"},
            "narration_script": {"type": "string"},
            "dialogue_script": {"type": "string"},
            "non_dialogue_action": string_array,
            "silent_visual_beats": string_array,
            "emotional_progression": string_array,
            "dramatic_escalation": string_array,
            "narrative_structure": {
                "type": "object",
                "properties": {
                    "opening": {"type": "string"},
                    "middle": {"type": "string"},
                    "climax": {"type": "string"},
                    "resolution": {"type": "string"},
                },
                "required": ["opening", "middle", "climax", "resolution"],
                "additionalProperties": False,
            },
        },
        "required": list(_ENHANCEMENT_FIELDS),
        "additionalProperties": False,
    }


def _validated_enhancement(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Sulphur enhancement was not a JSON object")
    missing = [field for field in _ENHANCEMENT_FIELDS if field not in value]
    if missing:
        raise ValueError(f"Sulphur enhancement omitted fields: {', '.join(missing)}")
    for field in _ENHANCEMENT_FIELDS[:6]:
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"Sulphur enhancement field '{field}' must be non-empty text")
    for field in _ENHANCEMENT_FIELDS[6:10]:
        if (
            not isinstance(value[field], list)
            or len(value[field]) < 4
            or not all(isinstance(item, str) and item.strip() for item in value[field])
        ):
            raise ValueError(f"Sulphur enhancement field '{field}' must contain four text items")
    structure = value["narrative_structure"]
    if not isinstance(structure, dict) or not all(
        isinstance(structure.get(key), str) and structure[key].strip()
        for key in ("opening", "middle", "climax", "resolution")
    ):
        raise ValueError("Sulphur enhancement narrative_structure is incomplete")
    return {field: value[field] for field in _ENHANCEMENT_FIELDS}


def enhance_phase_one_package(
    *,
    original_prompt: str,
    target_duration_sec: float,
    creative_direction: dict[str, Any],
    baseline_package: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Return validated enhancement fields; callers retain deterministic fallback."""

    cfg = settings or get_settings()
    if not (cfg.sulphur_configured and cfg.sulphur_phase_one_enabled):
        raise RuntimeError("Sulphur Phase 1 enhancement is disabled")

    baseline = {
        field: baseline_package.get(field)
        for field in _ENHANCEMENT_FIELDS
    }
    scene_clip_plan = plan_scenes_for_duration(target_duration_sec)
    user_payload = {
        "task": "Enhance the complete CineForge Phase 1 script package.",
        "source_prompt": original_prompt[:16_000],
        "target_duration_sec": target_duration_sec,
        "planned_scene_count": scene_clip_plan.planned_scene_count,
        "scene_duration_plan_sec": list(scene_clip_plan.scene_duration_plan_sec),
        "clip_duration_policy": {
            "nominal_sec": NOMINAL_CLIP_DURATION_SEC,
            "minimum_sec": MIN_CLIP_DURATION_SEC,
            "maximum_sec": MAX_CLIP_DURATION_SEC,
        },
        "creative_direction": creative_direction,
        "baseline_package": baseline,
        "requirements": [
            "Keep at least four movement sections and all supported source events.",
            "Keep the complete script production-useful and at least as detailed as the baseline.",
            (
                f"Write for exactly {scene_clip_plan.planned_scene_count} Phase 2 scenes, "
                "following the supplied duration plan; each generated clip is 6-10 seconds."
            ),
            "Return exactly the requested JSON fields.",
        ],
    }
    body = {
        "model": get_active_lm_studio_model_id(cfg),
        "temperature": 0.35,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "cineforge_phase_one_enhancement",
                "strict": False,
                "schema": _schema(),
            },
        },
    }
    with httpx.Client(
        timeout=httpx.Timeout(cfg.sulphur_timeout_sec),
        follow_redirects=False,
    ) as client:
        response = client.post(
            f"{cfg.sulphur_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": "Bearer lm-studio",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        if len(response.content) > cfg.sulphur_max_response_bytes:
            raise ValueError("Sulphur response exceeded the configured byte limit")
        envelope = response.json()

    choices = envelope.get("choices") if isinstance(envelope, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Sulphur response did not contain message content")
    return _validated_enhancement(json.loads(content))
