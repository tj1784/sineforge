"""Project-lane and workflow-admission tests for Agentless dry runs."""

from __future__ import annotations

from collections.abc import Generator
import hashlib
import json
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.routes import agentless_workflow
from backend.app.db.base import Base, Project, WorkflowTemplate
from backend.app.db.session import get_db
from backend.app.services.agentless_workflow import (
    ROLE_REQUIRED_SEMANTIC_MAPPINGS,
    AgentlessCompilationError,
)
from backend.app.schemas.agentless_workflow import AgentlessWorkflowRole


def _sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.fixture()
def api_context(
    tmp_path,
) -> Generator[
    tuple[TestClient, sessionmaker, UUID, UUID],
    None,
    None,
]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'agentless.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    agentless_project_id = uuid4()
    studio_project_id = uuid4()
    with session_factory() as db:
        db.add_all(
            (
                Project(
                    id=agentless_project_id,
                    name="Agentless",
                    description=None,
                    workflow_lane="agentless",
                ),
                Project(
                    id=studio_project_id,
                    name="Studio",
                    description=None,
                    workflow_lane="cineforge_studio",
                ),
            )
        )
        db.commit()

    app = FastAPI()
    app.include_router(agentless_workflow.router)

    def _override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as client:
        yield (
            client,
            session_factory,
            agentless_project_id,
            studio_project_id,
        )
    engine.dispose()


def _payload(
    project_id: UUID,
    *,
    anchor_version: str | None = None,
    anchor_sha256: str | None = None,
    video_version: str | None = None,
    video_sha256: str | None = None,
) -> dict:
    anchor_ref = {"template_id": "flux2-anchor"}
    video_ref = {"template_id": "ltx23-scene-reset"}
    if anchor_version is not None:
        anchor_ref["version"] = anchor_version
    if anchor_sha256 is not None:
        anchor_ref["sha256"] = anchor_sha256
    if video_version is not None:
        video_ref["version"] = video_version
    if video_sha256 is not None:
        video_ref["sha256"] = video_sha256
    return {
        "schema_version": "sineforge.agentless-scene-reset-request/v1",
        "project_id": str(project_id),
        "workflow_templates": {
            "anchor": anchor_ref,
            "video": video_ref,
        },
        "master_policy": {
            "intermediate_codec": "ffv1",
            "delivery_codec": "h265",
            "delivery_encode_count": 1,
            "intermediate_reencoding_allowed": False,
            "anchor_format": "png",
        },
        "scenes": [
            {
                "scene_id": "S001",
                "duration_sec": 20.0,
                "visible_character_ids": ["SARAH"],
                "character_reference_asset_ids": {
                    "SARAH": ["asset-sarah-front"],
                },
                "flux_reference_assets": {
                    "set_studio_asset_ids": ["asset-studio-main"],
                    "composition_asset_ids": ["asset-closeup-composition"],
                    "pose_asset_ids": [],
                    "prop_asset_ids": ["asset-microphone"],
                },
                "ingredients_reference_asset_id": "sheet-sarah-v1",
                "character_description_block": (
                    "Preserve Sarah's canonical identity, wardrobe, age, hair, "
                    "complexion, and accessories from the supplied references."
                ),
                "anchor_prompt": "A stable podcast close-up of Sarah.",
                "video_prompt": "Sarah speaks calmly to camera.",
                "image_seed": 101,
                "video_seed": 202,
                "output_prefix": "episode-S001",
            }
        ],
    }


def _admit_workflow(
    db: Session,
    *,
    name: str,
    role: str,
    class_type: str,
    include_semantic_mappings: bool = True,
    broken_mapping: str | None = None,
) -> str:
    semantic_role = AgentlessWorkflowRole(role)
    mapping_keys = sorted(
        ROLE_REQUIRED_SEMANTIC_MAPPINGS[semantic_role]
    )
    inputs = (
        {semantic_key: None for semantic_key in mapping_keys}
        if include_semantic_mappings
        else {}
    )
    workflow = {
        "1": {
            "class_type": class_type,
            "inputs": inputs,
        }
    }
    mappings = (
        {
            semantic_key: {
                "node_id": "1",
                "class_type": class_type,
                "input": (
                    "missing-input"
                    if semantic_key == broken_mapping
                    else semantic_key
                ),
            }
            for semantic_key in mapping_keys
        }
        if include_semantic_mappings
        else {}
    )
    sha256 = _sha256(workflow)
    db.add(
        WorkflowTemplate(
            name=name,
            version="1.0",
            workflow_api_json=workflow,
            manifest_json={
                "api_format": True,
                "runtime_qualified": True,
                "agentless_role": role,
                "nodes": mappings,
            },
            sha256=sha256,
            comfyui_commit="test-commit",
            custom_node_snapshot={},
        )
    )
    db.commit()
    return sha256


