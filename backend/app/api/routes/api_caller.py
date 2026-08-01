"""Compatibility CRUD surface for the retired external API Caller.

The operator library remains readable so older saved workflows are not lost.
Execution, analysis, job, runtime, and import routes fail closed and direct
clients to the Sineforge-native Runner.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.config import get_settings
from backend.app.schemas.api_caller import (
    ApiCallerAnalyzeRequest,
    ApiCallerRemoveResponse,
    ApiCallerRunRequest,
    ApiCallerRunnerImportRequest,
    ApiCallerRunnerImportResponse,
    ApiCallerWorkflowCreate,
    ApiCallerWorkflowDetail,
    ApiCallerWorkflowSummary,
    ApiCallerWorkflowUpdate,
)
from backend.app.services.api_workflows import (
    ApiWorkflowError,
    ApiWorkflowLibrary,
    ApiWorkflowNotFound,
)


router = APIRouter(prefix="/api-caller", tags=["api-caller-compatibility"])


def get_api_workflow_library() -> ApiWorkflowLibrary:
    return ApiWorkflowLibrary(get_settings().storage_root)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ApiWorkflowNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ApiWorkflowError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


def _legacy_runner_removed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "The external ComfyAPI Runner was removed from the unified app. "
            "Use /native-api-runner and the Sineforge Engine workspace."
        ),
    )


@router.get("/workflows", response_model=list[ApiCallerWorkflowSummary])
def list_workflows(
    library: ApiWorkflowLibrary = Depends(get_api_workflow_library),
) -> list[ApiCallerWorkflowSummary]:
    try:
        return [ApiCallerWorkflowSummary.model_validate(item) for item in library.list()]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workflows/{workflow_id}", response_model=ApiCallerWorkflowDetail)
def get_workflow(
    workflow_id: UUID,
    library: ApiWorkflowLibrary = Depends(get_api_workflow_library),
) -> ApiCallerWorkflowDetail:
    try:
        return ApiCallerWorkflowDetail.model_validate(library.get(workflow_id))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post(
    "/workflows",
    response_model=ApiCallerWorkflowDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow(
    payload: ApiCallerWorkflowCreate,
    library: ApiWorkflowLibrary = Depends(get_api_workflow_library),
) -> ApiCallerWorkflowDetail:
    try:
        return ApiCallerWorkflowDetail.model_validate(
            library.create(
                name=payload.name,
                version=payload.version,
                description=payload.description,
                source_filename=payload.source_filename,
                source_kind="operator_import",
                workflow=payload.workflow,
            )
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/workflows/{workflow_id}", response_model=ApiCallerWorkflowDetail)
def update_workflow(
    workflow_id: UUID,
    payload: ApiCallerWorkflowUpdate,
    library: ApiWorkflowLibrary = Depends(get_api_workflow_library),
) -> ApiCallerWorkflowDetail:
    try:
        fields = payload.model_fields_set
        return ApiCallerWorkflowDetail.model_validate(
            library.update(
                workflow_id,
                name=payload.name if "name" in fields else None,
                version=payload.version if "version" in fields else None,
                description=payload.description if "description" in fields else None,
                workflow=payload.workflow if "workflow" in fields else None,
            )
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.delete("/workflows/{workflow_id}", response_model=ApiCallerRemoveResponse)
def remove_workflow(
    workflow_id: UUID,
    library: ApiWorkflowLibrary = Depends(get_api_workflow_library),
) -> ApiCallerRemoveResponse:
    try:
        return ApiCallerRemoveResponse.model_validate(library.remove(workflow_id))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/analyze")
async def analyze_workflow(payload: ApiCallerAnalyzeRequest) -> dict[str, Any]:
    del payload
    raise _legacy_runner_removed()


@router.post("/run")
async def run_workflow(payload: ApiCallerRunRequest) -> dict[str, Any]:
    del payload
    raise _legacy_runner_removed()


@router.get("/jobs/{job_id}")
async def get_runner_job(job_id: str) -> dict[str, Any]:
    del job_id
    raise _legacy_runner_removed()


@router.get("/runtime")
async def get_runtime() -> dict[str, Any]:
    raise _legacy_runner_removed()


@router.post("/import-runner", response_model=ApiCallerRunnerImportResponse)
async def import_runner_workflows(
    payload: ApiCallerRunnerImportRequest,
    library: ApiWorkflowLibrary = Depends(get_api_workflow_library),
) -> ApiCallerRunnerImportResponse:
    del payload, library
    raise _legacy_runner_removed()
