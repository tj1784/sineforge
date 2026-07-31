from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import app


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(f"sqlite:///{(tmp_path / 'storyboard.db').as_posix()}", connect_args={"check_same_thread": False}, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)

    def override() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def make_story(client: TestClient) -> dict:
    project = client.post(
        "/projects",
        json={
            "name": "Storyboard test",
            "workflow_lane": "cineforge_studio",
        },
    ).json()
    response = client.post("/storyboard/stories", json={"project_id": project["id"], "title": "A test story", "base_story": "A small planning story.", "target_duration_sec": 8})
    assert response.status_code == 201
    return response.json()


def test_story_hierarchy_uses_stable_ids_and_aggregate_rollups(client: TestClient):
    story = make_story(client)
    chapter = client.post(f"/storyboard/stories/{story['id']}/chapters", json={"title": "Beginning", "order_index": 0}).json()
    scene = client.post(f"/storyboard/chapters/{chapter['id']}/scenes", json={"title": "Arrival", "order_index": 0}).json()
    shot = client.post(f"/storyboard/scenes/{scene['id']}/shots", json={"title": "Establish", "duration_sec": 8, "order_index": 0}).json()

    aggregate = client.get(f"/storyboard/stories/{story['id']}/aggregate")
    assert aggregate.status_code == 200
    payload = aggregate.json()
    assert payload["chapters"][0]["scenes"][0]["shots"][0]["id"] == shot["id"]
    assert payload["chapters"][0]["duration_sec"] == 8.0
    assert payload["chapters"][0]["scenes"][0]["shots"][0]["display_label"] == "A"


def test_shot_duration_outside_normal_range_requires_reason(client: TestClient):
    story = make_story(client)
    chapter = client.post(f"/storyboard/stories/{story['id']}/chapters", json={"title": "Beginning", "order_index": 0}).json()
    scene = client.post(f"/storyboard/chapters/{chapter['id']}/scenes", json={"title": "Arrival", "order_index": 0}).json()
    response = client.post(f"/storyboard/scenes/{scene['id']}/shots", json={"title": "Too short", "duration_sec": 5, "order_index": 0})
    assert response.status_code == 422
    assert "override" in response.text.lower()


def test_readiness_is_backend_derived_and_approval_does_not_render(client: TestClient):
    story = make_story(client)
    readiness = client.get(f"/storyboard/stories/{story['id']}/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is False
    phase_a = client.get(f"/storyboard/stories/{story['id']}/phase-a").json()
    response = client.post(
        f"/storyboard/stories/{story['id']}/approve",
        json={"approved_by": "Producer", "expected_revision": phase_a["revision"]},
    )
    assert response.status_code == 409
    assert "queue" not in response.text.lower()


def test_approval_route_requires_revision_precondition(client: TestClient):
    story = make_story(client)
    response = client.post(
        f"/storyboard/stories/{story['id']}/approve",
        json={"approved_by": "Producer"},
    )
    assert response.status_code == 422
    assert "expected_revision" in response.text


def test_user_provided_voice_requires_consent(client: TestClient):
    story = make_story(client)
    response = client.post(
        f"/voices/stories/{story['id']}/profiles",
        json={
            "name": "Unconsented",
            "setup_mode": "user_provided_consented",
            "source_description": "User-provided sample",
            "consent_required": True,
            "consent_confirmed": False,
        },
    )
    assert response.status_code == 422


def test_partial_shot_lifecycle_and_ordered_character_links(client: TestClient):
    story = make_story(client)
    chapter = client.post(
        f"/storyboard/stories/{story['id']}/chapters",
        json={"title": "Beginning", "order_index": 0},
    ).json()
    scene = client.post(
        f"/storyboard/chapters/{chapter['id']}/scenes",
        json={"title": "Arrival", "order_index": 0},
    ).json()
    shot = client.post(
        f"/storyboard/scenes/{scene['id']}/shots",
        json={"title": "Establish", "duration_sec": 8, "order_index": 0},
    ).json()

    invalid = client.patch(
        f"/storyboard/shots/{shot['id']}", json={"production_status": "blocked"}
    )
    assert invalid.status_code == 422
    assert "blocked_reason" in invalid.text

    patched = client.patch(
        f"/storyboard/shots/{shot['id']}",
        json={
            "title": "Blocked establish",
            "production_status": "blocked",
            "blocked_reason": "Reference conflict",
            "approval_state": "blocked",
            "camera_direction": "Slow push",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Blocked establish"
    assert patched.json()["production_status"] == "blocked"
    assert patched.json()["blocked_reason"] == "Reference conflict"
    assert patched.json()["duration_sec"] == 8

    characters = [
        client.post(
            f"/storyboard/stories/{story['id']}/characters",
            json={"name": name},
        ).json()
        for name in ("Alex", "Dana")
    ]
    replaced = client.put(
        f"/storyboard/shots/{shot['id']}/characters",
        json={
            "characters": [
                {"character_id": characters[1]["id"], "order_index": 0},
                {"character_id": characters[0]["id"], "order_index": 1},
            ]
        },
    )
    assert replaced.status_code == 200
    assert [item["character_id"] for item in replaced.json()] == [
        characters[1]["id"],
        characters[0]["id"],
    ]

    other_story = make_story(client)
    foreign_character = client.post(
        f"/storyboard/stories/{other_story['id']}/characters",
        json={"name": "Foreign"},
    ).json()
    cross_story = client.put(
        f"/storyboard/shots/{shot['id']}/characters",
        json={
            "characters": [
                {"character_id": foreign_character["id"], "order_index": 0}
            ]
        },
    )
    assert cross_story.status_code == 422
    assert "same story" in cross_story.text

    deleted = client.delete(
        f"/storyboard/shots/{shot['id']}/characters/{characters[0]['id']}"
    )
    assert deleted.status_code == 204
    remaining = client.get(f"/storyboard/shots/{shot['id']}/characters")
    assert remaining.status_code == 200
    assert [item["character_id"] for item in remaining.json()] == [characters[1]["id"]]


def test_storyboard_json_export_uses_complete_canonical_phase1_snapshot(
    client: TestClient,
):
    story = make_story(client)
    response = client.get(f"/storyboard/stories/{story['id']}/export.json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_name"] == "cineforge.storyboard.phase1.v1"
    assert payload["story"]["id"] == story["id"]
    assert payload["story"]["base_story"] == "A small planning story."
    assert "settings" in payload
    assert "chapters" in payload
    assert "characters" in payload
    assert "voice_profiles" in payload
    assert "planning_assets" in payload
    assert "task_provider_assignments" in payload
