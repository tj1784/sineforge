"""Schemas for factual, evidence-only runtime model/workflow catalog reads."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceStatus(StrEnum):
    """Factual status derived only from registered DB/runtime evidence."""

    unknown = "unknown"
    registered = "registered"
    path_recorded = "path_recorded"
    checksum_recorded = "checksum_recorded"
    benchmark_recorded = "benchmark_recorded"


class NativeVoiceCapability(StrEnum):
    supported = "supported"
    unsupported = "unsupported"
    unknown = "unknown"


class ModelCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family: str
    name: str
    source_url: str | None = None
    license: str | None = None
    evidence_level: str
    notes: str | None = None
    registration_status: EvidenceStatus = EvidenceStatus.registered
    variant_count: int = 0


class ModelVariantCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: UUID
    variant_name: str
    params_b: float | None = None
    precision: str | None = None
    quantization: str | None = None
    compatible_24gb_status: str
    notes: str | None = None
    # Factual capability fields — never invent support.
    native_voice_capability: str = NativeVoiceCapability.unknown.value
    native_voice_capability_source: str | None = None
    native_voice_capability_checked_at: datetime | None = None
    # Evidence-only install/path/benchmark claims.
    path_status: EvidenceStatus = EvidenceStatus.unknown
    checksum_status: EvidenceStatus = EvidenceStatus.unknown
    has_file_path_recorded: bool = False
    has_sha256_recorded: bool = False
    has_file_size_recorded: bool = False
    file_size_bytes: int | None = None
    benchmark_status: EvidenceStatus = EvidenceStatus.unknown
    benchmark_run_count: int = 0
    # Explicit non-claims for clients.
    claims: dict = Field(
        default_factory=lambda: {
            "installed": False,
            "validated": False,
            "benchmarked": False,
            "downloaded": False,
        }
    )


class WorkflowTemplateCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: str
    sha256: str
    comfyui_commit: str | None = None
    created_at: datetime
    registration_status: EvidenceStatus = EvidenceStatus.registered
    has_manifest: bool = True
    has_workflow_api: bool = True
    benchmark_status: EvidenceStatus = EvidenceStatus.unknown
    benchmark_run_count: int = 0
    claims: dict = Field(
        default_factory=lambda: {
            "installed": False,
            "validated": False,
            "benchmarked": False,
            "comfy_reachable": False,
        }
    )


class QuantizationCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    applies_to: str
    loader_node: str | None = None
    evidence_level: str
    recommended_24gb: bool = False
    notes: str | None = None
    registration_status: EvidenceStatus = EvidenceStatus.registered


class LoraCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    purpose: str
    evidence_level: str
    quantized_base_status: str = "unknown"
    license: str | None = None
    notes: str | None = None
    path_status: EvidenceStatus = EvidenceStatus.unknown
    has_file_path_recorded: bool = False
    has_sha256_recorded: bool = False
    claims: dict = Field(
        default_factory=lambda: {
            "installed": False,
            "validated": False,
            "benchmarked": False,
        }
    )


class RuntimeCatalogSummary(BaseModel):
    models: int = 0
    model_variants: int = 0
    workflow_templates: int = 0
    quantizations: int = 0
    loras: int = 0
    benchmark_runs: int = 0
    evidence_note: str = (
        "Statuses reflect registered database evidence only. "
        "Unknown remains unknown. This endpoint never probes ComfyUI, GPUs, "
        "installers, downloads, or external providers."
    )


class RuntimeCatalogResponse(BaseModel):
    summary: RuntimeCatalogSummary
    models: list[ModelCatalogItem] = Field(default_factory=list)
    model_variants: list[ModelVariantCatalogItem] = Field(default_factory=list)
    workflow_templates: list[WorkflowTemplateCatalogItem] = Field(default_factory=list)
    quantizations: list[QuantizationCatalogItem] = Field(default_factory=list)
    loras: list[LoraCatalogItem] = Field(default_factory=list)


class LocalModelInventoryResponse(BaseModel):
    """Read-only filename inventory reported by the active ComfyUI instance."""

    status: str
    source_url: str
    total_count: int = 0
    categories: dict[str, list[str]] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)


class WorkflowArchetypeCatalogItem(BaseModel):
    archetype_id: str
    name: str
    modality: str
    default_model_key: str | None = None
    readiness: str
    enabled: bool = False


class WorkflowCandidateCatalogItem(BaseModel):
    candidate_id: str
    archetype_id: str
    name: str
    modality: str
    source_url: str
    source_tier: str
    required_model_key: str
    relative_path: str | None = None
    admission_state: str
    notes: str


class WorkflowCandidateAssessmentItem(BaseModel):
    candidate_id: str
    state: str
    local_path: str | None = None
    sha256: str | None = None
    base_model_references: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class WorkflowPresetCatalogItem(BaseModel):
    preset_id: str
    name: str
    modality: str
    model_key: str
    default_archetype_id: str
    quality_profile: str
    readiness: str
    enabled: bool = False


class WorkflowCandidateRegistryResponse(BaseModel):
    catalog_version: str
    execution_policy: str
    archetypes: list[WorkflowArchetypeCatalogItem] = Field(default_factory=list)
    candidates: list[WorkflowCandidateCatalogItem] = Field(default_factory=list)
    assessments: list[WorkflowCandidateAssessmentItem] = Field(default_factory=list)
    presets: list[WorkflowPresetCatalogItem] = Field(default_factory=list)
