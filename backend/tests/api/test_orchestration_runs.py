"""API tests for durable, nonblocking planning orchestration."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.routes import orchestration_runs
from backend.app.db.base import (
    Base,
    ComfyJob,
    FFmpegJob,
    OrchestrationRun,
    Project,
    Story,
    WorkflowRun,
)
from backend.app.db.session import get_db
from backend.app.services.planning.engine import PlanningEngine
from backend.app.services.planning.executor import planning_execution_controller
from backend.app.services.planning.provider import MockPlanningProvider


class BlockingMockProvider(MockPlanningProvider):
    """Deterministic provider whose first call can be held by the test."""

    def __init__(self) -> None:
        super().__init__(fixed_latency_ms=0)
        self.entered = threading.Event()
        self.release = threading.Event()
        self._count_lock = threading.Lock()
        self.call_count = 0

    def invoke(self, request):  # noqa: ANN001
        with self._count_lock:
            self.call_count += 1
        self.entered.set()
        if not self.release.wait(timeout=10):
            raise RuntimeError("test provider release timed out")
        return super().invoke(request)


class BoundaryFailureEngine(PlanningEngine):
    def execute_claimed_run(self, run_id, *, resumed=False):  # noqa: ANN001, ARG002
        raise RuntimeError("deliberate worker boundary failure")


@pytest.fixture()
def client_and_db(tmp_path, monkeypatch):  # noqa: ANN001
    database_path = (tmp_path / "orchestration-api.db").as_posix()
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    provider = BlockingMockProvider()

    def _engine(db: Session) -> PlanningEngine:
        return PlanningEngine(db, providers={"mock": provider})

    monkeypatch.setattr(orchestration_runs, "_engine", _engine)

    app = FastAPI()
    app.include_router(orchestration_runs.router)
    app.dependency_overrides[get_db] = _override_db

    db = SessionLocal()
    project = Project(id=uuid.uuid4(), name="API Project", description=None, created_at=datetime.utcnow())
    db.add(project)
    db.flush()
    story = Story(
        id=uuid.uuid4(),
        project_id=project.id,
        title="API Story",
        base_story="A short story for API tests.",
        target_duration_sec=24.0,
        approval_state="draft",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(story)
    db.commit()
    story_id = story.id
    db.close()

    with TestClient(app) as client:
        try:
            yield client, story_id, SessionLocal, provider, engine
        finally:
            provider.release.set()
            planning_execution_controller.wait_for_idle(timeout=10)

    engine.dispose()


def _create_run(client: TestClient, story_id: uuid.UUID, *, tasks=None) -> str:  # noqa: ANN001
    response = client.post(
        "/orchestration/runs",
        json={
            "story_id": str(story_id),
            "requested_by": "api-tester",
            "routing_mode": "automatic",
            "max_steps": 4,
            "repair_budget": 2,
            "time_budget_sec": 120,
            "task_types": tasks or ["shot_list", "production_proposal"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]["id"]


def _wait_for_run(client: TestClient, run_id: str, statuses: set[str], *, timeout: float = 6.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/orchestration/runs/{run_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in statuses:
            return last
        time.sleep(0.02)
    raise AssertionError(f"run did not reach {statuses}; last={last}")


def _force_run_status(SessionLocal, run_id: str, status: str) -> None:  # noqa: ANN001
    with SessionLocal() as db:
        run = db.get(OrchestrationRun, uuid.UUID(run_id))
        assert run is not None
        run.status = status
        if status == "completed":
            run.completed_at = datetime.utcnow()
        elif status == "failed":
            run.failed_at = datetime.utcnow()
            run.failure_category = "test"
            run.failure_message = "forced terminal state"
        elif status == "canceled":
            run.canceled_at = datetime.utcnow()
            run.cancel_reason = "forced terminal state"
        db.commit()


def test_start_is_nonblocking_and_progress_is_observable(client_and_db):
    client, story_id, _sessions, provider, _bind = client_and_db
    run_id = _create_run(client, story_id)

    started_at = time.monotonic()
    start = client.post(f"/orchestration/runs/{run_id}/start")
    elapsed = time.monotonic() - started_at

    assert start.status_code == 202, start.text
    assert elapsed < 0.75
    assert start.json()["run"]["status"] == "running"
    assert "poll" in start.json()["message"].lower()
    assert provider.entered.wait(timeout=2)

    detail = _wait_for_run(client, run_id, {"running"})
    assert any(step["status"] == "running" for step in detail["steps"])
    assert any(invocation["status"] == "pending" for invocation in detail["invocations"])

    provider.release.set()
    completed = _wait_for_run(client, run_id, {"completed"})
    assert completed["proposals"][0]["status"] == "pending_review"


def test_duplicate_start_does_not_duplicate_execution(client_and_db):
    client, story_id, _sessions, provider, _bind = client_and_db
    run_id = _create_run(client, story_id)

    first = client.post(f"/orchestration/runs/{run_id}/start")
    assert first.status_code == 202
    assert provider.entered.wait(timeout=2)

    duplicate = client.post(f"/orchestration/runs/{run_id}/start")
    assert duplicate.status_code == 202, duplicate.text
    assert "already active" in duplicate.json()["message"].lower()
    time.sleep(0.05)
    assert provider.call_count == 1

    provider.release.set()
    _wait_for_run(client, run_id, {"completed"})


def test_cancel_is_accepted_during_provider_execution_and_remains_terminal(client_and_db):
    client, story_id, SessionLocal, provider, bind = client_and_db
    run_id = _create_run(client, story_id)
    assert client.post(f"/orchestration/runs/{run_id}/start").status_code == 202
    assert provider.entered.wait(timeout=2)

    canceled = client.post(
        f"/orchestration/runs/{run_id}/cancel",
        json={"reason": "stop", "requested_by": "api-tester"},
    )
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["run"]["status"] == "canceled"

    provider.release.set()
    planning_execution_controller.wait(uuid.UUID(run_id), bind=bind, timeout=6)
    final = _wait_for_run(client, run_id, {"canceled"})
    assert all(step["status"] == "canceled" for step in final["steps"])
    assert not final["proposals"]

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ComfyJob)) == 0
        assert db.scalar(select(func.count()).select_from(FFmpegJob)) == 0
        assert db.scalar(select(func.count()).select_from(WorkflowRun)) == 0


def test_unexpected_worker_failure_is_recorded_durably(client_and_db, monkeypatch):
    client, story_id, _sessions, provider, _bind = client_and_db
    provider.release.set()

    def _failing_engine(db: Session) -> PlanningEngine:
        return BoundaryFailureEngine(db, providers={"mock": provider})

    monkeypatch.setattr(orchestration_runs, "_engine", _failing_engine)
    run_id = _create_run(client, story_id, tasks=["story_structure"])
    start = client.post(f"/orchestration/runs/{run_id}/start")
    assert start.status_code == 202

    failed = _wait_for_run(client, run_id, {"failed"})
    assert failed["failure_category"] == "internal"
    assert "planning worker failed" in failed["failure_message"].lower()
    assert any(event["event_type"] == "run_failed" for event in failed["events"])


def test_running_run_can_be_resubmitted_for_checkpoint_recovery(client_and_db):
    client, story_id, SessionLocal, provider, _bind = client_and_db
    run_id = _create_run(client, story_id)
    with SessionLocal() as db:
        PlanningEngine(db, providers={"mock": provider}).claim_run(uuid.UUID(run_id))

    recovered = client.post(f"/orchestration/runs/{run_id}/start")
    assert recovered.status_code == 202, recovered.text
    assert "recovery" in recovered.json()["message"].lower()
    assert provider.entered.wait(timeout=2)
    provider.release.set()
    detail = _wait_for_run(client, run_id, {"completed"})
    assert any(event["event_type"] == "run_resumed" for event in detail["events"])


def test_idempotent_create_via_api(client_and_db):
    client, story_id, _sessions, _provider, _bind = client_and_db
    payload = {
        "story_id": str(story_id),
        "idempotency_key": "api-idem-key-abcdefgh",
        "task_types": ["production_proposal"],
        "max_steps": 2,
    }
    first = client.post("/orchestration/runs", json=payload)
    second = client.post("/orchestration/runs", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["run"]["id"] == second.json()["run"]["id"]
    assert second.json()["idempotent_replay"] is True


def test_cancel_pending_via_api(client_and_db):
    client, story_id, _sessions, _provider, _bind = client_and_db
    run_id = _create_run(client, story_id)
    canceled = client.post(
        f"/orchestration/runs/{run_id}/cancel",
        json={"reason": "stop", "requested_by": "api-tester"},
    )
    assert canceled.status_code == 200
    assert canceled.json()["run"]["status"] == "canceled"


def test_retry_creates_new_audited_pending_run_without_rewriting_parent(client_and_db):
    client, story_id, _sessions, _provider, _bind = client_and_db
    parent_id = _create_run(client, story_id)
    assert client.post(f"/orchestration/runs/{parent_id}/cancel").status_code == 200
    parent_before = client.get(f"/orchestration/runs/{parent_id}").json()

    retried = client.post(
        f"/orchestration/runs/{parent_id}/retry",
        json={"requested_by": "retry-tester"},
    )
    assert retried.status_code == 201, retried.text
    body = retried.json()
    assert body["created"] is True
    assert body["run"]["status"] == "pending"
    assert body["run"]["id"] != parent_id
    retry_snapshot = body["run"]["routing_snapshot_json"]
    assert retry_snapshot["retry_of_run_id"] == parent_id
    assert retry_snapshot["retry_attempt"] == 1
    assert "retry_limit" not in retry_snapshot

    replay = client.post(
        f"/orchestration/runs/{parent_id}/retry",
        json={"requested_by": "retry-tester"},
    )
    assert replay.status_code == 201
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["run"]["id"] == body["run"]["id"]

    parent_after = client.get(f"/orchestration/runs/{parent_id}").json()
    assert parent_after["routing_snapshot_json"] == parent_before["routing_snapshot_json"]
    assert parent_after["events"] == parent_before["events"]


def test_completed_run_can_be_retried_for_user_iteration(client_and_db):
    client, story_id, _sessions, provider, _bind = client_and_db
    provider.release.set()
    parent_id = _create_run(client, story_id)
    assert client.post(f"/orchestration/runs/{parent_id}/start").status_code == 202
    completed = _wait_for_run(client, parent_id, {"completed"})
    assert completed["status"] == "completed"

    retried = client.post(
        f"/orchestration/runs/{parent_id}/retry",
        json={"requested_by": "iteration-tester"},
    )
    assert retried.status_code == 201, retried.text
    body = retried.json()
    assert body["created"] is True
    assert body["run"]["status"] == "pending"
    assert body["run"]["id"] != parent_id
    assert body["run"]["routing_snapshot_json"]["retry_of_run_id"] == parent_id
    assert body["run"]["routing_snapshot_json"]["retry_attempt"] == 1


@pytest.mark.parametrize("terminal_status", ["failed", "canceled"])
def test_failed_and_canceled_runs_can_be_retried_for_user_iteration(
    client_and_db,
    terminal_status,
):
    client, story_id, SessionLocal, _provider, _bind = client_and_db
    parent_id = _create_run(client, story_id)
    _force_run_status(SessionLocal, parent_id, terminal_status)

    retried = client.post(
        f"/orchestration/runs/{parent_id}/retry",
        json={"requested_by": "iteration-tester"},
    )

    assert retried.status_code == 201, retried.text
    body = retried.json()
    assert body["created"] is True
    assert body["run"]["status"] == "pending"
    assert body["run"]["id"] != parent_id
    assert body["run"]["routing_snapshot_json"]["retry_of_run_id"] == parent_id
    assert body["run"]["routing_snapshot_json"]["retry_attempt"] == 1


def test_pending_run_cannot_be_retried(client_and_db):
    client, story_id, _sessions, _provider, _bind = client_and_db
    run_id = _create_run(client, story_id)

    retried = client.post(f"/orchestration/runs/{run_id}/retry")
    assert retried.status_code == 409
    assert retried.json()["detail"]["code"] == "invalid_transition"


def test_running_run_cannot_be_retried(client_and_db):
    client, story_id, _sessions, provider, _bind = client_and_db
    run_id = _create_run(client, story_id)
    started = client.post(f"/orchestration/runs/{run_id}/start")
    assert started.status_code == 202, started.text
    assert provider.entered.wait(timeout=2)

    retried = client.post(f"/orchestration/runs/{run_id}/retry")

    assert retried.status_code == 409
    assert retried.json()["detail"]["code"] == "invalid_transition"
    provider.release.set()


def test_retry_chain_does_not_exhaust_normal_iterations(client_and_db):
    client, story_id, _sessions, _provider, _bind = client_and_db
    current_id = _create_run(client, story_id)
    assert client.post(f"/orchestration/runs/{current_id}/cancel").status_code == 200

    for expected_attempt in range(1, 6):
        retried = client.post(f"/orchestration/runs/{current_id}/retry")
        assert retried.status_code == 201, retried.text
        current_id = retried.json()["run"]["id"]
        assert retried.json()["run"]["routing_snapshot_json"]["retry_attempt"] == expected_attempt
        assert client.post(f"/orchestration/runs/{current_id}/cancel").status_code == 200


def test_list_story_runs_and_unknown_run(client_and_db):
    client, story_id, _sessions, _provider, _bind = client_and_db
    _create_run(client, story_id, tasks=["production_proposal"])
    listed = client.get(f"/orchestration/stories/{story_id}/runs")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    missing = client.get(f"/orchestration/runs/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "run_not_found"
