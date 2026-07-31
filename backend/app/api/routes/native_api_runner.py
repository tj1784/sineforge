"""Native SineForge API Runner.

Unlike ``/api-caller``, this surface never talks to the separately supervised
ComfyAPI Runner.  Operator-selected API JSON is stored in an isolated library,
validated against live ComfyUI object info, and submitted directly to the
configured ComfyUI URL only after an explicit confirmed request.
"""

from __future__ import annotations

import asyncio
import mimetypes
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse

from backend.app.core.config import get_settings
from backend.app.schemas.api_caller import (
    ApiCallerRemoveResponse,
)
from backend.app.schemas.native_api_runner import (
    NativeRunnerAnalyzeRequest,
    NativeRunnerComfyUILoadResponse,
    NativeRunnerMediaUploadResponse,
    NativeRunnerMemoryRequest,
    NativeRunnerRunRequest,
    NativeRunnerRunResponse,
    NativeRunnerWorkflowCreate,
    NativeRunnerWorkflowDetail,
    NativeRunnerWorkflowSummary,
    NativeRunnerWorkflowUpdate,
)
from backend.app.services.api_workflows import (
    ApiWorkflowError,
    ApiWorkflowNotFound,
    normalize_api_workflow,
    workflow_sha256,
)
from backend.app.services.comfy.client import ComfyUIClient
from backend.app.services.native_api_runner import (
    NATIVE_RUNNER_SCHEMA,
    NativeApiRunnerStateStore,
    NativeApiWorkflowLibrary,
    NativeRepositoryWorkflowReadOnly,
    analyze_native_workflow,
    summarize_history,
    summarize_queue,
)


router = APIRouter(prefix="/native-api-runner", tags=["native-api-runner"])
PROMPT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
SINGLE_RANGE_PATTERN = re.compile(r"^bytes=\d*-\d*$")
MAX_MEDIA_UPLOAD_BYTES = 256 * 1024 * 1024
ALLOWED_MEDIA_UPLOAD_TYPES: dict[str, frozenset[str]] = {
    ".png": frozenset({"image/png", "application/octet-stream"}),
    ".jpg": frozenset({"image/jpeg", "application/octet-stream"}),
    ".jpeg": frozenset({"image/jpeg", "application/octet-stream"}),
    ".webp": frozenset({"image/webp", "application/octet-stream"}),
    ".gif": frozenset({"image/gif", "application/octet-stream"}),
    ".bmp": frozenset({"image/bmp", "application/octet-stream"}),
    ".mp4": frozenset({"video/mp4", "application/octet-stream"}),
    ".mov": frozenset({"video/quicktime", "application/octet-stream"}),
    ".webm": frozenset({"video/webm", "application/octet-stream"}),
    ".mkv": frozenset({"video/x-matroska", "application/octet-stream"}),
    ".avi": frozenset(
        {
            "video/avi",
            "video/msvideo",
            "video/x-msvideo",
            "application/octet-stream",
        }
    ),
    ".wav": frozenset(
        {
            "audio/vnd.wave",
            "audio/wav",
            "audio/x-wav",
            "audio/wave",
            "application/octet-stream",
        }
    ),
    ".mp3": frozenset({"audio/mpeg", "application/octet-stream"}),
    ".flac": frozenset({"audio/flac", "audio/x-flac", "application/octet-stream"}),
    ".ogg": frozenset(
        {"audio/ogg", "video/ogg", "application/ogg", "application/octet-stream"}
    ),
    ".m4a": frozenset(
        {"audio/mp4", "audio/x-m4a", "application/octet-stream"}
    ),
    ".aac": frozenset({"audio/aac", "application/octet-stream"}),
}
SAFE_INLINE_OUTPUT_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/bmp",
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "video/x-matroska",
        "video/x-msvideo",
        "video/avi",
        "video/msvideo",
        "video/ogg",
        "audio/vnd.wave",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mpeg",
        "audio/flac",
        "audio/x-flac",
        "audio/ogg",
        "application/ogg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/aac",
    }
)
_idempotency_lock = asyncio.Lock()
_submitted_requests: dict[str, tuple[str, dict[str, Any]]] = {}
_native_prompt_clients: dict[str, str] = {}


