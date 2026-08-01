from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes import agent
from backend.app.core.config import Settings
from backend.app.db.base import (
    AgentActionReceipt,
    AgentAuditEvent,
    Base,
    CreativeReviewNote,
    Project,
    Story,
)
from backend.app.db.session import get_db
from backend.app.services.agent.service import AgentService


class FakeProvider:
    def __init__(self, action: dict[str, Any]) -> None:
        self.action = action
        self.messages: list[dict[str, str]] = []

    async def health(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "reachable": True,
            "status": "ok",
            "models": [{"id": "test-operator-model", "owned_by": "lm-studio"}],
            "active_model_id": "test-operator-model",
            "error": None,
        }

    async def complete_action(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        idempotency_key: str,
        thinking_enabled: bool = True,
    ) -> dict[str, Any]:
        self.messages = messages
        return self.action


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _settings() -> Settings:
    return Settings(
        ai_agent_enabled=True,
        ai_model="test-operator-model",
        ai_base_url="http://127.0.0.1:1234/v1",
        database_url="sqlite://",
    )


def _client(db: Session, provider: FakeProvider) -> TestClient:
    app = FastAPI()
    app.include_router(agent.router)

    def override_get_db() -> Generator[Session, None, None]:
        yield db

    def override_agent_service() -> AgentService:
        return AgentService(_settings(), provider=provider)  # type: ignore[arg-type]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[agent.get_agent_service] = override_agent_service
    return TestClient(app)


def _project(db: Session) -> Project:
    project = Project(name="Transfiguration", description="Local operator test")
    db.add(project)
    db.flush()
    return project


