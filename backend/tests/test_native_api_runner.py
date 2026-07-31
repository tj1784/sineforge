from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from backend.app.api.routes import native_api_runner as route
from backend.app.api.routes.native_api_runner import get_native_api_workflow_library
from backend.app.main import create_app
from backend.app.services.api_workflows import ApiWorkflowLibrary, workflow_sha256
from backend.app.services.native_api_runner import (
    NativeApiWorkflowLibrary,
    NativeRepositoryWorkflowReadOnly,
    analyze_native_workflow,
    summarize_history,
)


def _workflow(prompt: str = "A native SineForge test") -> dict[str, Any]:
    return {
        "1": {
            "class_type": "TextNode",
            "inputs": {"text": prompt},
            "_meta": {"title": "Positive prompt"},
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {"images": ["1", 0], "filename_prefix": "native/test"},
            "_meta": {"title": "Save image"},
        },
    }


def _object_info() -> dict[str, Any]:
    return {
        "TextNode": {
            "input": {"required": {"text": ["STRING", {"multiline": True}]}},
            "output": ["IMAGE"],
            "output_node": False,
        },
        "SaveImage": {
            "input": {
                "required": {
                    "images": ["IMAGE"],
                    "filename_prefix": ["STRING", {"default": "ComfyUI"}],
                }
            },
            "output_node": True,
        },
    }