def get_native_api_workflow_library() -> NativeApiWorkflowLibrary:
    return NativeApiWorkflowLibrary(get_settings().storage_root)


def get_native_api_runner_state_store(
    library: NativeApiWorkflowLibrary = Depends(get_native_api_workflow_library),
) -> NativeApiRunnerStateStore:
    return NativeApiRunnerStateStore(library.storage_root)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ApiWorkflowNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, NativeRepositoryWorkflowReadOnly):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ApiWorkflowError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    if isinstance(exc, httpx.HTTPStatusError):
        detail: Any
        try:
            detail = exc.response.json()
        except ValueError:
            detail = exc.response.text[:2000]
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "ComfyUI rejected the native Runner request.", "comfyui": detail},
        )
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ComfyUI is unavailable: {exc}",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Native API Runner failed unexpectedly.",
    )


def _validate_prompt_id(prompt_id: str) -> str:
    if not PROMPT_ID_PATTERN.fullmatch(prompt_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid ComfyUI prompt identifier.",
        )
    return prompt_id


def _native_client_id(
    prompt_id: str,
    state_store: NativeApiRunnerStateStore,
) -> str:
    client_id = _native_prompt_clients.get(prompt_id)
    if client_id is None:
        persisted = state_store.get_by_prompt_id(prompt_id)
        client_id = (
            str(persisted.get("client_id"))
            if persisted is not None and persisted.get("client_id")
            else None
        )
        if client_id is not None:
            _native_prompt_clients[prompt_id] = client_id
    if client_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Native API Runner prompt was not found.",
        )
    return client_id


