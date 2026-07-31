from fastapi.testclient import TestClient

from backend.app.main import app


def test_catalog_exposes_versioned_ltx_and_held_wan() -> None:
    with TestClient(app) as client:
        response = client.get("/production-profiles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_profile_ref"] == "ltx_base@1"
    profiles = {item["ref"]: item for item in payload["profiles"]}
    assert profiles["ltx_base@1"]["execution_qualified"] is True
    assert profiles["ltx_base@2"]["status"] == "qualified"
    assert profiles["ltx_base@2"]["execution_qualified"] is True
    assert profiles["ltx_base@2"]["selectable_for_execution"] is True
    assert profiles["ltx_base@2"]["capabilities"]["native_audio"] == "supported"
    assert profiles["ltx_base@2"]["capabilities"]["external_foley"] is False
    assert profiles["ltx_base@2"]["frame_policy"]["min_segment_duration_sec"] == 8
    assert profiles["ltx_base@2"]["frame_policy"]["max_segment_duration_sec"] == 15
    assert profiles["wan_base@1"]["execution_qualified"] is False
    assert profiles["wan_base@1"]["selectable_for_execution"] is False
    assert profiles["wan_base@1"]["status"] == "on_hold"
    assert profiles["wan_base@1"]["hold_reason"] == (
        "Local WAN dry run did not complete successfully."
    )
    assert profiles["wan_base@1"]["frame_policy"]["max_subscene_duration_sec"] == 90


def test_profile_alias_resolution_and_unknown_profile() -> None:
    with TestClient(app) as client:
        alias = client.get("/production-profiles/wan")
        missing = client.get("/production-profiles/not-a-profile")

    assert alias.status_code == 200
    assert alias.json()["ref"] == "wan_base@1"
    assert missing.status_code == 404
