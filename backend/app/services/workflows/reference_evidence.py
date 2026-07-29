"""Strict, non-executing validation for versioned workflow-reference evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowReferenceArtifact(BaseModel):
    """One disabled artifact whose provenance is stronger than runtime claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    artifact_kind: Literal["comfyui_ui_workflow", "reconstruction_manifest"]
    provenance_class: Literal["official_reference", "recovery_evidence"]
    not_author_original: Literal[True]
    relative_path: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_name: str = Field(min_length=1, max_length=300)
    archive_entry: str = Field(min_length=1, max_length=500)
    official_source_url: str | None
    official_source_commit: str | None
    capabilities: tuple[str, ...] = Field(min_length=1)
    api_format: Literal[False]
    runtime_qualified: Literal[False]
    enabled: Literal[False]
    qualification_blockers: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_provenance(self) -> WorkflowReferenceArtifact:
        if "\\" in self.relative_path or self.relative_path.startswith("/"):
            raise ValueError("relative_path must be portable and repository-relative")
        if ".." in Path(self.relative_path).parts:
            raise ValueError("relative_path must not traverse outside the repository")
        if self.provenance_class == "official_reference":
            if not self.official_source_url or not self.official_source_commit:
                raise ValueError(
                    "official references require a pinned source URL and commit"
                )
        elif self.official_source_url is not None or self.official_source_commit is not None:
            raise ValueError(
                "recovery evidence must not invent an official source identity"
            )
        return self


class WorkflowReferenceCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    catalog_id: str = Field(min_length=1, max_length=128)
    execution_policy: Literal["disabled_evidence_only"]
    artifacts: tuple[WorkflowReferenceArtifact, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_artifact_ids(self) -> WorkflowReferenceCatalog:
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("workflow-reference artifact IDs must be unique")
        return self


EvidenceState = Literal[
    "evidence_verified",
    "missing",
    "hash_mismatch",
    "invalid_json",
    "invalid_structure",
]


@dataclass(frozen=True, slots=True)
class WorkflowReferenceAssessment:
    artifact_id: str
    state: EvidenceState
    local_path: str
    actual_sha256: str | None
    reasons: tuple[str, ...]


def load_reference_catalog(
    repository_root: Path | None = None,
) -> WorkflowReferenceCatalog:
    repository_root = repository_root or Path(__file__).resolve().parents[4]
    path = repository_root / "storage/workflow_templates/wan22_reference_catalog.json"
    return WorkflowReferenceCatalog.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def assess_reference_artifact(
    artifact: WorkflowReferenceArtifact,
    repository_root: Path,
) -> WorkflowReferenceAssessment:
    """Validate bytes and structure without importing or executing the graph."""

    root = repository_root.resolve()
    local_path = (root / artifact.relative_path).resolve()
    if not local_path.is_relative_to(root):
        return WorkflowReferenceAssessment(
            artifact.artifact_id,
            "invalid_structure",
            str(local_path),
            None,
            ("Artifact path escapes the repository root.",),
        )
    if not local_path.is_file():
        return WorkflowReferenceAssessment(
            artifact.artifact_id,
            "missing",
            str(local_path),
            None,
            ("Versioned evidence file is missing.",),
        )

    raw = local_path.read_bytes()
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != artifact.sha256:
        return WorkflowReferenceAssessment(
            artifact.artifact_id,
            "hash_mismatch",
            str(local_path),
            actual_sha256,
            ("Versioned evidence bytes do not match the catalog digest.",),
        )
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return WorkflowReferenceAssessment(
            artifact.artifact_id,
            "invalid_json",
            str(local_path),
            actual_sha256,
            ("Versioned evidence is not valid UTF-8 JSON.",),
        )

    if artifact.artifact_kind == "comfyui_ui_workflow":
        valid_structure = (
            isinstance(document, dict)
            and isinstance(document.get("nodes"), list)
            and bool(document["nodes"])
        )
        structure_reason = (
            "ComfyUI UI workflow parsed; it remains disabled and is not API format."
        )
    else:
        valid_structure = (
            isinstance(document, dict)
            and isinstance(document.get("provenance"), dict)
            and document["provenance"].get("wan_workflows")
            == "official_comfyui_reference_not_author_original"
        )
        structure_reason = (
            "Recovery manifest parsed and retains the WAN provenance boundary."
        )
    if not valid_structure:
        return WorkflowReferenceAssessment(
            artifact.artifact_id,
            "invalid_structure",
            str(local_path),
            actual_sha256,
            ("Evidence JSON does not match its declared artifact kind.",),
        )
    return WorkflowReferenceAssessment(
        artifact.artifact_id,
        "evidence_verified",
        str(local_path),
        actual_sha256,
        (
            structure_reason,
            "No runtime, model, node, quality, or license qualification is claimed.",
        ),
    )


def assess_reference_catalog(
    repository_root: Path | None = None,
) -> tuple[WorkflowReferenceAssessment, ...]:
    repository_root = repository_root or Path(__file__).resolve().parents[4]
    catalog = load_reference_catalog(repository_root)
    return tuple(
        assess_reference_artifact(artifact, repository_root)
        for artifact in catalog.artifacts
    )
