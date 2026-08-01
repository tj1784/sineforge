import asyncio
import ipaddress
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from backend.app.core.config import Settings, get_settings
from backend.app.services.comfy.client import ComfyUIClient
from backend.app.services.comfy.engine import ComfyEngineError, ComfyEngineManager
from backend.app.services.ffmpeg.service import FFmpegService
from backend.app.services.lm_studio_models import (
    LMStudioModelService,
    get_active_lm_studio_model_id,
)
from backend.app.services.telemetry.gpu import GPUTelemetryService


router = APIRouter(tags=["health"])
CURRENT_PHASE = "Bundled ComfyUI engine with Sineforge-native submission"
_RESTART_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def _app_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    manager = getattr(request.app.state, "comfy_engine", None)
    if isinstance(manager, ComfyEngineManager):
        return manager.settings
    return get_settings()


def _engine_manager(request: Request) -> ComfyEngineManager:
    manager = getattr(request.app.state, "comfy_engine", None)
    if isinstance(manager, ComfyEngineManager):
        return manager
    # This fallback keeps direct ASGI/unit-test construction read-only. Only
    # the launcher-provided process flag allows lifecycle mutations.
    return ComfyEngineManager(_app_settings(request))


def _owned_engine_manager(request: Request) -> ComfyEngineManager:
    manager = getattr(request.app.state, "comfy_engine", None)
    if not isinstance(manager, ComfyEngineManager):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The Sineforge engine owner is unavailable because application lifespan is not active.",
        )
    return manager


def _require_local_control(request: Request) -> None:
    """Reject browser cross-site lifecycle mutations against the loopback API."""

    hostname = request.url.hostname or ""
    if hostname != "testserver":
        try:
            loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            loopback = hostname.casefold() == "localhost"
        if not loopback:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Loopback control only.")

    if request.headers.get("sec-fetch-site", "").casefold() == "cross-site":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site control denied.")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        normalized = origin.rstrip("/")
        allowed = {
            item.rstrip("/")
            for item in _app_settings(request).cors_allowed_origins
            if item != "*"
        }
        if parsed.scheme not in {"http", "https"} or normalized not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Untrusted control origin.")


@router.get("/")
def root_status() -> dict:
    return {
        "app": "CineForge",
        "status": "ok",
        "message": "CineForge backend is running.",
        "docs_url": "/docs",
        "frontend_dev_url": "http://127.0.0.1:5174",
        "generation_enabled": True,
        "prompt_submission_publicly_accessible": False,
        "current_phase": CURRENT_PHASE,
    }


@router.get("/favicon.ico", status_code=status.HTTP_204_NO_CONTENT)
def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/health")
def health(request: Request) -> dict:
    settings = _app_settings(request)
    return {
        "status": "ok",
        "env": settings.env,
        "queue_worker_enabled": settings.queue_worker_enabled,
        "autonomy_mode": settings.autonomy_mode,
        "runtime_isolation": (
            "bundled_comfyui_subprocess"
            if settings.comfyui_backend_managed
            else "unmanaged_diagnostic_mode"
        ),
    }


@router.get("/health/comfy")
async def health_comfy(request: Request) -> dict:
    async with ComfyUIClient(str(_app_settings(request).comfyui_base_url)) as client:
        return await client.health()


@router.get("/health/comfy-api-runner")
async def health_comfy_api_runner(request: Request) -> dict:
    """Compatibility health route for clients predating the native Runner."""

    comfy = await health_comfy(request)
    return {
        "status": comfy.get("status", "unavailable"),
        "reachable": bool(comfy.get("reachable")),
        "mode": "sineforge_native",
        "legacy_external_runner_required": False,
        "message": "Workflow execution is built into Sineforge.",
    }


@router.get("/runtime/engine")
async def engine_status(request: Request) -> dict:
    return await _engine_manager(request).status()


@router.get("/health/engine/ready")
async def engine_ready(request: Request) -> Response:
    payload = await _engine_manager(request).status()
    return JSONResponse(
        payload,
        status_code=(status.HTTP_200_OK if payload.get("ready") else status.HTTP_503_SERVICE_UNAVAILABLE),
    )


