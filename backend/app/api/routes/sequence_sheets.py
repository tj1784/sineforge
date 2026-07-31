"""Project-scoped LTX Sequence Sheet validation and execution admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import Project, ProjectStoryboardSettings
from backend.app.db.session import get_db
from backend.app.schemas.sequence_sheet import (
    CompiledLtxSequencePlan,
    SequenceSheet,
)
from backend.app.schemas.project_workflows import (
    is_cineforge_studio_workflow_lane,
)
from backend.app.services.production_profiles import (
    ProductionProfileOnHold,
    ProductionProfileQualificationRequired,
    resolve_production_profile,
)
from backend.app.services.sequence_sheets import (
    LtxSequenceCompilationError,
    adapt_studio_sequence_payload,
    compile_ltx_sequence,
)
from backend.app.services.sequence_sheets.persistence import (
    SequenceIdempotencyConflict,
    SequencePersistenceError,
    SequenceWorkflowAdmissionError,
    persist_sequence_execution,
    require_admitted_workflows,
)


router = APIRouter(prefix="/projects", tags=["sequence-sheets"])

_SEQUENCE_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "project_id",
        "model_family",
        "rows",
        # Execute controls may be supplied in the body by older clients or as
        # headers by clients that keep the canonical sheet body unchanged.
        "idempotency_key",
        "allow_rendering",
    }
)


@dataclass(frozen=True, slots=True)
class _PreparedSequence:
    source_payload: dict[str, Any]
    sheet: SequenceSheet
    compiled: CompiledLtxSequencePlan
    issues: tuple[dict[str, Any], ...]
    raw_row_count: int


def _http_error(
    status_code: int,
    code: str,
    message: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _require_project(db: Session, project_id: UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "project_not_found",
            "Project not found.",
        )
    return project


def _require_generic_sequence_lane(project: Project) -> None:
    if is_cineforge_studio_workflow_lane(project.workflow_lane):
        return
    required_endpoint = (
        f"/projects/{project.id}/agentless-workflow/dry-run"
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "workflow_lane_mismatch",
            "message": (
                "Agentless projects cannot use the generic Sequence Sheet "
                f"routes. Use {required_endpoint}."
            ),
            "actual_workflow_lane": project.workflow_lane,
            "required_endpoint": required_endpoint,
        },
    )


def _sequence_source_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"idempotency_key", "allow_rendering"}
    }


def _validate_envelope(
    *,
    project_id: UUID,
    payload: object,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_sequence_sheet_request",
            "Sequence Sheet request body must be an object.",
        )
    unknown = sorted(set(payload) - _SEQUENCE_TOP_LEVEL_FIELDS)
    if unknown:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_sequence_sheet_fields",
            f"Unknown Sequence Sheet request fields: {', '.join(unknown)}.",
        )
    request_project_id = payload.get("project_id")
    if not isinstance(request_project_id, str):
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_project_id",
            "The request project_id must be a UUID string.",
        )
    try:
        parsed_project_id = UUID(request_project_id)
    except ValueError as exc:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_project_id",
            "The request project_id must be a valid UUID string.",
        ) from exc
    if parsed_project_id != project_id:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "project_id_mismatch",
            "The request project_id does not match the project in the URL.",
        )

    model_family = payload.get("model_family")
    if model_family == "wan":
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "wan_on_hold",
            "WAN execution is on hold after the unsuccessful local dry run; "
            "Sequence Sheet v1 accepts only LTX.",
        )
    if model_family != "ltx":
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_model_family",
            "model_family must be 'ltx'.",
        )
    return _sequence_source_payload(payload)


def _invalid_dry_run_response(
    *,
    project_id: UUID,
    issues: list[dict[str, Any]],
    raw_row_count: int,
) -> dict[str, Any]:
    return {
        "ok": False,
        "valid": False,
        "status": "invalid",
        "schema_version": "sineforge.sequence-sheet/v1",
        "project_id": str(project_id),
        "model_family": "ltx",
        "summary": {
            "row_count": raw_row_count,
            "enabled_row_count": 0,
            "total_duration_sec": 0.0,
        },
        "issues": issues,
        "diagnostics": issues,
        "validation": {
            "valid": False,
            "issues": issues,
            "errors": [
                issue
                for issue in issues
                if issue.get("severity") == "error"
            ],
            "warnings": [
                issue
                for issue in issues
                if issue.get("severity") == "warning"
            ],
        },
        "compiled": None,
        "ready_to_execute": False,
        "qualification": {
            "qualified": False,
            "blockers": [],
        },
    }


def _prepare_sequence(
    *,
    project_id: UUID,
    source_payload: dict[str, Any],
) -> _PreparedSequence | dict[str, Any]:
    raw_rows = source_payload.get("rows")
    raw_row_count = len(raw_rows) if isinstance(raw_rows, list) else 0
    adapted = adapt_studio_sequence_payload(
        {
            "schema_version": source_payload.get("schema_version"),
            "rows": raw_rows,
        }
    )
    issues = [
        diagnostic.model_dump(mode="json", exclude_none=True)
        for diagnostic in adapted.diagnostics
    ]
    if not adapted.valid or adapted.sheet is None:
        return _invalid_dry_run_response(
            project_id=project_id,
            issues=issues,
            raw_row_count=raw_row_count,
        )
    try:
        compiled = compile_ltx_sequence(adapted.sheet)
    except LtxSequenceCompilationError as exc:
        issues.append(
            {
                "severity": "error",
                "code": "ltx_compilation_failed",
                "message": str(exc),
            }
        )
        return _invalid_dry_run_response(
            project_id=project_id,
            issues=issues,
            raw_row_count=raw_row_count,
        )
    return _PreparedSequence(
        source_payload=source_payload,
        sheet=adapted.sheet,
        compiled=compiled,
        issues=tuple(issues),
        raw_row_count=raw_row_count,
    )


def _qualification_status(
    db: Session,
    prepared: _PreparedSequence,
) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    profiles = {
        row.production_profile_ref: resolve_production_profile(
            row.production_profile_ref
        )
        for row in prepared.sheet.rows
    }
    for profile in profiles.values():
        if not profile.execution_qualified:
            blockers.append(
                {
                    "code": (
                        "profile_on_hold"
                        if profile.status == "on_hold"
                        else "profile_qualification_required"
                    ),
                    "profile_ref": profile.ref,
                    "message": (
                        f"Production profile {profile.ref} is {profile.status} "
                        "and cannot execute until its runtime gate passes."
                    ),
                }
            )
    try:
        require_admitted_workflows(db, prepared.sheet)
    except SequenceWorkflowAdmissionError as exc:
        blockers.append(
            {
                "code": "workflow_qualification_required",
                "message": str(exc),
            }
        )
    return {
        "qualified": not blockers,
        "blockers": blockers,
    }


def _dry_run_response(
    *,
    project_id: UUID,
    prepared: _PreparedSequence,
    qualification: dict[str, Any],
) -> dict[str, Any]:
    segments = prepared.compiled.segments
    issues = list(prepared.issues)
    existing_issue_codes = {
        issue.get("code") for issue in issues
    }
    for blocker in qualification["blockers"]:
        # The canonical validator already emits the profile authoring warning.
        # Avoid duplicating it while still exposing the complete blocker object.
        if (
            blocker["code"] == "profile_qualification_required"
            and "ltx_profile_requires_qualification" in existing_issue_codes
        ):
            continue
        issues.append(
            {
                "severity": "warning",
                "code": blocker["code"],
                "message": blocker["message"],
                **(
                    {"profile_ref": blocker["profile_ref"]}
                    if "profile_ref" in blocker
                    else {}
                ),
            }
        )
    enabled_row_count = len(prepared.sheet.rows)
    total_duration = sum(
        segment.requested_duration_sec for segment in segments
    )
    total_generated_duration = sum(
        segment.generated_duration_sec for segment in segments
    )
    is_qualified = bool(qualification["qualified"])
    return {
        "ok": True,
        "valid": True,
        "status": "ready" if is_qualified else "valid_with_blockers",
        "schema_version": prepared.sheet.schema_version,
        "project_id": str(project_id),
        "model_family": "ltx",
        "summary": {
            "row_count": prepared.raw_row_count,
            "enabled_row_count": enabled_row_count,
            "total_duration_sec": total_duration,
            "compiled_duration_sec": total_generated_duration,
            "frame_count": sum(segment.frame_count for segment in segments),
        },
        "issues": issues,
        "diagnostics": issues,
        "validation": {
            "valid": True,
            "issues": issues,
            "errors": [],
            "warnings": [
                issue
                for issue in issues
                if issue.get("severity") == "warning"
            ],
        },
        "compiled": prepared.compiled.model_dump(
            mode="json",
            exclude_none=True,
        ),
        "ready_to_execute": is_qualified,
        "qualification": qualification,
    }


def _resolve_idempotency_key(
    payload: Mapping[str, Any],
    header_value: str | None,
) -> str:
    body_value = payload.get("idempotency_key")
    if body_value is not None and not isinstance(body_value, str):
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_idempotency_key",
            "idempotency_key must be a string.",
        )
    if (
        isinstance(body_value, str)
        and header_value is not None
        and body_value.strip() != header_value.strip()
    ):
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "idempotency_key_mismatch",
            "Body and Idempotency-Key header values do not match.",
        )
    value = (header_value or body_value or "").strip()
    if not 8 <= len(value) <= 128:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "idempotency_key_required",
            "Provide an Idempotency-Key header or body idempotency_key "
            "containing 8 through 128 characters.",
        )
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_idempotency_key",
            "idempotency_key must contain only visible ASCII characters.",
        )
    return value


def _parse_confirmation(
    payload: Mapping[str, Any],
    header_value: str | None,
) -> bool:
    body_value = payload.get("allow_rendering")
    if body_value is not None and not isinstance(body_value, bool):
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_rendering_confirmation",
            "allow_rendering must be a boolean.",
        )
    header_bool: bool | None = None
    if header_value is not None:
        normalized = header_value.strip().casefold()
        if normalized not in {"true", "false"}:
            raise _http_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_rendering_confirmation",
                "X-Allow-Rendering must be 'true' or 'false'.",
            )
        header_bool = normalized == "true"
    if (
        body_value is not None
        and header_bool is not None
        and body_value is not header_bool
    ):
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "rendering_confirmation_mismatch",
            "Body and X-Allow-Rendering header values do not match.",
        )
    confirmed = (
        header_bool
        if header_bool is not None
        else body_value
        if isinstance(body_value, bool)
        else False
    )
    if not confirmed:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "rendering_confirmation_required",
            "Execution requires explicit allow_rendering=true confirmation.",
        )
    return True


@router.post("/{project_id}/sequence-sheet/dry-run")
def dry_run_sequence_sheet(
    project_id: UUID,
    payload: object = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Compile and inspect an LTX sheet without mutating or queueing work."""

    project = _require_project(db, project_id)
    _require_generic_sequence_lane(project)
    source_payload = _validate_envelope(
        project_id=project_id,
        payload=payload,
    )
    prepared = _prepare_sequence(
        project_id=project_id,
        source_payload=source_payload,
    )
    if isinstance(prepared, dict):
        return prepared
    qualification = _qualification_status(db, prepared)
    return _dry_run_response(
        project_id=project_id,
        prepared=prepared,
        qualification=qualification,
    )


