"""SineForge operator API Caller.

All submission is explicit. Merely listing, selecting, importing, or analyzing
a workflow never queues work in ComfyUI.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
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
    normalize_api_workflow,
)
from backend.app.services.comfy.runner import ComfyAPIRunnerClient


router = APIRouter(prefix="/api-caller", tags=["api-caller"])


def get_api_workflow_library() -> ApiWorkflowLibrary:
    return ApiWorkflowLibrary(get_settings().storage_root)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ApiWorkflowNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ApiWorkflowError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        detail: Any
        try:
            detail = exc.response.json()
        except ValueError:
            detail = exc.response.text
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "ComfyAPI Runner rejected the request.", "runner": detail},
        )
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ComfyAPI Runner is unavailable: {exc}",
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


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
    workflow = normalize_api_workflow(payload.workflow)
    settings = get_settings()
    try:
        async with ComfyAPIRunnerClient(
            str(settings.comfy_api_runner_base_url),
            timeout=30.0,
        ) as client:
            return await client.analyze_workflow(workflow)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/run")
async def run_workflow(payload: ApiCallerRunRequest) -> dict[str, Any]:
    """Explicit operator mutation: submit the supplied working copy."""

    workflow = normalize_api_workflow(payload.workflow)
    settings = get_settings()
    try:
        async with ComfyAPIRunnerClient(
            str(settings.comfy_api_runner_base_url),
            timeout=30.0,
            allow_mutation=True,
        ) as client:
            return await client.run_workflow(
                workflow,
                comfy_url=str(settings.comfyui_base_url),
                workflow_name=payload.workflow_name,
                queue_count=payload.queue_count,
                merge_movie=payload.merge_movie,
                vary_seed=payload.vary_seed,
                save_latents=payload.save_latents,
            )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/jobs/{job_id}")
async def get_runner_job(job_id: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        async with ComfyAPIRunnerClient(
            str(settings.comfy_api_runner_base_url),
            timeout=15.0,
        ) as client:
            return await client.get_job(job_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/runtime")
async def get_runtime() -> dict[str, Any]:
    settings = get_settings()
    comfy_url = str(settings.comfyui_base_url)
    runner_url = str(settings.comfy_api_runner_base_url)
    async with ComfyAPIRunnerClient(runner_url, timeout=5.0) as client:
        health = await client.health(comfy_url)
    return {
        "ok": bool(health.get("reachable")),
        "comfy_url": comfy_url,
        "runner_url": runner_url,
        "runner": health,
    }


@router.post("/import-runner", response_model=ApiCallerRunnerImportResponse)
async def import_runner_workflows(
    payload: ApiCallerRunnerImportRequest,
    library: ApiWorkflowLibrary = Depends(get_api_workflow_library),
) -> ApiCallerRunnerImportResponse:
    settings = get_settings()
    requested = set(payload.workflow_ids or [])
    imported = 0
    updated = 0
    skipped = 0
    results: list[ApiCallerWorkflowSummary] = []
    try:
        async with ComfyAPIRunnerClient(
            str(settings.comfy_api_runner_base_url),
            timeout=30.0,
        ) as client:
            index = await client.list_static_workflows()
            presets = index.get("workflows") if isinstance(index, dict) else None
            for preset in presets if isinstance(presets, list) else []:
                if not isinstance(preset, dict):
                    skipped += 1
                    continue
                source_id = str(preset.get("id") or "")
                if requested and source_id not in requested:
                    continue
                if preset.get("format") != "api" or not preset.get("queueable"):
                    skipped += 1
                    continue
                detail = await client.get_static_workflow(source_id)
                workflow = detail.get("workflow") if isinstance(detail, dict) else None
                detail_preset = detail.get("preset") if isinstance(detail, dict) else None
                metadata = detail_preset if isinstance(detail_preset, dict) else preset
                stored, created = library.upsert_runner_workflow(
                    source_id=source_id,
                    name=str(metadata.get("name") or source_id),
                    description=(
                        str(metadata["description"])
                        if metadata.get("description") is not None
                        else None
                    ),
                    workflow=workflow,
                    source_filename=(
                        str(metadata["filename"])
                        if metadata.get("filename") is not None
                        else None
                    ),
                )
                imported += int(created)
                updated += int(not created)
                results.append(ApiCallerWorkflowSummary.model_validate(stored))
    except Exception as exc:
        raise _http_error(exc) from exc
    return ApiCallerRunnerImportResponse(
        ok=True,
        imported=imported,
        updated=updated,
        skipped=skipped,
        workflows=results,
    )
