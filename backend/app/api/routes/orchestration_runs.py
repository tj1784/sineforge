"""HTTP routes for Storyboard Phase 1 orchestration runs.

Mount this router from the application factory when wiring is authorized.
This module does not register itself and does not touch render/media systems.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.orchestration import (
    CancelOrchestrationRunRequest,
    CreateOrchestrationRunRequest,
    CreateOrchestrationRunResponse,
    ManualTaskRoute,
    OrchestrationEventRead,
    OrchestrationRunDetailRead,
    OrchestrationRunRead,
    OrchestrationStepRead,
    ProposalSummaryRead,
    ProviderInvocationRead,
    PlanningTaskType,
    RoutingMode,
    RunActionResponse,
)
from backend.app.services.planning.engine import PlanningEngine
from backend.app.services.planning.errors import PlanningError, PlanningErrorCode
from backend.app.services.planning.executor import (
    ExecutionCapacityError,
    ExecutionSubmissionError,
    planning_execution_controller,
)


router = APIRouter(prefix="/orchestration", tags=["orchestration"])
TERMINAL_RETRY_STATUSES = {"completed", "failed", "canceled"}


class RetryOrchestrationRunRequest(BaseModel):
    """Audit input for creating a new immutable retry run."""

    model_config = ConfigDict(extra="forbid")

    requested_by: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


def _http_error(error: PlanningError) -> HTTPException:
    code_map = {
        PlanningErrorCode.STORY_NOT_FOUND: status.HTTP_404_NOT_FOUND,
        PlanningErrorCode.RUN_NOT_FOUND: status.HTTP_404_NOT_FOUND,
        PlanningErrorCode.ACTIVE_RUN_EXISTS: status.HTTP_409_CONFLICT,
        PlanningErrorCode.ALREADY_TERMINAL: status.HTTP_409_CONFLICT,
        PlanningErrorCode.INVALID_TRANSITION: status.HTTP_409_CONFLICT,
        PlanningErrorCode.IDEMPOTENCY_CONFLICT: status.HTTP_409_CONFLICT,
        PlanningErrorCode.BUDGET_EXHAUSTED: status.HTTP_409_CONFLICT,
        PlanningErrorCode.TIME_BUDGET_EXCEEDED: status.HTTP_409_CONFLICT,
        PlanningErrorCode.CANCELED: status.HTTP_409_CONFLICT,
        PlanningErrorCode.VALIDATION_FAILED: status.HTTP_422_UNPROCESSABLE_ENTITY,
        PlanningErrorCode.CONTRACT_VIOLATION: status.HTTP_422_UNPROCESSABLE_ENTITY,
        PlanningErrorCode.ROUTING_FAILED: status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
    status_code = code_map.get(error.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(
        status_code=status_code,
        detail={
            "code": error.code.value,
            "category": error.category.value,
            "message": error.message,
            "retryable": error.retryable,
            "details": error.details,
        },
    )


def _engine(db: Session) -> PlanningEngine:
    return PlanningEngine(db)


def _run_read(run) -> OrchestrationRunRead:
    return OrchestrationRunRead.model_validate(run)


@router.post(
    "/runs",
    response_model=CreateOrchestrationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_orchestration_run(
    payload: CreateOrchestrationRunRequest,
    db: Session = Depends(get_db),
) -> CreateOrchestrationRunResponse:
    engine = _engine(db)
    try:
        run, created = engine.create_run(payload)
    except PlanningError as error:
        raise _http_error(error) from error
    return CreateOrchestrationRunResponse(
        run=_run_read(run),
        created=created,
        idempotent_replay=not created,
    )


@router.get("/runs/{run_id}", response_model=OrchestrationRunDetailRead)
def get_orchestration_run(run_id: UUID, db: Session = Depends(get_db)) -> OrchestrationRunDetailRead:
    engine = _engine(db)
    try:
        detail = engine.get_run_detail(run_id)
    except PlanningError as error:
        raise _http_error(error) from error

    run = detail["run"]
    base = OrchestrationRunRead.model_validate(run)
    return OrchestrationRunDetailRead(
        **base.model_dump(),
        steps=[OrchestrationStepRead.model_validate(s) for s in detail["steps"]],
        events=[OrchestrationEventRead.model_validate(e) for e in detail["events"]],
        invocations=[ProviderInvocationRead.model_validate(i) for i in detail["invocations"]],
        proposals=[ProposalSummaryRead.model_validate(p) for p in detail["proposals"]],
    )


@router.get("/stories/{story_id}/runs", response_model=list[OrchestrationRunRead])
def list_story_runs(story_id: UUID, db: Session = Depends(get_db)) -> list[OrchestrationRunRead]:
    engine = _engine(db)
    runs = engine.list_runs_for_story(story_id)
    return [_run_read(run) for run in runs]


@router.post(
    "/runs/{run_id}/start",
    response_model=RunActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_orchestration_run(run_id: UUID, db: Session = Depends(get_db)) -> RunActionResponse:
    engine = _engine(db)
    owner_id = planning_execution_controller.owner_id
    claim_token = planning_execution_controller.new_claim_token()
    try:
        run, newly_started = engine.claim_run(
            run_id,
            owner_id=owner_id,
            claim_token=claim_token,
        )
    except PlanningError as error:
        raise _http_error(error) from error

    if run.execution_claim_token != claim_token:
        return RunActionResponse(
            run=_run_read(run),
            message="Planning execution is already active; poll this run for persisted progress",
        )

    try:
        submission = planning_execution_controller.submit(
            run.id,
            bind=db.get_bind(),
            engine_factory=_engine,
            resumed=not newly_started,
            owner_id=owner_id,
            claim_token=claim_token,
        )
    except ExecutionCapacityError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "planning_capacity_full",
                "message": str(error),
                "retryable": True,
            },
        ) from error
    except ExecutionSubmissionError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "planning_submission_failed",
                "message": str(error),
                "retryable": True,
            },
        ) from error

    message = (
        "Planning execution is already active; poll this run for persisted progress"
        if submission.already_active
        else (
            "Planning recovery accepted; execution will resume from persisted checkpoints"
            if not newly_started
            else "Planning accepted; poll this run for persisted progress"
        )
    )
    return RunActionResponse(run=_run_read(run), message=message)


@router.post(
    "/runs/{run_id}/retry",
    response_model=CreateOrchestrationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def retry_orchestration_run(
    run_id: UUID,
    payload: RetryOrchestrationRunRequest | None = None,
    db: Session = Depends(get_db),
) -> CreateOrchestrationRunResponse:
    """Create an audited pending iteration without rewriting prior history."""

    engine = _engine(db)
    try:
        prior = engine.get_run(run_id)
        if prior.status not in TERMINAL_RETRY_STATUSES:
            raise PlanningError(
                PlanningErrorCode.INVALID_TRANSITION,
                "Only terminal planning runs can be retried",
                details={"run_id": str(prior.id), "status": prior.status},
            )

        prior_snapshot = dict(prior.routing_snapshot_json or {})
        retry_attempt = int(prior_snapshot.get("retry_attempt") or 0) + 1

        raw_tasks = list(prior_snapshot.get("task_types") or [])
        if not raw_tasks:
            raw_tasks = [
                step.task_type
                for step in engine.repo.get_steps(prior.id)
                if step.attempt_number == 1
            ]
        task_types = [PlanningTaskType(item) for item in raw_tasks]

        manual_routes: list[ManualTaskRoute] = []
        for task_name, raw_route in dict(prior_snapshot.get("manual_routes") or {}).items():
            route = dict(raw_route or {})
            manual_routes.append(
                ManualTaskRoute(
                    task_type=PlanningTaskType(task_name),
                    provider_identifier=str(route.get("provider_identifier") or ""),
                    logical_model=route.get("logical_model"),
                    resolved_model=route.get("resolved_model"),
                    rationale=route.get("rationale"),
                )
            )

        body = payload or RetryOrchestrationRunRequest()
        idempotency_seed = body.idempotency_key or f"attempt-{retry_attempt}"
        retry_idempotency_key = "retry-" + hashlib.sha256(
            f"{prior.id}|{idempotency_seed}".encode("utf-8")
        ).hexdigest()
        requested_mode = (
            prior_snapshot.get("requested_mode")
            or prior_snapshot.get("mode")
            or RoutingMode.automatic.value
        )
        retry_request = CreateOrchestrationRunRequest(
            story_id=prior.story_id,
            base_storyboard_version_id=prior.base_storyboard_version_id,
            requested_by=body.requested_by or prior.requested_by,
            routing_mode=RoutingMode(requested_mode),
            manual_routes=manual_routes,
            prefer_local_providers=bool(prior_snapshot.get("prefer_local_providers", True)),
            prefer_hosted_providers=bool(prior_snapshot.get("prefer_hosted_providers", False)),
            max_steps=prior.max_steps,
            repair_budget=prior.repair_budget,
            time_budget_sec=int(prior_snapshot.get("time_budget_sec") or 300),
            transport_retry_limit=int(prior_snapshot.get("transport_retry_limit") or 2),
            idempotency_key=retry_idempotency_key,
            task_types=task_types,
        )
        retry, created = engine.create_run(retry_request)

        expected_parent = str(prior.id)
        retry_snapshot = dict(retry.routing_snapshot_json or {})
        if not created and retry_snapshot.get("retry_of_run_id") != expected_parent:
            raise PlanningError(
                PlanningErrorCode.IDEMPOTENCY_CONFLICT,
                "Retry idempotency key resolved to a run with different lineage",
            )
        if created:
            retry_snapshot.update(
                {
                    "retry_of_run_id": expected_parent,
                    "retry_root_run_id": str(
                        prior_snapshot.get("retry_root_run_id") or prior.id
                    ),
                    "retry_attempt": retry_attempt,
                }
            )
            retry.routing_snapshot_json = retry_snapshot
            engine.repo.db.add(retry)
            engine.repo.add_event(
                run_id=retry.id,
                event_type="run_retry_created",
                actor_type="user" if body.requested_by else "system",
                actor_reference=body.requested_by,
                details={
                    "retry_of_run_id": expected_parent,
                    "retry_attempt": retry_attempt,
                },
            )
            engine.repo.commit()
    except (ValueError, TypeError) as error:
        raise _http_error(
            PlanningError(
                PlanningErrorCode.VALIDATION_FAILED,
                f"Prior run cannot be retried safely: {error}",
            )
        ) from error
    except PlanningError as error:
        raise _http_error(error) from error

    return CreateOrchestrationRunResponse(
        run=_run_read(retry),
        created=created,
        idempotent_replay=not created,
    )


@router.post("/runs/{run_id}/cancel", response_model=RunActionResponse)
def cancel_orchestration_run(
    run_id: UUID,
    payload: CancelOrchestrationRunRequest | None = None,
    db: Session = Depends(get_db),
) -> RunActionResponse:
    engine = _engine(db)
    body = payload or CancelOrchestrationRunRequest()
    try:
        run = engine.cancel_run(
            run_id,
            reason=body.reason,
            requested_by=body.requested_by,
        )
    except PlanningError as error:
        raise _http_error(error) from error
    return RunActionResponse(run=_run_read(run), message="Run canceled")


@router.get("/runs/{run_id}/events", response_model=list[OrchestrationEventRead])
def list_run_events(run_id: UUID, db: Session = Depends(get_db)) -> list[OrchestrationEventRead]:
    engine = _engine(db)
    try:
        detail = engine.get_run_detail(run_id)
    except PlanningError as error:
        raise _http_error(error) from error
    return [OrchestrationEventRead.model_validate(e) for e in detail["events"]]


@router.get("/runs/{run_id}/steps", response_model=list[OrchestrationStepRead])
def list_run_steps(run_id: UUID, db: Session = Depends(get_db)) -> list[OrchestrationStepRead]:
    engine = _engine(db)
    try:
        detail = engine.get_run_detail(run_id)
    except PlanningError as error:
        raise _http_error(error) from error
    return [OrchestrationStepRead.model_validate(s) for s in detail["steps"]]


@router.get("/runs/{run_id}/invocations", response_model=list[ProviderInvocationRead])
def list_run_invocations(
    run_id: UUID, db: Session = Depends(get_db)
) -> list[ProviderInvocationRead]:
    engine = _engine(db)
    try:
        detail = engine.get_run_detail(run_id)
    except PlanningError as error:
        raise _http_error(error) from error
    return [ProviderInvocationRead.model_validate(i) for i in detail["invocations"]]
