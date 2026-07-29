from fastapi.testclient import TestClient

from backend.app.main import app


def test_catalog_exposes_ltx_and_non_executable_wan() -> None:
    with TestClient(app) as client:
        response = client.get("/production-profiles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_profile_ref"] == "ltx_base@1"
    profiles = {item["ref"]: item for item in payload["profiles"]}
    assert profiles["ltx_base@1"]["execution_qualified"] is True
    assert profiles["wan_base@1"]["execution_qualified"] is False
    assert profiles["wan_base@1"]["status"] == "qualification_required"
    assert profiles["wan_base@1"]["frame_policy"]["max_subscene_duration_sec"] == 90


def test_profile_alias_resolution_and_unknown_profile() -> None:
    with TestClient(app) as client:
        alias = client.get("/production-profiles/wan")
        missing = client.get("/production-profiles/not-a-profile")

    assert alias.status_code == 200
    assert alias.json()["ref"] == "wan_base@1"
    assert missing.status_code == 404
