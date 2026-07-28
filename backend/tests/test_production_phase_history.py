"""Immutable production-phase version history (SQLite disposable DB only)."""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import (
    AuditLog,
    Base,
    ProductionPhase,
    ProductionPhaseVersion,
    Project,
    Story,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.schemas.production import PhaseVersionCreateRequest
from backend.app.services import production_phases


@pytest.fixture
def db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'history.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _story(db: Session) -> Story:
    project = Project(name=f"History Project {uuid4().hex[:8]}", description="history")
    db.add(project)
    db.flush()
    story = Story(
        project_id=project.id,
        title="History Story",
        base_story="A quiet mountain becomes a place of revelation.",
        target_duration_sec=300,
        audience="General",
        genre="Sacred narrative",
        tone="Reverent",
        visual_style="Photoreal",
        point_of_view="Third person",
        production_notes="Planning only",
        approval_state="draft",
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


def test_eight_phase_contract_and_baselines(db_session: Session):
    story = _story(db_session)
    pipeline = production_phases.get_pipeline(db_session, story.id)
    assert pipeline.exact_phase_count == 8
    assert len(pipeline.phases) == 8
    assert [p.phase_number for p in pipeline.phases] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert all(p.version_count >= 1 for p in pipeline.phases)
    assert all(
        p.latest_version and p.latest_version.source == "baseline"
        for p in pipeline.phases
    )
    # Idempotent
    again = production_phases.get_pipeline(db_session, story.id)
    assert [p.version_count for p in again.phases] == [p.version_count for p in pipeline.phases]


def test_manual_append_all_phases_unique_and_immutable(db_session: Session):
    story = _story(db_session)
    production_phases.get_pipeline(db_session, story.id)
    prior_rows: dict[int, list[tuple]] = {}
    for phase_number in range(1, 9):
        rows = list(
            db_session.scalars(
                select(ProductionPhaseVersion)
                .join(ProductionPhase)
                .where(
                    ProductionPhase.story_id == story.id,
                    ProductionPhase.phase_number == phase_number,
                )
                .order_by(ProductionPhaseVersion.version_number)
            )
        )
        prior_rows[phase_number] = [
            (
                row.id,
                row.version_number,
                row.input_hash,
                row.output_hash,
                row.label,
                row.notes,
                row.source,
            )
            for row in rows
        ]
        created = production_phases.create_phase_version(
            db_session,
            story.id,
            phase_number,
            PhaseVersionCreateRequest(
                label=f"Director review P{phase_number}",
                notes="Milestone",
                requested_by="tester",
            ),
        )
        assert created.version.version_number == len(prior_rows[phase_number]) + 1
        assert created.version.source == "manual"
        assert created.version.previous_version_id == prior_rows[phase_number][-1][0]
        assert created.version.verified is True
        if phase_number == 8:
            assert created.version.output_json["picture"][
                "production_profile_key"
            ] == "ltx_base@1"
            assert (
                created.version.output_json["picture"]["stitch_stage"]
                == "phase7_before_audio"
            )

    # Prior rows unchanged byte-for-byte on tracked fields
    for phase_number, expected in prior_rows.items():
        rows = list(
            db_session.scalars(
                select(ProductionPhaseVersion)
                .join(ProductionPhase)
                .where(
                    ProductionPhase.story_id == story.id,
                    ProductionPhase.phase_number == phase_number,
                )
                .order_by(ProductionPhaseVersion.version_number)
            )
        )
        for index, fields in enumerate(expected):
            row = rows[index]
            assert (
                row.id,
                row.version_number,
                row.input_hash,
                row.output_hash,
                row.label,
                row.notes,
                row.source,
            ) == fields


def test_hash_tamper_and_cross_phase_rejection(db_session: Session, client: TestClient):
    story = _story(db_session)
    production_phases.get_pipeline(db_session, story.id)
    phase = db_session.scalar(
        select(ProductionPhase).where(
            ProductionPhase.story_id == story.id, ProductionPhase.phase_number == 2
        )
    )
    version = db_session.scalar(
        select(ProductionPhaseVersion)
        .where(ProductionPhaseVersion.production_phase_id == phase.id)
        .order_by(ProductionPhaseVersion.version_number)
    )
    # Tamper output without updating hash
    version.output_json = {**version.output_json, "tampered": True}
    db_session.commit()
    response = client.get(
        f"/production/stories/{story.id}/phases/2/versions/{version.id}"
    )
    assert response.status_code == 422
    assert "integrity" in response.json()["detail"].lower()

    # Cross-phase rejection
    other = client.get(
        f"/production/stories/{story.id}/phases/3/versions/{version.id}"
    )
    assert other.status_code == 422


def test_export_complete_or_fail_and_routes(client: TestClient, db_session: Session):
    story = _story(db_session)
    listed = client.get(f"/production/stories/{story.id}/phases/1/versions")
    assert listed.status_code == 200
    assert len(listed.json()) >= 1
    created = client.post(
        f"/production/stories/{story.id}/phases/4/versions",
        json={"label": "Location pass", "notes": "env coverage"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["version"]["label"] == "Location pass"
    assert body["version"]["source"] == "manual"
    assert body["pipeline"]["exact_phase_count"] == 8

    export = client.get(f"/production/stories/{story.id}/versions/export")
    assert export.status_code == 200
    payload = export.json()
    assert payload["integrity"]["verified"] is True
    assert payload["integrity"]["iteration_count"] >= 9
    assert payload["story_id"] == str(story.id)
    assert set(payload["integrity"]["phase_counts"].keys()) == {
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
    }


def test_missing_story_and_no_delete_route(client: TestClient):
    missing = uuid4()
    assert client.get(f"/production/stories/{missing}").status_code == 404
    # No delete endpoint for history
    story = None
    # FastAPI should 405/404 for DELETE on versions collection
    response = client.delete(f"/production/stories/{missing}/phases/1/versions/{missing}")
    assert response.status_code in {404, 405, 422}


def test_phase_six_approval_does_not_artificially_gate_local_generation_or_phase_seven(
    client: TestClient, db_session: Session
):
    story = _story(db_session)
    assert client.get(f"/production/stories/{story.id}").status_code == 200

    out_of_order = client.post(
        f"/production/stories/{story.id}/phases/2/approve",
        json={"approved_by": "CineForge QA"},
    )
    assert out_of_order.status_code == 422
    assert "Phase 1 must be approved" in out_of_order.json()["detail"]

    for phase_number in range(1, 6):
        response = client.post(
            f"/production/stories/{story.id}/phases/{phase_number}/approve",
            json={
                "approved_by": "CineForge QA",
                "notes": (
                    f"QA approved Phase {phase_number} planning only; "
                    "no media execution was certified."
                ),
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["phase"]["lifecycle_state"] == "approved"
        assert body["phase"]["approved_at"] is not None

    phase_six = client.post(
        f"/production/stories/{story.id}/phases/6/approve",
        json={"approved_by": "CineForge QA", "notes": "Creative image QA."},
    )
    assert phase_six.status_code == 200, phase_six.text
    assert phase_six.json()["phase"]["lifecycle_state"] == "approved"

    pipeline = client.get(f"/production/stories/{story.id}").json()
    assert all(phase["lifecycle_state"] == "approved" for phase in pipeline["phases"][:6])
    phase_seven = pipeline["phases"][6]
    assert phase_seven["lifecycle_state"] == "drafting"
    assert phase_seven["approved_at"] is None
    assert phase_seven["is_locked"] is False

    phase_seven_approval = client.post(
        f"/production/stories/{story.id}/phases/7/approve",
        json={
            "approved_by": "CineForge QA",
            "notes": "Planning approval only; no picture-lock media evidence.",
        },
    )
    assert phase_seven_approval.status_code == 200, phase_seven_approval.text
    phase_eight = phase_seven_approval.json()["pipeline"]["phases"][7]
    assert phase_eight["lifecycle_state"] == "not_started"
    assert phase_eight["is_locked"] is True
    assert "immutable picture lock" in phase_eight["locked_reason"]

    blocked_phase_eight = client.post(
        f"/production/stories/{story.id}/phases/8/approve",
        json={"approved_by": "CineForge QA"},
    )
    assert blocked_phase_eight.status_code == 422
    assert "Planning approval alone is not media evidence" in (
        blocked_phase_eight.json()["detail"]
    )

    approval_logs = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "production_phase_approved")
            .order_by(AuditLog.created_at)
        )
    )
    assert len(approval_logs) == 7
    assert all(log.details["media_generated"] is False for log in approval_logs)