class FakeComfyUIClient:
    submissions: list[tuple[dict[str, Any], str]] = []
    queue_payload: dict[str, Any] = {"queue_running": [], "queue_pending": []}
    history_payload: dict[str, Any] = {}
    deleted_ids: list[str] = []
    memory_calls = 0
    uploads: list[tuple[str, str, str]] = []
    editor_transfers: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "FakeComfyUIClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "reachable": True}

    async def get_object_info(self) -> dict[str, Any]:
        return _object_info()

    async def get_queue(self) -> dict[str, Any]:
        return self.queue_payload

    async def get_history(self, _prompt_id: str) -> dict[str, Any]:
        return self.history_payload

    async def submit_prompt(
        self,
        prompt: dict[str, Any],
        client_id: str,
    ) -> dict[str, Any]:
        self.submissions.append((prompt, client_id))
        return {"prompt_id": "native-prompt-1", "number": 7, "node_errors": {}}

    async def stage_editor_workflow(
        self,
        *,
        name: str,
        workflow: dict[str, Any],
    ) -> dict[str, Any]:
        self.editor_transfers.append((name, workflow))
        return {
            "ok": True,
            "token": "bc8c139e-1330-4ec8-9323-116a91ff3c85",
            "expires_in_sec": 300,
        }

    async def delete_queue_items(self, prompt_ids: list[str]) -> dict[str, Any]:
        self.deleted_ids.extend(prompt_ids)
        rows = self.queue_payload.get("queue_pending")
        if isinstance(rows, list):
            self.queue_payload["queue_pending"] = [
                row
                for row in rows
                if not (
                    isinstance(row, list)
                    and len(row) > 1
                    and str(row[1]) in prompt_ids
                )
            ]
        return {"status": "ok"}

    async def interrupt(self) -> dict[str, Any]:
        return {"status": "ok"}

    async def free_memory(
        self,
        *,
        unload_models: bool = True,
        free_memory: bool = True,
    ) -> dict[str, Any]:
        del unload_models, free_memory
        type(self).memory_calls += 1
        return {"status": "ok"}

    async def upload_image_file(
        self,
        _image,
        filename: str,
        *,
        subfolder: str = "",
        overwrite: bool = False,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        del overwrite
        self.uploads.append((filename, subfolder, content_type))
        return {"name": filename, "subfolder": subfolder, "type": "input"}


def _reset_fake_client() -> None:
    FakeComfyUIClient.submissions.clear()
    FakeComfyUIClient.queue_payload = {"queue_running": [], "queue_pending": []}
    FakeComfyUIClient.history_payload = {}
    FakeComfyUIClient.deleted_ids.clear()
    FakeComfyUIClient.memory_calls = 0
    FakeComfyUIClient.uploads.clear()
    FakeComfyUIClient.editor_transfers.clear()
    route._submitted_requests.clear()
    route._native_prompt_clients.clear()


def test_native_library_starts_empty_and_is_isolated_from_api_caller(tmp_path: Path):
    legacy = ApiWorkflowLibrary(tmp_path)
    native = NativeApiWorkflowLibrary(tmp_path, include_repository=False)
    legacy.create(
        name="Legacy Runner workflow",
        version="1.0",
        description=None,
        workflow=_workflow(),
    )

    assert native.list() == []
    native.create(
        name="Explicit native import",
        version="1.0",
        description=None,
        workflow=_workflow("native"),
    )

    assert [item["name"] for item in native.list()] == ["Explicit native import"]
    assert [item["name"] for item in legacy.list()] == ["Legacy Runner workflow"]


def test_repository_workflow_catalog_is_shared_and_read_only(tmp_path: Path):
    native = NativeApiWorkflowLibrary(tmp_path)

    listed = native.list()

    assert len(listed) == 173
    assert {item["category"] for item in listed} == {
        "Image Editing & Composition",
        "Image Generation",
        "Prompting & Language",
        "Speech, Audio & Music",
        "Upscaling & Restoration",
        "Utilities & Workflow Tools",
        "Video & Animation",
    }
    assert sum(item["repository_managed"] for item in listed) == 173
    assert sum(
        item["workflow_status"] == "requires_custom_nodes" for item in listed
    ) == 42

    original = native.get(listed[0]["id"])
    assert original["source_workflow"] is not None
    assert original["instructions"]
    assert original["requirements"]["custom_node_root"] == (
        r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes"
    )

    try:
        native.update(
            original["id"],
            description="Local repository override",
        )
    except NativeRepositoryWorkflowReadOnly as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("Repository update unexpectedly succeeded.")

    try:
        native.remove(original["id"])
    except NativeRepositoryWorkflowReadOnly as exc:
        assert "cannot be archived" in str(exc)
    else:
        raise AssertionError("Repository removal unexpectedly succeeded.")

    unchanged = native.get(original["id"])
    assert unchanged["description"] == original["description"]
    assert unchanged["is_overridden"] is False
    assert not (native.root / f"{original['id']}.json").is_file()

    dynamic_podcast = next(
        item
        for item in listed
        if item["name"]
        == "LTX-2.3 Dynamic Podcast — Local Qwen JSON + Native Audio"
    )
    assert dynamic_podcast["subcategory"] == "LTX-2.3 · Dynamic podcasts"
    assert dynamic_podcast["repository_managed"] is True
    podcast_detail = native.get(dynamic_podcast["id"])
    assert podcast_detail["workflow"]["2"]["class_type"] == (
        "SineForgeLTXPodcastPlanner"
    )
    assert podcast_detail["workflow"]["6"]["inputs"]["format"] == "json"
    assert podcast_detail["requirements"]["local_services"][0]["cloud"] is False
    assert podcast_detail["requirements"]["shared_model_root"] == (
        r"C:\ComfyUI\ComfyUI_Shared_Folders\models"
    )
    assert podcast_detail["requirements"]["trusted_prompt_model_root"] == (
        r"C:\Users\Blokey\.lmstudio\models"
    )
    assert (
        podcast_detail["requirements"]["local_services"][0][
            "trust_contract_enforced"
        ]
        is True
    )
    assert (
        podcast_detail["requirements"]["local_services"][0]["preload"]
        is False
    )
    assert podcast_detail["requirements"]["prompt_examples"] == [
        "Workflows/LTX23/"
        "SineForge_LTX23_Podcast_Geopolitics_To_Everyday.prompt.json"
    ]
    assert {
        item["preferred_relative_path"]
        for item in podcast_detail["requirements"]["model_files"]
    } == {
        "checkpoints/sulphur2Base_distilled.safetensors",
        "text_encoders/gemma_3_12B_it_fp8_e4m3fn.safetensors",
        "text_encoders/ltx-2.3_text_projection_bf16.safetensors",
        "vae/LTX23_video_vae_bf16.safetensors",
        "vae/LTX23_audio_vae_bf16.safetensors",
        "latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
    }
    assert (
        podcast_detail["requirements"]["qualification"]["status"]
        == "static_validated_not_rendered"
    )

    continuation = next(
        item
        for item in listed
        if item["name"]
        == "LTX-2.3 + Krea 2 Lossless Continuation Loop — Local Qwen JSON"
    )
    assert continuation["subcategory"] == "LTX-2.3 · Automated continuation"
    assert continuation["repository_managed"] is True
    continuation_detail = native.get(continuation["id"])
    assert continuation_detail["workflow"]["2"]["class_type"] == (
        "easy forLoopStart"
    )
    assert continuation_detail["workflow"]["3"]["class_type"] == (
        "SineForgeLTXKreaContinuationPlanner"
    )
    assert continuation_detail["workflow"]["14"]["class_type"] == (
        "SaveImageAdvanced"
    )
    assert continuation_detail["workflow"]["14"]["inputs"]["format"] == {
        "format": "png",
        "bit_depth": "16-bit",
        "input_color_space": "sRGB",
    }
    assert continuation_detail["workflow"]["16"]["inputs"]["format"] == (
        "video/ffv1-mkv"
    )
    assert continuation_detail["workflow"]["18"]["inputs"]["batch_index"] == -1
    assert continuation_detail["workflow"]["20"]["inputs"]["format"] == {
        "format": "png",
        "bit_depth": "16-bit",
        "input_color_space": "sRGB",
    }
    assert continuation_detail["workflow"]["22"]["class_type"] == (
        "easy forLoopEnd"
    )
    assert {
        item["preferred_relative_path"]
        for item in continuation_detail["requirements"]["model_files"]
    } == {
        "diffusion_models/krea2TurboOfficialComfy_krea2RawInt8Convrot.safetensors",
        "text_encoders/qwen3vl_4b_fp8_scaled.safetensors",
        "vae/qwen_image_vae.safetensors",
        "checkpoints/sulphur2Base_distilled.safetensors",
        "text_encoders/gemma_3_12B_it_fp8_e4m3fn.safetensors",
        "text_encoders/ltx-2.3_text_projection_bf16.safetensors",
        "vae/LTX23_video_vae_bf16.safetensors",
        "vae/LTX23_audio_vae_bf16.safetensors",
        "latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
    }


def test_repository_routes_reject_mutation_and_stage_original_for_comfyui(
    tmp_path: Path,
    monkeypatch,
):
    library = NativeApiWorkflowLibrary(tmp_path)
    repository_workflow = library.list()[0]
    original = library.get(repository_workflow["id"])
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: library
    client = TestClient(app)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)

    updated = client.put(
        f"/native-api-runner/workflows/{original['id']}",
        json={"description": "Attempted mutation"},
    )
    removed = client.delete(f"/native-api-runner/workflows/{original['id']}")
    loaded = client.post(
        f"/native-api-runner/workflows/{original['id']}/load-in-comfyui"
    )
    opened = client.get(
        f"/native-api-runner/workflows/{original['id']}/open-in-comfyui",
        follow_redirects=False,
    )

    assert updated.status_code == 409
    assert removed.status_code == 409
    assert "read-only" in updated.json()["detail"]
    assert loaded.status_code == 200
    assert loaded.json() == {
        "ok": True,
        "workflow_id": original["id"],
        "workflow_name": original["name"],
        "comfy_url": "http://127.0.0.1:8888",
        "open_url": (
            "http://127.0.0.1:8888/"
            "?sineforge_workflow=bc8c139e-1330-4ec8-9323-116a91ff3c85"
        ),
        "transfer_token": "bc8c139e-1330-4ec8-9323-116a91ff3c85",
        "expires_in_sec": 300,
        "queued": False,
    }
    assert FakeComfyUIClient.editor_transfers == [
        (original["name"], original["source_workflow"]),
        (original["name"], original["source_workflow"]),
    ]
    assert FakeComfyUIClient.submissions == []
    assert opened.status_code == 303
    assert opened.headers["location"].startswith(
        "http://127.0.0.1:8888/?sineforge_workflow="
    )
    assert opened.headers["cache-control"] == "no-store"


