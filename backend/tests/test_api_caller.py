from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes.api_caller import get_api_workflow_library
from backend.app.main import create_app
from backend.app.services.api_workflows import (
    ApiWorkflowLibrary,
    ApiWorkflowNotFound,
    ApiWorkflowValidationError,
    normalize_api_workflow,
)
from backend.app.services.comfy.runner import ComfyAPIRunnerClient


def _workflow(prompt: str = "A cinematic test frame") -> dict:
    return {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
            "_meta": {"title": "Positive prompt"},
        },
        "2": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "example.safetensors"},
        },
    }


def test_api_workflow_library_create_update_and_recoverable_remove(tmp_path: Path):
    library = ApiWorkflowLibrary(tmp_path)

    created = library.create(
        name="WAN test",
        version="1.0",
        description="operator copy",
        workflow={"prompt": _workflow()},
        source_kind="operator_import",
        source_filename="wan.api.json",
    )

    assert created["node_count"] == 2
    assert created["workflow"]["1"]["inputs"]["text"] == "A cinematic test frame"
    assert len(created["sha256"]) == 64
    assert library.list()[0]["id"] == created["id"]

    updated = library.update(
        created["id"],
        name="WAN test edited",
        description="",
        workflow=_workflow("Edited prompt"),
    )
    assert updated["name"] == "WAN test edited"
    assert updated["description"] is None
    assert updated["workflow"]["1"]["inputs"]["text"] == "Edited prompt"
    assert updated["sha256"] != created["sha256"]

    removed = library.remove(created["id"])
    assert removed == {
        "ok": True,
        "id": created["id"],
        "name": "WAN test edited",
        "archived": True,
    }
    assert library.list() == []
    assert len(list((tmp_path / "api_workflow_archive").glob("*.json"))) == 1
    with pytest.raises(ApiWorkflowNotFound):
        library.get(created["id"])


def test_api_workflow_validation_rejects_visual_graph():
    with pytest.raises(ApiWorkflowValidationError, match="API-format"):
        normalize_api_workflow(
            {
                "nodes": [{"id": 1, "type": "KSampler"}],
                "links": [],
                "version": 0.4,
            }
        )


def test_api_caller_crud_routes_use_operator_library(tmp_path: Path):
    library = ApiWorkflowLibrary(tmp_path)
    app = create_app()
    app.dependency_overrides[get_api_workflow_library] = lambda: library
    client = TestClient(app)

    created_response = client.post(
        "/api-caller/workflows",
        json={
            "name": "Route workflow",
            "version": "2.0",
            "description": "created in test",
            "source_filename": "route.api.json",
            "workflow": _workflow(),
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["node_count"] == 2

    listed = client.get("/api-caller/workflows")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [created["id"]]

    updated = client.put(
        f"/api-caller/workflows/{created['id']}",
        json={"name": "Renamed route workflow", "workflow": _workflow("New text")},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed route workflow"
    assert updated.json()["workflow"]["1"]["inputs"]["text"] == "New text"

    removed = client.delete(f"/api-caller/workflows/{created['id']}")
    assert removed.status_code == 200
    assert removed.json()["archived"] is True
    assert client.get(f"/api-caller/workflows/{created['id']}").status_code == 404


def test_legacy_api_caller_execution_is_retired():
    response = TestClient(create_app()).get("/api-caller/runtime")

    assert response.status_code == 410
    assert "native-api-runner" in response.json()["detail"]


@pytest.mark.asyncio
async def test_runner_submission_forwards_operator_batch_options():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/run"
        body = request.read()
        assert b'"queueCount":3' in body
        assert b'"mergeMovie":true' in body
        assert b'"varySeed":true' in body
        assert b'"saveLatents":true' in body
        return httpx.Response(200, json={"ok": True, "jobId": "runner-job"})

    async with ComfyAPIRunnerClient(
        "http://127.0.0.1:8022",
        allow_mutation=True,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.run_workflow(
            _workflow(),
            comfy_url="http://127.0.0.1:8888",
            workflow_name="SineForge operator",
            queue_count=3,
            merge_movie=True,
            vary_seed=True,
            save_latents=True,
        )

    assert result == {"ok": True, "jobId": "runner-job"}
