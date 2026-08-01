"""Central creative-theme resolution and prompt compilation.

The default branch is intentionally a byte-for-byte passthrough.  Preset
branches only compile content direction; workflow/model selection remains with
the existing deterministic generation services.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from backend.app.schemas.themes import (
    THEME_VERSION,
    BiblicalContext,
    CreativeThemeId,
    CreativeThemeRead,
    ThemeCatalogRead,
)


THEME_CATALOG = ThemeCatalogRead(
    themes=[
        CreativeThemeRead(
            id=CreativeThemeId.default,
            version=THEME_VERSION,
            label="Default",
            description="Current CineForge setup.",
            mode="passthrough",
            requires_context=False,
            context_schema_id=None,
            prompt_profile_id=None,
        ),
        CreativeThemeRead(
            id=CreativeThemeId.greek_mythology,
            version=THEME_VERSION,
            label="Greek Mythology Theme",
            description="Grounded live-action ancient Greek mythology.",
            mode="preset",
            requires_context=False,
            context_schema_id=None,
            prompt_profile_id="greek_mythology_grounded_v1",
        ),
        CreativeThemeRead(
            id=CreativeThemeId.biblical,
            version=THEME_VERSION,
            label="Biblical Theme",
            description="Source-faithful, historically grounded biblical cinema.",
            mode="preset",
            requires_context=True,
            context_schema_id="biblical_context_v1",
            prompt_profile_id="biblical_grounded_v1",
        ),
    ]
)

_THEMES = {theme.id: theme for theme in THEME_CATALOG.themes}


GREEK_PREFIX = (
    "Grounded live-action ancient Greek mythological cinema; Bronze Age Aegean "
    "material culture, weathered natural people, handmade linen, aged bronze, "
    "timber, stone, sea air, and practical light; mythic events treated with "
    "human scale and physical consequence"
)
GREEK_QUALITY = (
    "layered foreground, middle ground, and background; natural skin texture, "
    "motivated cinematic light, restrained halation and fine 35 mm grain"
)
GREEK_EXCLUSIONS = (
    "glossy fantasy game art, modern objects, plastic skin, superhero armor, "
    "generic medieval Europe, weightless action, excessive magical particles"
)

BIBLICAL_PREFIX = (
    "Grounded sacred-history cinema; source-faithful narrative setting, "
    "historically plausible people, status, clothing, architecture, tools, food, "
    "vessels, and weapons; natural weathered skin and restrained human performance"
)
BIBLICAL_QUALITY = (
    "tactile handmade materials; one motivated practical or passage-supported "
    "extraordinary light source; layered foreground, middle ground, and background; "
    "subtle halation and restrained 35 mm grain"
)
BIBLICAL_EXCLUSIONS = (
    "no invented event, character, object, or miracle that contradicts the supplied "
    "source; no active Greek-myth supernatural beings; no generic medieval church, "
    "Renaissance devotional staging, modern objects, plastic skin, or generic fantasy"
)

_HISTORICAL_CLAUSES = {
    "hb_patriarchal_canaan": (
        "Bronze Age-inspired Canaan with pastoral camps, mudbrick settlements, "
        "handmade household goods, and regional trade"
    ),
    "hb_exodus_egypt_sinai": (
        "story-period Egypt and Sinai rendered without asserting a disputed exact chronology"
    ),
    "hb_iron_age_israel_judah": (
        "Iron Age Israel or Judah with hill-country settlements and period-appropriate material culture"
    ),
    "hb_assyrian_babylonian_exile": (
        "Levantine or Mesopotamian setting under Assyrian or Babylonian imperial pressure"
    ),
    "hb_persian_return": (
        "Persian-period Yehud, rebuilding communities, and restrained Achaemenid influence"
    ),
    "nt_herodian_galilee_judea": (
        "early first-century Galilee, Judea, or Samaria with agrarian, fishing, and village life"
    ),
    "nt_jerusalem_second_temple": (
        "Herodian Jerusalem and the Second Temple; never Solomon's Temple"
    ),
    "nt_roman_military_admin": (
        "early-imperial Roman roads, taxation, courts, administration, or military presence as requested"
    ),
    "nt_acts_eastern_mediterranean": (
        "first-century eastern Mediterranean port or Roman city with location-correct "
        "Hellenistic and Roman architecture and diaspora communities"
    ),
    "biblical_visionary": (
        "passage-specific prophetic or apocalyptic imagery, with every extraordinary element anchored to the cited source"
    ),
}

_ROMAN_CLAUSES = {
    "none": "no Roman personnel, standards, administration, or imperial symbols",
    "ambient_rule": "Roman rule is ambient context; do not insert soldiers unless the scene asks for them",
    "civic_administration": "period-appropriate Roman civic administration is visible where narratively relevant",
    "military": "period-appropriate Roman military personnel and equipment are visible where the source requires them",
    "imperial_center": "the setting reflects the material culture and authority of the Roman imperial center",
}

_SACRED_CLAUSES = {
    "indirect_manifestation": (
        "represent the sacred indirectly through passage-supported light, weather, sound, reaction, or environment; no automatic halo"
    ),
    "text_explicit": (
        "show sacred manifestation only as explicitly described by the supplied passage; add no automatic halo or celestial effect"
    ),
    "traditional_iconography": (
        "traditional iconographic elements are permitted only where the user explicitly selected this policy"
    ),
}

_ANGEL_CLAUSES = {
    "human_messenger_default": "angels appear as human messengers by default; no automatic wings",
    "text_specific_being": "any angelic being follows the passage's specific physical description",
    "traditional_winged": "traditional winged angel imagery is permitted by explicit project policy",
}

_MIRACLE_CLAUSES = {
    "restrained": "miraculous action remains restrained, physical, and centered on human reaction",
    "cinematic": "miraculous action may be cinematically legible but remains source-bounded and physically coherent",
    "visionary": "visionary intensity is permitted only for the passage-specific extraordinary imagery",
}


@dataclass(frozen=True)
class ResolvedThemePrompts:
    requested_theme_id: str
    resolved_theme_id: str
    theme_version: str
    context: dict[str, Any]
    positive_prompt: str
    negative_prompt: str
    positive_prompt_sha256: str
    negative_prompt_sha256: str
    snapshot: dict[str, Any]
    snapshot_sha256: str


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def theme_catalog() -> ThemeCatalogRead:
    return THEME_CATALOG.model_copy(deep=True)


def validate_theme_selection(
    theme_id: CreativeThemeId | str | None,
    theme_context: BiblicalContext | dict[str, Any] | None,
) -> tuple[CreativeThemeRead, BiblicalContext | None]:
    resolved_id = CreativeThemeId(theme_id or CreativeThemeId.default)
    theme = _THEMES[resolved_id]
    if resolved_id is CreativeThemeId.biblical:
        if theme_context is None:
            raise ValueError("Biblical Theme requires its historical context fields.")
        context = (
            theme_context
            if isinstance(theme_context, BiblicalContext)
            else BiblicalContext.model_validate(theme_context)
        )
        return theme, context
    if theme_context not in (None, {}):
        raise ValueError("theme_context is only accepted for Biblical Theme.")
    return theme, None


def _join_prompt_parts(parts: Iterable[str | None], separator: str = ". ") -> str:
    return separator.join(part.strip(" .") for part in parts if part and part.strip(" ."))


def _biblical_context_clauses(context: BiblicalContext) -> list[str]:
    clauses = [
        f"Canon context: {context.canon_context.replace('_', ' ')}",
        f"Narrative period: {context.narrative_period}",
        f"Historical setting: {_HISTORICAL_CLAUSES[context.historical_preset]}",
        f"Region: {context.region}",
        f"Cultures represented: {', '.join(context.culture)}",
        _ROMAN_CLAUSES[context.roman_presence],
        _SACRED_CLAUSES[context.sacred_representation_policy],
        _ANGEL_CLAUSES[context.angel_policy],
        _MIRACLE_CLAUSES[context.miracle_intensity],
    ]
    if context.scripture_reference:
        clauses.insert(1, f"Scripture reference: {context.scripture_reference}")
    return clauses


def compile_theme_prompts(
    *,
    theme_id: CreativeThemeId | str | None,
    theme_context: BiblicalContext | dict[str, Any] | None,
    positive_prompt: str,
    negative_prompt: str,
    medium: Literal["planning", "image", "video"] = "image",
    continuity_clauses: Iterable[str] = (),
) -> ResolvedThemePrompts:
    theme, biblical_context = validate_theme_selection(theme_id, theme_context)

    # This branch is a strict invariant: no trimming, normalising, prefixing,
    # suffixing, deduplication, or punctuation changes.
    if theme.id is CreativeThemeId.default:
        compiled_positive = positive_prompt
        compiled_negative = negative_prompt
        context_dict: dict[str, Any] = {}
    elif theme.id is CreativeThemeId.greek_mythology:
        context_dict = {}
        motion = (
            "one restrained subject action, one secondary environmental motion, and no more than one camera move"
            if medium == "video"
            else None
        )
        compiled_positive = _join_prompt_parts(
            [GREEK_PREFIX, positive_prompt, *continuity_clauses, motion, GREEK_QUALITY]
        )
        compiled_negative = _join_prompt_parts(
            [negative_prompt, GREEK_EXCLUSIONS], separator=", "
        )
    else:
        assert biblical_context is not None
        context_dict = biblical_context.model_dump(mode="json", exclude_none=True)
        motion = (
            "one restrained subject action, one secondary environmental motion, and no more than one camera move"
            if medium == "video"
            else None
        )
        compiled_positive = _join_prompt_parts(
            [
                BIBLICAL_PREFIX,
                positive_prompt,
                *_biblical_context_clauses(biblical_context),
                *continuity_clauses,
                motion,
                BIBLICAL_QUALITY,
                BIBLICAL_EXCLUSIONS,
            ]
        )
        compiled_negative = _join_prompt_parts(
            [negative_prompt, BIBLICAL_EXCLUSIONS], separator=", "
        )

    snapshot = {
        "id": theme.id.value,
        "version": theme.version,
        "label": theme.label,
        "mode": theme.mode,
        "prompt_profile_id": theme.prompt_profile_id,
        "context": context_dict,
        "medium": medium,
    }
    snapshot_sha256 = _canonical_hash(snapshot)
    return ResolvedThemePrompts(
        requested_theme_id=(theme_id.value if isinstance(theme_id, CreativeThemeId) else str(theme_id or "default")),
        resolved_theme_id=theme.id.value,
        theme_version=theme.version,
        context=context_dict,
        positive_prompt=compiled_positive,
        negative_prompt=compiled_negative,
        positive_prompt_sha256=_sha256_text(compiled_positive),
        negative_prompt_sha256=_sha256_text(compiled_negative),
        snapshot=snapshot,
        snapshot_sha256=snapshot_sha256,
    )


def compile_project_theme_prompts(
    project: Any,
    *,
    positive_prompt: str,
    negative_prompt: str,
    medium: Literal["planning", "image", "video"] = "image",
    continuity_clauses: Iterable[str] = (),
) -> ResolvedThemePrompts:
    return compile_theme_prompts(
        theme_id=getattr(project, "theme_id", "default"),
        theme_context=getattr(project, "theme_context_json", None),
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        medium=medium,
        continuity_clauses=continuity_clauses,
    )


def theme_planning_guidance(project: Any) -> ResolvedThemePrompts:
    return compile_project_theme_prompts(
        project,
        positive_prompt="Preserve the user's story, actions, dialogue, and source intent as primary.",
        negative_prompt="",
        medium="planning",
    )