@router.post("/runtime/engine/start", status_code=status.HTTP_202_ACCEPTED)
async def start_engine(request: Request) -> dict:
    _require_local_control(request)
    manager = _owned_engine_manager(request)
    try:
        manager.start_in_background(force=True)
    except ComfyEngineError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {
        "status": "starting",
        "message": "Sineforge is starting its bundled ComfyUI engine.",
    }


@router.post("/runtime/engine/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_engine(request: Request, force: bool = False) -> dict:
    _require_local_control(request)
    manager = _owned_engine_manager(request)
    try:
        await manager.stop(force=force)
    except ComfyEngineError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {
        "status": "stopped",
        "message": "The bundled ComfyUI engine stopped.",
    }


async def _health_sulphur(settings: Settings) -> dict:
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


@router.get("/health/sulphur")
async def health_sulphur(request: Request) -> dict:
    return await _health_sulphur(_app_settings(request))


@router.post("/runtime/comfyui/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_comfyui(request: Request, force: bool = False) -> dict:
    """Schedule a restart through Sineforge's in-process engine owner."""

    try:
        _require_local_control(request)
        payload = await _owned_engine_manager(request).schedule_restart(force=force)
    except ComfyEngineError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    restart_id = payload.get("restart_id") if isinstance(payload, dict) else None
    if not isinstance(restart_id, str) or not _RESTART_ID_RE.fullmatch(restart_id):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The bundled engine manager returned an invalid restart identifier.",
        )
    return payload


@router.get("/runtime/comfyui/restart/{restart_id}")
async def comfyui_restart_status(restart_id: str, request: Request) -> dict:
    if not _RESTART_ID_RE.fullmatch(restart_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid ComfyUI restart identifier.",
        )
    payload = _engine_manager(request).restart_status(restart_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The bundled engine restart record was not found.",
        )
    return payload


@router.get("/health/gpu")
def health_gpu() -> dict:
    return GPUTelemetryService().health()


@router.get("/health/ffmpeg")
def health_ffmpeg() -> dict:
    return FFmpegService().health()


@router.get("/runtime/status")
async def runtime_status(request: Request) -> dict:
    manager = _engine_manager(request)
    settings = manager.settings
    managed_engine, sulphur_status = await asyncio.gather(
        manager.status(),
        _health_sulphur(settings),
    )
    engine_ready = bool(managed_engine.get("ready"))
    comfy_status = {
        "status": "ok" if engine_ready else "unavailable",
        "reachable": bool(managed_engine.get("reachable")),
        "ready": engine_ready,
        "managed": bool(managed_engine.get("managed")),
        "checks": managed_engine.get("checks", {}),
        "error": managed_engine.get("last_error"),
    }
    runner_status = {
        "status": "ok" if engine_ready else "unavailable",
        "reachable": engine_ready,
        "mode": "sineforge_native",
        "legacy_external_runner_required": False,
    }
    object_info = {
        "status": "ok" if engine_ready else "unavailable",
        "available": engine_ready,
        "class_count": None,
        "required_nodes_ready": not bool(managed_engine.get("missing_required_nodes")),
        "missing_required_nodes": managed_engine.get("missing_required_nodes", []),
        "error": managed_engine.get("last_error"),
    }

    required_statuses = ["ok" if engine_ready else "unavailable"]
    if settings.sulphur_planning_enabled:
        required_statuses.append(sulphur_status.get("status"))

    return {
        "status": "ok" if all(item == "ok" for item in required_statuses) else "degraded",
        "environment": settings.env,
        "current_phase": CURRENT_PHASE,
        "engine": managed_engine,
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
            "api_runner_available": engine_ready,
            "execution_mode": "sineforge_native",
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
            "engine_api": "/native-api-runner/runtime",
            "engine_control": "/runtime/engine",
            "comfyui_api": str(settings.comfyui_base_url).rstrip("/"),
        },
    }

