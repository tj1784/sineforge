"""Durable, idempotent persistence for admitted LTX Sequence Sheet plans.

This module deliberately stops at the durable scheduling boundary.  It records
the immutable source/canonical/compiled plan and its per-row execution ledger,
but it does not patch or submit a ComfyUI prompt.  Submission is only safe once
the exact API-format workflow has a qualified manifest and a scheduler owns the
row lease.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.base import (
    SequenceExecutionRun,
    SequencePlan,
    SequencePlanRevision,
    SequenceRow,
    SequenceRowDependency,
    SequenceRowExecution,
    WorkflowTemplate,
)
from backend.app.schemas.sequence_sheet import (
    CompiledLtxSequencePlan,
    ContinuitySource,
    SequenceSheet,
)


class SequencePersistenceError(RuntimeError):
    """Base class for a rejected durable Sequence Sheet operation."""


class SequenceIdempotencyConflict(SequencePersistenceError):
    """An idempotency key was reused with different request content."""


class SequenceWorkflowAdmissionError(SequencePersistenceError):
    """A row does not reference an exact, qualified API-format workflow."""


@dataclass(frozen=True, slots=True)
class AdmittedWorkflow:
    template_id: UUID
    name: str
    version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class SequencePersistenceResult:
    plan_id: UUID
    revision_id: UUID
    run_id: UUID
    status: str
    row_count: int
    idempotent_replay: bool


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: Any) -> str:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
    else:
        encoded = _canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_api_prompt(workflow: object) -> bool:
    """Return whether a value has the minimum ComfyUI API-prompt structure."""

    if not isinstance(workflow, dict) or not workflow:
        return False
    return all(
        isinstance(node_id, str)
        and isinstance(node, dict)
        and isinstance(node.get("class_type"), str)
        and bool(node["class_type"].strip())
        and isinstance(node.get("inputs"), dict)
        for node_id, node in workflow.items()
    )


def require_admitted_workflows(
    db: Session,
    sheet: SequenceSheet,
) -> dict[tuple[str, str, str], AdmittedWorkflow]:
    """Resolve every exact static workflow or fail closed.

    Admission is intentionally explicit: a row must pin a SHA-256, the database
    record must match name/version/hash, the stored workflow must be API-format,
    and its manifest must say both ``api_format`` and ``runtime_qualified``.
    Visual workflow JSON and best-effort converters are never accepted here.
    """

    admitted: dict[tuple[str, str, str], AdmittedWorkflow] = {}
    for row in sheet.rows_in_editorial_order():
        if row.workflow_sha256 is None:
            raise SequenceWorkflowAdmissionError(
                f"Row {row.row_id!r} must pin workflow_sha256 before execution."
            )
        key = (
            row.workflow_template_id,
            row.workflow_version,
            row.workflow_sha256,
        )
        if key in admitted:
            continue
        candidates = list(
            db.scalars(
                select(WorkflowTemplate).where(
                    WorkflowTemplate.name == row.workflow_template_id,
                    WorkflowTemplate.version == row.workflow_version,
                    WorkflowTemplate.sha256 == row.workflow_sha256,
                )
            )
        )
        if len(candidates) != 1:
            raise SequenceWorkflowAdmissionError(
                "No unique static workflow matches "
                f"{row.workflow_template_id}@{row.workflow_version} "
                f"with SHA-256 {row.workflow_sha256}."
            )
        template = candidates[0]
        manifest = (
            template.manifest_json
            if isinstance(template.manifest_json, dict)
            else {}
        )
        if not _is_api_prompt(template.workflow_api_json):
            raise SequenceWorkflowAdmissionError(
                f"Workflow {template.name}@{template.version} is not an "
                "API-format ComfyUI prompt."
            )
        actual_sha256 = _sha256(template.workflow_api_json)
        if actual_sha256 != template.sha256:
            raise SequenceWorkflowAdmissionError(
                f"Workflow {template.name}@{template.version} content does not "
                "match its recorded SHA-256."
            )
        if (
            manifest.get("api_format") is not True
            or manifest.get("runtime_qualified") is not True
        ):
            raise SequenceWorkflowAdmissionError(
                f"Workflow {template.name}@{template.version} has not passed "
                "the exact static API workflow qualification gate."
            )
        admitted[key] = AdmittedWorkflow(
            template_id=template.id,
            name=template.name,
            version=template.version,
            sha256=template.sha256,
        )
    return admitted


def _existing_result(
    db: Session,
    *,
    project_id: UUID,
    idempotency_key: str,
    request_sha256: str,
) -> SequencePersistenceResult | None:
    existing = db.scalar(
        select(SequenceExecutionRun).where(
            SequenceExecutionRun.project_id == project_id,
            SequenceExecutionRun.idempotency_key == idempotency_key,
        )
    )
    if existing is None:
        return None
    if existing.request_sha256 != request_sha256:
        raise SequenceIdempotencyConflict(
            "That idempotency key was already used for a different "
            "Sequence Sheet execution request."
        )
    revision = db.get(SequencePlanRevision, existing.sequence_plan_revision_id)
    if revision is None:
        raise SequencePersistenceError(
            "The idempotent execution record references a missing plan revision."
        )
    plan = db.get(SequencePlan, revision.sequence_plan_id)
    if plan is None:
        raise SequencePersistenceError(
            "The idempotent execution record references a missing plan."
        )
    row_count = len(
        list(
            db.scalars(
                select(SequenceRow).where(
                    SequenceRow.sequence_plan_revision_id == revision.id
                )
            )
        )
    )
    return SequencePersistenceResult(
        plan_id=plan.id,
        revision_id=revision.id,
        run_id=existing.id,
        status=existing.status,
        row_count=row_count,
        idempotent_replay=True,
    )


def persist_sequence_execution(
    db: Session,
    *,
    project_id: UUID,
    source_payload: Mapping[str, Any],
    sheet: SequenceSheet,
    compiled: CompiledLtxSequencePlan,
    idempotency_key: str,
    allow_rendering_snapshot: bool,
    created_by: str | None = None,
) -> SequencePersistenceResult:
    """Atomically create the immutable plan and execution ledgers.

    The caller must enforce project permission and profile qualification first.
    This function independently enforces exact workflow admission before it
    writes anything.
    """

    request_sha256 = _sha256(source_payload)
    replay = _existing_result(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        request_sha256=request_sha256,
    )
    if replay is not None:
        return replay

    require_admitted_workflows(db, sheet)
    profile_refs = {row.production_profile_ref for row in sheet.rows}
    if len(profile_refs) != 1:
        raise SequencePersistenceError(
            "One Sequence Sheet execution must use exactly one production profile."
        )
    profile_ref = next(iter(profile_refs))

    canonical_payload = sheet.model_dump(mode="json", exclude_none=True)
    compiled_payload = compiled.model_dump(mode="json", exclude_none=True)
    canonical_sha256 = _sha256(canonical_payload)
    segment_by_row_id = {
        segment.row_id: segment for segment in compiled.segments
    }

    plan = SequencePlan(
        project_id=project_id,
        name=f"Sequence Sheet {canonical_sha256[:12]}",
        status="approved",
    )
    db.add(plan)
    db.flush()

    revision = SequencePlanRevision(
        sequence_plan_id=plan.id,
        revision=1,
        schema_version=sheet.schema_version,
        profile_ref=profile_ref,
        source_kind="studio",
        source_sha256=request_sha256,
        canonical_sha256=canonical_sha256,
        compiled_plan_sha256=compiled.plan_sha256,
        status="approved",
        source_json=dict(source_payload),
        canonical_json=canonical_payload,
        compiled_plan_json=compiled_payload,
        validation_json={
            "valid": True,
            "provider_family": "ltx",
            "workflow_admission": "qualified",
        },
        created_by=created_by,
    )
    db.add(revision)
    db.flush()
    plan.active_revision_id = revision.id

    rows_by_public_id: dict[str, SequenceRow] = {}
    for canonical_row in sheet.rows_in_editorial_order():
        segment = segment_by_row_id[canonical_row.row_id]
        row_payload = canonical_row.model_dump(mode="json", exclude_none=True)
        row_record = SequenceRow(
            sequence_plan_revision_id=revision.id,
            row_id=canonical_row.row_id,
            row_revision=1,
            order_index=canonical_row.order,
            enabled=True,
            workflow_template_key=canonical_row.workflow_template_id,
            workflow_version=canonical_row.workflow_version,
            workflow_sha256=canonical_row.workflow_sha256,
            profile_ref=canonical_row.production_profile_ref,
            generation_mode=canonical_row.generation_mode.value,
            prompt=canonical_row.prompt,
            negative_prompt=canonical_row.negative_prompt,
            requested_duration_sec=canonical_row.duration_sec,
            compiled_frame_count=segment.frame_count,
            compiled_duration_sec=segment.generated_duration_sec,
            fps_numerator=segment.fps_numerator,
            fps_denominator=segment.fps_denominator,
            concrete_seed=segment.seed,
            seed_origin=segment.seed_origin.value,
            continuity_source=canonical_row.continuity_source.value,
            continuity_asset_id=canonical_row.continuity_asset_id,
            continuity_row_id=canonical_row.continuity_row_id,
            character_ids_json=list(canonical_row.character_ids),
            asset_ids_json=list(canonical_row.asset_ids),
            reference_asset_ids_json=list(canonical_row.reference_asset_ids),
            output_basename=canonical_row.output_basename,
            canonical_row_sha256=_sha256(row_payload),
            compiled_segment_json=segment.model_dump(
                mode="json",
                exclude_none=True,
            ),
        )
        db.add(row_record)
        rows_by_public_id[canonical_row.row_id] = row_record
    db.flush()

    dependency_successors: set[str] = set()
    for canonical_row in sheet.rows_in_editorial_order():
        segment = segment_by_row_id[canonical_row.row_id]
        continuity_dependency: str | None = None
        if canonical_row.continuity_source in {
            ContinuitySource.PREVIOUS_LAST_FRAME,
            ContinuitySource.ROW_LAST_FRAME,
        }:
            continuity_dependency = segment.continuity.row_id
        for predecessor_public_id in segment.dependency_row_ids:
            is_continuity = predecessor_public_id == continuity_dependency
            db.add(
                SequenceRowDependency(
                    sequence_plan_revision_id=revision.id,
                    predecessor_row_id=rows_by_public_id[
                        predecessor_public_id
                    ].id,
                    successor_row_id=rows_by_public_id[canonical_row.row_id].id,
                    dependency_kind=(
                        "last_frame_continuity"
                        if is_continuity
                        else "explicit"
                    ),
                    required_artifact_kind=(
                        "last_frame_image" if is_continuity else None
                    ),
                )
            )
            dependency_successors.add(canonical_row.row_id)

    execution = SequenceExecutionRun(
        project_id=project_id,
        sequence_plan_revision_id=revision.id,
        idempotency_key=idempotency_key,
        request_sha256=request_sha256,
        profile_ref=profile_ref,
        status="pending",
        allow_rendering_snapshot=allow_rendering_snapshot,
    )
    db.add(execution)
    db.flush()

    for canonical_row in sheet.rows_in_editorial_order():
        db.add(
            SequenceRowExecution(
                sequence_execution_run_id=execution.id,
                sequence_row_id=rows_by_public_id[canonical_row.row_id].id,
                status=(
                    "blocked_on_dependency"
                    if canonical_row.row_id in dependency_successors
                    else "ready"
                ),
                current_attempt=0,
                idempotency_key=(
                    f"seqrow-{execution.id.hex[:20]}-"
                    f"{_sha256(canonical_row.row_id)[:20]}"
                ),
            )
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = _existing_result(
            db,
            project_id=project_id,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
        )
        if replay is not None:
            return replay
        raise

    return SequencePersistenceResult(
        plan_id=plan.id,
        revision_id=revision.id,
        run_id=execution.id,
        status=execution.status,
        row_count=len(sheet.rows),
        idempotent_replay=False,
    )