@router.get("/workflows", response_model=list[NativeRunnerWorkflowSummary])
def list_workflows(
    library: NativeApiWorkflowLibrary = Depends(get_native_api_workflow_library),
) -> list[NativeRunnerWorkflowSummary]:
    try:
        return [NativeRunnerWorkflowSummary.model_validate(item) for item in library.list()]
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/workflows/{workflow_id}", response_model=NativeRunnerWorkflowDetail)
def get_workflow(
    workflow_id: UUID,
    library: NativeApiWorkflowLibrary = Depends(get_native_api_workflow_library),
) -> NativeRunnerWorkflowDetail:
    try:
        return NativeRunnerWorkflowDetail.model_validate(library.get(workflow_id))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post(
    "/workflows/{workflow_id}/load-in-comfyui",
    response_model=NativeRunnerComfyUILoadResponse,
)
async def load_workflow_in_comfyui(
    workflow_id: UUID,
    library: NativeApiWorkflowLibrary = Depends(get_native_api_workflow_library),
) -> NativeRunnerComfyUILoadResponse:
    """Stage a bundled editor graph and return its one-time ComfyUI canvas URL."""

    try:
        workflow = library.get(workflow_id)
        if not workflow.get("repository_managed"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Only read-only repository workflows use the ComfyUI canvas "
                    "handoff. Download operator workflow JSON instead."
                ),
            )
        source_workflow = workflow.get("source_workflow")
        if (
            not isinstance(source_workflow, dict)
            or not isinstance(source_workflow.get("nodes"), list)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This repository record has no editor-format ComfyUI workflow.",
            )

        comfy_url = str(get_settings().comfyui_base_url).rstrip("/")
        async with ComfyUIClient(
            comfy_url,
            timeout=12.0,
            allow_mutation=True,
        ) as client:
            transfer = await client.stage_editor_workflow(
                name=str(workflow["name"]),
                workflow=source_workflow,
            )

        try:
            transfer_token = UUID(str(transfer.get("token")))
        except (TypeError, ValueError, AttributeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="ComfyUI returned an invalid workflow-transfer token.",
            ) from exc
        expires_in_sec = transfer.get("expires_in_sec")
        if not isinstance(expires_in_sec, int) or expires_in_sec <= 0:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="ComfyUI returned an invalid workflow-transfer lifetime.",
            )

        return NativeRunnerComfyUILoadResponse(
            ok=True,
            workflow_id=UUID(str(workflow["id"])),
            workflow_name=str(workflow["name"]),
            comfy_url=comfy_url,
            open_url=f"{comfy_url}/?sineforge_workflow={quote(str(transfer_token))}",
            transfer_token=transfer_token,
            expires_in_sec=expires_in_sec,
            queued=False,
        )
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "The SineForge workflow bridge is not active in ComfyUI. "
                    "Install the bundled bridge and restart ComfyUI once."
                ),
            ) from exc
        raise _http_error(exc) from exc
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get(
    "/workflows/{workflow_id}/open-in-comfyui",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
)
async def open_workflow_in_comfyui(
    workflow_id: UUID,
    library: NativeApiWorkflowLibrary = Depends(get_native_api_workflow_library),
) -> RedirectResponse:
    """Stage and redirect a directly opened browser tab to ComfyUI."""

    staged = await load_workflow_in_comfyui(workflow_id, library)
    return RedirectResponse(
        url=staged.open_url,
        status_code=status.HTTP_303_SEE_OTHER,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.post(
    "/workflows",
    response_model=NativeRunnerWorkflowDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow(
    payload: NativeRunnerWorkflowCreate,
    library: NativeApiWorkflowLibrary = Depends(get_native_api_workflow_library),
) -> NativeRunnerWorkflowDetail:
    try:
        return NativeRunnerWorkflowDetail.model_validate(
            library.create(
                name=payload.name,
                version=payload.version,
                description=payload.description,
                category=payload.category,
                subcategory=payload.subcategory,
                episode=payload.episode,
                instructions=payload.instructions,
                tags=payload.tags,
                requirements=payload.requirements,
                source_filename=payload.source_filename,
                source_kind="native_operator_import",
                workflow=payload.workflow,
            )
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/workflows/{workflow_id}", response_model=NativeRunnerWorkflowDetail)
def update_workflow(
    workflow_id: UUID,
    payload: NativeRunnerWorkflowUpdate,
    library: NativeApiWorkflowLibrary = Depends(get_native_api_workflow_library),
) -> NativeRunnerWorkflowDetail:
    try:
        fields = payload.model_fields_set
        return NativeRunnerWorkflowDetail.model_validate(
            library.update(
                workflow_id,
                name=payload.name if "name" in fields else None,
                version=payload.version if "version" in fields else None,
                description=payload.description if "description" in fields else None,
                category=payload.category if "category" in fields else None,
                subcategory=payload.subcategory if "subcategory" in fields else None,
                episode=payload.episode if "episode" in fields else None,
                instructions=payload.instructions if "instructions" in fields else None,
                tags=payload.tags if "tags" in fields else None,
                requirements=(
                    payload.requirements if "requirements" in fields else None
                ),
                workflow=payload.workflow if "workflow" in fields else None,
            )
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.delete("/workflows/{workflow_id}", response_model=ApiCallerRemoveResponse)
def remove_workflow(
    workflow_id: UUID,
    library: NativeApiWorkflowLibrary = Depends(get_native_api_workflow_library),
) -> ApiCallerRemoveResponse:
    try:
        return ApiCallerRemoveResponse.model_validate(library.remove(workflow_id))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/runtime")
async def get_runtime() -> dict[str, Any]:
    comfy_url = str(get_settings().comfyui_base_url)
    async with ComfyUIClient(comfy_url, timeout=8.0) as client:
        health, object_info, queue = await asyncio.gather(
            client.health(),
            client.get_object_info(),
            client.get_queue(),
            return_exceptions=True,
        )

    health_payload = (
        health
        if isinstance(health, dict)
        else {"status": "unavailable", "reachable": False, "error": str(health)}
    )
    object_payload = object_info if isinstance(object_info, dict) else None
    queue_payload = queue if isinstance(queue, dict) else {}
    return {
        "schema": NATIVE_RUNNER_SCHEMA,
        "ok": bool(health_payload.get("reachable")) and object_payload is not None,
        "comfyUrl": comfy_url,
        "comfy": health_payload,
        "objectInfo": {
            "available": object_payload is not None,
            "classCount": len(object_payload or {}),
            "error": None if object_payload is not None else str(object_info),
        },
        "queue": summarize_queue(queue_payload),
        "externalRunnerUsed": False,
        "capabilities": {
            "library": True,
            "liveValidation": True,
            "directSubmission": True,
            "mediaUpload": True,
            "outputPreview": True,
            "cancelPending": True,
            # ComfyUI's standard /interrupt endpoint is global rather than
            # prompt-scoped, so the embedded runner deliberately does not
            # expose it on a shared local ComfyUI instance.
            "interruptActive": False,
            "freeMemory": True,
            "seedVariation": False,
            "mergeMovie": False,
            "saveLatents": False,
        },
    }


@router.post("/analyze")
async def analyze_workflow(payload: NativeRunnerAnalyzeRequest) -> dict[str, Any]:
    try:
        workflow = normalize_api_workflow(payload.workflow)
        async with ComfyUIClient(
            str(get_settings().comfyui_base_url),
            timeout=30.0,
        ) as client:
            object_info = await client.get_object_info()
        return analyze_native_workflow(workflow, object_info)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/run", response_model=NativeRunnerRunResponse)
async def run_workflow(
    payload: NativeRunnerRunRequest,
    state_store: NativeApiRunnerStateStore = Depends(
        get_native_api_runner_state_store
    ),
) -> NativeRunnerRunResponse:
    try:
        workflow = normalize_api_workflow(payload.workflow)
        digest = workflow_sha256(workflow)
        if digest != payload.workflow_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The working JSON changed after validation. Validate this exact graph again.",
            )

        async with _idempotency_lock:
            persisted = state_store.get_by_idempotency_key(payload.idempotency_key)
            if persisted is not None:
                if persisted["workflow_sha256"] != digest:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="The idempotency key was already used for different workflow JSON.",
                    )
                persisted_response = persisted.get("response")
                if isinstance(persisted_response, dict):
                    prompt_id = str(persisted_response.get("prompt_id") or "")
                    client_id = str(persisted_response.get("client_id") or "")
                    if prompt_id and client_id:
                        _native_prompt_clients[prompt_id] = client_id
                        _submitted_requests[payload.idempotency_key] = (
                            digest,
                            persisted_response,
                        )
                    return NativeRunnerRunResponse.model_validate(persisted_response)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This idempotency key already has an unresolved submission. "
                        "Inspect ComfyUI before choosing a new key; SineForge will not "
                        "risk submitting a duplicate render."
                    ),
                )

            prior = _submitted_requests.get(payload.idempotency_key)
            if prior is not None:
                prior_digest, prior_response = prior
                if prior_digest != digest:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="The idempotency key was already used for different workflow JSON.",
                    )
                prompt_id = str(prior_response.get("prompt_id") or "")
                client_id = str(prior_response.get("client_id") or "")
                if prompt_id and client_id:
                    _native_prompt_clients[prompt_id] = client_id
                return NativeRunnerRunResponse.model_validate(prior_response)

            async with ComfyUIClient(
                str(get_settings().comfyui_base_url),
                timeout=30.0,
            ) as client:
                object_info = await client.get_object_info()
            analysis = analyze_native_workflow(workflow, object_info)
            if not analysis["queueable"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "message": "Live validation failed; nothing was queued.",
                        "analysis": analysis,
                    },
                )

            client_id = f"sineforge-native-{uuid4()}"
            reserved, reservation = state_store.reserve(
                idempotency_key=payload.idempotency_key,
                workflow_sha256=digest,
                client_id=client_id,
            )
            if not reserved:
                if reservation["workflow_sha256"] != digest:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="The idempotency key was already used for different workflow JSON.",
                    )
                prior_response = reservation.get("response")
                if isinstance(prior_response, dict):
                    return NativeRunnerRunResponse.model_validate(prior_response)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This idempotency key already has an unresolved submission.",
                )

            async with ComfyUIClient(
                str(get_settings().comfyui_base_url),
                timeout=45.0,
                allow_mutation=True,
            ) as client:
                result = await client.submit_prompt(workflow, client_id)

            node_errors = result.get("node_errors")
            if node_errors:
                state_store.release_unsubmitted_reservation(
                    idempotency_key=payload.idempotency_key,
                    client_id=client_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "message": "ComfyUI rejected one or more workflow nodes.",
                        "node_errors": node_errors,
                    },
                )
            prompt_id = result.get("prompt_id")
            if not isinstance(prompt_id, str) or not prompt_id:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="ComfyUI accepted the request without returning a prompt identifier.",
                )
            response = NativeRunnerRunResponse(
                contract=NATIVE_RUNNER_SCHEMA,
                ok=True,
                prompt_id=prompt_id,
                queue_number=result.get("number"),
                client_id=client_id,
                workflow_sha256=digest,
                submitted_at=datetime.now(UTC).isoformat(),
            )
            response_payload = response.model_dump()
            state_store.complete_submission(
                idempotency_key=payload.idempotency_key,
                workflow_sha256=digest,
                prompt_id=prompt_id,
                client_id=client_id,
                response=response_payload,
            )
            _submitted_requests[payload.idempotency_key] = (digest, response_payload)
            _native_prompt_clients[prompt_id] = client_id
            return response
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/jobs/{prompt_id}")
async def get_job(
    prompt_id: str,
    state_store: NativeApiRunnerStateStore = Depends(
        get_native_api_runner_state_store
    ),
) -> dict[str, Any]:
    safe_prompt_id = _validate_prompt_id(prompt_id)
    _native_client_id(safe_prompt_id, state_store)
    try:
        async with ComfyUIClient(
            str(get_settings().comfyui_base_url),
            timeout=20.0,
        ) as client:
            history, queue = await asyncio.gather(
                client.get_history(safe_prompt_id),
                client.get_queue(),
            )
        result = summarize_history(safe_prompt_id, history, queue)
        state_store.update_prompt_state(safe_prompt_id, str(result["state"]))
        return result
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/jobs/{prompt_id}/cancel")
async def cancel_job(
    prompt_id: str,
    interrupt_active: bool = Query(False),
    state_store: NativeApiRunnerStateStore = Depends(
        get_native_api_runner_state_store
    ),
) -> dict[str, Any]:
    safe_prompt_id = _validate_prompt_id(prompt_id)
    expected_client_id = _native_client_id(safe_prompt_id, state_store)
    try:
        async with ComfyUIClient(
            str(get_settings().comfyui_base_url),
            timeout=20.0,
            allow_mutation=True,
        ) as client:
            queue = summarize_queue(await client.get_queue())
            pending_ids = {item["promptId"] for item in queue["pending"]}
            running_ids = {item["promptId"] for item in queue["running"]}
            if safe_prompt_id in pending_ids:
                pending_item = next(
                    item for item in queue["pending"] if item["promptId"] == safe_prompt_id
                )
                if pending_item.get("clientId") not in {None, expected_client_id}:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="The queued prompt is not owned by the native API Runner.",
                    )
                await client.delete_queue_items([safe_prompt_id])
                verification_queue = await client.get_queue()
                verification_history = await client.get_history(safe_prompt_id)
                verification = summarize_history(
                    safe_prompt_id,
                    verification_history,
                    verification_queue,
                )
                if verification["state"] != "unknown":
                    state_store.update_prompt_state(
                        safe_prompt_id,
                        str(verification["state"]),
                    )
                    return {
                        "ok": False,
                        "promptId": safe_prompt_id,
                        "action": f"cancel_raced_{verification['state']}",
                    }
                state_store.update_prompt_state(safe_prompt_id, "failed")
                return {
                    "ok": True,
                    "promptId": safe_prompt_id,
                    "action": "deleted_pending",
                }
            if safe_prompt_id in running_ids:
                running_item = next(
                    item for item in queue["running"] if item["promptId"] == safe_prompt_id
                )
                if running_item.get("clientId") not in {None, expected_client_id}:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="The active prompt is not owned by the native API Runner.",
                    )
                del interrupt_active
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Active interruption is disabled because ComfyUI's interrupt "
                        "operation is global and could stop unrelated work. Use ComfyUI "
                        "directly only if you intend to interrupt its active prompt."
                    ),
                )
            return {
                "ok": False,
                "promptId": safe_prompt_id,
                "action": "not_in_queue",
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/memory/free")
async def free_memory(payload: NativeRunnerMemoryRequest) -> dict[str, Any]:
    try:
        async with ComfyUIClient(
            str(get_settings().comfyui_base_url),
            timeout=30.0,
            allow_mutation=True,
        ) as client:
            queue = summarize_queue(await client.get_queue())
            if queue["runningCount"] or queue["pendingCount"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "ComfyUI has running or pending work. Wait for the entire queue "
                        "to become empty before unloading models."
                    ),
                )
            # Re-read immediately before the global free operation to reduce
            # the race window with work submitted outside SineForge.
            final_queue = summarize_queue(await client.get_queue())
            if final_queue["runningCount"] or final_queue["pendingCount"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="ComfyUI queue changed; free-memory was not requested.",
                )
            result = await client.free_memory(
                unload_models=payload.unload_models,
                free_memory=payload.free_memory,
            )
        return {
            "ok": True,
            "action": "free_memory",
            "comfyui": result,
            "externalRunnerUsed": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/media", response_model=NativeRunnerMediaUploadResponse)
async def upload_media(
    request: Request,
    filename: str = Query(..., min_length=1, max_length=240),
    subfolder: str = Query("sineforge_native", max_length=120),
) -> NativeRunnerMediaUploadResponse:
    safe_name = Path(filename).name
    if safe_name != filename or safe_name in {"", ".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Media filename must not contain a path.",
        )
    extension = Path(safe_name).suffix.casefold()
    allowed_content_types = ALLOWED_MEDIA_UPLOAD_TYPES.get(extension)
    if allowed_content_types is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Native Runner uploads are limited to raster images, audio, and video. "
                "Active document formats such as HTML, SVG, XML, and scripts are prohibited."
            ),
        )
    request_content_type = (
        request.headers.get("content-type") or "application/octet-stream"
    ).split(";", 1)[0].strip().casefold()
    if request_content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"{request_content_type} is not valid for a {extension} media upload.",
        )
    normalized_subfolder = subfolder.replace("\\", "/").strip("/")
    if any(part in {"", ".", ".."} for part in normalized_subfolder.split("/")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Media subfolder is invalid.",
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_MEDIA_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Media upload exceeds the 256 MiB native Runner limit.",
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header.",
            ) from exc

    temporary = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode="w+b")
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_MEDIA_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Media upload exceeds the 256 MiB native Runner limit.",
                )
            temporary.write(chunk)
        if received == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Media upload is empty.",
            )
        temporary.seek(0)
        async with ComfyUIClient(
            str(get_settings().comfyui_base_url),
            timeout=120.0,
            allow_mutation=True,
        ) as client:
            result = await client.upload_image_file(
                temporary,
                safe_name,
                subfolder=normalized_subfolder,
                overwrite=False,
                content_type=request_content_type,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        temporary.close()
    return NativeRunnerMediaUploadResponse(
        ok=True,
        filename=str(result.get("name") or safe_name),
        subfolder=str(result.get("subfolder") or normalized_subfolder),
        type=str(result.get("type") or "input"),
    )


@router.get("/outputs")
async def get_output(
    request: Request,
    prompt_id: str = Query(..., min_length=1, max_length=160),
    filename: str = Query(..., min_length=1, max_length=512),
    subfolder: str = Query("", max_length=512),
    output_type: str = Query("output", alias="type", pattern=r"^(output|temp)$"),
    state_store: NativeApiRunnerStateStore = Depends(
        get_native_api_runner_state_store
    ),
) -> StreamingResponse:
    safe_prompt_id = _validate_prompt_id(prompt_id)
    _native_client_id(safe_prompt_id, state_store)
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Output filename must not contain a path.",
        )
    normalized_subfolder = subfolder.replace("\\", "/").strip("/")
    if any(part in {".", ".."} for part in normalized_subfolder.split("/") if part):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Output subfolder is invalid.",
        )
    try:
        async with ComfyUIClient(
            str(get_settings().comfyui_base_url),
            timeout=20.0,
        ) as client:
            history = await client.get_history(safe_prompt_id)
        job = summarize_history(safe_prompt_id, history, {})
        requested_output = (safe_name, normalized_subfolder, output_type)
        observed_outputs = {
            (
                str(output.get("filename") or ""),
                str(output.get("subfolder") or ""),
                str(output.get("type") or "output"),
            )
            for output in job["outputs"]
        }
        if requested_output not in observed_outputs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The requested file is not an output of this native prompt.",
            )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise _http_error(exc) from exc

    range_header = request.headers.get("range")
    upstream_headers: dict[str, str] = {"Accept-Encoding": "identity"}
    if range_header and SINGLE_RANGE_PATTERN.fullmatch(range_header):
        upstream_headers["Range"] = range_header
    upstream_client = httpx.AsyncClient(
        base_url=str(get_settings().comfyui_base_url).rstrip("/"),
        timeout=httpx.Timeout(60.0, read=300.0),
    )
    upstream_request = upstream_client.build_request(
        "GET",
        "/view",
        params={
            "filename": safe_name,
            "subfolder": normalized_subfolder,
            "type": output_type,
        },
        headers=upstream_headers,
    )
    try:
        upstream = await upstream_client.send(upstream_request, stream=True)
        if upstream.status_code >= 400:
            response_status = upstream.status_code
            await upstream.aclose()
            await upstream_client.aclose()
            raise HTTPException(
                status_code=response_status,
                detail="ComfyUI could not serve the native prompt output.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        await upstream_client.aclose()
        raise _http_error(exc) from exc

    guessed_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    media_type = (
        guessed_type if guessed_type in SAFE_INLINE_OUTPUT_TYPES else "application/octet-stream"
    )
    disposition = "inline" if media_type in SAFE_INLINE_OUTPUT_TYPES else "attachment"
    response_headers = {
        "Content-Disposition": (
            f"{disposition}; filename*=UTF-8''{quote(safe_name, safe='')}"
        ),
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cross-Origin-Resource-Policy": "same-origin",
        "X-Content-Type-Options": "nosniff",
    }
    for header_name in (
        "accept-ranges",
        "content-length",
        "content-range",
        "etag",
        "last-modified",
    ):
        header_value = upstream.headers.get(header_name)
        if header_value:
            response_headers[header_name] = header_value

    async def stream_body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await upstream_client.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=upstream.status_code,
        media_type=media_type,
        headers=response_headers,
    )