def test_native_analysis_uses_live_classes_and_hash():
    workflow = _workflow()
    analysis = analyze_native_workflow(workflow, _object_info())

    assert analysis["queueable"] is True
    assert analysis["workflowSha256"] == workflow_sha256(workflow)
    assert analysis["nodeCount"] == 2
    assert analysis["outputNodes"] == [
        {"nodeId": "2", "classType": "SaveImage", "title": "Save image"}
    ]
    assert analysis["promptFields"][0]["input"] == "text"

    missing = analyze_native_workflow(workflow, {"SaveImage": _object_info()["SaveImage"]})
    assert missing["queueable"] is False
    assert any(issue["code"] == "NODE_CLASS_UNAVAILABLE" for issue in missing["issues"])


def test_native_analysis_rejects_broken_graph_links():
    workflow = _workflow()
    workflow["2"]["inputs"]["images"] = ["missing-node", 0]

    analysis = analyze_native_workflow(workflow, _object_info())

    assert analysis["queueable"] is False
    assert any(issue["code"] == "LINK_SOURCE_MISSING" for issue in analysis["issues"])

    workflow = _workflow()
    workflow["2"]["inputs"]["images"] = ["1", 9]
    invalid_output = analyze_native_workflow(workflow, _object_info())
    assert invalid_output["queueable"] is False
    assert any(
        issue["code"] == "LINK_OUTPUT_INVALID"
        for issue in invalid_output["issues"]
    )

    incompatible_info = _object_info()
    incompatible_info["TextNode"]["output"] = ["STRING"]
    mismatched_type = analyze_native_workflow(_workflow(), incompatible_info)
    assert mismatched_type["queueable"] is False
    assert any(
        issue["code"] == "LINK_TYPE_MISMATCH"
        for issue in mismatched_type["issues"]
    )


