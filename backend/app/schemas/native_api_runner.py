from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NativeRunnerWorkflowSummary(BaseModel):
    id: UUID
    name: str
    version: str
    description: str | None = None
    category: str = "Uncategorized"
    subcategory: str = "General"
    episode: str | None = None
    instructions: str | None = None
    tags: list[str] = Field(default_factory=list)
    requirements: dict[str, Any] = Field(default_factory=dict)
    workflow_status: Literal["converted", "requires_custom_nodes"] = "converted"
    repository_managed: bool = False
    is_overridden: bool = False
    source_kind: str | None = None
    source_id: str | None = None
    source_filename: str | None = None
    source_archive: str | None = None
    source_entry: str | None = None
    node_count: int
    sha256: str
    created_at: str
    updated_at: str


class NativeRunnerWorkflowDetail(NativeRunnerWorkflowSummary):
    workflow: dict[str, Any]
    source_workflow: dict[str, Any] | None = None
    source_workflow_sha256: str | None = None


class NativeRunnerComfyUILoadResponse(BaseModel):
    ok: bool
    workflow_id: UUID
    workflow_name: str
    comfy_url: str
    open_url: str
    transfer_token: UUID
    expires_in_sec: int
    queued: Literal[False] = False


class NativeRunnerWorkflowCreate(StrictRequest):
    name: str = Field(min_length=1, max_length=240)
    version: str = Field(default="1.0", min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=12_000)
    category: str = Field(default="Uncategorized", min_length=1, max_length=120)
    subcategory: str = Field(default="General", min_length=1, max_length=160)
    episode: str | None = Field(default=None, max_length=40)
    instructions: str | None = Field(default=None, max_length=20_000)
    tags: list[str] = Field(default_factory=list, max_length=40)
    requirements: dict[str, Any] = Field(default_factory=dict)
    source_filename: str | None = Field(default=None, max_length=1024)
    workflow: dict[str, Any]


class NativeRunnerWorkflowUpdate(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    version: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=12_000)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    subcategory: str | None = Field(default=None, min_length=1, max_length=160)
    episode: str | None = Field(default=None, max_length=40)
    instructions: str | None = Field(default=None, max_length=20_000)
    tags: list[str] | None = Field(default=None, max_length=40)
    requirements: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None


class NativeRunnerAnalyzeRequest(StrictRequest):
    workflow: dict[str, Any]


class NativeRunnerRunRequest(StrictRequest):
    workflow: dict[str, Any]
    workflow_name: str = Field(min_length=1, max_length=160)
    workflow_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    confirmation: Literal[True]
    idempotency_key: str = Field(min_length=8, max_length=120)

    @field_validator("workflow_sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        lowered = value.casefold()
        if any(character not in "0123456789abcdef" for character in lowered):
            raise ValueError("workflow_sha256 must be hexadecimal")
        return lowered


class NativeRunnerMediaUploadResponse(BaseModel):
    ok: bool
    filename: str
    subfolder: str
    type: str


class NativeRunnerRunResponse(BaseModel):
    contract: str
    ok: bool
    prompt_id: str
    queue_number: int | float | None = None
    client_id: str
    workflow_sha256: str
    submitted_at: str
    external_runner_used: Literal[False] = False


class NativeRunnerMemoryRequest(StrictRequest):
    confirmation: Literal[True]
    unload_models: bool = True
    free_memory: bool = True
