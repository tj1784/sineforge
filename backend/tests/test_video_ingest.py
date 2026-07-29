from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes.assets import router as assets_router
from backend.app.api.routes.video_ingest import router as video_ingest_router
from backend.app.db.base import Base, PlanningMediaAsset, Project
from backend.app.db.session import get_db
from backend.app.services import reference_assets as assets


@pytest.fixture()
def client_and_db(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = factory()

    class _Settings:
        storage_root = Path(tmp_path)

    monkeypatch.setattr(assets, "get_settings", lambda: _Settings())
    monkeypatch.setattr(assets.shutil, "which", lambda name: f"C:/{name}.exe")
    monkeypatch.setattr(
        assets.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "h264",
                            "codec_long_name": "H.264",
                            "profile": "High",
                            "pix_fmt": "yuv420p",
                            "width": 1280,
                            "height": 720,
                            "avg_frame_rate": "24/1",
                            "r_frame_rate": "24/1",
                            "time_base": "1/12288",
                            "nb_frames": "240",
                        }
                    ],
                    "format": {"duration": "10.0"},
                }
            ),
        ),
    )

    project = Project(name="Video ingest", description=None)
    session.add(project)
    session.commit()
    session.refresh(project)

    app = FastAPI()
    app.include_router(assets_router)
    app.include_router(video_ingest_router)

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, session, project
    session.close()
    engine.dispose()


def test_streamed_video_ingest_preserves_bytes_probe_and_duplicate(
    client_and_db,
) -> None:
    client, session, project = client_and_db
    source = b"bounded-fake-video-payload"
    endpoint = (
        f"/video/phase-7/projects/{project.id}/sources/upload"
        "?original_filename=source.mp4"
    )

    created = client.post(
        endpoint, content=source, headers={"content-type": "video/mp4"}
    )
    duplicate = client.post(
        endpoint, content=source, headers={"content-type": "video/mp4"}
    )

    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["created"] is True
    assert payload["asset"]["kind"] == "video_source"
    assert payload["asset"]["width"] == 1280
    assert payload["asset"]["height"] == 720
    assert payload["asset"]["duration_sec"] == 10.0
    assert (
        payload["asset"]["metadata_json"][
            "full_decode_required_before_picture_lock"
        ]
        is True
    )
    asset = session.get(PlanningMediaAsset, UUID(payload["asset"]["id"]))
    managed_path = assets.resolve_managed_path(asset)
    assert managed_path.read_bytes() == source

    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert duplicate.json()["asset"]["id"] == payload["asset"]["id"]
    assert managed_path.read_bytes() == source


def test_generic_asset_upload_redirects_video_to_streaming_boundary(
    client_and_db,
) -> None:
    client, _, project = client_and_db

    response = client.post(
        f"/assets/projects/{project.id}/upload"
        "?kind=video_source&original_filename=source.mp4",
        content=b"video",
        headers={"content-type": "video/mp4"},
    )

    assert response.status_code == 422
    assert "/video/phase-7/" in response.json()["detail"]


def test_video_ingest_rejects_unsupported_container(client_and_db) -> None:
    client, _, project = client_and_db

    response = client.post(
        f"/video/phase-7/projects/{project.id}/sources/upload"
        "?original_filename=source.avi",
        content=b"video",
        headers={"content-type": "video/x-msvideo"},
    )

    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]
