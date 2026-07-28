"""Contracts for CineForge's exact seven-phase production lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


PhaseLifecycleState = Literal[
    "not_started",
    "drafting",
    "qa_pending",
    "needs_revision",
    "ready_for_review",
    "approved",
    "blocked",
]

PhaseVersionSource = Literal[
    "baseline",
    "manual",
    "generated",
    "revision",
    "imported",
]

PhaseOneBaselineKey = Literal["transfiguration_phase_one"]


class PhaseOneGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_prompt: str = Field(min_length=1)
    target_duration_sec: float = Field(gt=0, le=21_600)
    audience: str | None = None
    genre: str | None = None
    tone: str | None = None
    language: str = Field(default="English", min_length=1, max_length=100)
    visual_style: str | None = None
    narration_dialogue_preference: str | None = None
    source_fidelity_constraints: str | None = None
    content_constraints: str | None = None
    requested_chapter_count: int = Field(default=1, ge=1, le=50)
    chapter_intake: list[dict[str, Any]] = Field(default_factory=list)
    comparison_baseline: PhaseOneBaselineKey | None = None
    requested_by: str | None = Field(default=None, max_length=200)


class PhaseOneRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version_number: int = Field(gt=0)
    project_title: str = Field(min_length=1, max_length=300)
    logline: str = Field(min_length=1)
    short_synopsis: str = Field(min_length=1)
    detailed_treatment: str = Field(min_length=1)
    complete_script: str = Field(min_length=1)
    narration_script: str = ""
    dialogue_script: str = ""
    non_dialogue_action: list[str] = Field(default_factory=list)
    silent_visual_beats: list[str] = Field(default_factory=list)
    emotional_progression: list[str] = Field(default_factory=list)
    dramatic_escalation: list[str] = Field(default_factory=list)
    source_fidelity_notes: list[str] = Field(default_factory=list)
    creative_assumptions: list[str] = Field(default_factory=list)
    requested_by: str | None = Field(default=None, max_length=200)


class PhaseVersionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=4000)
    requested_by: str | None = Field(default=None, max_length=200)


class PhaseApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_by: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=4000)


class PhaseApproveResponse(BaseModel):
    pipeline: "ProductionPipelineRead"
    phase: "ProductionPhaseRead"
    message: str


class PhaseVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    label: str
    notes: str
    source: PhaseVersionSource
    lifecycle_state: PhaseLifecycleState
    completed: bool
    snapshot_schema_version: int
    input_hash: str
    output_hash: str
    created_by: str | None = None
    previous_version_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class PhaseVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    label: str = ""
    notes: str = ""
    source: PhaseVersionSource = "manual"
    snapshot_schema_version: int = 1
    lifecycle_state: PhaseLifecycleState
    completed: bool
    input_snapshot_json: dict[str, Any]
    output_json: dict[str, Any]
    input_hash: str
    output_hash: str
    created_by: str | None = None
    previous_version_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    verified: bool = True


class PhaseVersionDetail(PhaseVersionRead):
    story_id: UUID
    project_id: UUID
    phase_number: int
    phase_name: str


class QAReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: UUID | None = None
    report_json: dict
    created_at: datetime


class ProductionPhaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    phase_number: int
    name: str
    lifecycle_state: PhaseLifecycleState
    current_version_number: int | None = None
    version_count: int = 0
    is_locked: bool
    locked_reason: str | None = None
    is_stale: bool
    stale_reason: str | None = None
    generation_completed_at: datetime | None = None
    approved_at: datetime | None = None
    latest_version: PhaseVersionRead | None = None
    latest_qa_report: QAReportRead | None = None


class ProductionPipelineRead(BaseModel):
    story_id: UUID
    project_id: UUID
    exact_phase_count: Literal[7] = 7
    phases: list[ProductionPhaseRead]
    completion_message: str | None = None


class PhaseOneMutationResponse(BaseModel):
    pipeline: ProductionPipelineRead
    phase: ProductionPhaseRead
    completion_message: str


class PhaseVersionCreateResponse(BaseModel):
    version: PhaseVersionDetail
    pipeline: ProductionPipelineRead


class PhaseHistoryExportIntegrity(BaseModel):
    verified: Literal[True] = True
    iteration_count: int
    snapshot_count: int
    phase_counts: dict[str, int]
    hashes: list[str]


class PhaseHistoryExport(BaseModel):
    schema_name: Literal["cineforge.phase-history"] = "cineforge.phase-history"
    version: Literal[1] = 1
    project_id: UUID
    story_id: UUID
    exported_at: datetime
    integrity: PhaseHistoryExportIntegrity
    iterations: list[PhaseVersionDetail]
