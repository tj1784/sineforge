"""Non-rendering Phase 8 audio API contract tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import audio
from backend.app.schemas.audio import PCM_QA_MAX_SAMPLES


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(audio.router)
    return TestClient(app)


def plan_payload(**lock_overrides) -> dict:
    picture_lock = {
        "content_hash": "locked-picture",
        "total_frames": 240,
        "frame_rate": {"numerator": 30, "denominator": 1},
        "time_base": {"numerator": 1, "denominator": 90_000},
        "locked": True,
    }
    picture_lock.update(lock_overrides)
    return {
        "picture_lock": picture_lock,
        "expected_picture_lock_hash": "locked-picture",
        "boundaries": [],
    }


def test_policy_and_profiles_make_no_rendering_claim(client: TestClient) -> None:
    policy = client.get("/audio/foley-policy")
    profiles = client.get("/audio/delivery-profiles")

    assert policy.status_code == 200
    assert policy.json()["planning_only"] is True
    assert policy.json()["performs_rendering"] is False
    assert policy.json()["maximum_analysis_frames"] == 450
    assert policy.json()["pcm_qa_max_samples"] == PCM_QA_MAX_SAMPLES
    assert set(policy.json()["boundary_policies"]) == {
        "hard_cut",
        "continuous_ambience",
        "visual_crossfade",
    }
    assert profiles.status_code == 200
    assert profiles.json()["planning_only"] is True
    assert {profile["name"] for profile in profiles.json()["profiles"]} == {
        "web",
        "broadcast",
        "preserve_dynamics",
    }


def test_plans_exact_api_window_without_generating_audio(client: TestClient) -> None:
    response = client.post("/audio/foley-windows/plan", json=plan_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "planned"
    assert body["planning_only"] is True
    assert body["generated_audio"] is False
    assert body["window_count"] == 1
    assert body["expected_total_samples"] == 8 * 48_000
    window = body["windows"][0]
    assert window["core_frames"] == {"start": 0, "end": 240, "count": 240}
    assert window["core_pts"] == {
        "start": {"numerator": 0, "denominator": 1},
        "end": {"numerator": 720_000, "denominator": 1},
    }
    assert window["output_samples"] == {
        "start": 0,
        "end": 384_000,
        "count": 384_000,
        "sample_rate_hz": 48_000,
    }


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (plan_payload(locked=False), "immutable"),
        (
            {
                **plan_payload(),
                "expected_picture_lock_hash": "changed-picture",
            },
            "hash mismatch",
        ),
    ],
)
def test_plan_refuses_mutable_or_mismatched_picture_lock(
    client: TestClient,
    payload: dict,
    detail: str,
) -> None:
    response = client.post("/audio/foley-windows/plan", json=payload)

    assert response.status_code == 409
    assert detail in response.json()["detail"]


def test_derive_attempt_is_deterministic_and_non_executing(client: TestClient) -> None:
    plan = client.post("/audio/foley-windows/plan", json=plan_payload()).json()
    payload = {
        "window": plan["windows"][0],
        "current_picture_lock_hash": "locked-picture",
        "attempt_number": 1,
        "base_seed": 42,
        "model_id": "foley-model",
        "model_hash": "model-hash",
        "workflow_hash": "workflow-hash",
        "prompt_hash": "prompt-hash",
    }

    first = client.post("/audio/foley-attempts/derive", json=payload)
    repeated = client.post("/audio/foley-attempts/derive", json=payload)

    assert first.status_code == 200
    assert first.json() == repeated.json()
    assert first.json()["operation"] == "metadata_derived"
    assert first.json()["planning_only"] is True
    assert first.json()["generation_started"] is False
    assert first.json()["seed"] >= 0


def test_attempt_refuses_stale_picture_hash(client: TestClient) -> None:
    plan = client.post("/audio/foley-windows/plan", json=plan_payload()).json()
    response = client.post(
        "/audio/foley-attempts/derive",
        json={
            "window": plan["windows"][0],
            "current_picture_lock_hash": "changed-picture",
            "attempt_number": 1,
            "base_seed": 42,
            "model_id": "foley-model",
            "model_hash": "model-hash",
            "workflow_hash": "workflow-hash",
            "prompt_hash": "prompt-hash",
        },
    )

    assert response.status_code == 409
    assert "stale picture lock" in response.json()["detail"]


def test_numeric_pcm_qa_reports_silence_without_reading_media(
    client: TestClient,
) -> None:
    response = client.post(
        "/audio/pcm/qa",
        json={"samples": [0.0, 0.0, 0.0], "expected_sample_count": 3},
    )

    assert response.status_code == 200
    assert response.json() == {
        "operation": "numeric_pcm_qa",
        "planning_only": True,
        "media_read": False,
        "passed": False,
        "is_silent": True,
        "finite": True,
        "expected_sample_count": 3,
        "actual_sample_count": 3,
        "peak_dbfs": None,
        "rms_dbfs": None,
        "findings": ["unexpected silence detected"],
    }


def test_numeric_pcm_qa_payload_is_strictly_bounded(client: TestClient) -> None:
    response = client.post(
        "/audio/pcm/qa",
        json={
            "samples": [0.1] * (PCM_QA_MAX_SAMPLES + 1),
            "expected_sample_count": PCM_QA_MAX_SAMPLES + 1,
        },
    )

    assert response.status_code == 422


def test_contracts_reject_paths_and_unknown_execution_fields(
    client: TestClient,
) -> None:
    payload = plan_payload()
    payload["local_path"] = r"C:\media\silent.mp4"

    response = client.post("/audio/foley-windows/plan", json=payload)

    assert response.status_code == 422
    assert "local_path" in response.text

