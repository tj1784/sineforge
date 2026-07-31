"""Project API and durable-ledger tests for LTX Sequence Sheets."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import Mock
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.routes import sequence_sheets
from backend.app.db.base import (
    Base,
    Project,
    ProjectStoryboardSettings,
    SequenceExecutionRun,
    SequencePlan,
    SequencePlanRevision,
    SequenceRow,
    SequenceRowAttempt,
    SequenceRowDependency,
    SequenceRowExecution,
    WorkflowTemplate,
)
from backend.app.db.session import get_db
from backend.app.services.sequence_sheets import (
    adapt_studio_sequence_payload,
    compile_ltx_sequence,
)
from backend.app.services.sequence_sheets.persistence import (
    SequenceIdempotencyConflict,
    persist_sequence_execution,
)
from backend.app.services.storyboard_settings import (
    default_settings_values,
    production_profile_settings_values,
)


WORKFLOW_SHA256 = (
    "1f76ced65655d07222cb72ffdfab4e132"
    "c7386ed72e3ddc7e8c77bebae762e11"
)


@pytest.fixture()
def api_context(tmp_path) -> Generator[tuple[TestClient, sessionmaker, UUID], None, None]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'sequence-sheet.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    project_id = uuid4()
    with session_factory() as db:
        db.add(
            Project(
                id=project_id,
                name="Sequence API Project",
                description=None,
            )
        )
        settings_values = default_settings_values()
        settings_values.update(
            production_profile_settings_values("ltx_base@2")
        )
        db.add(
            ProjectStoryboardSettings(
                project_id=project_id,
                **settings_values,
            )
        )
        db.commit()

    app = FastAPI()
    app.include_router(sequence_sheets.router)

    def _override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as client:
        yield client, session_factory, project_id
    engine.dispose()


def _row(
    *,
    row_id: str = "row-001",
    order: int = 1,
    duration_sec: float = 8.0,
    enabled: bool = True,
    continuity_source: str = "asset:opening-frame",
    input_asset_id: str | None = "opening-frame",
    output_name: str | None = None,
) -> dict:
    return {
        "row_id": row_id,
        "order": order,
        "enabled": enabled,
        "scene_id": "scene-001",
        "subscene_id": f"subscene-{order:03d}",
        "template_key": "ltx_i2v_static",
        "workflow_version": "1.0",
        "workflow_sha256": WORKFLOW_SHA256,
        "model_profile": "ltx_base@2",
        "mode": "i2v",
        "prompt": f"Photorealistic sequence row {order}.",
        "negative_prompt": "blur, compression artifacts",
        "duration_sec": duration_sec,
        "seed": "derive",
        "continuity_source": continuity_source,
        "input_asset_id": input_asset_id,
        "character_ids": ["character-main"],
        "asset_ids": ["location-home"],
        "reference_asset_ids": ["wardrobe-main"],
        "output_name": output_name or f"sequence_{order:03d}",
        "max_attempts": 2,
        "on_error": "stop",
    }


def _payload(project_id: UUID, *, rows: list[dict] | None = None) -> dict:
    return {
        "schema_version": "sineforge.sequence-sheet/v1",
        "project_id": str(project_id),
        "model_family": "ltx",
        "rows": rows or [_row()],
    }


def _count(db: Session, model) -> int:  # noqa: ANN001
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.parametrize(
    ("duration_sec", "expected_frames"),
    [(8.0, 193), (15.0, 361)],
)
def test_dry_run_compiles_eight_and_fifteen_seconds_while_workflow_is_unqualified(
    api_context,
    duration_sec: float,
    expected_frames: int,
) -> None:
    client, session_factory, project_id = api_context

    response = client.post(
        f"/projects/{project_id}/sequence-sheet/dry-run",
        json=_payload(
            project_id,
            rows=[_row(duration_sec=duration_sec)],
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["status"] == "valid_with_blockers"
    assert body["summary"]["total_duration_sec"] == duration_sec
    assert body["compiled"]["segments"][0]["frame_count"] == expected_frames
    assert body["qualification"]["qualified"] is False
    assert {
        blocker["code"] for blocker in body["qualification"]["blockers"]
    } == {
        "workflow_qualification_required",
    }
    with session_factory() as db:
        assert _count(db, SequencePlan) == 0
        assert _count(db, SequenceExecutionRun) == 0


@pytest.mark.parametrize("duration_sec", [7.999, 15.001])
def test_dry_run_rejects_values_outside_exact_eight_to_fifteen_bounds(
    api_context,
    duration_sec: float,
) -> None:
    client, _, project_id = api_context

    response = client.post(
        f"/projects/{project_id}/sequence-sheet/dry-run",
        json=_payload(
            project_id,
            rows=[_row(duration_sec=duration_sec)],
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any(
        issue.get("column") == "duration_sec"
        or "duration_sec" in issue["message"]
        for issue in body["issues"]
    )


def test_dry_run_omits_disabled_rows_before_compilation(api_context) -> None:
    client, _, project_id = api_context
    rows = [
        _row(),
        _row(
            row_id="row-disabled",
            order=2,
            duration_sec=7.0,
            enabled=False,
            output_name="disabled_invalid_duration",
        ),
    ]

    response = client.post(
        f"/projects/{project_id}/sequence-sheet/dry-run",
        json=_payload(project_id, rows=rows),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["summary"]["row_count"] == 2
    assert body["summary"]["enabled_row_count"] == 1
    assert len(body["compiled"]["segments"]) == 1


def test_project_id_mismatch_and_wan_fail_with_stable_codes(api_context) -> None:
    client, _, project_id = api_context

    mismatch = _payload(project_id)
    mismatch["project_id"] = str(uuid4())
    mismatch_response = client.post(
        f"/projects/{project_id}/sequence-sheet/dry-run",
        json=mismatch,
    )
    assert mismatch_response.status_code == 409
    assert mismatch_response.json()["detail"]["code"] == "project_id_mismatch"

    wan = _payload(project_id)
    wan["model_family"] = "wan"
    wan_response = client.post(
        f"/projects/{project_id}/sequence-sheet/dry-run",
        json=wan,
    )
    assert wan_response.status_code == 409
    assert wan_response.json()["detail"]["code"] == "wan_on_hold"


@pytest.mark.parametrize(
    "endpoint",
    [
        "sequence-sheet/dry-run",
        "sequence-sheet/execute",
    ],
)
def test_agentless_project_rejects_generic_sequence_endpoints_before_compilation_or_persistence(
    api_context,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    client, session_factory, project_id = api_context
    with session_factory() as db:
        project = db.get(Project, project_id)
        assert project is not None
        project.workflow_lane = "agentless"
        db.commit()

    validate_envelope = Mock()
    prepare_sequence = Mock()
    persist_execution = Mock()
    monkeypatch.setattr(
        sequence_sheets,
        "_validate_envelope",
        validate_envelope,
    )
    monkeypatch.setattr(
        sequence_sheets,
        "_prepare_sequence",
        prepare_sequence,
    )
    monkeypatch.setattr(
        sequence_sheets,
        "persist_sequence_execution",
        persist_execution,
    )

    response = client.post(
        f"/projects/{project_id}/{endpoint}",
        json=_payload(project_id),
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail == {
        "code": "workflow_lane_mismatch",
        "message": (
            "Agentless projects cannot use the generic Sequence Sheet routes. "
            f"Use /projects/{project_id}/agentless-workflow/dry-run."
        ),
        "actual_workflow_lane": "agentless",
        "required_endpoint": (
            f"/projects/{project_id}/agentless-workflow/dry-run"
        ),
    }
    validate_envelope.assert_not_called()
    prepare_sequence.assert_not_called()
    persist_execution.assert_not_called()
    with session_factory() as db:
        assert _count(db, SequencePlan) == 0
        assert _count(db, SequenceExecutionRun) == 0


def test_execute_fails_closed_without_an_admitted_workflow_or_writes(
    api_context,
) -> None:
    client, session_factory, project_id = api_context

    response = client.post(
        f"/projects/{project_id}/sequence-sheet/execute",
        headers={
            "Idempotency-Key": "sequence-execute-0001",
            "X-Allow-Rendering": "true",
        },
        json=_payload(project_id),
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"]
        == "workflow_qualification_required"
    )
    with session_factory() as db:
        for model in (
            SequencePlan,
            SequencePlanRevision,
            SequenceRow,
            SequenceRowDependency,
            SequenceExecutionRun,
            SequenceRowExecution,
            SequenceRowAttempt,
        ):
            assert _count(db, model) == 0


def test_execute_honors_persisted_project_rendering_gate(api_context) -> None:
    client, session_factory, project_id = api_context
    with session_factory() as db:
        settings = db.scalar(
            select(ProjectStoryboardSettings).where(
                ProjectStoryboardSettings.project_id == project_id
            )
        )
        assert settings is not None
        settings.allow_rendering = False
        db.commit()

    response = client.post(
        f"/projects/{project_id}/sequence-sheet/execute",
        headers={
            "Idempotency-Key": "sequence-execute-disabled-0001",
            "X-Allow-Rendering": "true",
        },
        json=_payload(project_id),
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"]
        == "project_rendering_disabled"
    )
    with session_factory() as db:
        assert _count(db, SequencePlan) == 0
        assert _count(db, SequenceExecutionRun) == 0


def test_execute_requires_caller_idempotency_and_render_confirmation(
    api_context,
) -> None:
    client, _, project_id = api_context

    no_idempotency = client.post(
        f"/projects/{project_id}/sequence-sheet/execute",
        headers={"X-Allow-Rendering": "true"},
        json=_payload(project_id),
    )
    assert no_idempotency.status_code == 422
    assert (
        no_idempotency.json()["detail"]["code"]
        == "idempotency_key_required"
    )

    no_confirmation = client.post(
        f"/projects/{project_id}/sequence-sheet/execute",
        headers={"Idempotency-Key": "sequence-execute-0002"},
        json=_payload(project_id),
    )
    assert no_confirmation.status_code == 409
    assert (
        no_confirmation.json()["detail"]["code"]
        == "rendering_confirmation_required"
    )

    body_controls = {
        **_payload(project_id),
        "idempotency_key": "sequence-execute-body-0003",
        "allow_rendering": True,
    }
    body_control_response = client.post(
        f"/projects/{project_id}/sequence-sheet/execute",
        json=body_controls,
    )
    # Body controls are accepted; execution reaches workflow admission.
    assert body_control_response.status_code == 409
    assert (
        body_control_response.json()["detail"]["code"]
        == "workflow_qualification_required"
    )


def _canonical_and_compiled(payload: dict):
    adapted = adapt_studio_sequence_payload(
        {
            "schema_version": payload["schema_version"],
            "rows": payload["rows"],
        }
    )
    assert adapted.valid is True
    assert adapted.sheet is not None
    return adapted.sheet, compile_ltx_sequence(adapted.sheet)


def _admit_workflow(db: Session) -> None:
    db.add(
        WorkflowTemplate(
            name="ltx_i2v_static",
            version="1.0",
            workflow_api_json={
                "1": {
                    "class_type": "TestLtxSampler",
                    "inputs": {},
                }
            },
            manifest_json={
                "api_format": True,
                "runtime_qualified": True,
            },
            sha256=WORKFLOW_SHA256,
            comfyui_commit="test-commit",
            custom_node_snapshot={},
        )
    )
    db.commit()


def test_persistence_is_transactional_and_idempotent_at_service_boundary(
    api_context,
) -> None:
    _, session_factory, project_id = api_context
    payload = _payload(
        project_id,
        rows=[
            _row(),
            _row(
                row_id="row-002",
                order=2,
                duration_sec=15.0,
                continuity_source="previous_last_frame",
                input_asset_id=None,
            ),
        ],
    )
    sheet, compiled = _canonical_and_compiled(payload)

    with session_factory() as db:
        _admit_workflow(db)
        created = persist_sequence_execution(
            db,
            project_id=project_id,
            source_payload=payload,
            sheet=sheet,
            compiled=compiled,
            idempotency_key="service-idempotency-0001",
            allow_rendering_snapshot=True,
        )
        assert created.idempotent_replay is False
        assert created.row_count == 2
        assert _count(db, SequencePlan) == 1
        assert _count(db, SequencePlanRevision) == 1
        assert _count(db, SequenceRow) == 2
        assert _count(db, SequenceRowDependency) == 1
        assert _count(db, SequenceExecutionRun) == 1
        assert _count(db, SequenceRowExecution) == 2
        assert _count(db, SequenceRowAttempt) == 0
        statuses = set(db.scalars(select(SequenceRowExecution.status)))
        assert statuses == {"ready", "blocked_on_dependency"}

        replay = persist_sequence_execution(
            db,
            project_id=project_id,
            source_payload=payload,
            sheet=sheet,
            compiled=compiled,
            idempotency_key="service-idempotency-0001",
            allow_rendering_snapshot=True,
        )
        assert replay.idempotent_replay is True
        assert replay.run_id == created.run_id
        assert _count(db, SequencePlan) == 1
        assert _count(db, SequenceExecutionRun) == 1

        changed_source = {**payload, "client_note": "different content"}
        with pytest.raises(SequenceIdempotencyConflict):
            persist_sequence_execution(
                db,
                project_id=project_id,
                source_payload=changed_source,
                sheet=sheet,
                compiled=compiled,
                idempotency_key="service-idempotency-0001",
                allow_rendering_snapshot=True,
            )
        assert _count(db, SequencePlan) == 1
        assert _count(db, SequenceExecutionRun) == 1