@router.post("/{project_id}/sequence-sheet/execute")
def execute_sequence_sheet(
    project_id: UUID,
    payload: object = Body(...),
    idempotency_key_header: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    allow_rendering_header: str | None = Header(
        default=None,
        alias="X-Allow-Rendering",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist a qualified execution ledger without submitting ComfyUI."""

    project = _require_project(db, project_id)
    _require_generic_sequence_lane(project)
    if not isinstance(payload, dict):
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_sequence_sheet_request",
            "Sequence Sheet request body must be an object.",
        )
    idempotency_key = _resolve_idempotency_key(
        payload,
        idempotency_key_header,
    )
    allow_rendering_snapshot = _parse_confirmation(
        payload,
        allow_rendering_header,
    )
    source_payload = _validate_envelope(
        project_id=project_id,
        payload=payload,
    )
    prepared = _prepare_sequence(
        project_id=project_id,
        source_payload=source_payload,
    )
    if isinstance(prepared, dict):
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_sequence_sheet",
            "Sequence Sheet validation failed; run dry-run and resolve its "
            "reported issues before execution.",
        )

    settings = db.scalar(
        select(ProjectStoryboardSettings).where(
            ProjectStoryboardSettings.project_id == project_id
        )
    )
    if settings is None or not bool(settings.allow_rendering):
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "project_rendering_disabled",
            "This project's persisted settings do not allow rendering.",
        )

    profiles = {
        row.production_profile_ref: resolve_production_profile(
            row.production_profile_ref
        )
        for row in prepared.sheet.rows
    }
    for profile in profiles.values():
        try:
            profile.require_execution_qualified()
        except ProductionProfileOnHold as exc:
            raise _http_error(
                status.HTTP_409_CONFLICT,
                "profile_on_hold",
                str(exc),
            ) from exc
        except ProductionProfileQualificationRequired as exc:
            raise _http_error(
                status.HTTP_409_CONFLICT,
                "profile_qualification_required",
                str(exc),
            ) from exc

    try:
        # Explicitly check before entering the persistence boundary so the API
        # emits a stable conflict rather than ever attempting best-effort patching.
        require_admitted_workflows(db, prepared.sheet)
        persisted = persist_sequence_execution(
            db,
            project_id=project_id,
            source_payload=prepared.source_payload,
            sheet=prepared.sheet,
            compiled=prepared.compiled,
            idempotency_key=idempotency_key,
            allow_rendering_snapshot=allow_rendering_snapshot,
        )
    except SequenceWorkflowAdmissionError as exc:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "workflow_qualification_required",
            str(exc),
        ) from exc
    except SequenceIdempotencyConflict as exc:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "idempotency_conflict",
            str(exc),
        ) from exc
    except SequencePersistenceError as exc:
        db.rollback()
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "sequence_persistence_conflict",
            str(exc),
        ) from exc

    return {
        "ok": True,
        "valid": True,
        "status": persisted.status,
        "schema_version": prepared.sheet.schema_version,
        "project_id": str(project_id),
        "model_family": "ltx",
        "run_id": str(persisted.run_id),
        "plan_id": str(persisted.plan_id),
        "revision_id": str(persisted.revision_id),
        "job_id": None,
        "idempotent_replay": persisted.idempotent_replay,
        "summary": {
            "row_count": persisted.row_count,
            "enabled_row_count": persisted.row_count,
            "total_duration_sec": sum(
                row.duration_sec for row in prepared.sheet.rows
            ),
        },
        "issues": [],
        "ready_to_execute": True,
        "submission": {
            "queued": False,
            "reason": (
                "Durable row ledgers are ready for the dependency-aware "
                "scheduler; this API boundary does not submit ComfyUI directly."
            ),
        },
    }
