"""Admission-evidence tests for the disabled WAN 2.2 reference package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from backend.app.services.workflows.reference_evidence import (
    WorkflowReferenceArtifact,
    assess_reference_artifact,
    assess_reference_catalog,
    load_reference_catalog,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_wan_reference_catalog_is_disabled_and_provenance_explicit():
    catalog = load_reference_catalog(REPOSITORY_ROOT)

    assert catalog.execution_policy == "disabled_evidence_only"
    assert len(catalog.artifacts) == 3
    assert {artifact.provenance_class for artifact in catalog.artifacts} == {
        "official_reference",
        "recovery_evidence",
    }
    assert all(artifact.not_author_original for artifact in catalog.artifacts)
    assert all(not artifact.api_format for artifact in catalog.artifacts)
    assert all(not artifact.runtime_qualified for artifact in catalog.artifacts)
    assert all(not artifact.enabled for artifact in catalog.artifacts)


def test_all_versioned_reference_bytes_and_structures_verify():
    assessments = assess_reference_catalog(REPOSITORY_ROOT)

    assert len(assessments) == 3
    assert {assessment.state for assessment in assessments} == {
        "evidence_verified"
    }
    assert all(
        "No runtime, model, node, quality, or license qualification is claimed."
        in assessment.reasons
        for assessment in assessments
    )


def test_official_graphs_are_exact_ui_references_not_api_templates():
    catalog = load_reference_catalog(REPOSITORY_ROOT)
    official = [
        artifact
        for artifact in catalog.artifacts
        if artifact.provenance_class == "official_reference"
    ]

    assert {artifact.sha256 for artifact in official} == {
        "6eea9b627b10fcfaf3e75a43aad2c58d8daabdbf72b32ede1602c668cac376bb",
        "9fb579e07caff9081c14a4c0e3b983e210aa7d976f83f1c2758d2ad6ed949fdf",
    }
    for artifact in official:
        path = REPOSITORY_ROOT / artifact.relative_path
        raw = path.read_bytes()
        document = json.loads(raw)
        assert hashlib.sha256(raw).hexdigest() == artifact.sha256
        assert isinstance(document["nodes"], list)
        assert document["nodes"]
        assert path.name == "workflow_ui_reference.json"
        assert not (path.parent / "workflow_api.json").exists()
        assert not (path.parent / "workflow_manifest.json").exists()


def test_recovery_manifest_retains_source_hygiene_labels():
    catalog = load_reference_catalog(REPOSITORY_ROOT)
    evidence = next(
        artifact
        for artifact in catalog.artifacts
        if artifact.artifact_kind == "reconstruction_manifest"
    )
    document = json.loads(
        (REPOSITORY_ROOT / evidence.relative_path).read_text(encoding="utf-8")
    )

    assert (
        document["provenance"]["flux_workflow"]
        == "recovered_exactly_from_png_metadata"
    )
    assert (
        document["provenance"]["wan_workflows"]
        == "official_comfyui_reference_not_author_original"
    )
    assert document["provenance"]["long_video_process"] == "article_derived"
    assert document["provenance"]["duration_and_interpolation"].startswith(
        "forensic_inference"
    )


def test_catalog_schema_cannot_enable_or_runtime_qualify_reference():
    catalog = load_reference_catalog(REPOSITORY_ROOT)
    data = catalog.artifacts[0].model_dump()

    data["enabled"] = True
    with pytest.raises(ValidationError):
        WorkflowReferenceArtifact.model_validate(data)

    data["enabled"] = False
    data["runtime_qualified"] = True
    with pytest.raises(ValidationError):
        WorkflowReferenceArtifact.model_validate(data)


def test_assessment_fails_closed_on_hash_mismatch(tmp_path):
    source_catalog = load_reference_catalog(REPOSITORY_ROOT)
    source = source_catalog.artifacts[0]
    relative_path = Path("storage/workflow_templates/reference.json")
    local_path = tmp_path / relative_path
    local_path.parent.mkdir(parents=True)
    local_path.write_text('{"nodes":[]}', encoding="utf-8")
    artifact = source.model_copy(
        update={"relative_path": relative_path.as_posix()}
    )

    assessment = assess_reference_artifact(artifact, tmp_path)

    assert assessment.state == "hash_mismatch"
    assert assessment.actual_sha256 != artifact.sha256
