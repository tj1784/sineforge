"""Focused coverage for direct Phase 7 ComfyUI submission."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest

from backend.app.db.base import PlanningMediaAsset, Story
from backend.app.schemas.video_generation import PhaseSevenVideoQueueResponse
from backend.app.services import phase_seven_videos


def test_copy_starting_image_uses_configured_comfy_input_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "managed" / "approved.png"
    source.parent.mkdir()
    source.write_bytes(b"approved-starting-frame")
    input_root = tmp_path / "sineforge-storage" / "inputs"
    story = Story(
        id=uuid4(),
        project_id=uuid4(),
        title="Direct engine",
        base_story="A direct ComfyUI submission.",
        target_duration_sec=10,
    )
    asset = PlanningMediaAsset(id=uuid4())

    monkeypatch.setattr(
        phase_seven_videos,
        "get_settings",
        lambda: SimpleNamespace(comfyui_input_dir=input_root),
    )
    monkeypatch.setattr(
        phase_seven_videos.reference_assets,
        "resolve_managed_path",
        lambda _asset: source,
    )

    relative_name = phase_seven_videos._copy_starting_image_to_comfy_input(
        story,
        "S01A",
        asset,
    )

    assert relative_name.startswith(f"cineforge\\{story.project_id}\\phase7\\s01a_")
    copied = input_root / Path(relative_name.replace("\\", "/"))
    assert copied.read_bytes() == source.read_bytes()


def test_post_comfy_prompt_calls_native_prompt_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["method"] = request.method
        observed["url"] = str(request.url)
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"prompt_id": "comfy-prompt-7", "number": 3, "node_errors": {}},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):  # noqa: ANN002, ANN003
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(phase_seven_videos.httpx, "Client", client_factory)

    prompt_id = phase_seven_videos._post_comfy_prompt(
        {"1": {"class_type": "LoadImage", "inputs": {"image": "frame.png"}}},
        client_id="phase7-client",
        comfyui_url="http://127.0.0.1:8190",
    )

    assert prompt_id == "comfy-prompt-7"
    assert observed == {
        "method": "POST",
        "url": "http://127.0.0.1:8190/prompt",
        "payload": {
            "prompt": {
                "1": {
                    "class_type": "LoadImage",
                    "inputs": {"image": "frame.png"},
                }
            },
            "client_id": "phase7-client",
        },
    }


def test_post_comfy_prompt_rejects_missing_prompt_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"number": 1})
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        phase_seven_videos.httpx,
        "Client",
        lambda *args, **kwargs: real_client(
            *args,
            transport=transport,
            **kwargs,
        ),
    )

    with pytest.raises(
        phase_seven_videos.PhaseSevenVideoError,
        match="did not return a prompt_id",
    ):
        phase_seven_videos._post_comfy_prompt(
            {},
            client_id="phase7-client",
            comfyui_url="http://127.0.0.1:8190",
        )


def test_blocked_queue_reports_comfy_engine_without_runner_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid4()
    story = Story(
        id=uuid4(),
        project_id=project_id,
        title="Blocked direct engine",
        base_story="A blocked shot.",
        target_duration_sec=10,
    )
    project = SimpleNamespace(id=project_id, workflow_lane="cineforge_studio")
    shot = SimpleNamespace(
        id=uuid4(),
        title="S01A",
        display_label=None,
        starting_image_asset_id=None,
    )
    db = MagicMock()

    def db_get(model, entity_id):  # noqa: ANN001
        if model is phase_seven_videos.Story and entity_id == story.id:
            return story
        if model is phase_seven_videos.Project and entity_id == project_id:
            return project
        return None

    db.get.side_effect = db_get
    monkeypatch.setattr(
        phase_seven_videos,
        "get_settings",
        lambda: SimpleNamespace(
            comfyui_base_url="http://127.0.0.1:8190/",
            comfyui_input_dir=Path("storage/inputs"),
        ),
    )
    monkeypatch.setattr(
        phase_seven_videos,
        "_shot_rows",
        lambda _db, _story_id: [
            (SimpleNamespace(), SimpleNamespace(), shot, 1, 1)
        ],
    )

    result = phase_seven_videos.queue_story_videos(
        db,
        story.id,
        requested_by="test",
    )

    assert result["engine"] == "comfyui"
    assert result["comfyui_url"] == "http://127.0.0.1:8190"
    assert result["runner_url"] == result["comfyui_url"]
    assert result["queued_count"] == 0
    assert result["blocked_count"] == 1
    assert result["jobs"] == []


def test_queue_submits_patched_workflow_directly_and_preserves_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid4()
    story = Story(
        id=uuid4(),
        project_id=project_id,
        title="Direct Phase 7",
        base_story="One approved shot.",
        target_duration_sec=10,
    )
    project = SimpleNamespace(id=project_id, workflow_lane="cineforge_studio")
    asset = SimpleNamespace(
        id=uuid4(),
        archived_at=None,
        kind="starting_image",
        approval_state="approved",
    )
    shot = SimpleNamespace(
        id=uuid4(),
        title="S01A Push in",
        display_label=None,
        starting_image_asset_id=asset.id,
        duration_sec=8.0,
    )
    scene = SimpleNamespace(id=uuid4(), title="Scene 1")
    chapter = SimpleNamespace(id=uuid4())
    input_root = tmp_path / "storage" / "inputs"
    db = MagicMock()

    def db_get(model, entity_id):  # noqa: ANN001
        if model is phase_seven_videos.Story and entity_id == story.id:
            return story
        if model is phase_seven_videos.Project and entity_id == project_id:
            return project
        if model is phase_seven_videos.PlanningMediaAsset and entity_id == asset.id:
            return asset
        return None

    db.get.side_effect = db_get
    monkeypatch.setattr(
        phase_seven_videos,
        "get_settings",
        lambda: SimpleNamespace(
            comfyui_base_url="http://127.0.0.1:8190/",
            comfyui_input_dir=input_root,
        ),
    )
    monkeypatch.setattr(
        phase_seven_videos,
        "_shot_rows",
        lambda _db, _story_id: [(chapter, scene, shot, 1, 1)],
    )
    monkeypatch.setattr(
        phase_seven_videos,
        "_latest_prompt_package",
        lambda _db, _shot_id: None,
    )
    monkeypatch.setattr(
        phase_seven_videos,
        "_build_video_prompt",
        lambda *_args: ("positive", "negative"),
    )
    monkeypatch.setattr(
        phase_seven_videos,
        "_copy_starting_image_to_comfy_input",
        lambda *_args, **kwargs: (
            "cineforge\\project\\phase7\\s01a.png"
            if kwargs["input_dir"] == input_root
            else pytest.fail("Phase 7 used the wrong ComfyUI input directory")
        ),
    )
    submitted: dict[str, object] = {}

    def submit_prompt(workflow, *, client_id, comfyui_url):  # noqa: ANN001
        submitted["workflow"] = workflow
        submitted["client_id"] = client_id
        submitted["comfyui_url"] = comfyui_url
        return "direct-prompt-1"

    monkeypatch.setattr(
        phase_seven_videos,
        "_post_comfy_prompt",
        submit_prompt,
    )

    workflow = {
        "5": {"inputs": {"text": ""}},
        "6": {"inputs": {"text": ""}},
        "8": {"inputs": {"image": ""}},
        "10": {"inputs": {"length": 0}},
        "11": {"inputs": {"noise_seed": 0}},
        "13": {"inputs": {"filename_prefix": ""}},
    }
    result = phase_seven_videos.queue_story_videos(
        db,
        story.id,
        requested_by="operator",
        seed=41,
        workflow_api_json=workflow,
    )
    response = PhaseSevenVideoQueueResponse(**result)

    assert submitted["comfyui_url"] == "http://127.0.0.1:8190"
    assert str(submitted["client_id"]).startswith("sineforge-phase7-")
    assert submitted["workflow"]["5"]["inputs"]["text"] == "positive"
    assert submitted["workflow"]["8"]["inputs"]["image"].endswith("s01a.png")
    assert result["engine"] == "comfyui"
    assert result["comfyui_url"] == "http://127.0.0.1:8190"
    assert result["runner_url"] == result["comfyui_url"]
    assert response.jobs[0].comfy_prompt_id == "direct-prompt-1"
    assert response.jobs[0].runner_job_id == "direct-prompt-1"
    assert response.jobs[0].engine == "comfyui"
    audit = db.add.call_args.args[0]
    assert audit.details["engine"] == "comfyui"
    assert audit.details["comfy_prompt_ids"] == ["direct-prompt-1"]
    assert audit.details["runner_job_ids"] == ["direct-prompt-1"]
    db.commit.assert_called_once_with()