def _story(db: Session, project: Project) -> Story:
    story = Story(
        project_id=project.id,
        title="Scene Ledger",
        base_story="A focused test story.",
        logline=None,
        synopsis=None,
        target_duration_sec=60,
        audience=None,
        tone=None,
        genre=None,
        visual_style=None,
        point_of_view=None,
        production_notes=None,
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


def _context(project: Project | None, story: Story | None = None) -> dict[str, Any]:
    return {
        "contextVersion": 1,
        "capturedAt": "2026-07-31T12:00:00Z",
        "routeId": "studio.story",
        "pathname": f"/projects/{project.id if project else 'none'}/studio/story",
        "pageViewId": "test-page-view",
        "pageTitle": "Story",
        "domain": "studio",
        "tenantId": "forged-tenant",
        "projectId": str(project.id) if project else None,
        "projectVersion": "forged-version",
        "recordType": "story" if story else None,
        "recordId": str(story.id) if story else None,
        "recordVersion": "forged-record-version",
        "parentRefs": [],
        "selectedRefs": [],
        "activeTab": "story",
        "activePanel": None,
        "filters": {},
        "mode": "view",
        "dirty": False,
        "capabilities": ["review.add_note", "workspace.apply_patch"],
        "correlationId": "test-correlation",
    }


def _create_session(client: TestClient, context: dict[str, Any]) -> str:
    response = client.post(
        "/agent/sessions",
        json={"actor_id": "tester", "title": "Test", "context": context},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_read_tool_uses_server_verified_project_context(db_session: Session):
    project = _project(db_session)
    story = _story(db_session, project)
    provider = FakeProvider(
        {
            "assistant_text": "I will read the current project.",
            "tool_call": {"name": "project.get", "arguments": {}},
        }
    )
    client = _client(db_session, provider)
    session_id = _create_session(client, _context(project, story))

    response = client.post(
        f"/agent/sessions/{session_id}/messages",
        json={
            "actor_id": "tester",
            "content": "What project is this?",
            "context": _context(project, story),
            "idempotency_key": "read-once",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["context_snapshot"]["hydrated_summary"]["project"]["id"] == str(project.id)
    assert payload["tool_activities"][0]["status"] == "succeeded"
    assert payload["tool_activities"][0]["result"]["resource"]["name"] == "Transfiguration"
    assert "workspace.apply_patch" not in provider.messages[1]["content"]


def test_forged_capability_cannot_create_write_proposal_without_project(db_session: Session):
    provider = FakeProvider(
        {
            "assistant_text": "Trying a note.",
            "tool_call": {
                "name": "review.add_note",
                "arguments": {
                    "target_type": "project",
                    "target_id": "00000000-0000-0000-0000-000000000001",
                    "note": "Injected note",
                },
            },
        }
    )
    client = _client(db_session, provider)
    context = _context(None, None)
    session_id = _create_session(client, context)

    response = client.post(
        f"/agent/sessions/{session_id}/messages",
        json={
            "actor_id": "tester",
            "content": "Fix this",
            "context": context,
            "idempotency_key": "blocked-write",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["tool_activities"][0]["status"] == "blocked"
    assert payload["proposals"] == []
    assert db_session.scalar(select(CreativeReviewNote)) is None


def test_review_note_requires_approval_is_idempotent_and_can_be_undone(db_session: Session):
    project = _project(db_session)
    story = _story(db_session, project)
    provider = FakeProvider(
        {
            "assistant_text": "I can add that as a review note after approval.",
            "tool_call": {
                "name": "review.add_note",
                "arguments": {
                    "target_type": "story",
                    "target_id": str(story.id),
                    "note": "Check the midpoint transition before render.",
                },
            },
        }
    )
    client = _client(db_session, provider)
    session_id = _create_session(client, _context(project, story))

    response = client.post(
        f"/agent/sessions/{session_id}/messages",
        json={
            "actor_id": "tester",
            "content": "Add a note.",
            "context": _context(project, story),
            "idempotency_key": "proposal-note",
        },
    )
    assert response.status_code == 200, response.text
    proposal = response.json()["proposals"][0]
    assert proposal["status"] == "pending_approval"
    assert proposal["approval_token"]
    assert db_session.scalar(select(CreativeReviewNote)) is None

    approval = {
        "actor_id": "tester",
        "approval_token": proposal["approval_token"],
        "idempotency_key": "apply-note-once",
    }
    first = client.post(f"/agent/proposals/{proposal['id']}/approve", json=approval)
    second = client.post(f"/agent/proposals/{proposal['id']}/approve", json=approval)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    notes = db_session.scalars(select(CreativeReviewNote)).all()
    assert len(notes) == 1
    assert notes[0].note == "Check the midpoint transition before render."

    undo = client.post(
        f"/agent/actions/{first.json()['id']}/undo",
        json={"actor_id": "tester", "reason": "test undo"},
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["undo_status"] == "completed"
    assert db_session.scalar(select(CreativeReviewNote)) is None
    assert db_session.scalar(select(AgentActionReceipt)).undo_status == "completed"
    assert db_session.scalar(select(AgentAuditEvent).where(AgentAuditEvent.event_type == "agent.action.undone"))


def test_stale_target_version_blocks_approved_mutation(db_session: Session):
    project = _project(db_session)
    story = _story(db_session, project)
    provider = FakeProvider(
        {
            "assistant_text": "Approval is needed.",
            "tool_call": {
                "name": "review.add_note",
                "arguments": {
                    "target_type": "story",
                    "target_id": str(story.id),
                    "note": "This should not apply after a stale write.",
                },
            },
        }
    )
    client = _client(db_session, provider)
    session_id = _create_session(client, _context(project, story))
    response = client.post(
        f"/agent/sessions/{session_id}/messages",
        json={
            "actor_id": "tester",
            "content": "Add a note.",
            "context": _context(project, story),
            "idempotency_key": "proposal-stale",
        },
    )
    proposal = response.json()["proposals"][0]

    story.title = "Changed after proposal"
    story.updated_at = datetime.utcnow() + timedelta(seconds=10)
    db_session.commit()

    approval = client.post(
        f"/agent/proposals/{proposal['id']}/approve",
        json={
            "actor_id": "tester",
            "approval_token": proposal["approval_token"],
            "idempotency_key": "stale-apply",
        },
    )
    assert approval.status_code == 409, approval.text
    assert "Target changed" in approval.json()["detail"]
    assert db_session.scalar(select(CreativeReviewNote)) is None
