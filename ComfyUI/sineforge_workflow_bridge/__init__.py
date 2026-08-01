"""Loopback-only SineForge workflow handoff for the ComfyUI editor.

The bridge never queues a prompt. It keeps a small, short-lived in-memory
transfer so a newly opened ComfyUI tab can load an editor-format workflow.
"""

from __future__ import annotations

import ipaddress
import json
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any

from aiohttp import web
from server import PromptServer

from .continuation_planner import (
    SineForgeContinuationLoopCount,
    SineForgeLTXGeneralContinuationPlanner,
    SineForgeLTXKreaContinuationPlanner,
)
from .character_ingredients_planner import (
    SineForgeKrea2CharacterIngredientsPlanner,
)
from .podcast_planner import SineForgeLTXPodcastPlanner


WEB_DIRECTORY = "./js"
NODE_CLASS_MAPPINGS: dict[str, Any] = {
    "SineForgeKrea2CharacterIngredientsPlanner": (
        SineForgeKrea2CharacterIngredientsPlanner
    ),
    "SineForgeContinuationLoopCount": SineForgeContinuationLoopCount,
    "SineForgeLTXGeneralContinuationPlanner": (
        SineForgeLTXGeneralContinuationPlanner
    ),
    "SineForgeLTXKreaContinuationPlanner": SineForgeLTXKreaContinuationPlanner,
    "SineForgeLTXPodcastPlanner": SineForgeLTXPodcastPlanner,
}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {
    "SineForgeKrea2CharacterIngredientsPlanner": (
        "SineForge · Selectable Local Model · Krea 2 Character Ingredients JSON"
    ),
    "SineForgeContinuationLoopCount": (
        "SineForge · Continuation Loop Count · 0 = Continuous"
    ),
    "SineForgeLTXGeneralContinuationPlanner": (
        "SineForge · Local Model General Continuation JSON"
    ),
    "SineForgeLTXKreaContinuationPlanner": (
        "SineForge · Local Model Krea 2 Continuation JSON"
    ),
    "SineForgeLTXPodcastPlanner": "SineForge · Local Podcast JSON Planner",
}

_TRANSFER_TTL_SECONDS = 300
_MAX_TRANSFER_BYTES = 24 * 1024 * 1024
_MAX_TRANSFERS = 32
_transfers: OrderedDict[str, dict[str, Any]] = OrderedDict()
_transfer_lock = threading.RLock()


def _is_loopback(request: web.Request) -> bool:
    remote = request.remote
    if not remote:
        return False
    try:
        return ipaddress.ip_address(remote.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _reject_non_loopback(request: web.Request) -> web.Response | None:
    if _is_loopback(request):
        return None
    return web.json_response(
        {"ok": False, "error": "Workflow transfer is restricted to loopback clients."},
        status=403,
    )


def _prune_expired(now: float) -> None:
    expired = [
        token
        for token, transfer in _transfers.items()
        if float(transfer["expires_at"]) <= now
    ]
    for token in expired:
        _transfers.pop(token, None)
    while len(_transfers) >= _MAX_TRANSFERS:
        _transfers.popitem(last=False)


def _valid_editor_workflow(workflow: object) -> bool:
    if not isinstance(workflow, dict):
        return False
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or not nodes or len(nodes) > 10_000:
        return False
    links = workflow.get("links")
    return links is None or isinstance(links, list)


@PromptServer.instance.routes.get("/sineforge/workflow-transfer/status")
async def sineforge_workflow_transfer_status(request: web.Request) -> web.Response:
    rejected = _reject_non_loopback(request)
    if rejected is not None:
        return rejected
    now = time.monotonic()
    with _transfer_lock:
        _prune_expired(now)
        pending_transfers = len(_transfers)
    # This is intentionally evaluated at request time, after ComfyUI has loaded
    # every custom node.  It gives the owning Sineforge process a cheap,
    # identity-bound readiness check without serializing the multi-megabyte
    # /object_info response on every poll.
    import nodes as comfy_nodes

    requested_nodes = list(dict.fromkeys(request.query.getall("required", [])))
    required_nodes = {
        name: name in comfy_nodes.NODE_CLASS_MAPPINGS for name in requested_nodes
    }
    return web.json_response(
        {
            "ok": True,
            "bridge": "sineforge-workflow-bridge",
            "version": 2,
            "ttl_seconds": _TRANSFER_TTL_SECONDS,
            "pending_transfers": pending_transfers,
            "nodes": sorted(NODE_CLASS_MAPPINGS),
            "required_nodes": required_nodes,
        }
    )


@PromptServer.instance.routes.post("/sineforge/workflow-transfer")
async def stage_sineforge_workflow(request: web.Request) -> web.Response:
    rejected = _reject_non_loopback(request)
    if rejected is not None:
        return rejected
    if request.content_length is None or request.content_length > _MAX_TRANSFER_BYTES:
        return web.json_response(
            {"ok": False, "error": "Workflow transfer payload is too large."},
            status=413,
        )
    try:
        payload = await request.json(loads=json.loads)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return web.json_response(
            {"ok": False, "error": "Workflow transfer payload must be valid JSON."},
            status=400,
        )
    if not isinstance(payload, dict) or payload.get("source") != "sineforge":
        return web.json_response(
            {"ok": False, "error": "Workflow transfer source was rejected."},
            status=400,
        )
    workflow = payload.get("workflow")
    if not _valid_editor_workflow(workflow):
        return web.json_response(
            {"ok": False, "error": "An editor-format ComfyUI workflow is required."},
            status=422,
        )
    encoded_size = len(
        json.dumps(workflow, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    if encoded_size > _MAX_TRANSFER_BYTES:
        return web.json_response(
            {"ok": False, "error": "Workflow transfer payload is too large."},
            status=413,
        )

    token = str(uuid.uuid4())
    now = time.monotonic()
    name = str(payload.get("name") or "SineForge workflow").strip()[:240]
    with _transfer_lock:
        _prune_expired(now)
        _transfers[token] = {
            "name": name or "SineForge workflow",
            "workflow": workflow,
            "expires_at": now + _TRANSFER_TTL_SECONDS,
        }
    return web.json_response(
        {
            "ok": True,
            "token": token,
            "expires_in_sec": _TRANSFER_TTL_SECONDS,
        }
    )


@PromptServer.instance.routes.get("/sineforge/workflow-transfer/{token}")
async def consume_sineforge_workflow(request: web.Request) -> web.Response:
    rejected = _reject_non_loopback(request)
    if rejected is not None:
        return rejected
    token = request.match_info.get("token", "")
    try:
        uuid.UUID(token)
    except ValueError:
        return web.json_response(
            {"ok": False, "error": "Workflow transfer token is invalid."},
            status=404,
        )

    now = time.monotonic()
    with _transfer_lock:
        _prune_expired(now)
        transfer = _transfers.pop(token, None)
    if transfer is None:
        return web.json_response(
            {"ok": False, "error": "Workflow transfer expired or was already used."},
            status=410,
        )
    return web.json_response(
        {
            "ok": True,
            "name": transfer["name"],
            "workflow": transfer["workflow"],
        }
    )


__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