def test_agentless_routes_reject_studio_projects_with_stable_code(
    api_context,
) -> None:
    client, _, _, studio_project_id = api_context

    profile = client.get(
        f"/projects/{studio_project_id}/agentless-workflow"
    )
    dry_run = client.post(
        f"/projects/{studio_project_id}/agentless-workflow/dry-run",
        json=_payload(studio_project_id),
    )

    assert profile.status_code == 409
    assert profile.json()["detail"]["code"] == "workflow_lane_mismatch"
    assert dry_run.status_code == 409
    assert dry_run.json()["detail"]["code"] == "workflow_lane_mismatch"


def test_profile_is_explicitly_agentless_and_fail_closed(api_context) -> None:
    client, _, project_id, _ = api_context

    response = client.get(f"/projects/{project_id}/agentless-workflow")

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_lane"] == "agentless"
    assert body["agent_runtime_required"] is True
    assert body["local_planning_agent_required"] is True
    assert body["hosted_planning_agents_allowed"] is False
    assert body["default_planning_agent"] == "qwen"
    assert body["selected_planning_agent"] == "qwen"
    assert body["prompt_artifact_format"] == "json"
    assert body["prompt_artifact_extension"] == ".json"
    assert body["deterministic_python_orchestrator"] is True
    assert body["max_logical_scenes"] == 50
    assert body["default_ten_second_frame_count"] == 241
    assert body["default_ten_second_playback_duration_sec"] == pytest.approx(
        241 / 24
    )
    assert body["batch_size"] == 1
    assert body["max_active_gpu_jobs"] == 1
    assert body["default_master_policy"]["intermediate_codec"] == (
        "prores_422_hq"
    )
    assert all(
        requirement["required_semantic_mappings"]
        for requirement in body["workflow_requirements"]
    )
    assert body["readiness"]["ready_to_execute"] is False
    assert body["readiness"]["workflows_admitted"] is False
    assert {
        admission["role"] for admission in body["readiness"]["admissions"]
    } == {"flux_anchor", "ltx_ingredients_i2v"}
    assert all(
        admission["status"] == "missing_exact_pin"
        for admission in body["readiness"]["admissions"]
    )