def test_native_analysis_only_marks_real_media_inputs() -> None:
    workflow = {
        "1": {
            "class_type": "MediaSettings",
            "inputs": {
                "image": "podcast.png",
                "audio_vae": "audio-vae.safetensors",
                "video_size": "Custom",
                "ratio_from_image": False,
                "override_audio": False,
            },
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["1", 0],
                "filename_prefix": "native/test",
            },
        },
    }
    object_info = {
        **_object_info(),
        "MediaSettings": {
            "input": {
                "required": {
                    "image": ["STRING"],
                    "audio_vae": [["audio-vae.safetensors"]],
                    "video_size": [["Custom"]],
                    "ratio_from_image": ["BOOLEAN"],
                    "override_audio": ["BOOLEAN"],
                }
            },
            "output": ["IMAGE"],
            "output_node": False,
        },
    }

    analysis = analyze_native_workflow(workflow, object_info)

    assert analysis["queueable"] is True
    assert [field["input"] for field in analysis["mediaTargets"]] == ["image"]


def test_native_routes_start_empty_and_submit_directly(
    tmp_path: Path,
    monkeypatch,
):
    library = NativeApiWorkflowLibrary(tmp_path, include_repository=False)
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: library
    client = TestClient(app)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)

    listed = client.get("/native-api-runner/workflows")
    assert listed.status_code == 200
    assert listed.json() == []

    runtime = client.get("/native-api-runner/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["externalRunnerUsed"] is False
    assert runtime.json()["objectInfo"]["classCount"] == 2

    workflow = _workflow()
    analyzed = client.post("/native-api-runner/analyze", json={"workflow": workflow})
    assert analyzed.status_code == 200
    digest = analyzed.json()["workflowSha256"]
    assert FakeComfyUIClient.submissions == []

    queued = client.post(
        "/native-api-runner/run",
        json={
            "workflow": workflow,
            "workflow_name": "Explicit native test",
            "workflow_sha256": digest,
            "confirmation": True,
            "idempotency_key": "native-test-request",
        },
    )
    assert queued.status_code == 200
    assert queued.json()["prompt_id"] == "native-prompt-1"
    assert queued.json()["external_runner_used"] is False
    assert len(FakeComfyUIClient.submissions) == 1
    assert FakeComfyUIClient.submissions[0][0] == workflow

    repeated = client.post(
        "/native-api-runner/run",
        json={
            "workflow": workflow,
            "workflow_name": "Explicit native test",
            "workflow_sha256": digest,
            "confirmation": True,
            "idempotency_key": "native-test-request",
        },
    )
    assert repeated.status_code == 200
    assert len(FakeComfyUIClient.submissions) == 1

    # Process-local caches are only accelerators. Durable ownership and
    # idempotency must survive a backend restart.
    route._submitted_requests.clear()
    route._native_prompt_clients.clear()
    repeated_after_restart = client.post(
        "/native-api-runner/run",
        json={
            "workflow": workflow,
            "workflow_name": "Explicit native test",
            "workflow_sha256": digest,
            "confirmation": True,
            "idempotency_key": "native-test-request",
        },
    )
    owned_after_restart = client.get(
        "/native-api-runner/jobs/native-prompt-1"
    )
    assert repeated_after_restart.status_code == 200
    assert repeated_after_restart.json()["prompt_id"] == "native-prompt-1"
    assert owned_after_restart.status_code == 200
    assert len(FakeComfyUIClient.submissions) == 1


def test_native_run_ignores_stale_validation_hash(tmp_path: Path, monkeypatch):
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: NativeApiWorkflowLibrary(
        tmp_path, include_repository=False
    )
    client = TestClient(app)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)
    workflow = _workflow()
    stale_digest = workflow_sha256(workflow)
    workflow["1"]["inputs"]["text"] = "edited after validation"

    response = client.post(
        "/native-api-runner/run",
        json={
            "workflow": workflow,
            "workflow_name": "Stale validation",
            "workflow_sha256": stale_digest,
            "confirmation": True,
            "idempotency_key": "stale-native-test",
        },
    )

    assert response.status_code == 200
    assert response.json()["prompt_id"] == "native-prompt-1"
    assert FakeComfyUIClient.submissions[0][0] == workflow


