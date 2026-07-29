from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ApiCallerWorkflowSummary(BaseModel):
    id: UUID
    name: str
    version: str
    description: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    source_filename: str | None = None
    node_count: int
    sha256: str
    created_at: str
    updated_at: str


class ApiCallerWorkflowDetail(ApiCallerWorkflowSummary):
    workflow: dict[str, Any]


class ApiCallerWorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    version: str = Field(default="1.0", min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    source_filename: str | None = Field(default=None, max_length=1024)
    workflow: dict[str, Any]


class ApiCallerWorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    version: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    workflow: dict[str, Any] | None = None


class ApiCallerAnalyzeRequest(BaseModel):
    workflow: dict[str, Any]


class ApiCallerRunRequest(BaseModel):
    workflow: dict[str, Any]
    workflow_name: str = Field(default="sineforge-api-caller", min_length=1, max_length=160)
    queue_count: int = Field(default=1, ge=1, le=50)
    merge_movie: bool = False
    vary_seed: bool = False
    save_latents: bool = False


class ApiCallerRunnerImportRequest(BaseModel):
    workflow_ids: list[str] | None = None


class ApiCallerRunnerImportResponse(BaseModel):
    ok: bool
    imported: int
    updated: int
    skipped: int
    workflows: list[ApiCallerWorkflowSummary]


class ApiCallerRemoveResponse(BaseModel):
    ok: bool
    id: UUID
    name: str
    archived: bool
