"""Creative generation theme contracts.

Themes affect generated content direction.  They do not select application
colour schemes, ComfyUI nodes, models, or workflow files.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


THEME_VERSION = "1.0.0"


class CreativeThemeId(str, Enum):
    default = "default"
    greek_mythology = "greek_mythology"
    biblical = "biblical"


class BiblicalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canon_context: Literal["hebrew_bible", "new_testament"]
    scripture_reference: str | None = Field(default=None, max_length=300)
    narrative_period: str = Field(min_length=1, max_length=300)
    historical_preset: Literal[
        "hb_patriarchal_canaan",
        "hb_exodus_egypt_sinai",
        "hb_iron_age_israel_judah",
        "hb_assyrian_babylonian_exile",
        "hb_persian_return",
        "nt_herodian_galilee_judea",
        "nt_jerusalem_second_temple",
        "nt_roman_military_admin",
        "nt_acts_eastern_mediterranean",
        "biblical_visionary",
    ]
    region: str = Field(min_length=1, max_length=300)
    culture: list[str] = Field(min_length=1, max_length=12)
    roman_presence: Literal[
        "none",
        "ambient_rule",
        "civic_administration",
        "military",
        "imperial_center",
    ]
    sacred_representation_policy: Literal[
        "indirect_manifestation",
        "text_explicit",
        "traditional_iconography",
    ]
    angel_policy: Literal[
        "human_messenger_default",
        "text_specific_being",
        "traditional_winged",
    ]
    miracle_intensity: Literal["restrained", "cinematic", "visionary"]

    @model_validator(mode="after")
    def validate_historical_consistency(self) -> "BiblicalContext":
        cleaned_cultures = [item.strip() for item in self.culture if item.strip()]
        if not cleaned_cultures:
            raise ValueError("Biblical Theme requires at least one culture.")
        self.culture = cleaned_cultures

        is_hebrew_preset = self.historical_preset.startswith("hb_")
        is_new_testament_preset = self.historical_preset.startswith("nt_")
        if is_hebrew_preset and self.canon_context != "hebrew_bible":
            raise ValueError(
                "Hebrew Bible historical presets require canon_context='hebrew_bible'."
            )
        if is_new_testament_preset and self.canon_context != "new_testament":
            raise ValueError(
                "New Testament historical presets require canon_context='new_testament'."
            )
        if self.canon_context == "hebrew_bible" and self.roman_presence != "none":
            raise ValueError(
                "Hebrew Bible contexts cannot include Roman presence."
            )
        return self

class CreativeThemeRead(BaseModel):
    id: CreativeThemeId
    version: str
    label: str
    description: str
    mode: Literal["passthrough", "preset"]
    requires_context: bool
    context_schema_id: str | None
    prompt_profile_id: str | None


class ThemeCatalogRead(BaseModel):
    default_theme_id: Literal["default"] = "default"
    themes: list[CreativeThemeRead]


class ProjectThemeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: CreativeThemeId
    theme_context: BiblicalContext | None = None

    @model_validator(mode="after")
    def validate_context_for_theme(self) -> "ProjectThemeUpdate":
        if self.theme_id is CreativeThemeId.biblical and self.theme_context is None:
            raise ValueError("Biblical Theme requires its historical context fields.")
        if self.theme_id is not CreativeThemeId.biblical and self.theme_context is not None:
            raise ValueError("theme_context is only accepted for Biblical Theme.")
        return self