def test_native_routes_map_visual_json_to_422(tmp_path: Path, monkeypatch):
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: NativeApiWorkflowLibrary(
        tmp_path, include_repository=False
    )
    client = TestClient(app, raise_server_exceptions=False)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)
    visual_graph = {"nodes": [], "links": []}

    analyzed = client.post("/native-api-runner/analyze", json={"workflow": visual_graph})
    submitted = client.post(
        "/native-api-runner/run",
        json={
            "workflow": visual_graph,
            "workflow_name": "Visual graph",
            "workflow_sha256": "0" * 64,
            "confirmation": True,
            "idempotency_key": "visual-graph-test",
        },
    )

    assert analyzed.status_code == 422
    assert submitted.status_code == 422
    assert FakeComfyUIClient.submissions == []


def test_native_cancel_is_restricted_to_owned_prompt(tmp_path: Path, monkeypatch):
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: NativeApiWorkflowLibrary(
        tmp_path, include_repository=False
    )
    client = TestClient(app)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)

    unknown = client.post("/native-api-runner/jobs/other-prompt/cancel")
    assert unknown.status_code == 404

    route._native_prompt_clients["native-prompt"] = "sineforge-native-owner"
    FakeComfyUIClient.queue_payload = {
        "queue_running": [],
        "queue_pending": [
            [1, "native-prompt", {}, {"client_id": "different-client"}],
        ],
    }
    foreign = client.post("/native-api-runner/jobs/native-prompt/cancel")
    assert foreign.status_code == 409
    assert FakeComfyUIClient.deleted_ids == []

    FakeComfyUIClient.queue_payload["queue_pending"][0][3]["client_id"] = (
        "sineforge-native-owner"
    )
    owned = client.post("/native-api-runner/jobs/native-prompt/cancel")
    assert owned.status_code == 200
    assert owned.json()["action"] == "deleted_pending"
    assert FakeComfyUIClient.deleted_ids == ["native-prompt"]

    route._native_prompt_clients["active-native-prompt"] = (
        "sineforge-native-owner"
    )
    FakeComfyUIClient.queue_payload = {
        "queue_running": [
            [
                2,
                "active-native-prompt",
                {},
                {"client_id": "sineforge-native-owner"},
            ]
        ],
        "queue_pending": [],
    }
    active = client.post(
        "/native-api-runner/jobs/active-native-prompt/cancel",
        params={"interrupt_active": True},
    )
    assert active.status_code == 409
    assert "interrupt operation is global" in active.json()["detail"]


