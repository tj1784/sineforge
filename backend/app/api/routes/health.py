import asyncio
import re

import httpx
from fastapi import APIRouter, HTTPException, Response, status

from backend.app.core.config import get_settings
from backend.app.services.comfy.client import ComfyUIClient
from backend.app.services.comfy.runner import ComfyAPIRunnerClient
from backend.app.services.ffmpeg.service import FFmpegService
from backend.app.services.lm_studio_models import (
    LMStudioModelService,
    get_active_lm_studio_model_id,
)
from backend.app.services.telemetry.gpu import GPUTelemetryService


router = APIRouter(tags=["health"])
CURRENT_PHASE = "Phase 2 controlled ComfyUI submission backend capability"
_RESTART_ID_RE = re.compile(r"^[a-f0-9]{32}$")


@router.get("/")
def root_status() -> dict:
    return {
        "app": "CineForge",
        "status": "ok",
        "message": "CineForge backend is running.",
        "docs_url": "/docs",
        "frontend_dev_url": "http://localhost:5173",
        "generation_enabled": False,
        "prompt_submission_publicly_accessible": False,
        "current_phase": CURRENT_PHASE,
    }


@router.get("/favicon.ico", status_code=status.HTTP_204_NO_CONTENT)
def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.env,
        "queue_worker_enabled": settings.queue_worker_enabled,
        "autonomy_mode": settings.autonomy_mode,
        "runtime_isolation": "comfyui_external_http_only",
    }


@router.get("/health/comfy")
async def health_comfy() -> dict:
    async with ComfyUIClient(str(get_settings().comfyui_base_url)) as client:
        return await client.health()


@router.get("/health/comfy-api-runner")
async def health_comfy_api_runner() -> dict:
    settings = get_settings()
    async with ComfyAPIRunnerClient(
        str(settings.comfy_api_runner_base_url),
    ) as client:
        return await client.health(str(settings.comfyui_base_url))


@router.get("/health/sulphur")
async def health_sulphur() -> dict:
    settings = get_settings()
    active_model_id = get_active_lm_studio_model_id(settings)
    if not settings.sulphur_planning_enabled:
        return {
            "status": "disabled",
            "reachable": False,
            "model_loaded": False,
            "model_id": active_model_id,
            "model_file": settings.sulphur_model_path.name,
        }
    catalog = await LMStudioModelService(settings).catalog()
    matching_model = next(
        (model for model in catalog.models if model.selected),
        None,
    )
    model_loaded = bool(matching_model and matching_model.loaded)
    return {
        "status": (
            "unavailable"
            if not catalog.reachable
            else ("ok" if model_loaded else "degraded")
        ),
        "reachable": catalog.reachable,
        "model_loaded": model_loaded,
        "model_id": catalog.active_model_id,
        "model_file": (
            matching_model.filename
            if matching_model and matching_model.filename
            else settings.sulphur_model_path.name
        ),
        "quantization": matching_model.quantization if matching_model else None,
        "context_length": matching_model.context_length if matching_model else None,
        "parallel": matching_model.parallel if matching_model else None,
        "error": catalog.error,
    }


@router.post("/runtime/comfyui/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_comfyui() -> dict:
    """Proxy one explicit local restart through the separately supervised Runner."""

    settings = get_settings()
    try:
        async with ComfyAPIRunnerClient(
            str(settings.comfy_api_runner_base_url),
            timeout=10,
            allow_mutation=True,
        ) as client:
            payload = await client.restart_comfy(
                comfy_url=str(settings.comfyui_base_url),
            )
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ComfyAPI Runner could not schedule the restart: {exc}",
        ) from exc

    restart_id = payload.get("restartId") if isinstance(payload, dict) else None
    if not isinstance(restart_id, str) or not _RESTART_ID_RE.fullmatch(restart_id):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ComfyAPI Runner returned an invalid restart identifier.",
        )
    return {
        "restart_id": restart_id,
        "status": "scheduled",
        "message": "ComfyUI restart scheduled through the local API Runner.",
    }


@router.get("/runtime/comfyui/restart/{restart_id}")
async def comfyui_restart_status(restart_id: str) -> dict:
    if not _RESTART_ID_RE.fullmatch(restart_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid ComfyUI restart identifier.",
        )
    settings = get_settings()
    try:
        async with ComfyAPIRunnerClient(
            str(settings.comfy_api_runner_base_url),
            timeout=10,
        ) as client:
            payload = await client.get_restart(restart_id)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ComfyAPI Runner restart status is unavailable: {exc}",
        ) from exc

    restart_status = str(payload.get("status") or "unknown")
    return {
        "restart_id": restart_id,
        "status": restart_status,
        "message": str(payload.get("message") or ""),
        "complete": restart_status == "complete",
        "failed": restart_status == "error",
    }


@router.get("/health/gpu")
def health_gpu() -> dict:
    return GPUTelemetryService().health()


@router.get("/health/ffmpeg")
def health_ffmpeg() -> dict:
    return FFmpegService().health()


@router.get("/runtime/status")
async def runtime_status() -> dict:
    settings = get_settings()
    comfy_status, runner_status, sulphur_status = await asyncio.gather(
        health_comfy(),
        health_comfy_api_runner(),
        health_sulphur(),
    )
    object_info = {
        "status": "not_checked",
        "available": False,
        "class_count": None,
        "error": None,
    }

    async with ComfyUIClient(str(settings.comfyui_base_url)) as client:
        try:
            object_info_payload = await client.get_object_info()
            object_info = {
                "status": "ok",
                "available": True,
                "class_count": len(object_info_payload),
                "error": None,
            }
        except Exception as exc:
            object_info = {
                "status": "unavailable",
                "available": False,
                "class_count": None,
                "error": str(exc),
            }

    required_statuses = [
        comfy_status.get("status"),
        runner_status.get("status"),
    ]
    if settings.sulphur_planning_enabled:
        required_statuses.append(sulphur_status.get("status"))

    return {
        "status": "ok" if all(item == "ok" for item in required_statuses) else "degraded",
        "environment": settings.env,
        "current_phase": CURRENT_PHASE,
        "comfyui": comfy_status,
        "comfy_api_runner": runner_status,
        "sulphur": sulphur_status,
        "object_info": object_info,
        "gpu": health_gpu(),
        "ffmpeg": health_ffmpeg(),
        "queue": {
            "worker_enabled": settings.queue_worker_enabled,
            "submission_enabled": False,
            "controlled_submission_enabled": True,
            "public_submission_enabled": False,
            "api_runner_available": runner_status.get("status") == "ok",
            "supported_states": [
                "pending",
                "reserved",
                "validating",
                "submitted",
                "running",
                "collecting_outputs",
                "complete",
                "validation_failed",
                "comfy_rejected",
                "runtime_failed",
                "timeout",
                "interrupted",
                "oom",
                "postprocess_failed",
                "canceled",
            ],
        },
        "disabled_actions": {
            "public_submit_prompt": "disabled",
            "websocket_monitor": "disabled_until_future_phase",
            "output_collection": "disabled_until_future_phase",
            "ffmpeg_assembly": "disabled_until_future_phase",
        },
        "links": {
            "comfyui": str(settings.comfyui_base_url).rstrip("/"),
            "comfy_api_runner": str(settings.comfy_api_runner_base_url).rstrip("/"),
        },
    }

