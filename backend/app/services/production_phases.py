"""Exact eight-phase production ledger and Phase 1 script generation.

This module is deliberately planning-text only.  It imports no media generator,
render queue, ComfyUI client, voice worker, model installer, or FFmpeg service.
Phase 1 stops at a versioned script package and QA report in
``ready_for_review`` or ``needs_revision``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.base import (
    AuditLog,
    Chapter,
    Character,
    CharacterReferenceAsset,
    PlanningMediaAsset,
    ProductionPhase,
    ProductionPhaseVersion,
    Project,
    ProjectStoryboardSettings,
    ProviderProfile,
    QAReport,
    Scene,
    Shot,
    ShotCharacter,
    ShotNarration,
    ShotPromptPackage,
    Story,
    TaskProviderAssignment,
    VoiceProfile,
)
from backend.app.schemas.production import (
    PhaseApproveRequest,
    PhaseApproveResponse,
    PhaseHistoryExport,
    PhaseHistoryExportIntegrity,
    PhaseOneGenerationInput,
    PhaseOneMutationResponse,
    PhaseOneRevisionRequest,
    PhaseVersionCreateRequest,
    PhaseVersionCreateResponse,
    PhaseVersionDetail,
    PhaseVersionRead,
    PhaseVersionSummary,
    ProductionPhaseRead,
    ProductionPipelineRead,
    QAReportRead,
)
from backend.app.schemas.project_workflows import is_agentless_workflow_lane
from backend.app.services.clip_planning import (
    MAX_CLIP_DURATION_SEC,
    MIN_CLIP_DURATION_SEC,
    NOMINAL_CLIP_DURATION_SEC,
    plan_scenes_for_duration,
)
from backend.app.services.lm_studio_models import (
    get_active_lm_studio_model_filename,
    get_active_lm_studio_model_id,
)
from backend.app.services.planning.sulphur_phase_one import enhance_phase_one_package


logger = logging.getLogger(__name__)

LEGACY_SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_SCHEMA_VERSION = 2
SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS = frozenset(
    {LEGACY_SNAPSHOT_SCHEMA_VERSION, SNAPSHOT_SCHEMA_VERSION}
)
PHASE_ONE_PACKAGE_SCHEMA = "cineforge.phase_one_script_package"
SUPPORTED_SOURCES = frozenset(
    {"baseline", "manual", "generated", "revision", "imported"}
)


PHASE_DEFINITIONS: tuple[tuple[int, str], ...] = (
    (1, "Script and Narrative Development"),
    (2, "Scene and Shot Segmentation"),
    (3, "Character Development"),
    (4, "Location and Key-Asset Development"),
    (5, "Production Prompt and Workflow Package"),
    (6, "Image and Voice Generation and Mapping"),
    (7, "Video Generation, Continuity, Assembly, and Picture Lock"),
    (8, "Foley, Audio Mix, Final Mux, and Delivery QA"),
)
LEGACY_PHASE_NAMES: dict[int, frozenset[str]] = {
    7: frozenset({"Video Generation, Assembly, and Final QA"}),
}
PHASE_EIGHT_PICTURE_LOCK_REQUIRED = (
    "Phase 8 remains locked until Phase 7 records an approved immutable picture "
    "lock with matching EDL, media, and technical-QA hashes. Planning approval "
    "alone is not media evidence."
)

COMPLETION_MESSAGE = "Your complete script is ready for review."
REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = (
    REPO_ROOT
    / "examples"
    / "projects"
    / "transfiguration_5m"
    / "phase_one_baseline.json"
)

_CONSTRAINT_PREFIXES = (
    "avoid ",
    "constraint",
    "do not ",
    "hard rule",
    "hard rule:",
    "must not ",
    "never ",
    "no ",
    "output ",
    "style ",
    "style:",
    "tone ",
    "tone:",
    "use ",
    "visual style",
    "visual style:",
)
_SPEECH_CUE_RE = re.compile(
    r"\b(?:asks?|commands?|declares?|replies?|says?|shouts?|speaks?|tells?|voices?|whispers?)\b",
    flags=re.IGNORECASE,
)
_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "again",
        "also",
        "been",
        "before",
        "being",
        "between",
        "could",
        "from",
        "have",
        "into",
        "more",
        "must",
        "only",
        "other",
        "should",
        "that",
        "their",
        "there",
        "these",
        "they",
        "this",
        "through",
        "with",
        "would",
    }
)
_FORBIDDEN_PHASE_ONE_KEYS = frozenset(
    {
        "characters",
        "comfy_job",
        "comfyui",
        "ffmpeg_job",
        "generation_jobs",
        "images",
        "locations",
        "render_jobs",
        "scenes",
        "shots",
        "starting_images",
        "videos",
        "voices",
        "workflow_routes",
    }
)


class ProductionPhaseError(ValueError):
    pass


class ProductionPhaseConflictError(ProductionPhaseError):
    pass


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9'’]+", value or "")


def _word_count(value: str) -> int:
    return len(_words(value))


def _shorten(value: str, max_words: int = 34) -> str:
    words = (value or "").strip().split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(" ,;:") + "…"


def _split_prompt(original_prompt: str) -> tuple[list[str], list[str]]:
    normalized = re.sub(r"\r\n?", "\n", original_prompt).strip()
    chunks = re.split(r"(?<=[.!?;])\s+|\n+", normalized)
    facts: list[str] = []
    constraints: list[str] = []
    for raw in chunks:
        text = re.sub(r"^[\s*#>\-–—\d.)]+", "", raw).strip()
        if len(text) < 3:
            continue
        lowered = text.casefold()
        if lowered.startswith(_CONSTRAINT_PREFIXES) or any(
            marker in lowered
            for marker in (
                "not the ascension",
                "does not fly",
                "does not ascend",
                "aspect ratio",
                "frames per second",
            )
        ):
            constraints.append(text)
        else:
            facts.append(text)

    if not facts:
        facts = [normalized]
    if len(facts) == 1 and len(facts[0].split(",")) >= 4:
        comma_facts = [item.strip() for item in facts[0].split(",") if len(item.strip()) > 8]
        if len(comma_facts) >= 3:
            facts = comma_facts
    return facts[:16], constraints


def _group_facts(facts: list[str], group_count: int = 4) -> list[list[str]]:
    groups: list[list[str]] = [[] for _ in range(group_count)]
    for index, fact in enumerate(facts):
        bucket = min(group_count - 1, int(index * group_count / max(1, len(facts))))
        groups[bucket].append(fact)
    previous = facts[0]
    for group in groups:
        if not group:
            group.append(previous)
        previous = group[-1]
    return groups


def _movement_name(index: int) -> str:
    return ("Opening", "Development", "Climax", "Resolution")[index]


def _movement_intent(index: int) -> str:
    return (
        "Establish the physical world, central relationship, and dramatic question without rushing.",
        "Let action and reaction deepen the stakes while every development remains traceable to the source.",
        "Concentrate the strongest change and emotional consequence into the dramatic high point.",
        "Let the consequence settle, resolve the central movement, and finish on a purposeful final image.",
    )[index]


def _build_phase_one_package(story: Story, payload: PhaseOneGenerationInput) -> dict[str, Any]:
    facts, prompt_constraints = _split_prompt(payload.original_prompt)
    groups = _group_facts(facts)
    target = round(float(payload.target_duration_sec), 3)
    scene_clip_plan = plan_scenes_for_duration(target)
    requested_chapter_count = max(1, int(payload.requested_chapter_count or 1))
    chapter_intake = list(payload.chapter_intake or [])
    movement_duration = target / 4
    narration_lines: list[str] = []
    dialogue_lines: list[str] = []
    action_lines: list[str] = []
    silent_beats: list[str] = []
    emotional_progression: list[str] = []
    dramatic_escalation: list[str] = []
    treatment_sections: list[str] = []
    script_sections: list[str] = []
    pacing_plan: list[dict[str, Any]] = []
    cumulative = 0.0

    quoted_dialogue = re.findall(r"[“\"]([^”\"]{2,300})[”\"]", payload.original_prompt)

    for index, group in enumerate(groups):
        name = _movement_name(index)
        intent = _movement_intent(index)
        group_text = " ".join(item.rstrip(".;") + "." for item in group)
        source_anchor = _shorten(group_text, 54)
        start = cumulative
        end = target if index == 3 else round(start + movement_duration, 3)
        duration = round(end - start, 3)
        cumulative = end

        treatment_sections.append(
            f"{name}: {intent} The source establishes: {group_text} "
            "The passage expands through observable action, human reaction, environmental change, "
            "and deliberate pauses rather than unsupported plot invention."
        )

        narration = _shorten(group_text, 72)
        narration_lines.append(narration)
        action = (
            f"Translate this source event into grounded non-dialogue action: {group_text} "
            f"Use {payload.visual_style or 'the selected visual direction'} to make cause, reaction, "
            "and consequence legible. Keep geography and physical behavior coherent; do not advance "
            "into events not supplied by the source."
        )
        action_lines.append(action)
        silent = (
            f"Hold a deliberate visual beat after “{_shorten(group_text, 20)}” so performance, "
            "environment, and emotional consequence can register without explanatory speech."
        )
        silent_beats.append(silent)
        emotional_progression.append(
            (
                "Orientation and anticipation",
                "Growing attention and uncertainty",
                "Overwhelming recognition and peak consequence",
                "Mercy, reflection, and resolved forward movement",
            )[index]
        )
        dramatic_escalation.append(
            f"{name}: move from {('introduction', 'complication', 'revelation', 'aftermath')[index]} "
            f"to the next supported consequence in the source: {_shorten(group_text, 24)}"
        )

        narration_words = _word_count(narration)
        spoken_seconds = round(narration_words / 145 * 60, 2)
        quoted_for_movement = quoted_dialogue[index] if index < len(quoted_dialogue) else None
        source_speech = next((fact for fact in group if _SPEECH_CUE_RE.search(fact)), None)
        dialogue_for_movement = quoted_for_movement
        if dialogue_for_movement is None and source_speech is not None:
            dialogue_for_movement = (
                "Source-required speech; exact wording requires human review: "
                f"{_shorten(source_speech, 54)}"
            )
        if dialogue_for_movement:
            dialogue_lines.append(dialogue_for_movement)
        dialogue_seconds = round(_word_count(dialogue_for_movement or "") / 135 * 60, 2)
        visual_seconds = round(max(0.0, duration - spoken_seconds - dialogue_seconds), 2)
        script_sections.append(
            "\n".join(
                (
                    f"## {name} · {start:06.2f}–{end:06.2f}",
                    f"**Narrative purpose:** {intent}",
                    f"**ACTION:** {action}",
                    f"**NARRATION:** {narration}",
                    (
                        f"**DIALOGUE:** {dialogue_for_movement}"
                        if dialogue_for_movement
                        else "**DIALOGUE:** No dialogue is required in this movement; performance and narration carry it."
                    ),
                    f"**SILENT VISUAL BEAT:** {silent}",
                    f"**SOURCE ANCHOR:** {source_anchor}",
                )
            )
        )
        pacing_plan.append(
            {
                "movement": name.casefold(),
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "duration_sec": duration,
                "narration_duration_sec": spoken_seconds,
                "dialogue_duration_sec": dialogue_seconds,
                "planned_visual_duration_sec": visual_seconds,
                "intent": intent,
            }
        )

    narration_script = "\n\n".join(narration_lines)
    dialogue_script = (
        "\n\n".join(dialogue_lines)
        if dialogue_lines
        else "No spoken character dialogue is required by the supplied source. Dialogue remains explicitly distinguished from narration."
    )
    complete_script = "\n\n".join(script_sections)
    narration_duration = round(_word_count(narration_script) / 145 * 60, 2)
    dialogue_duration = round(_word_count(" ".join(dialogue_lines)) / 135 * 60, 2)
    planned_visual_duration = round(max(0.0, target - narration_duration - dialogue_duration), 2)
    detailed_treatment = "\n\n".join(treatment_sections)
    source_notes = [
        "Every narrative movement retains a direct source anchor from the original prompt.",
        (
            f"Project creation requested {requested_chapter_count} chapter"
            f"{'' if requested_chapter_count == 1 else 's'} as Phase 2 planning guidance."
        ),
        (
            "Phase 2 must materialize exactly "
            f"{scene_clip_plan.planned_scene_count} scenes from total seconds divided by "
            f"{NOMINAL_CLIP_DURATION_SEC:g}, rounded up."
        ),
        "Macro movements are editorial guidance only; final scene and shot records remain reserved for Phase 2.",
    ]
    if payload.source_fidelity_constraints:
        source_notes.append(payload.source_fidelity_constraints.strip())
    source_notes.extend(prompt_constraints)
    if payload.content_constraints:
        source_notes.append(payload.content_constraints.strip())

    assumptions = [
        "The requested duration is achieved through supported action, reaction, environmental observation, and intentional silence.",
        "No new named character, location, object, or plot event was added beyond the supplied source.",
        "Dialogue is omitted unless quoted or clearly required by the supplied prompt.",
        (
            f"Generated clips use a nominal {NOMINAL_CLIP_DURATION_SEC:g}-second target "
            f"and remain between {MIN_CLIP_DURATION_SEC:g} and "
            f"{MAX_CLIP_DURATION_SEC:g} seconds."
        ),
    ]
    if payload.narration_dialogue_preference:
        assumptions.append(
            f"Narration/dialogue direction applied for review: {payload.narration_dialogue_preference.strip()}"
        )

    first_fact = _shorten(facts[0], 26).rstrip(".")
    last_fact = _shorten(facts[-1], 22).rstrip(".")
    package = {
        "schema_name": PHASE_ONE_PACKAGE_SCHEMA,
        "schema_version": 1,
        "project_title": story.title,
        "logline": f"{first_fact}, building toward {last_fact}.",
        "short_synopsis": (
            f"A {target / 60:g}-minute {payload.genre or 'cinematic'} narrative follows the source from "
            f"{_shorten(facts[0], 18).rstrip('.')} through {_shorten(facts[-1], 18).rstrip('.')}. "
            "The progression preserves the supplied events while allowing performance, atmosphere, "
            "and intentional silence to carry meaning."
        ),
        "detailed_treatment": detailed_treatment,
        "complete_script": complete_script,
        "narration_script": narration_script,
        "dialogue_script": dialogue_script,
        "non_dialogue_action": action_lines,
        "silent_visual_beats": silent_beats,
        "emotional_progression": emotional_progression,
        "dramatic_escalation": dramatic_escalation,
        "narrative_structure": {
            "opening": treatment_sections[0],
            "middle": "\n\n".join(treatment_sections[1:2]),
            "climax": treatment_sections[2],
            "resolution": treatment_sections[3],
        },
        "pacing_plan": pacing_plan,
        "chapter_planning": {
            "requested_chapter_count": requested_chapter_count,
            "provided_chapter_count": len(chapter_intake),
            "chapter_intake": chapter_intake,
            "phase_2_instruction": (
                "Use this as chapter-level planning guidance only. "
                "Do not treat it as persisted scene or shot segmentation until Phase 2."
            ),
        },
        "planned_scene_count": scene_clip_plan.planned_scene_count,
        "nominal_scene_duration_sec": NOMINAL_CLIP_DURATION_SEC,
        "clip_duration_range_sec": [
            MIN_CLIP_DURATION_SEC,
            MAX_CLIP_DURATION_SEC,
        ],
        "scene_duration_plan_sec": list(scene_clip_plan.scene_duration_plan_sec),
        "duration_analysis": {
            "target_duration_sec": target,
            "narration_word_count": _word_count(narration_script),
            "dialogue_word_count": _word_count(" ".join(dialogue_lines)),
            "narration_duration_sec": narration_duration,
            "dialogue_duration_sec": dialogue_duration,
            "planned_silence_visual_duration_sec": planned_visual_duration,
            "estimated_total_duration_sec": round(
                narration_duration + dialogue_duration + planned_visual_duration, 2
            ),
            "narration_wpm": 145,
            "dialogue_wpm": 135,
        },
        "script_word_count": _word_count(complete_script),
        "source_fidelity_notes": source_notes,
        "creative_assumptions": assumptions,
        "creative_direction": {
            "audience": payload.audience,
            "genre": payload.genre,
            "tone": payload.tone,
            "language": payload.language,
            "visual_style": payload.visual_style,
            "narration_dialogue_preference": payload.narration_dialogue_preference,
        },
        "generation_boundary": {
            "phase": 1,
            "text_only": True,
            "media_generated": False,
            "rendering_enabled": False,
            "final_scene_or_shot_segmentation_created": False,
        },
    }
    if payload.comparison_baseline:
        package["baseline_comparison"] = _compare_to_baseline(
            package, payload.comparison_baseline
        )
    return package


def _refresh_phase_one_metrics(
    package: dict[str, Any],
    payload: PhaseOneGenerationInput,
) -> None:
    """Recalculate bounded duration facts after text-only enhancement."""

    narration_script = str(package.get("narration_script") or "")
    dialogue_script = str(package.get("dialogue_script") or "")
    dialogue_words = (
        0
        if dialogue_script.startswith("No spoken character dialogue")
        else _word_count(dialogue_script)
    )
    narration_duration = round(_word_count(narration_script) / 145 * 60, 2)
    dialogue_duration = round(dialogue_words / 135 * 60, 2)
    target = round(float(payload.target_duration_sec), 3)
    planned_visual_duration = round(
        max(0.0, target - narration_duration - dialogue_duration),
        2,
    )
    package["script_word_count"] = _word_count(str(package.get("complete_script") or ""))
    package["duration_analysis"] = {
        **dict(package.get("duration_analysis") or {}),
        "target_duration_sec": target,
        "narration_word_count": _word_count(narration_script),
        "dialogue_word_count": dialogue_words,
        "narration_duration_sec": narration_duration,
        "dialogue_duration_sec": dialogue_duration,
        "planned_silence_visual_duration_sec": planned_visual_duration,
        "estimated_total_duration_sec": round(
            narration_duration + dialogue_duration + planned_visual_duration,
            2,
        ),
        "narration_wpm": 145,
        "dialogue_wpm": 135,
    }


def _apply_sulphur_phase_one_enhancement(
    package: dict[str, Any],
    payload: PhaseOneGenerationInput,
    *,
    required: bool = False,
) -> dict[str, Any]:
    """Use Sulphur when enabled, retaining the valid deterministic package on failure."""

    settings = get_settings()
    selected_agent = payload.planning_agent
    active_model_id = (
        payload.planning_model_id
        or get_active_lm_studio_model_id(settings)
    )
    active_model_file = get_active_lm_studio_model_filename(settings)
    if not (
        settings.sulphur_planning_enabled
        and settings.sulphur_phase_one_enabled
    ):
        if required:
            raise ProductionPhaseError(
                f"Selected local planning agent '{selected_agent}' is unavailable."
            )
        return package

    enhanced_package = dict(package)
    try:
        enhancement = enhance_phase_one_package(
            original_prompt=payload.original_prompt,
            target_duration_sec=float(payload.target_duration_sec),
            creative_direction=dict(package.get("creative_direction") or {}),
            baseline_package=package,
            model_id=active_model_id,
            settings=settings,
        )
        enhanced_package.update(enhancement)
        creative_direction = dict(enhanced_package.get("creative_direction") or {})
        creative_direction.update(
            {
                "script_provider": "local_lm_studio",
                "planning_agent": selected_agent,
                "script_model": active_model_id,
                "script_model_file": active_model_file,
                "prompt_artifact_format": payload.prompt_artifact_format,
                "prompt_schema_version": payload.prompt_schema_version,
            }
        )
        enhanced_package["creative_direction"] = creative_direction
        enhanced_package["source_fidelity_notes"] = [
            *list(enhanced_package.get("source_fidelity_notes") or []),
            (
                f"Script language was enhanced locally by {selected_agent}; "
                "deterministic QA remains authoritative."
            ),
        ]
        _refresh_phase_one_metrics(enhanced_package, payload)
        enhanced_qa = _qa_report(enhanced_package, payload)
        if not enhanced_qa.get("passed"):
            raise ValueError("Sulphur enhancement did not pass the Phase 1 QA contract")
        return enhanced_package
    except Exception as exc:
        logger.warning(
            "sulphur_phase_one_fallback error_type=%s",
            exc.__class__.__name__,
        )
        if required:
            raise ProductionPhaseError(
                f"Selected local planning agent '{selected_agent}' did not "
                "produce a valid structured JSON Phase 1 package."
            ) from exc
        fallback = dict(package)
        creative_direction = dict(fallback.get("creative_direction") or {})
        creative_direction.update(
            {
                "script_provider": "deterministic_fallback",
                "planning_agent": selected_agent,
                "script_model": active_model_id,
                "script_model_file": active_model_file,
                "prompt_artifact_format": payload.prompt_artifact_format,
                "prompt_schema_version": payload.prompt_schema_version,
            }
        )
        fallback["creative_direction"] = creative_direction
        fallback["source_fidelity_notes"] = [
            *list(fallback.get("source_fidelity_notes") or []),
            (
                f"{selected_agent} was requested but its structured enhancement did not pass the "
                "Phase 1 contract; the deterministic source-faithful script was retained."
            ),
        ]
        return fallback


def _scan_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).casefold() in _FORBIDDEN_PHASE_ONE_KEYS:
                found.append(child_path)
            found.extend(_scan_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_scan_forbidden_keys(child, f"{path}[{index}]"))
    return found


def _coverage_ratio(source: str, output: str) -> float:
    source_terms = {
        term.casefold()
        for term in _words(source)
        if len(term) >= 5 and term.casefold() not in _STOP_WORDS
    }
    if not source_terms:
        return 1.0
    output_terms = {term.casefold() for term in _words(output)}
    return round(len(source_terms & output_terms) / len(source_terms), 4)


def _qa_report(
    package: dict[str, Any], generation_input: PhaseOneGenerationInput
) -> dict[str, Any]:
    duration = dict(package.get("duration_analysis") or {})
    target = float(generation_input.target_duration_sec)
    estimated = float(duration.get("estimated_total_duration_sec") or 0)
    forbidden = _scan_forbidden_keys(package)
    coverage = _coverage_ratio(
        generation_input.original_prompt,
        " ".join(
            (
                str(package.get("detailed_treatment") or ""),
                str(package.get("complete_script") or ""),
                " ".join(package.get("source_fidelity_notes") or []),
            )
        ),
    )
    minimum_words = max(240, round(target * 1.1))
    expected_scene_clip_plan = plan_scenes_for_duration(target)
    actual_scene_durations = [
        float(item) for item in (package.get("scene_duration_plan_sec") or [])
    ]
    checks = [
        {
            "code": "scene_clip_plan",
            "label": "Scene count and short-clip durations match the total runtime",
            "passed": (
                int(package.get("planned_scene_count") or 0)
                == expected_scene_clip_plan.planned_scene_count
                and len(actual_scene_durations)
                == expected_scene_clip_plan.planned_scene_count
                and abs(sum(actual_scene_durations) - target) <= 0.01
                and all(
                    MIN_CLIP_DURATION_SEC <= item <= MAX_CLIP_DURATION_SEC
                    for item in actual_scene_durations
                )
            ),
            "blocking": True,
            "detail": (
                f"Planned {package.get('planned_scene_count', 0)} scenes using "
                f"ceil({target:g} / {NOMINAL_CLIP_DURATION_SEC:g}); clips must be "
                f"{MIN_CLIP_DURATION_SEC:g}-{MAX_CLIP_DURATION_SEC:g} seconds."
            ),
        },
        {
            "code": "source_fidelity",
            "label": "Original prompt remains represented",
            "passed": coverage >= 0.72,
            "blocking": True,
            "detail": f"Source-term coverage is {coverage:.0%} (minimum 72%).",
        },
        {
            "code": "narrative_structure",
            "label": "Beginning, progression, climax, and ending exist",
            "passed": all(
                str((package.get("narrative_structure") or {}).get(key) or "").strip()
                for key in ("opening", "middle", "climax", "resolution")
            ),
            "blocking": True,
            "detail": "Four macro narrative movements are present; no final scenes or shots were created.",
        },
        {
            "code": "production_length",
            "label": "Script is long enough for the requested runtime",
            "passed": int(package.get("script_word_count") or 0) >= minimum_words,
            "blocking": True,
            "detail": (
                f"Complete script contains {package.get('script_word_count', 0)} words; "
                f"minimum for this duration is {minimum_words}."
            ),
        },
        {
            "code": "duration_support",
            "label": "Spoken and visual duration support the target",
            "passed": abs(estimated - target) <= 0.5,
            "blocking": True,
            "detail": f"Estimated {estimated:.2f}s against a {target:.2f}s target.",
        },
        {
            "code": "speech_distinction",
            "label": "Narration and dialogue are explicitly distinguished",
            "passed": bool(str(package.get("narration_script") or "").strip())
            and bool(str(package.get("dialogue_script") or "").strip()),
            "blocking": True,
            "detail": "Narration and dialogue have separate editable fields and script labels.",
        },
        {
            "code": "intentional_silence",
            "label": "Silent visual beats are intentional",
            "passed": len(package.get("silent_visual_beats") or []) >= 4,
            "blocking": True,
            "detail": "Each macro movement includes a declared silent visual beat.",
        },
        {
            "code": "creative_consistency",
            "label": "Audience, tone, language, and style remain declared",
            "passed": bool((package.get("creative_direction") or {}).get("language")),
            "blocking": True,
            "detail": "Creative direction is stored with the versioned output for review.",
        },
        {
            "code": "assumptions_disclosed",
            "label": "Creative assumptions are disclosed",
            "passed": bool(package.get("creative_assumptions")),
            "blocking": True,
            "detail": "Assumptions are explicit and editable.",
        },
        {
            "code": "phase_boundary",
            "label": "Phase 1 produced no downstream production records",
            "passed": not forbidden
            and (package.get("generation_boundary") or {}).get("media_generated") is False
            and (package.get("generation_boundary") or {}).get("rendering_enabled") is False,
            "blocking": True,
            "detail": (
                "Text-only Phase 1 boundary is intact."
                if not forbidden
                else f"Forbidden downstream fields found: {', '.join(forbidden)}"
            ),
        },
    ]
    passed = all(item["passed"] or not item["blocking"] for item in checks)
    comparison = package.get("baseline_comparison")
    review_items = list((comparison or {}).get("review_items") or [])
    return {
        "schema_name": "cineforge.phase_qa_report",
        "schema_version": 1,
        "phase_number": 1,
        "passed": passed,
        "result": "pass" if passed else "fail",
        "checks": checks,
        "blocking_failures": [item for item in checks if item["blocking"] and not item["passed"]],
        "review_items": review_items,
        "baseline_comparison": comparison,
        "phase_boundary": {
            "images_generated": False,
            "voices_generated": False,
            "videos_generated": False,
            "comfyui_submitted": False,
            "ffmpeg_executed": False,
            "rendering_enabled": False,
        },
    }


def _compare_to_baseline(package: dict[str, Any], baseline_key: str) -> dict[str, Any]:
    if baseline_key != "transfiguration_phase_one":
        raise ProductionPhaseError(f"Unknown Phase 1 baseline: {baseline_key}")
    if not BASELINE_PATH.is_file():
        raise ProductionPhaseError(f"Phase 1 baseline is missing: {BASELINE_PATH}")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    narrative = " ".join(
        (
            str(package.get("detailed_treatment") or ""),
            str(package.get("complete_script") or ""),
            str(package.get("narration_script") or ""),
        )
    ).casefold()
    differences: list[dict[str, Any]] = []
    missing = 0
    for event in baseline.get("required_events") or []:
        alternatives = event.get("term_groups") or []
        matched = all(any(term.casefold() in narrative for term in group) for group in alternatives)
        classification = "equivalent" if matched else "missing"
        if not matched:
            missing += 1
        differences.append(
            {
                "item": event.get("label"),
                "classification": classification,
                "detail": "Required source event is represented." if matched else "Required source event was not found.",
            }
        )

    unsafe_hits = [
        phrase
        for phrase in baseline.get("unsafe_positive_assertions") or []
        if phrase.casefold() in narrative
    ]
    for phrase in unsafe_hits:
        differences.append(
            {
                "item": phrase,
                "classification": "unsafe",
                "detail": "Forbidden action appears as narrative action and requires correction.",
            }
        )

    duration_target = float(baseline.get("target_duration_sec") or 0)
    duration_actual = float(
        (package.get("duration_analysis") or {}).get("estimated_total_duration_sec") or 0
    )
    duration_ok = abs(duration_actual - duration_target) <= 0.5
    differences.append(
        {
            "item": "target duration",
            "classification": "equivalent" if duration_ok else "regression",
            "detail": f"Generated {duration_actual:.2f}s; baseline target {duration_target:.2f}s.",
        }
    )
    overall = (
        "unsafe"
        if unsafe_hits
        else "missing"
        if missing
        else "regression"
        if not duration_ok
        else "acceptable_variation"
    )
    review_items = list(baseline.get("required_human_review") or [])
    return {
        "baseline_key": baseline_key,
        "baseline_project_id": baseline.get("baseline_project_id"),
        "classification": overall,
        "differences": differences,
        "missing_count": missing,
        "unsafe_count": len(unsafe_hits),
        "review_items": review_items,
        "note": "Comparison evaluates coverage and safety, not exact wording.",
    }


def ensure_contract(db: Session, story: Story, *, commit: bool = False) -> list[ProductionPhase]:
    existing = list(
        db.scalars(
            select(ProductionPhase)
            .where(ProductionPhase.story_id == story.id)
            .order_by(ProductionPhase.phase_number)
        )
    )
    by_number = {item.phase_number: item for item in existing}
    created: list[ProductionPhase] = []
    for phase_number, name in PHASE_DEFINITIONS:
        phase = by_number.get(phase_number)
        if phase is None:
            phase = ProductionPhase(
                story_id=story.id,
                phase_number=phase_number,
                name=name,
                lifecycle_state="not_started",
                is_locked=phase_number != 1,
                locked_reason=(
                    None
                    if phase_number == 1
                    else PHASE_EIGHT_PICTURE_LOCK_REQUIRED
                    if phase_number == 8
                    else f"Phase {phase_number - 1} must be approved before this phase can begin."
                ),
                is_stale=False,
            )
            db.add(phase)
            created.append(phase)
        elif phase.name in LEGACY_PHASE_NAMES.get(phase_number, frozenset()):
            phase.name = name
        elif phase.name != name:
            raise ProductionPhaseError(
                f"Phase {phase_number} name drifted from the canonical eight-phase contract."
            )
    if created:
        db.flush()
        db.add(
            AuditLog(
                entity_type="story",
                entity_id=story.id,
                action="production_contract_initialized",
                details={
                    "exact_phase_count": 8,
                    "created_phase_numbers": [item.phase_number for item in created],
                },
            )
        )
    if commit:
        db.commit()
    return list(
        db.scalars(
            select(ProductionPhase)
            .where(ProductionPhase.story_id == story.id)
            .order_by(ProductionPhase.phase_number)
        )
    )


def _latest_version(db: Session, phase_id: UUID) -> ProductionPhaseVersion | None:
    return db.scalar(
        select(ProductionPhaseVersion)
        .where(ProductionPhaseVersion.production_phase_id == phase_id)
        .order_by(ProductionPhaseVersion.version_number.desc())
        .limit(1)
    )


def _is_phase_one_package(value: Any) -> bool:
    return isinstance(value, dict) and value.get("schema_name") == PHASE_ONE_PACKAGE_SCHEMA


def _latest_phase_one_package(
    db: Session, phase_id: UUID
) -> ProductionPhaseVersion | None:
    """Most recent Phase 1 script package version (generated or revised).

    Manual retains and baselines may sit on top as narrative snapshots; the UI
    and revision path must still resolve the last real script package.
    """
    rows = list(
        db.scalars(
            select(ProductionPhaseVersion)
            .where(ProductionPhaseVersion.production_phase_id == phase_id)
            .order_by(ProductionPhaseVersion.version_number.desc())
        )
    )
    for row in rows:
        if _is_phase_one_package(row.output_json):
            return row
    return None


def _latest_qa(db: Session, version_id: UUID) -> QAReport | None:
    return db.scalar(
        select(QAReport)
        .where(
            QAReport.entity_type == "production_phase_version",
            QAReport.entity_id == version_id,
        )
        .order_by(QAReport.created_at.desc())
        .limit(1)
    )


def _version_count(db: Session, phase_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ProductionPhaseVersion)
            .where(ProductionPhaseVersion.production_phase_id == phase_id)
        )
        or 0
    )


def _phase_read(db: Session, phase: ProductionPhase) -> ProductionPhaseRead:
    # Phase 1: prefer the latest *script package* even if a baseline/snapshot
    # was retained later — UI needs package fields, not an empty narrative shell.
    if phase.phase_number == 1:
        version = _latest_phase_one_package(db, phase.id) or _latest_version(db, phase.id)
    else:
        version = _latest_version(db, phase.id)
    qa = _latest_qa(db, version.id) if version is not None else None
    latest = None
    if version is not None:
        latest = PhaseVersionRead.model_validate(version)
        latest.verified = True
    return ProductionPhaseRead(
        id=phase.id,
        phase_number=phase.phase_number,
        name=phase.name,
        lifecycle_state=phase.lifecycle_state,
        current_version_number=phase.current_version_number,
        version_count=_version_count(db, phase.id),
        is_locked=phase.is_locked,
        locked_reason=phase.locked_reason,
        is_stale=phase.is_stale,
        stale_reason=phase.stale_reason,
        generation_completed_at=phase.generation_completed_at,
        approved_at=phase.approved_at,
        latest_version=latest,
        latest_qa_report=QAReportRead.model_validate(qa) if qa is not None else None,
    )


def get_pipeline(db: Session, story_id: UUID, *, ensure: bool = True) -> ProductionPipelineRead:
    story = db.get(Story, story_id)
    if story is None:
        raise ProductionPhaseError("Story not found.")
    phases = ensure_contract(db, story, commit=False)
    if ensure:
        ensure_phase_baselines(db, story, phases=phases, commit=True)
        phases = ensure_contract(db, story, commit=False)
    reads = [_phase_read(db, phase) for phase in phases]
    if len(reads) != 8:
        raise ProductionPhaseError("Production contract must contain exactly eight phases.")
    phase_one = reads[0]
    message = COMPLETION_MESSAGE if phase_one.lifecycle_state == "ready_for_review" else None
    return ProductionPipelineRead(
        story_id=story.id,
        project_id=story.project_id,
        phases=reads,
        completion_message=message,
    )


def _persist_phase_one_version(
    db: Session,
    *,
    story: Story,
    phase: ProductionPhase,
    input_snapshot: dict[str, Any],
    package: dict[str, Any],
    qa: dict[str, Any],
    created_by: str | None,
    commit: bool,
    source: str = "generated",
    label: str | None = None,
    notes: str = "",
) -> ProductionPhaseVersion:
    previous = _latest_version(db, phase.id)
    next_version = 1 if previous is None else previous.version_number + 1
    # Append-only: never mutate prior version rows (including superseded_at).
    state = "ready_for_review" if qa.get("passed") else "needs_revision"
    if not label:
        label = "Generated package" if source == "generated" else f"Revision {next_version}"
    version = ProductionPhaseVersion(
        production_phase_id=phase.id,
        version_number=next_version,
        lifecycle_state=state,
        completed=True,
        label=label.strip() or f"Version {next_version}",
        notes=(notes or "").strip(),
        source=source if source in SUPPORTED_SOURCES else "generated",
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
        input_snapshot_json=input_snapshot,
        output_json=package,
        input_hash=_canonical_hash(input_snapshot),
        output_hash=_canonical_hash(package),
        created_by=created_by,
        previous_version_id=previous.id if previous is not None else None,
    )
    db.add(version)
    db.flush()
    db.add(
        QAReport(
            entity_type="production_phase_version",
            entity_id=version.id,
            report_json=qa,
        )
    )
    phase.lifecycle_state = state
    phase.current_version_number = next_version
    phase.is_locked = False
    phase.locked_reason = None
    phase.is_stale = False
    phase.stale_reason = None
    phase.generation_completed_at = datetime.now(timezone.utc)
    story.logline = package.get("logline")
    story.synopsis = package.get("short_synopsis")
    story.narrative_objectives_json = {
        "phase_one_emotional_progression": package.get("emotional_progression") or [],
        "phase_one_dramatic_escalation": package.get("dramatic_escalation") or [],
        "phase_one_source_fidelity_notes": package.get("source_fidelity_notes") or [],
    }
    story.pacing_plan_json = {"macro_movements": package.get("pacing_plan") or []}
    story.duration_strategy_json = dict(package.get("duration_analysis") or {})
    story.approval_state = "draft"

    downstream = list(
        db.scalars(
            select(ProductionPhase).where(
                ProductionPhase.story_id == story.id,
                ProductionPhase.phase_number > 1,
            )
        )
    )
    for item in downstream:
        item.is_locked = True
        item.locked_reason = f"Phase {item.phase_number - 1} must be approved before this phase can begin."
        if item.current_version_number is not None:
            item.is_stale = True
            item.stale_reason = f"Phase 1 changed to version {next_version}; regeneration review is required."

    db.add(
        AuditLog(
            entity_type="production_phase_version",
            entity_id=version.id,
            action="phase_one_completed" if qa.get("passed") else "phase_one_needs_revision",
            details={
                "story_id": str(story.id),
                "phase_number": 1,
                "version_number": next_version,
                "completed": True,
                "approved": False,
                "lifecycle_state": state,
                "qa_passed": bool(qa.get("passed")),
                "media_generated": False,
            },
        )
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return version


def generate_phase_one(
    db: Session,
    story_id: UUID,
    payload: PhaseOneGenerationInput,
    *,
    commit: bool = True,
) -> PhaseOneMutationResponse:
    story = db.get(Story, story_id)
    if story is None:
        raise ProductionPhaseError("Story not found.")
    phases = ensure_contract(db, story, commit=False)
    phase = phases[0]
    if phase.is_locked:
        raise ProductionPhaseError(phase.locked_reason or "Phase 1 is locked.")
    phase.lifecycle_state = "drafting"
    db.add(
        AuditLog(
            entity_type="production_phase",
            entity_id=phase.id,
            action="phase_one_drafting_started",
            details={"story_id": str(story.id), "approved": False},
        )
    )
    project = db.get(Project, story.project_id)
    local_agent_required = bool(
        project is not None
        and is_agentless_workflow_lane(project.workflow_lane)
    )
    if local_agent_required:
        project_settings = db.scalar(
            select(ProjectStoryboardSettings).where(
                ProjectStoryboardSettings.project_id == story.project_id
            )
        )
        prompting_policy = (
            dict(project_settings.prompting_policy_json or {})
            if project_settings is not None
            else {}
        )
        selected_agent = str(
            prompting_policy.get("planning_agent") or "qwen"
        )
        if selected_agent not in {"qwen", "sulphur"}:
            raise ProductionPhaseError(
                "Agentless Phase 1 requires a valid persisted local planning "
                "agent (qwen or sulphur)."
            )
        payload = payload.model_copy(
            update={
                "planning_agent": selected_agent,
                "prompt_artifact_format": "json",
                "prompt_schema_version": (
                    "sineforge.local-planning-prompt/v1"
                ),
            }
        )
    package = _build_phase_one_package(story, payload)
    package = _apply_sulphur_phase_one_enhancement(
        package,
        payload,
        required=local_agent_required,
    )
    if local_agent_required:
        creative_direction = dict(package.get("creative_direction") or {})
        creative_direction.update(
            {
                "workflow_lane": project.workflow_lane,
                "hosted_planning_agents_allowed": False,
                "production_orchestrator": "deterministic_python",
            }
        )
        package["creative_direction"] = creative_direction
    phase.lifecycle_state = "qa_pending"
    qa = _qa_report(package, payload)
    _persist_phase_one_version(
        db,
        story=story,
        phase=phase,
        input_snapshot=payload.model_dump(mode="json"),
        package=package,
        qa=qa,
        created_by=payload.requested_by,
        commit=commit,
        source="generated",
        label="Generated package",
    )
    pipeline = get_pipeline(db, story.id, ensure=False)
    phase_read = pipeline.phases[0]
    message = COMPLETION_MESSAGE if qa.get("passed") else "Your script needs revision before review."
    return PhaseOneMutationResponse(
        pipeline=pipeline,
        phase=phase_read,
        completion_message=message,
    )


def revise_phase_one(
    db: Session,
    story_id: UUID,
    payload: PhaseOneRevisionRequest,
) -> PhaseOneMutationResponse:
    story = db.get(Story, story_id)
    if story is None:
        raise ProductionPhaseError("Story not found.")
    phases = ensure_contract(db, story, commit=False)
    phase = phases[0]
    current = _latest_version(db, phase.id)
    if current is None:
        raise ProductionPhaseError("Phase 1 has no generated version to revise.")
    if current.version_number != payload.expected_version_number:
        raise ProductionPhaseConflictError(
            f"Phase 1 is now version {current.version_number}; reload before saving your revision."
        )
    # Prefer the most recent script package even when a later manual retain
    # snapshot is the ledger head (concurrency still uses current_version_number).
    package_row = _latest_phase_one_package(db, phase.id)
    if package_row is None:
        raise ProductionPhaseError("Phase 1 has no generated version to revise.")
    generation_input = PhaseOneGenerationInput.model_validate(package_row.input_snapshot_json)
    package = dict(package_row.output_json)
    package.update(
        payload.model_dump(
            mode="json",
            exclude={"expected_version_number", "requested_by"},
        )
    )
    package["script_word_count"] = _word_count(str(package.get("complete_script") or ""))
    narration_duration = round(_word_count(str(package.get("narration_script") or "")) / 145 * 60, 2)
    dialogue_text = str(package.get("dialogue_script") or "")
    dialogue_words = 0 if dialogue_text.startswith("No spoken character dialogue") else _word_count(dialogue_text)
    dialogue_duration = round(dialogue_words / 135 * 60, 2)
    target = float(generation_input.target_duration_sec)
    visual_duration = round(max(0.0, target - narration_duration - dialogue_duration), 2)
    package["duration_analysis"] = {
        **dict(package.get("duration_analysis") or {}),
        "target_duration_sec": target,
        "narration_word_count": _word_count(str(package.get("narration_script") or "")),
        "dialogue_word_count": dialogue_words,
        "narration_duration_sec": narration_duration,
        "dialogue_duration_sec": dialogue_duration,
        "planned_silence_visual_duration_sec": visual_duration,
        "estimated_total_duration_sec": round(
            narration_duration + dialogue_duration + visual_duration, 2
        ),
    }
    if generation_input.comparison_baseline:
        package["baseline_comparison"] = _compare_to_baseline(
            package, generation_input.comparison_baseline
        )
    qa = _qa_report(package, generation_input)
    _persist_phase_one_version(
        db,
        story=story,
        phase=phase,
        input_snapshot=current.input_snapshot_json,
        package=package,
        qa=qa,
        created_by=payload.requested_by,
        commit=True,
        source="revision",
        label=f"Revision {current.version_number + 1}",
    )
    pipeline = get_pipeline(db, story.id, ensure=False)
    message = COMPLETION_MESSAGE if qa.get("passed") else "Your script needs revision before review."
    return PhaseOneMutationResponse(
        pipeline=pipeline,
        phase=pipeline.phases[0],
        completion_message=message,
    )


def _require_story(db: Session, story_id: UUID) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise ProductionPhaseError("Story not found.")
    return story


def _require_phase(
    db: Session, story: Story, phase_number: int
) -> ProductionPhase:
    if phase_number < 1 or phase_number > 8:
        raise ProductionPhaseError("Phase number must be between 1 and 8.")
    phases = ensure_contract(db, story, commit=False)
    phase = next((item for item in phases if item.phase_number == phase_number), None)
    if phase is None:
        raise ProductionPhaseError(f"Phase {phase_number} is missing from the contract.")
    return phase


def _media_ref(asset: PlanningMediaAsset) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "kind": asset.kind,
        "source_type": asset.source_type,
        "managed_uri": asset.managed_uri,
        "original_filename": asset.original_filename,
        "content_hash": asset.sha256,
        "mime_type": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "size_bytes": asset.size_bytes,
        "approval_state": asset.approval_state,
        "metadata_json": asset.metadata_json or {},
    }


def build_phase_snapshot(
    db: Session, story: Story, phase_number: int
) -> dict[str, Any]:
    """Build a phase-scoped snapshot from live canonical records (no media bytes)."""
    project = db.get(Project, story.project_id)
    project_settings = db.scalar(
        select(ProjectStoryboardSettings).where(
            ProjectStoryboardSettings.project_id == story.project_id
        )
    )
    chapters = list(
        db.scalars(
            select(Chapter)
            .where(Chapter.story_id == story.id, Chapter.archived_at.is_(None))
            .order_by(Chapter.order_index, Chapter.created_at)
        )
    )
    chapter_ids = [chapter.id for chapter in chapters]
    scenes = (
        list(
            db.scalars(
                select(Scene)
                .where(Scene.chapter_id.in_(chapter_ids), Scene.archived_at.is_(None))
                .order_by(Scene.order_index, Scene.created_at)
            )
        )
        if chapter_ids
        else []
    )
    scene_ids = [scene.id for scene in scenes]
    shots = (
        list(
            db.scalars(
                select(Shot)
                .where(Shot.scene_id.in_(scene_ids), Shot.archived_at.is_(None))
                .order_by(Shot.order_index, Shot.created_at)
            )
        )
        if scene_ids
        else []
    )
    characters = list(
        db.scalars(
            select(Character)
            .where(Character.story_id == story.id, Character.archived_at.is_(None))
            .order_by(Character.created_at)
        )
    )
    voices = list(
        db.scalars(
            select(VoiceProfile)
            .where(VoiceProfile.story_id == story.id, VoiceProfile.archived_at.is_(None))
            .order_by(VoiceProfile.created_at)
        )
    )
    assets = list(
        db.scalars(
            select(PlanningMediaAsset)
            .where(
                PlanningMediaAsset.project_id == story.project_id,
                PlanningMediaAsset.archived_at.is_(None),
            )
            .order_by(PlanningMediaAsset.created_at)
        )
    )
    shot_ids = [shot.id for shot in shots]
    narrations = (
        {
            row.shot_id: row
            for row in db.scalars(
                select(ShotNarration).where(ShotNarration.shot_id.in_(shot_ids))
            )
        }
        if shot_ids
        else {}
    )
    prompt_packages = (
        list(
            db.scalars(
                select(ShotPromptPackage)
                .where(ShotPromptPackage.shot_id.in_(shot_ids))
                .order_by(ShotPromptPackage.shot_id, ShotPromptPackage.version.desc())
            )
        )
        if shot_ids
        else []
    )
    shot_characters = (
        list(db.scalars(select(ShotCharacter).where(ShotCharacter.shot_id.in_(shot_ids))))
        if shot_ids
        else []
    )
    character_ids = [character.id for character in characters]
    char_refs = (
        list(
            db.scalars(
                select(CharacterReferenceAsset).where(
                    CharacterReferenceAsset.character_id.in_(character_ids)
                )
            )
        )
        if character_ids
        else []
    )
    assignments = list(
        db.scalars(
            select(TaskProviderAssignment).where(
                TaskProviderAssignment.story_id == story.id
            )
        )
    )
    providers = list(
        db.scalars(select(ProviderProfile).order_by(ProviderProfile.display_name))
    )

    narrative = {
        "story_id": str(story.id),
        "project_id": str(story.project_id),
        "project_name": project.name if project else None,
        "title": story.title,
        "base_story": story.base_story,
        "logline": story.logline,
        "synopsis": story.synopsis,
        "target_duration_sec": float(story.target_duration_sec)
        if story.target_duration_sec is not None
        else None,
        "audience": story.audience,
        "genre": story.genre,
        "tone": story.tone,
        "visual_style": story.visual_style,
        "point_of_view": story.point_of_view,
        "production_notes": story.production_notes,
        "approval_state": story.approval_state,
        "narrative_objectives_json": story.narrative_objectives_json or {},
        "pacing_plan_json": story.pacing_plan_json or {},
        "duration_strategy_json": story.duration_strategy_json or {},
    }
    structure = {
        "chapters": [
            {
                "id": str(c.id),
                "title": c.title,
                "summary": c.summary,
                "order_index": c.order_index,
            }
            for c in chapters
        ],
        "scenes": [
            {
                "id": str(s.id),
                "chapter_id": str(s.chapter_id) if s.chapter_id else None,
                "title": s.title,
                "summary": s.summary,
                "location": s.location,
                "order_index": s.order_index,
            }
            for s in scenes
        ],
        "shots": [
            {
                "id": str(sh.id),
                "scene_id": str(sh.scene_id) if sh.scene_id else None,
                "title": sh.title,
                "story_purpose": sh.story_purpose,
                "visual_description": sh.visual_description,
                "duration_sec": float(sh.duration_sec)
                if sh.duration_sec is not None
                else None,
                "location": sh.location,
                "order_index": sh.order_index,
                "approval_state": sh.approval_state,
                "production_status": sh.production_status,
                "continuity_source_type": sh.continuity_source_type,
                "continuity_source_shot_id": str(sh.continuity_source_shot_id)
                if sh.continuity_source_shot_id
                else None,
                "starting_image_asset_id": str(sh.starting_image_asset_id)
                if sh.starting_image_asset_id
                else None,
            }
            for sh in shots
        ],
    }
    identity = {
        "characters": [
            {
                "id": str(c.id),
                "name": c.name,
                "role": c.role,
                "physical_description": c.physical_description,
                "age_range": c.age_range,
                "personality": c.personality,
                "approval_state": c.approval_state,
            }
            for c in characters
        ],
        "character_reference_links": [
            {
                "id": str(r.id),
                "character_id": str(r.character_id),
                "asset_id": str(r.asset_id) if r.asset_id else None,
                "reference_role": r.reference_role,
                "approved": r.approved,
                "order_index": r.order_index,
            }
            for r in char_refs
        ],
        "voices": [
            {
                "id": str(v.id),
                "name": v.name,
                "character_id": str(v.character_id) if v.character_id else None,
                "setup_mode": v.setup_mode,
                "provider": v.provider,
                "language": v.language,
                "consent_confirmed": v.consent_confirmed,
                "approval_state": v.approval_state,
            }
            for v in voices
        ],
    }
    locations = sorted(
        {
            value
            for value in [
                *(s.location for s in scenes if s.location),
                *(sh.location for sh in shots if sh.location),
            ]
            if value
        }
    )
    location_state = {
        "locations": locations,
        "key_assets": [],
        "continuity_states": [],
    }
    prompts = {
        "prompt_packages": [
            {
                "id": str(p.id),
                "shot_id": str(p.shot_id),
                "version": p.version,
                "image_prompt": p.image_prompt,
                "video_prompt": p.video_prompt,
                "negative_prompt": p.negative_prompt,
            }
            for p in prompt_packages
        ],
        "task_assignments": [
            {
                "id": str(a.id),
                "task_type": a.task_type,
                "provider_profile_id": str(a.provider_profile_id)
                if a.provider_profile_id
                else None,
            }
            for a in assignments
        ],
        "provider_profiles": [
            {
                "id": str(p.id),
                "display_name": p.display_name,
                "provider_identifier": p.provider_identifier,
            }
            for p in providers
        ],
    }
    media = {
        "planning_media": [_media_ref(a) for a in assets],
        "shot_character_links": [
            {
                "shot_id": str(link.shot_id),
                "character_id": str(link.character_id),
                "role_in_shot": link.role_in_shot,
                "order_index": link.order_index,
            }
            for link in shot_characters
        ],
        "narrations": [
            {
                "shot_id": str(n.shot_id),
                "narration_text": n.narration_text,
                "voice_profile_id": str(n.voice_profile_id)
                if n.voice_profile_id
                else None,
            }
            for n in narrations.values()
        ],
    }
    picture = {
        "planned_shot_count": len(shots),
        "planned_runtime_sec": round(
            sum(float(sh.duration_sec or 0) for sh in shots), 2
        ),
        "production_profile_key": (
            project_settings.production_profile_key
            if project_settings is not None
            else "ltx_base@1"
        ),
        "stitch_stage": (
            project_settings.stitch_stage
            if project_settings is not None
            else "phase7_before_audio"
        ),
        "picture_locked": False,
        "picture_lock": None,
        "canonical_edl": None,
        "analysis_proxy": None,
        "qa_state": "not_evaluated",
        "manifest": {
            "schema": "cineforge.picture_manifest_preview",
            "version": 2,
            "note": "Planning snapshot only; no rendered clips are claimed.",
        },
    }
    audio_delivery = {
        "audio_enabled": (
            bool(project_settings.audio_enabled)
            if project_settings is not None
            else True
        ),
        "picture_lock_required": True,
        "picture_lock_hash": None,
        "foley_windows": [],
        "stems": [],
        "mix_master": None,
        "final_output": None,
        "delivery_ready": False,
        "qa_state": "not_evaluated",
        "manifest": {
            "schema": "cineforge.audio_delivery_manifest_preview",
            "version": 1,
            "note": "Planning snapshot only; no generated audio or final mux is claimed.",
        },
    }

    domains = {
        1: {"narrative": narrative},
        2: {"narrative": narrative, "structure": structure},
        3: {"identity": identity},
        4: {"locations": location_state, "structure": {"scenes": structure["scenes"]}},
        5: {"prompts": prompts, "structure": {"shots": structure["shots"]}},
        6: {
            "media": media,
            "identity": identity,
            "structure": {"shots": structure["shots"]},
        },
        7: {"picture": picture, "structure": structure, "media": media},
        8: {
            "audio_delivery": audio_delivery,
            "picture": {
                "picture_locked": picture["picture_locked"],
                "picture_lock": picture["picture_lock"],
                "production_profile_key": picture["production_profile_key"],
                "stitch_stage": picture["stitch_stage"],
            },
            "media": media,
        },
    }
    body = domains.get(phase_number, {})
    return {
        "schema_name": "cineforge.production_phase_snapshot",
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "phase_number": phase_number,
        "story_id": str(story.id),
        "project_id": str(story.project_id),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        **body,
    }


def _verify_version_row(
    version: ProductionPhaseVersion,
    *,
    expected_phase_id: UUID | None = None,
    expected_story_id: UUID | None = None,
    expected_project_id: UUID | None = None,
    phase: ProductionPhase | None = None,
    story: Story | None = None,
) -> None:
    if version.snapshot_schema_version not in SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS:
        raise ProductionPhaseError(
            f"Unsupported snapshot schema version {version.snapshot_schema_version}."
        )
    if version.source not in SUPPORTED_SOURCES:
        raise ProductionPhaseError(f"Unsupported version source {version.source!r}.")
    if not version.input_snapshot_json and not version.output_json:
        raise ProductionPhaseError("Version snapshot is missing.")
    if _canonical_hash(version.input_snapshot_json) != version.input_hash:
        raise ProductionPhaseError("Version input snapshot failed integrity verification.")
    if _canonical_hash(version.output_json) != version.output_hash:
        raise ProductionPhaseError("Version output snapshot failed integrity verification.")
    if expected_phase_id is not None and version.production_phase_id != expected_phase_id:
        raise ProductionPhaseError("Version belongs to a different production phase.")
    if phase is not None and version.production_phase_id != phase.id:
        raise ProductionPhaseError("Version belongs to a different production phase.")
    if story is not None and phase is not None and phase.story_id != story.id:
        raise ProductionPhaseError("Version belongs to a different story.")
    if expected_story_id is not None and story is not None and story.id != expected_story_id:
        raise ProductionPhaseError("Version belongs to a different story.")
    if expected_project_id is not None and story is not None and story.project_id != expected_project_id:
        raise ProductionPhaseError("Version belongs to a different project.")


def _append_version(
    db: Session,
    *,
    phase: ProductionPhase,
    label: str,
    notes: str,
    source: str,
    input_snapshot: dict[str, Any],
    output_json: dict[str, Any],
    lifecycle_state: str,
    completed: bool,
    created_by: str | None,
    commit: bool,
) -> ProductionPhaseVersion:
    if source not in SUPPORTED_SOURCES:
        raise ProductionPhaseError(f"Unsupported version source {source!r}.")
    clean_label = (label or "").strip()
    if not clean_label:
        raise ProductionPhaseError("Iteration label is required.")
    clean_notes = (notes or "").strip()
    phase_id = phase.id

    def _insert_once(target_phase: ProductionPhase) -> ProductionPhaseVersion:
        previous = _latest_version(db, target_phase.id)
        next_version = 1 if previous is None else previous.version_number + 1
        row = ProductionPhaseVersion(
            production_phase_id=target_phase.id,
            version_number=next_version,
            lifecycle_state=lifecycle_state,
            completed=completed,
            label=clean_label,
            notes=clean_notes,
            source=source,
            snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
            input_snapshot_json=input_snapshot,
            output_json=output_json,
            input_hash=_canonical_hash(input_snapshot),
            output_hash=_canonical_hash(output_json),
            created_by=created_by,
            previous_version_id=previous.id if previous is not None else None,
        )
        db.add(row)
        db.flush()
        target_phase.current_version_number = next_version
        if target_phase.lifecycle_state == "not_started":
            target_phase.lifecycle_state = lifecycle_state
        return row

    try:
        version = _insert_once(phase)
    except IntegrityError as exc:
        db.rollback()
        # Retry once after a concurrent version-number collision or after a
        # rollback expired the in-memory phase object. Re-fetching the phase is
        # required for SQLite because a rollback can invalidate phase rows that
        # were created earlier in the same transaction.
        refreshed_phase = db.get(ProductionPhase, phase_id)
        if refreshed_phase is None:
            raise ProductionPhaseError(
                "Production phase disappeared while appending a version; reload the phase contract."
            ) from exc
        phase = refreshed_phase
        version = _insert_once(phase)

    db.add(
        AuditLog(
            entity_type="production_phase_version",
            entity_id=version.id,
            action="production_phase_version_retained",
            details={
                "phase_number": phase.phase_number,
                "version_number": version.version_number,
                "source": source,
                "label": clean_label,
            },
        )
    )
    if commit:
        db.commit()
        db.refresh(version)
    else:
        db.flush()
    return version


def ensure_phase_baselines(
    db: Session,
    story: Story,
    *,
    phases: list[ProductionPhase] | None = None,
    commit: bool = True,
) -> list[ProductionPhaseVersion]:
    """Idempotently create a baseline version only when a phase has zero history."""
    phases = phases or ensure_contract(db, story, commit=False)
    created: list[ProductionPhaseVersion] = []
    for phase in phases:
        attached_phase = db.get(ProductionPhase, phase.id)
        if attached_phase is None:
            # The phase list may have been produced before a transaction
            # rollback. Rebuild the canonical contract and continue with the
            # live row for the same phase number.
            phases = ensure_contract(db, story, commit=False)
            attached_phase = next(
                (item for item in phases if item.phase_number == phase.phase_number),
                None,
            )
            if attached_phase is None:
                raise ProductionPhaseError(
                    f"Phase {phase.phase_number} is missing from the contract."
                )
        phase = attached_phase
        if _version_count(db, phase.id) > 0:
            continue
        snapshot = build_phase_snapshot(db, story, phase.phase_number)
        created.append(
            _append_version(
                db,
                phase=phase,
                label="Baseline",
                notes="Initial retained state for this phase.",
                source="baseline",
                input_snapshot={"reason": "baseline", "phase_number": phase.phase_number},
                output_json=snapshot,
                lifecycle_state="not_started"
                if phase.lifecycle_state == "not_started"
                else phase.lifecycle_state,
                completed=False,
                created_by="system:baseline",
                commit=False,
            )
        )
    if commit:
        db.commit()
    else:
        db.flush()
    return created


def list_phase_versions(
    db: Session, story_id: UUID, phase_number: int
) -> list[PhaseVersionSummary]:
    story = _require_story(db, story_id)
    phase = _require_phase(db, story, phase_number)
    ensure_phase_baselines(db, story, phases=[phase], commit=True)
    rows = list(
        db.scalars(
            select(ProductionPhaseVersion)
            .where(ProductionPhaseVersion.production_phase_id == phase.id)
            .order_by(ProductionPhaseVersion.version_number.asc())
        )
    )
    return [PhaseVersionSummary.model_validate(row) for row in rows]


def get_phase_version(
    db: Session, story_id: UUID, phase_number: int, version_id: UUID
) -> PhaseVersionDetail:
    story = _require_story(db, story_id)
    phase = _require_phase(db, story, phase_number)
    version = db.get(ProductionPhaseVersion, version_id)
    if version is None:
        raise ProductionPhaseError("Version not found.")
    _verify_version_row(version, phase=phase, story=story)
    base = PhaseVersionRead.model_validate(version).model_dump()
    base["verified"] = True
    return PhaseVersionDetail(
        **base,
        story_id=story.id,
        project_id=story.project_id,
        phase_number=phase.phase_number,
        phase_name=phase.name,
    )


def create_phase_version(
    db: Session,
    story_id: UUID,
    phase_number: int,
    payload: PhaseVersionCreateRequest,
) -> PhaseVersionCreateResponse:
    story = _require_story(db, story_id)
    phases = ensure_contract(db, story, commit=False)
    phase = _require_phase(db, story, phase_number)
    ensure_phase_baselines(db, story, phases=phases, commit=False)
    # Phase 1 retains the generated script package when present so the pipeline
    # head (and ProductionPhases packageData) stay aligned with the package schema.
    retained_package = (
        _latest_phase_one_package(db, phase.id) if phase_number == 1 else None
    )
    if retained_package is not None and _is_phase_one_package(retained_package.output_json):
        snapshot = dict(retained_package.output_json)
        # Preserve the original generation input so revise_phase_one can validate
        # PhaseOneGenerationInput from this retained head (no retain metadata keys).
        prior_input = retained_package.input_snapshot_json
        if isinstance(prior_input, dict) and "original_prompt" in prior_input:
            input_snapshot = dict(prior_input)
        else:
            input_snapshot = {
                "reason": "manual_retain",
                "phase_number": phase_number,
                "requested_by": payload.requested_by,
                "retained_from_version_id": str(retained_package.id),
            }
        completed = bool(retained_package.completed)
    else:
        snapshot = build_phase_snapshot(db, story, phase_number)
        input_snapshot = {
            "reason": "manual_retain",
            "phase_number": phase_number,
            "requested_by": payload.requested_by,
        }
        completed = False
    version = _append_version(
        db,
        phase=phase,
        label=payload.label,
        notes=payload.notes,
        source="manual",
        input_snapshot=input_snapshot,
        output_json=snapshot,
        lifecycle_state=phase.lifecycle_state
        if phase.lifecycle_state != "not_started"
        else "drafting",
        completed=completed,
        created_by=payload.requested_by,
        commit=True,
    )
    detail = get_phase_version(db, story_id, phase_number, version.id)
    pipeline = get_pipeline(db, story_id, ensure=False)
    return PhaseVersionCreateResponse(version=detail, pipeline=pipeline)


def approve_phase(
    db: Session,
    story_id: UUID,
    phase_number: int,
    payload: PhaseApproveRequest,
    *,
    commit: bool = True,
) -> PhaseApproveResponse:
    """Mark a production phase approved and unlock the next phase.

    Approval records the ledger state only. Media generation is handled by the
    dedicated local runtime routes for the relevant phase.
    """
    if phase_number < 1 or phase_number > 8:
        raise ProductionPhaseError("Phase number must be between 1 and 8.")
    story = _require_story(db, story_id)
    phases = ensure_contract(db, story, commit=False)
    ensure_phase_baselines(db, story, phases=phases, commit=False)
    phase = _require_phase(db, story, phase_number)

    if phase.lifecycle_state == "approved" and phase.approved_at is not None:
        pipeline = get_pipeline(db, story_id, ensure=False)
        return PhaseApproveResponse(
            pipeline=pipeline,
            phase=next(p for p in pipeline.phases if p.phase_number == phase_number),
            message=f"Phase {phase_number} is already approved.",
        )

    if phase_number > 1:
        previous = next(p for p in phases if p.phase_number == phase_number - 1)
        if previous.lifecycle_state != "approved":
            raise ProductionPhaseError(
                f"Phase {phase_number - 1} must be approved before phase {phase_number} can be approved."
            )

    # Approving a phase that is still locked because its predecessor was just
    # approved is allowed only when that predecessor is now approved.
    if phase.is_locked and phase_number > 1:
        if phase_number == 8:
            raise ProductionPhaseError(PHASE_EIGHT_PICTURE_LOCK_REQUIRED)
        previous = next(p for p in phases if p.phase_number == phase_number - 1)
        if previous.lifecycle_state == "approved":
            phase.is_locked = False
            phase.locked_reason = None
        else:
            raise ProductionPhaseError(
                phase.locked_reason
                or f"Phase {phase_number} is locked until phase {phase_number - 1} is approved."
            )
    elif phase.is_locked and phase_number == 1:
        raise ProductionPhaseError(phase.locked_reason or "Phase 1 is locked.")

    now = datetime.now(timezone.utc)
    phase.lifecycle_state = "approved"
    phase.approved_at = now
    phase.is_locked = False
    phase.locked_reason = None
    phase.is_stale = False
    phase.stale_reason = None

    snapshot = build_phase_snapshot(db, story, phase_number)
    _append_version(
        db,
        phase=phase,
        label=f"Approved phase {phase_number}",
        notes=(payload.notes or "").strip()
        or f"Approved by {payload.approved_by} at {now.isoformat()}",
        source="manual",
        input_snapshot={
            "reason": "phase_approval",
            "phase_number": phase_number,
            "approved_by": payload.approved_by,
        },
        output_json=snapshot,
        lifecycle_state="approved",
        completed=True,
        created_by=payload.approved_by,
        commit=False,
    )

    next_phase = next((p for p in phases if p.phase_number == phase_number + 1), None)
    if next_phase is not None:
        if next_phase.phase_number == 8:
            next_phase.is_locked = True
            next_phase.locked_reason = PHASE_EIGHT_PICTURE_LOCK_REQUIRED
            next_phase.lifecycle_state = "not_started"
        else:
            next_phase.is_locked = False
            next_phase.locked_reason = None
            if next_phase.lifecycle_state == "not_started":
                next_phase.lifecycle_state = "drafting"

    db.add(
        AuditLog(
            entity_type="production_phase",
            entity_id=phase.id,
            action="production_phase_approved",
            details={
                "story_id": str(story.id),
                "phase_number": phase_number,
                "approved_by": payload.approved_by,
                "media_generated": False,
            },
        )
    )
    if commit:
        db.commit()
    else:
        db.flush()

    pipeline = get_pipeline(db, story_id, ensure=False)
    return PhaseApproveResponse(
        pipeline=pipeline,
        phase=next(p for p in pipeline.phases if p.phase_number == phase_number),
        message=f"Phase {phase_number} approved. "
        + (
            PHASE_EIGHT_PICTURE_LOCK_REQUIRED
            if next_phase is not None and next_phase.phase_number == 8
            else f"Phase {phase_number + 1} is unlocked for planning."
            if next_phase is not None
            else "All eight phases are approved."
        ),
    )


def export_phase_history(db: Session, story_id: UUID) -> PhaseHistoryExport:
    story = _require_story(db, story_id)
    phases = ensure_contract(db, story, commit=False)
    ensure_phase_baselines(db, story, phases=phases, commit=True)
    iterations: list[PhaseVersionDetail] = []
    phase_counts: dict[str, int] = {}
    hashes: list[str] = []
    for phase in phases:
        rows = list(
            db.scalars(
                select(ProductionPhaseVersion)
                .where(ProductionPhaseVersion.production_phase_id == phase.id)
                .order_by(ProductionPhaseVersion.version_number.asc())
            )
        )
        phase_counts[str(phase.phase_number)] = len(rows)
        for row in rows:
            _verify_version_row(row, phase=phase, story=story)
            base = PhaseVersionRead.model_validate(row).model_dump()
            base["verified"] = True
            detail = PhaseVersionDetail(
                **base,
                story_id=story.id,
                project_id=story.project_id,
                phase_number=phase.phase_number,
                phase_name=phase.name,
            )
            iterations.append(detail)
            hashes.append(row.output_hash)
    if not iterations:
        raise ProductionPhaseError("History export found no verified iterations.")
    return PhaseHistoryExport(
        project_id=story.project_id,
        story_id=story.id,
        exported_at=datetime.now(timezone.utc),
        integrity=PhaseHistoryExportIntegrity(
            verified=True,
            iteration_count=len(iterations),
            snapshot_count=len(set(hashes)),
            phase_counts=phase_counts,
            hashes=hashes,
        ),
        iterations=iterations,
    )
