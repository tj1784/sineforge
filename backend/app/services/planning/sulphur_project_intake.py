"""Validated Sulphur intake for one-prompt CineForge project creation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.config import Settings, get_settings
from backend.app.schemas.api import ProjectWorkspaceCreate, SulphurProjectPromptCreate
from backend.app.schemas.project_workflows import ProjectWorkflowLane
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
    "You are CineForge's selected local project intake producer. "
    "Extract a complete production brief from the user's message and return only the requested JSON. "
    "Preserve explicit facts, creative constraints, runtime, audience, style, language, and format. "
    "Use conservative defaults only when a field is not supplied. Convert all requested runtimes to "
    "seconds. Do not return analysis, markdown, hidden reasoning, commands, file paths, credentials, "
    "ComfyUI payloads, or executable instructions. This is planning data only."
)

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def _explicit_runtime_seconds(prompt: str) -> float | None:
    """Extract an explicit user runtime without trusting model arithmetic.

    The largest duration is selected so a total such as ``60 seconds`` wins
    over accompanying clip guidance such as ``8-second scenes``. Compound
    minute/second expressions are handled as one value.
    """

    text = prompt.casefold()
    candidates: list[float] = []
    compound_spans: list[tuple[int, int]] = []
    compound_pattern = re.compile(
        r"\b(?P<minutes>\d+(?:\.\d+)?)\s*[- ]*\s*"
        r"(?:minutes?|mins?)\s*(?:and\s*)?"
        r"(?P<seconds>\d+(?:\.\d+)?)\s*[- ]*\s*(?:seconds?|secs?)\b"
    )
    for match in compound_pattern.finditer(text):
        candidates.append(
            float(match.group("minutes")) * 60 + float(match.group("seconds"))
        )
        compound_spans.append(match.span())

    def in_compound(position: int) -> bool:
        return any(start <= position < end for start, end in compound_spans)

    numeric_pattern = re.compile(
        r"\b(?P<value>\d+(?:\.\d+)?)\s*[- ]*\s*"
        r"(?P<unit>hours?|hrs?|minutes?|mins?|seconds?|secs?)\b"
    )
    for match in numeric_pattern.finditer(text):
        if in_compound(match.start()):
            continue
        value = float(match.group("value"))
        unit = match.group("unit")
        multiplier = 3600 if unit.startswith(("hour", "hr")) else 60 if unit.startswith(("minute", "min")) else 1
        candidates.append(value * multiplier)

    word_pattern = re.compile(
        rf"\b(?P<value>{'|'.join(_NUMBER_WORDS)})\s*[- ]+\s*"
        r"(?P<unit>hours?|minutes?|seconds?)\b"
    )
    for match in word_pattern.finditer(text):
        value = float(_NUMBER_WORDS[match.group("value")])
        unit = match.group("unit")
        multiplier = 3600 if unit.startswith("hour") else 60 if unit.startswith("minute") else 1
        candidates.append(value * multiplier)

    if not candidates:
        return None
    runtime = max(candidates)
    if runtime < 24 or runtime > 21_600:
        raise SulphurProjectIntakeError(
            "Explicit project runtime must be between 24 seconds and 6 hours"
        )
    return runtime


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
    planning_agent: Literal["sulphur", "qwen", "grok"]
    intake_model: str

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
    if request.planning_agent == "sulphur":
        default_model_id = cfg.sulphur_model_id
    elif request.planning_agent == "grok":
        default_model_id = cfg.grok_model_id
    else:
        default_model_id = cfg.qwen_model_id
    model_id = request.planning_model_id or default_model_id
    if not cfg.sulphur_planning_enabled:
        agent_name = (
            "Sulphur 2 Base"
            if request.planning_agent == "sulphur"
            else "Grok"
            if request.planning_agent == "grok"
            else "Qwen3 4B Hivemind"
        )
        raise SulphurProjectIntakeError(
            f"{agent_name} local planning is disabled"
        )

    prompt = request.prompt.strip()
    body = {
        "model": model_id,
        "temperature": 0.1,
        "max_tokens": 1800,
        "messages": [
            {
                "role": "system",
                "content": json.dumps(
                    {
                        "schema_version": "sineforge.local-agent-system/v1",
                        "agent_role": "project_intake",
                        "instructions": [_SYSTEM_PROMPT],
                        "response_artifact_format": "json",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "schema_version": request.prompt_schema_version,
                        "prompt_artifact_format": request.prompt_artifact_format,
                        "workflow_lane": request.workflow_lane,
                        "planning_agent": request.planning_agent,
                        "planning_model_id": model_id,
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

    explicit_runtime = _explicit_runtime_seconds(prompt)
    if (
        explicit_runtime is not None
        and abs(float(brief.target_duration_sec) - explicit_runtime) > 0.001
    ):
        logger.warning(
            "sulphur_runtime_corrected model_seconds=%s explicit_seconds=%s",
            brief.target_duration_sec,
            explicit_runtime,
        )
        brief = brief.model_copy(
            update={"target_duration_sec": explicit_runtime}
        )

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
        workflow_lane=ProjectWorkflowLane.cineforge_studio,
        planning_agent=request.planning_agent,
        planning_model_id=model_id,
        prompt_artifact_format=request.prompt_artifact_format,
        prompt_schema_version=request.prompt_schema_version,
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
        auto_approve_phases_through=1,
        run_phase_one=True,
        run_phases_two_through_five=True,
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
        require_production_plan_approval=False,
        orchestration_mode="Local-first",
        privacy_preference=f"Local-only {request.planning_agent.title()} planning",
        quality_preference="Quality weighted",
        cost_sensitivity="Local compute preferred",
    )
    logger.info(
        "sulphur_project_intake_ready prompt_hash=%s target_seconds=%s scenes=%s model=%s",
        hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        clip_plan.target_duration_sec,
        clip_plan.planned_scene_count,
        model_id,
    )
    return SulphurProjectIntakeResult(
        brief=brief,
        workspace_payload=workspace_payload,
        clip_plan=clip_plan,
        planning_agent=request.planning_agent,
        intake_model=model_id,
    )
