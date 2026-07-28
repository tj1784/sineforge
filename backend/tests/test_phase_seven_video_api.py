"""API-boundary tests for non-rendering Phase 7 video contracts."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.routes.video import router


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


@pytest.fixture()
def client() -> TestClient:
    isolated_app = FastAPI()
    isolated_app.include_router(router)
    return TestClient(isolated_app)


def _provider() -> dict:
    return {
        "profile_id": "wan-base-quality",
        "fps_numerator": 16,
        "fps_denominator": 1,
        "min_frames": 1,
        "max_frames": 81,
        "frame_stride": 4,
        "frame_offset": 1,
        "duplicate_boundary_frames": 1,
    }


def _edl() -> dict:
    return {
        "edl_id": "edl-1",
        "stitch_stage": "phase7_before_audio",
        "fps_numerator": 16,
        "fps_denominator": 1,
        "decisions": [
            {
                "decision_id": "decision-1",
                "asset_id": "asset-a",
                "asset_sha256": SHA_A,
                "source_start_frame": 0,
                "source_end_frame_exclusive": 81,
                "timeline_start_frame": 0,
                "drop_leading_frames": 0,
            },
            {
                "decision_id": "decision-2",
                "asset_id": "asset-b",
                "asset_sha256": SHA_B,
                "source_start_frame": 0,
                "source_end_frame_exclusive": 81,
                "timeline_start_frame": 81,
                "drop_leading_frames": 1,
            },
        ],
    }


def test_policy_and_capabilities_are_explicitly_non_rendering(client):
    policy = client.get("/video/phase-7/policy")
    assert policy.status_code == 200
    assert policy.json()["preferred_subscene_min_sec"] == 15
    assert policy.json()["subscene_max_sec"] == 90
    assert policy.json()["default_stitch_stage"] == "phase7_before_audio"
    assert policy.json()["rendering_performed"] is False

    capabilities = client.get("/video/phase-7/capabilities")
    assert capabilities.status_code == 200
    body = capabilities.json()
    assert body["accepts_local_paths"] is False
    assert body["executes_comfyui"] is False
    assert body["executes_ffmpeg"] is False
    assert body["persists_state"] is False
    assert body["rendering_performed"] is False


def test_compile_subscene_returns_bounded_plan_without_execution_claim(client):
    response = client.post(
        "/video/phase-7/subscenes/compile",
        json={
            "subscene": {"subscene_id": "scene-a", "duration_sec": 15},
            "provider": _provider(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "plan_only"
    assert body["rendering_performed"] is False
    assert body["segment_count"] == 3
    assert [segment["frame_count"] for segment in body["segments"]] == [81, 81, 81]
    assert [segment["drop_leading_frames"] for segment in body["segments"]] == [
        0,
        1,
        1,
    ]


def test_compile_short_subscene_fails_closed_without_reason(client):
    response = client.post(
        "/video/phase-7/subscenes/compile",
        json={
            "subscene": {"subscene_id": "short", "duration_sec": 8},
            "provider": _provider(),
        },
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]["code"]
        == "video_domain_validation_failed"
    )


def test_api_forbids_unknown_fields_and_path_like_identifiers(client):
    unknown = client.post(
        "/video/phase-7/subscenes/compile",
        json={
            "subscene": {
                "subscene_id": "scene-a",
                "duration_sec": 15,
                "local_path": "C:\\Users\\example\\input.mp4",
            },
            "provider": _provider(),
        },
    )
    assert unknown.status_code == 422

    path_id = client.post(
        "/video/phase-7/subscenes/compile",
        json={
            "subscene": {
                "subscene_id": "C:\\Users\\example\\input.mp4",
                "duration_sec": 15,
            },
            "provider": _provider(),
        },
    )
    assert path_id.status_code == 422


def test_invalid_provider_constraints_fail_closed(client):
    provider = _provider()
    provider["frame_offset"] = 4
    response = client.post(
        "/video/phase-7/subscenes/compile",
        json={
            "subscene": {"subscene_id": "scene-a", "duration_sec": 15},
            "provider": provider,
        },
    )

    assert response.status_code == 422
    assert "frame_offset" in response.json()["detail"]["message"]


def test_validate_edl_returns_canonical_digest_and_exact_timeline(client):
    response = client.post("/video/phase-7/edl/validate", json=_edl())

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["rendering_performed"] is False
    assert body["total_frame_count"] == 161
    assert body["duration_sec"] == pytest.approx(10.0625)
    assert len(body["edl_sha256"]) == 64
    assert body["decisions"][1]["timeline_frame_count"] == 80


def test_validate_edl_rejects_gap(client):
    payload = _edl()
    payload["decisions"][1]["timeline_start_frame"] = 82
    response = client.post("/video/phase-7/edl/validate", json=payload)

    assert response.status_code == 422
    assert "contiguous" in response.json()["detail"]["message"]


def test_construct_picture_lock_returns_contract_not_render_claim(client):
    response = client.post(
        "/video/phase-7/picture-locks/construct",
        json={
            "edl": _edl(),
            "picture_lock_id": "lock-1",
            "final_video_asset_id": "final-video",
            "final_video_sha256": SHA_C,
            "assembly_manifest_sha256": SHA_B,
            "width": 1280,
            "height": 704,
            "pixel_format": "yuv420p",
            "locked_at": "2026-07-28T10:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["contract_only"] is True
    assert body["rendering_performed"] is False
    assert body["frame_count"] == 161
    assert body["selected_asset_ids"] == ["asset-a", "asset-b"]
    assert body["final_video_sha256"] == SHA_C


def test_construct_picture_lock_rejects_naive_time_and_bad_hash(client):
    payload = {
        "edl": _edl(),
        "picture_lock_id": "lock-1",
        "final_video_asset_id": "final-video",
        "final_video_sha256": SHA_C,
        "assembly_manifest_sha256": SHA_B,
        "width": 1280,
        "height": 704,
        "pixel_format": "yuv420p",
        "locked_at": "2026-07-28T10:00:00",
    }
    naive = client.post(
        "/video/phase-7/picture-locks/construct",
        json=payload,
    )
    assert naive.status_code == 422
    assert "timezone-aware" in naive.json()["detail"]["message"]

    payload["locked_at"] = "2026-07-28T10:00:00Z"
    payload["final_video_sha256"] = "not-a-hash"
    bad_hash = client.post(
        "/video/phase-7/picture-locks/construct",
        json=payload,
    )
    assert bad_hash.status_code == 422
