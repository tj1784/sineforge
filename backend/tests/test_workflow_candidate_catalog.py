import json
from pathlib import Path

import pytest

from backend.app.api.routes.runtime_catalog import get_workflow_candidate_registry
from backend.app.services.generation_model_contract import (
    PLANNING_IMAGE_MODEL,
    VIDEO_MODEL,
    validate_workflow_base_models,
    workflow_base_model_references,
)
from backend.app.services.workflows.candidate_catalog import (
    ARCHETYPES,
    CANDIDATES,
    assess_candidate,
    build_preset_catalog,
    catalog_document,
    validate_catalog_contract,
)


def test_catalog_has_twelve_archetypes_and_exactly_sixty_four_presets() -> None:
    validate_catalog_contract()
    assert len(ARCHETYPES) == 12
    assert len({item.archetype_id for item in ARCHETYPES}) == 12

    presets = build_preset_catalog()
    assert len(presets) == 64
    assert presets[0]["preset_id"] == "CF-PRESET-001"
    assert presets[-1]["preset_id"] == "CF-PRESET-064"
    assert not any(item["enabled"] for item in presets)


def test_catalog_restricts_every_non_rejected_candidate_to_product_models() -> None:
    document = catalog_document()
    candidates = document["candidates"]
    assert any(
        item["admission_state"] == "rejected_model_contract"
        and item["required_model_key"] == "flux1_dev_gguf"
        for item in candidates
    )
    assert {
        item["required_model_key"]
        for item in candidates
        if item["admission_state"] != "rejected_model_contract"
    } == {"flux2_dev_fp8mixed", "ltx2_3_22b_distilled_1_1_fp8"}


def test_read_only_runtime_endpoint_exposes_registry() -> None:
    response = get_workflow_candidate_registry()
    assert response.execution_policy == "non_executing_candidate_registry"
    assert len(response.archetypes) == 12
    assert len(response.presets) == 64
    assert len(response.assessments) == len(response.candidates)
    assert {
        item.state for item in response.assessments
    } <= {
        "source_resolution_required",
        "download_pending",
        "candidate_review",
        "benchmark_required",
        "rejected_model_contract",
    }
    assert not any(item.enabled for item in response.presets)


def test_workflow_model_scanner_supports_api_and_ui_formats() -> None:
    api_workflow = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": PLANNING_IMAGE_MODEL},
        }
    }
    ui_workflow = {
        "nodes": [
            {
                "id": 1,
                "type": "CheckpointLoaderSimple",
                "widgets_values": [VIDEO_MODEL],
            }
        ]
    }
    assert workflow_base_model_references(api_workflow) == (PLANNING_IMAGE_MODEL,)
    assert workflow_base_model_references(ui_workflow) == (VIDEO_MODEL,)
    assert validate_workflow_base_models(api_workflow, "image") == (
        PLANNING_IMAGE_MODEL,
    )
    assert validate_workflow_base_models(ui_workflow, "video") == (VIDEO_MODEL,)


@pytest.mark.parametrize(
    "model_name",
    [
        "flux1-dev-Q8_0.gguf",
        "flux1-fill-dev.safetensors",
        "flux2_dev_fp8mixed.safetensors",
    ],
)
def test_workflow_model_contract_accepts_local_flux_family_for_images(model_name: str) -> None:
    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": model_name},
        }
    }
    assert validate_workflow_base_models(workflow, "image") == (model_name,)


@pytest.mark.parametrize(
    ("modality", "model_name"),
    [
        ("image", "cyberrealisticXL_v100.safetensors"),
        ("video", "ltx-2.3-22b-dev-fp8.safetensors"),
        ("video", "ltx-2.3-22b-distilled-1.1.safetensors"),
    ],
)
def test_workflow_model_contract_rejects_non_flux_images_and_non_contract_videos(
    modality: str, model_name: str
) -> None:
    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": model_name},
        }
    }
    with pytest.raises(ValueError):
        validate_workflow_base_models(workflow, modality)  # type: ignore[arg-type]


def test_missing_candidate_bytes_stay_download_pending(tmp_path: Path) -> None:
    candidate = next(item for item in CANDIDATES if item.relative_path)
    assessment = assess_candidate(candidate, tmp_path)
    assert assessment.state == "download_pending"
    assert assessment.sha256 is None


def test_downloaded_candidate_is_hashed_but_not_enabled(tmp_path: Path) -> None:
    candidate = next(
        item
        for item in CANDIDATES
        if item.modality == "image"
        and item.source_tier == "official"
        and item.relative_path
    )
    local_path = tmp_path / candidate.relative_path
    local_path.parent.mkdir(parents=True)
    local_path.write_text(
        json.dumps(
            {
                "1": {
                    "class_type": "UNETLoader",
                    "inputs": {"unet_name": PLANNING_IMAGE_MODEL},
                }
            }
        ),
        encoding="utf-8",
    )
    assessment = assess_candidate(candidate, tmp_path)
    assert assessment.state == "benchmark_required"
    assert assessment.sha256
    assert assessment.base_model_references == (PLANNING_IMAGE_MODEL,)