def test_native_memory_release_rejects_running_work(tmp_path: Path, monkeypatch):
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: NativeApiWorkflowLibrary(
        tmp_path, include_repository=False
    )
    client = TestClient(app)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)
    FakeComfyUIClient.queue_payload = {
        "queue_running": [[1, "production-prompt", {}, {"client_id": "production"}]],
        "queue_pending": [],
    }

    response = client.post(
        "/native-api-runner/memory/free",
        json={"confirmation": True, "unload_models": True, "free_memory": True},
    )

    assert response.status_code == 409
    assert FakeComfyUIClient.memory_calls == 0

    FakeComfyUIClient.queue_payload = {
        "queue_running": [],
        "queue_pending": [
            [2, "pending-prompt", {}, {"client_id": "another-tool"}],
        ],
    }
    pending_response = client.post(
        "/native-api-runner/memory/free",
        json={"confirmation": True, "unload_models": True, "free_memory": True},
    )
    assert pending_response.status_code == 409
    assert FakeComfyUIClient.memory_calls == 0


def test_native_media_blocks_active_content_and_streams_allowed_media(
    tmp_path: Path,
    monkeypatch,
):
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: NativeApiWorkflowLibrary(
        tmp_path, include_repository=False
    )
    client = TestClient(app)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)

    blocked = client.post(
        "/native-api-runner/media?filename=payload.html",
        content=b"<script>alert(1)</script>",
        headers={"Content-Type": "text/html"},
    )
    allowed = client.post(
        "/native-api-runner/media?filename=anchor.png",
        content=b"not-decoded-by-the-proxy",
        headers={"Content-Type": "image/png"},
    )

    assert blocked.status_code == 415
    assert allowed.status_code == 200
    assert FakeComfyUIClient.uploads == [
        ("anchor.png", "sineforge_native", "image/png")
    ]


def test_native_output_requires_owned_history_record(tmp_path: Path, monkeypatch):
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: NativeApiWorkflowLibrary(
        tmp_path, include_repository=False
    )
    client = TestClient(app)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)
    route._native_prompt_clients["native-output-prompt"] = "sineforge-native-owner"

    response = client.get(
        "/native-api-runner/outputs",
        params={
            "prompt_id": "native-output-prompt",
            "filename": "not-observed.html",
            "type": "output",
        },
    )

    assert response.status_code == 404


def test_native_output_forces_active_content_to_safe_attachment(
    tmp_path: Path,
    monkeypatch,
):
    app = create_app()
    app.dependency_overrides[get_native_api_workflow_library] = lambda: NativeApiWorkflowLibrary(
        tmp_path, include_repository=False
    )
    client = TestClient(app)
    _reset_fake_client()
    monkeypatch.setattr(route, "ComfyUIClient", FakeComfyUIClient)
    route._native_prompt_clients["native-output-prompt"] = "sineforge-native-owner"
    FakeComfyUIClient.history_payload = {
        "native-output-prompt": {
            "status": {
                "status_str": "success",
                "completed": True,
                "messages": [],
            },
            "outputs": {
                "9": {
                    "files": [
                        {
                            "filename": "result.html",
                            "subfolder": "",
                            "type": "output",
                        }
                    ]
                }
            },
        }
    }
    original_async_client = httpx.AsyncClient

    class OutputStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"<script>window.top.location='bad'</script>"

    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            stream=OutputStream(),
            headers={"Content-Type": "text/html"},
        )
    )

    def output_client(*_args, **kwargs):
        return original_async_client(
            base_url=kwargs["base_url"],
            timeout=kwargs["timeout"],
            transport=transport,
        )

    monkeypatch.setattr(route.httpx, "AsyncClient", output_client)
    response = client.get(
        "/native-api-runner/outputs",
        params={
            "prompt_id": "native-output-prompt",
            "filename": "result.html",
            "type": "output",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/octet-stream")
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"


def test_native_history_uses_terminal_status_text():
    history = {
        "native-prompt": {
            "status": {
                "status_str": "interrupted",
                "completed": False,
                "messages": [],
            },
            "outputs": {},
        }
    }

    summary = summarize_history("native-prompt", history, {})

    assert summary["state"] == "failed"
