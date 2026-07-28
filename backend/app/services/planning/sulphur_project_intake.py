"""Validated Sulphur intake for one-prompt CineForge project creation."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.config import Settings, get_settings
from backend.app.schemas.api import ProjectWorkspaceCreate, SulphurProjectPromptCreate
from backend.app.services.clip_planning import (
    MAX_CLIP_DURATION_SEC,
    MIN_CLIP_DURATION_SEC,
    NOMINAL_CLIP_DURATION_SEC,
    SceneClipPlan,
    plan_scenes_for_duration,
)


logger = logging.getLogger(__name__)

_OUTPUT_DIMENSIONS: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "16:9": ((1280, 720), (1920, 1080)),
    "9:16": ((720, 1280), (1080, 1920)),
    "2.39:1": ((1280, 536), (1920, 804)),
    "1:1": ((1024, 1024), (1920, 1920)),
}

_SYSTEM_PROMPT = (
    "You are Sulphur, CineForge's local project intake producer. "
    "Extract a complete production brief from the user's message and return only the requested JSON. "
    "Preserve explicit facts, creative constraints, runtime, audience, style, language, and format. "
    "Use conservative defaults only when a field is not supplied. Convert all requested runtimes to "
    "seconds. Do not return analysis, markdown, hidden reasoning, commands, file paths, credentials, "
    "ComfyUI payloads, or executable instructions. This is planning data only."
)


class SulphurProjectIntakeError(RuntimeError):
    """A sanitized local-model intake failure that must not create a project."""


class SulphurProjectBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    target_duration_sec: float = Field(ge=24, le=21_600)
    audience: str = Field(default="General audience", min_length=1, max_length=500)
    genre: str = Field(default="Cinematic narrative", min_length=1, max_length=300)
    tone: str = Field(default="Grounded, cinematic, human", min_length=1, max_length=500)
    point_of_view: str = Field(default="Third person", min_length=1, max_length=300)
    visual_style: str = Field(
        default="Photoreal cinematic realism",
        min_length=1,
        max_length=1000,
    )
    production_notes: str = Field(default="", max_length=4000)
    language: str = Field(default="English", min_length=1, max_length=100)
    narration_dialogue_preference: str = Field(default="", max_length=1000)
    source_fidelity_constraints: str = Field(default="", max_length=2000)
    content_constraints: str = Field(default="", max_length=2000)
    aspect_ratio: Literal["16:9", "9:16", "2.39:1", "1:1"] = "16:9"
    fps: float = Field(default=24, ge=1, le=120)


class SulphurProjectIntakeResult(BaseModel):
    brief: SulphurProjectBrief
    workspace_payload: ProjectWorkspaceCreate
    clip_plan: SceneClipPlan

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _generation_schema() -> dict[str, object]:
    """LM Studio-compatible grammar; Pydantic enforces all detailed bounds afterward."""

    string_fields = (
        "title",
        "description",
        "audience",
        "genre",
        "tone",
        "point_of_view",
        "visual_style",
        "production_notes",
        "language",
        "narration_dialogue_preference",
        "source_fidelity_constraints",
        "content_constraints",
    )
    properties: dict[str, object] = {
        field: {"type": "string"} for field in string_fields
    }
    properties.update(
        {
            "target_duration_sec": {"type": "number"},
            "aspect_ratio": {
                "type": "string",
                "enum": list(_OUTPUT_DIMENSIONS),
            },
            "fps": {"type": "number"},
        }
    )
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _response_content(envelope: object) -> str:
    if not isinstance(envelope, dict):
        raise SulphurProjectIntakeError("Sulphur returned an invalid response envelope")
    choices = envelope.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise SulphurProjectIntakeError("Sulphur returned no project brief")
    return content


def build_sulphur_project_intake(
    request: SulphurProjectPromptCreate,
    *,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> SulphurProjectIntakeResult:
    """Extract a validated brief, then prepare the existing atomic workspace request."""

    cfg = settings or get_settings()
    if not cfg.sulphur_configured:
        raise SulphurProjectIntakeError("Sulphur is not configured or its GGUF is unavailable")

    prompt = request.prompt.strip()
    body = {
        "model": cfg.sulphur_model_id,
        "temperature": 0.1,
        "max_tokens": 1800,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Create a complete CineForge project intake brief.",
                        "source_message": prompt,
                        "runtime_rule": (
                            "Convert the requested total length to seconds. The project will create "
                            "ceil(total_seconds / 8) scenes, with generated clips constrained to "
                            "6–10 seconds each. Use 300 seconds only if no runtime is provided."
                        ),
                        "defaults": {
                            "target_duration_sec": 300,
                            "aspect_ratio": "16:9",
                            "fps": 24,
                            "language": "English",
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "cineforge_sulphur_project_intake",
                "strict": False,
                "schema": _generation_schema(),
            },
        },
    }

    try:
        with httpx.Client(
            timeout=httpx.Timeout(cfg.sulphur_timeout_sec),
            follow_redirects=False,
            transport=transport,
        ) as client:
            response = client.post(
                f"{cfg.sulphur_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": "Bearer lm-studio",
                    "Content-Type": "application/json",
                    "Idempotency-Key": request.idempotency_key,
                },
                json=body,
            )
            response.raise_for_status()
            if len(response.content) > cfg.sulphur_max_response_bytes:
                raise SulphurProjectIntakeError(
                    "Sulphur project brief exceeded the configured response limit"
                )
            envelope = response.json()
        brief = SulphurProjectBrief.model_validate_json(_response_content(envelope))
    except SulphurProjectIntakeError:
        raise
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        raise SulphurProjectIntakeError(
            f"Sulphur could not produce a valid project brief ({exc.__class__.__name__})"
        ) from exc

    clip_plan = plan_scenes_for_duration(brief.target_duration_sec)
    if not clip_plan.durations_within_generation_range:
        raise SulphurProjectIntakeError(
            "The requested runtime cannot satisfy both the eight-second scene rule "
            "and the six-to-ten-second clip range"
        )

    preview, final = _OUTPUT_DIMENSIONS[brief.aspect_ratio]
    clip_note = (
        f"Scene generation plan: exactly {clip_plan.planned_scene_count} scenes for "
        f"{clip_plan.target_duration_sec:g} total seconds, using a nominal "
        f"{NOMINAL_CLIP_DURATION_SEC:g}-second clip target; every planned clip must remain "
        f"between {MIN_CLIP_DURATION_SEC:g} and {MAX_CLIP_DURATION_SEC:g} seconds."
    )
    production_notes = "\n\n".join(
        item for item in (brief.production_notes.strip(), clip_note) if item
    )
    workspace_payload = ProjectWorkspaceCreate(
        idempotency_key=request.idempotency_key,
        name=brief.title,
        auto_title=False,
        description=brief.description,
        source_mode="story",
        story_title=brief.title,
        # Preserve the full user message; extracted fields supplement rather than replace it.
        base_story=prompt,
        target_duration_sec=brief.target_duration_sec,
        audience=brief.audience,
        genre=brief.genre,
        tone=brief.tone,
        point_of_view=brief.point_of_view,
        visual_style=brief.visual_style,
        production_notes=production_notes,
        language=brief.language,
        narration_dialogue_preference=brief.narration_dialogue_preference or None,
        source_fidelity_constraints=brief.source_fidelity_constraints or None,
        content_constraints=brief.content_constraints or None,
        requested_chapter_count=max(1, min(5, (clip_plan.planned_scene_count + 7) // 8)),
        bootstrap_phase_plan=True,
        auto_approve_phases_through=5,
        run_phase_one=True,
        aspect_ratio=brief.aspect_ratio,
        preview_width=preview[0],
        preview_height=preview[1],
        final_width=final[0],
        final_height=final[1],
        fps=brief.fps,
        captions_enabled=True,
        audio_enabled=True,
        speaking_rate=1,
        prefer_hosted_providers=False,
        prefer_local_providers=True,
        allow_model_download=True,
        allow_rendering=True,
        require_production_plan_approval=True,
        orchestration_mode="Local-first",
        privacy_preference="Local-only Sulphur planning",
        quality_preference="Quality weighted",
        cost_sensitivity="Local compute preferred",
    )
    logger.info(
        "sulphur_project_intake_ready prompt_hash=%s target_seconds=%s scenes=%s model=%s",
        hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        clip_plan.target_duration_sec,
        clip_plan.planned_scene_count,
        cfg.sulphur_model_id,
    )
    return SulphurProjectIntakeResult(
        brief=brief,
        workspace_payload=workspace_payload,
        clip_plan=clip_plan,
    )
