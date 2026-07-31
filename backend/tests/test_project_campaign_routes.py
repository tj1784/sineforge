from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import app


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "cineforge_routes_test.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    Base.metadata.create_all(engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_create_and_get_project_db_backed(client):
    create_response = client.post(
        "/projects",
        json={
            "name": "Launch Film",
            "description": "Hero cut",
            "workflow_lane": "cineforge_studio",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Launch Film"
    assert created["description"] == "Hero cut"
    assert created["persistence"] == "db"
    assert created["created_at"]

    get_response = client.get(f"/projects/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == created


def test_list_projects_returns_created_projects(client):
    first_response = client.post(
        "/projects",
        json={"name": "First Project", "workflow_lane": "cineforge_studio"},
    )
    second_response = client.post(
        "/projects",
        json={"name": "Second Project", "workflow_lane": "cineforge_studio"},
    )

    response = client.get("/projects")

    assert response.status_code == 200
    project_ids = {project["id"] for project in response.json()}
    assert project_ids == {first_response.json()["id"], second_response.json()["id"]}


def test_get_missing_project_returns_404(client):
    response = client.get(f"/projects/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_create_campaign_requires_existing_project(client):
    response = client.post(
        "/campaigns",
        json={
            "project_id": str(uuid4()),
            "name": "Missing project campaign",
            "target_duration_sec": 12.5,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_create_and_get_campaign_db_backed(client):
    project_response = client.post(
        "/projects",
        json={
            "name": "Project for Campaign",
            "workflow_lane": "cineforge_studio",
        },
    )
    project_id = project_response.json()["id"]

    create_response = client.post(
        "/campaigns",
        json={"project_id": project_id, "name": "Episode One", "target_duration_sec": 30},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["project_id"] == project_id
    assert created["name"] == "Episode One"
    assert created["target_duration_sec"] == 30.0
    assert created["persistence"] == "db"
    assert created["created_at"]

    get_response = client.get(f"/campaigns/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == created


def test_list_campaigns_can_filter_by_project(client):
    first_project = client.post(
        "/projects",
        json={"name": "Project One", "workflow_lane": "cineforge_studio"},
    ).json()
    second_project = client.post(
        "/projects",
        json={"name": "Project Two", "workflow_lane": "cineforge_studio"},
    ).json()
    first_campaign = client.post(
        "/campaigns",
        json={"project_id": first_project["id"], "name": "Project One Campaign"},
    ).json()
    client.post(
        "/campaigns",
        json={"project_id": second_project["id"], "name": "Project Two Campaign"},
    )

    response = client.get(f"/campaigns?project_id={first_project['id']}")

    assert response.status_code == 200
    assert response.json() == [first_campaign]


def test_get_missing_campaign_returns_404(client):
    response = client.get(f"/campaigns/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Campaign not found."