def test_dry_run_compiles_without_writes_and_reports_missing_exact_pins(
    api_context,
) -> None:
    client, session_factory, project_id, _ = api_context

    response = client.post(
        f"/projects/{project_id}/agentless-workflow/dry-run",
        json=_payload(project_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["status"] == "valid_with_blockers"
    assert body["plan"]["segment_count"] == 2
    assert [
        segment["frame_count"] for segment in body["plan"]["segments"]
    ] == [241, 241]
    assert [
        segment["playback_duration_sec"]
        for segment in body["plan"]["segments"]
    ] == pytest.approx([241 / 24, 241 / 24])
    assert body["plan"]["master_policy"] == {
        "intermediate_codec": "ffv1",
        "delivery_codec": "h265",
        "delivery_encode_count": 1,
        "intermediate_reencoding_allowed": False,
        "anchor_format": "png",
    }
    assert body["plan"]["submission_enabled"] is False
    assert body["readiness"]["ready_to_execute"] is False
    assert body["readiness"]["workflows_admitted"] is False
    assert {
        admission["status"]
        for admission in body["readiness"]["admissions"]
    } == {"missing_exact_pin"}

    with session_factory() as db:
        assert db.query(WorkflowTemplate).count() == 0


def test_exact_api_workflows_can_be_admitted_but_submission_stays_blocked(
    api_context,
) -> None:
    client, session_factory, project_id, _ = api_context
    with session_factory() as db:
        anchor_sha = _admit_workflow(
            db,
            name="flux2-anchor",
            role="flux_anchor",
            class_type="TestFluxAnchor",
        )
        video_sha = _admit_workflow(
            db,
            name="ltx23-scene-reset",
            role="ltx_ingredients_i2v",
            class_type="TestLtxIngredientsI2V",
        )

    response = client.post(
        f"/projects/{project_id}/agentless-workflow/dry-run",
        json=_payload(
            project_id,
            anchor_version="1.0",
            anchor_sha256=anchor_sha,
            video_version="1.0",
            video_sha256=video_sha,
        ),
    )

    assert response.status_code == 200
    readiness = response.json()["readiness"]
    assert readiness["workflows_admitted"] is True
    assert readiness["ready_to_execute"] is False
    assert {
        admission["status"] for admission in readiness["admissions"]
    } == {"admitted"}
    assert all(
        admission["validated_semantic_mappings"]
        for admission in readiness["admissions"]
    )
    assert [blocker["code"] for blocker in readiness["blockers"]] == [
        "agentless_execution_boundary_not_implemented"
    ]


def test_dry_run_rejects_body_and_route_project_mismatch(
    api_context,
) -> None:
    client, _, project_id, _ = api_context

    response = client.post(
        f"/projects/{project_id}/agentless-workflow/dry-run",
        json=_payload(uuid4()),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "project_scope_mismatch"


def test_role_label_without_semantic_mappings_is_not_admitted(
    api_context,
) -> None:
    client, session_factory, project_id, _ = api_context
    with session_factory() as db:
        anchor_sha = _admit_workflow(
            db,
            name="flux2-anchor",
            role="flux_anchor",
            class_type="TestFluxAnchor",
            include_semantic_mappings=False,
        )
        video_sha = _admit_workflow(
            db,
            name="ltx23-scene-reset",
            role="ltx_ingredients_i2v",
            class_type="TestLtxIngredientsI2V",
        )

    response = client.post(
        f"/projects/{project_id}/agentless-workflow/dry-run",
        json=_payload(
            project_id,
            anchor_version="1.0",
            anchor_sha256=anchor_sha,
            video_version="1.0",
            video_sha256=video_sha,
        ),
    )

    assert response.status_code == 200
    readiness = response.json()["readiness"]
    assert readiness["workflows_admitted"] is False
    by_role = {
        admission["role"]: admission
        for admission in readiness["admissions"]
    }
    assert by_role["flux_anchor"]["status"] == "semantic_mapping_invalid"
    assert by_role["flux_anchor"]["admitted"] is False
    assert by_role["ltx_ingredients_i2v"]["status"] == "admitted"


def test_every_semantic_mapping_must_resolve_exact_node_class_and_input(
    api_context,
) -> None:
    client, session_factory, project_id, _ = api_context
    with session_factory() as db:
        anchor_sha = _admit_workflow(
            db,
            name="flux2-anchor",
            role="flux_anchor",
            class_type="TestFluxAnchor",
            broken_mapping="image_seed",
        )
        video_sha = _admit_workflow(
            db,
            name="ltx23-scene-reset",
            role="ltx_ingredients_i2v",
            class_type="TestLtxIngredientsI2V",
        )

    response = client.post(
        f"/projects/{project_id}/agentless-workflow/dry-run",
        json=_payload(
            project_id,
            anchor_version="1.0",
            anchor_sha256=anchor_sha,
            video_version="1.0",
            video_sha256=video_sha,
        ),
    )

    assert response.status_code == 200
    admission = next(
        item
        for item in response.json()["readiness"]["admissions"]
        if item["role"] == "flux_anchor"
    )
    assert admission["status"] == "semantic_mapping_invalid"
    assert "missing-input" in admission["detail"]


def test_compiler_failure_is_exposed_as_clean_422(
    api_context,
    monkeypatch,
) -> None:
    client, _, project_id, _ = api_context

    def _fail_compilation(*_args, **_kwargs):
        raise AgentlessCompilationError(
            "Derived segment_id is not a valid bounded opaque identifier."
        )

    monkeypatch.setattr(
        agentless_workflow,
        "dry_run_agentless_workflow",
        _fail_compilation,
    )

    response = client.post(
        f"/projects/{project_id}/agentless-workflow/dry-run",
        json=_payload(project_id),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "agentless_compilation_failed",
        "message": (
            "Derived segment_id is not a valid bounded opaque identifier."
        ),
    }
