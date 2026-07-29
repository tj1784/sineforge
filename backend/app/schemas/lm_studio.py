"""Validated contracts for the local LM Studio model selector."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}$")


class LMStudioModelRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    key: str
    display_name: str
    filename: str | None = None
    publisher: str | None = None
    architecture: str | None = None
    quantization: str | None = None
    params_string: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    max_context_length: int | None = Field(default=None, ge=0)
    context_length: int | None = Field(default=None, ge=0)
    parallel: int | None = Field(default=None, ge=0)
    installed: bool
    loaded: bool
    selected: bool
    loaded_instance_ids: list[str] = Field(default_factory=list)


class LMStudioModelCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_name: str = "runtime.lm_studio_models.v1"
    status: str
    reachable: bool
    active_model_id: str
    configured_model_id: str
    models: list[LMStudioModelRead] = Field(default_factory=list)
    error: str | None = None


class LMStudioModelActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not _MODEL_ID_RE.fullmatch(cleaned):
            raise ValueError("model_id must be a safe LM Studio model identifier")
        return cleaned


class LMStudioModelActivateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    active_model_id: str
    loaded: bool
    load_time_seconds: float | None = Field(default=None, ge=0)
    model: LMStudioModelRead
