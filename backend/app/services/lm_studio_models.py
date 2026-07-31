"""Local-only LM Studio catalog, activation, and persisted model selection.

The model selector is deliberately bounded to models reported by LM Studio or
the two administrator-installed GGUFs known to SineForge. It never downloads,
moves, or deletes model files. Switching may unload the prior SineForge
planning model from memory so the replacement has enough VRAM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.app.core.config import Settings, get_settings
from backend.app.schemas.lm_studio import (
    LMStudioModelActivateResponse,
    LMStudioModelCatalogResponse,
    LMStudioModelRead,
)


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}$")
_SELECTION_LOCK = RLock()
_SELECTION_FILENAME = "lm-studio-model-selection.json"


@dataclass(frozen=True)
class _KnownModel:
    model_id: str
    key: str
    display_name: str
    path: Path
    publisher: str


def _known_models(settings: Settings) -> tuple[_KnownModel, ...]:
    return (
        _KnownModel(
            model_id=settings.sulphur_model_id,
            key=settings.sulphur_model_id,
            display_name="Sulphur 2 Base",
            path=settings.sulphur_model_path,
            publisher="SulphurAI",
        ),
        _KnownModel(
            model_id=settings.qwen_model_id,
            key=settings.qwen_model_id,
            display_name="Qwen3 4B Hivemind · Heretic · Q4_K_M",
            path=settings.qwen_model_path,
            publisher="DavidAU",
        ),
    )


def _selection_path(settings: Settings) -> Path:
    return settings.storage_root / "runtime" / _SELECTION_FILENAME


def _read_selection(settings: Settings) -> dict[str, Any] | None:
    path = _selection_path(settings)
    with _SELECTION_LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
    if not isinstance(payload, dict):
        return None
    model_id = payload.get("model_id")
    if not isinstance(model_id, str) or not _MODEL_ID_RE.fullmatch(model_id):
        return None
    return payload


def _write_selection(
    settings: Settings,
    *,
    model_id: str,
    key: str,
    display_name: str,
    filename: str | None,
) -> None:
    path = _selection_path(settings)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "schema_name": "runtime.lm_studio_model_selection.v1",
        "model_id": model_id,
        "key": key,
        "display_name": display_name,
        "filename": filename,
        "selected_at": datetime.now(timezone.utc).isoformat(),
    }
    with _SELECTION_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


def get_active_lm_studio_model_id(settings: Settings | None = None) -> str:
    """Return the persisted runtime selection or the configured Qwen fallback."""

    cfg = settings or get_settings()
    selection = _read_selection(cfg)
    return str(selection["model_id"]) if selection else cfg.qwen_model_id


def get_active_lm_studio_model_filename(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    selection = _read_selection(cfg)
    if selection:
        filename = selection.get("filename")
        if isinstance(filename, str) and filename:
            return filename
        selected_id = str(selection["model_id"])
        for known in _known_models(cfg):
            if selected_id == known.model_id:
                return known.path.name
    return cfg.qwen_model_path.name


class LMStudioUnavailableError(RuntimeError):
    pass


class LMStudioModelNotFoundError(LookupError):
    pass


class LMStudioModelService:
    """Bounded model management client for one loopback LM Studio server."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport
        parsed = urlsplit(self.settings.sulphur_base_url)
        self.native_base_url = urlunsplit(
            (parsed.scheme, parsed.netloc, "/api/v1", "", "")
        )

    async def _live_entries(self) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=3.0),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.get(f"{self.native_base_url}/models")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise LMStudioUnavailableError(str(exc)) from exc
        entries = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise LMStudioUnavailableError("LM Studio returned an invalid model catalog")
        return [entry for entry in entries if isinstance(entry, dict)]

    def _fallback_models(self, active_model_id: str) -> list[LMStudioModelRead]:
        return [
            LMStudioModelRead(
                model_id=known.model_id,
                key=known.key,
                display_name=known.display_name,
                filename=known.path.name,
                publisher=known.publisher,
                quantization=(
                    "Q8_0"
                    if known.model_id == self.settings.sulphur_model_id
                    else "Q4_K_M"
                ),
                size_bytes=known.path.stat().st_size if known.path.is_file() else None,
                installed=known.path.is_file(),
                loaded=False,
                selected=known.model_id == active_model_id,
            )
            for known in _known_models(self.settings)
        ]

    @staticmethod
    def _loaded_instance_ids(entry: dict[str, Any]) -> list[str]:
        instances = entry.get("loaded_instances")
        if not isinstance(instances, list):
            return []
        return [
            str(instance["id"])
            for instance in instances
            if isinstance(instance, dict)
            and isinstance(instance.get("id"), str)
            and _MODEL_ID_RE.fullmatch(instance["id"])
        ]

    def _normalize_live_model(
        self,
        entry: dict[str, Any],
        *,
        active_model_id: str,
    ) -> LMStudioModelRead | None:
        key = entry.get("key")
        if (
            entry.get("type") not in {None, "llm"}
            or not isinstance(key, str)
            or not _MODEL_ID_RE.fullmatch(key)
        ):
            return None
        instance_ids = self._loaded_instance_ids(entry)
        model_id = (
            active_model_id
            if active_model_id in instance_ids
            else (instance_ids[0] if key == active_model_id and instance_ids else key)
        )
        quantization = entry.get("quantization")
        quantization_name = (
            quantization.get("name") if isinstance(quantization, dict) else None
        )
        matching_known = next(
            (
                known
                for known in _known_models(self.settings)
                if known.model_id in {key, *instance_ids}
            ),
            None,
        )
        loaded_instances = (
            entry.get("loaded_instances")
            if isinstance(entry.get("loaded_instances"), list)
            else []
        )
        first_loaded_config = next(
            (
                instance.get("config")
                for instance in loaded_instances
                if isinstance(instance, dict)
                and isinstance(instance.get("config"), dict)
            ),
            {},
        )
        return LMStudioModelRead(
            model_id=model_id,
            key=key,
            display_name=str(entry.get("display_name") or key),
            filename=matching_known.path.name if matching_known else None,
            publisher=(
                str(entry["publisher"])
                if isinstance(entry.get("publisher"), str)
                else None
            ),
            architecture=(
                str(entry["architecture"])
                if isinstance(entry.get("architecture"), str)
                else None
            ),
            quantization=(
                str(quantization_name) if isinstance(quantization_name, str) else None
            ),
            params_string=(
                str(entry["params_string"])
                if isinstance(entry.get("params_string"), str)
                else None
            ),
            size_bytes=(
                int(entry["size_bytes"])
                if isinstance(entry.get("size_bytes"), int)
                and entry["size_bytes"] >= 0
                else None
            ),
            max_context_length=(
                int(entry["max_context_length"])
                if isinstance(entry.get("max_context_length"), int)
                and entry["max_context_length"] >= 0
                else None
            ),
            context_length=(
                int(first_loaded_config["context_length"])
                if isinstance(first_loaded_config.get("context_length"), int)
                and first_loaded_config["context_length"] >= 0
                else None
            ),
            parallel=(
                int(first_loaded_config["parallel"])
                if isinstance(first_loaded_config.get("parallel"), int)
                and first_loaded_config["parallel"] >= 0
                else None
            ),
            installed=True,
            loaded=bool(instance_ids),
            selected=active_model_id in {key, *instance_ids},
            loaded_instance_ids=instance_ids,
        )

    async def catalog(self) -> LMStudioModelCatalogResponse:
        active_model_id = get_active_lm_studio_model_id(self.settings)
        fallback = self._fallback_models(active_model_id)
        try:
            entries = await self._live_entries()
        except LMStudioUnavailableError as exc:
            return LMStudioModelCatalogResponse(
                status="unavailable",
                reachable=False,
                active_model_id=active_model_id,
                configured_model_id=self.settings.qwen_model_id,
                models=fallback,
                error=str(exc),
            )

        live_models = [
            normalized
            for entry in entries
            if (normalized := self._normalize_live_model(
                entry,
                active_model_id=active_model_id,
            ))
            is not None
        ]
        live_identifiers = {
            identifier
            for model in live_models
            for identifier in (model.key, model.model_id, *model.loaded_instance_ids)
        }
        combined = [
            *live_models,
            *[
                model
                for model in fallback
                if model.model_id not in live_identifiers
            ],
        ]
        combined.sort(
            key=lambda model: (
                not model.selected,
                not model.loaded,
                model.display_name.casefold(),
            )
        )
        return LMStudioModelCatalogResponse(
            status="ok",
            reachable=True,
            active_model_id=active_model_id,
            configured_model_id=self.settings.qwen_model_id,
            models=combined,
        )

    async def activate(self, requested_model_id: str) -> LMStudioModelActivateResponse:
        if not _MODEL_ID_RE.fullmatch(requested_model_id):
            raise LMStudioModelNotFoundError("Invalid LM Studio model identifier")

        entries = await self._live_entries()
        active_before = get_active_lm_studio_model_id(self.settings)
        live_models = [
            normalized
            for entry in entries
            if (normalized := self._normalize_live_model(
                entry,
                active_model_id=active_before,
            ))
            is not None
        ]
        requested = next(
            (
                model
                for model in live_models
                if requested_model_id
                in {model.key, model.model_id, *model.loaded_instance_ids}
            ),
            None,
        )
        if requested is None:
            raise LMStudioModelNotFoundError(
                "LM Studio does not report the requested local model"
            )

        instance_id = next(
            (
                model_id
                for model_id in requested.loaded_instance_ids
                if model_id == requested_model_id
            ),
            requested.loaded_instance_ids[0] if requested.loaded_instance_ids else None,
        )
        previous_models = [
            model
            for model in live_models
            if model.key != requested.key
            and model.loaded
        ]
        unloaded_previous: list[LMStudioModelRead] = []
        load_time_seconds: float | None = None
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(900.0, connect=3.0),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                for previous in previous_models:
                    for previous_instance_id in previous.loaded_instance_ids:
                        response = await client.post(
                            f"{self.native_base_url}/models/unload",
                            json={"instance_id": previous_instance_id},
                        )
                        response.raise_for_status()
                    unloaded_previous.append(previous)
                if instance_id is None:
                    response = await client.post(
                        f"{self.native_base_url}/models/load",
                        json={
                            "model": requested.key,
                            "context_length": 8192,
                            "flash_attention": True,
                            "echo_load_config": True,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    raw_instance_id = (
                        payload.get("instance_id")
                        if isinstance(payload, dict)
                        else None
                    )
                    if (
                        not isinstance(raw_instance_id, str)
                        or not _MODEL_ID_RE.fullmatch(raw_instance_id)
                    ):
                        raise LMStudioUnavailableError(
                            "LM Studio did not return a safe loaded model identifier"
                        )
                    instance_id = raw_instance_id
                    raw_load_time = payload.get("load_time_seconds")
                    if isinstance(raw_load_time, (int, float)) and raw_load_time >= 0:
                        load_time_seconds = float(raw_load_time)
        except (
            httpx.HTTPError,
            ValueError,
            json.JSONDecodeError,
            LMStudioUnavailableError,
        ) as exc:
            # A switch may have released the prior model to make VRAM available.
            # Best-effort restoration keeps the last persisted selection usable
            # when loading the replacement fails.
            for previous in unloaded_previous:
                try:
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(900.0, connect=3.0),
                        follow_redirects=False,
                        transport=self.transport,
                    ) as recovery_client:
                        recovery = await recovery_client.post(
                            f"{self.native_base_url}/models/load",
                            json={
                                "model": previous.key,
                                "context_length": 8192,
                                "flash_attention": True,
                            },
                        )
                        recovery.raise_for_status()
                except (httpx.HTTPError, ValueError):
                    pass
            raise LMStudioUnavailableError(str(exc)) from exc

        selected_model = requested.model_copy(
            update={
                "model_id": instance_id,
                "loaded": True,
                "selected": True,
                "loaded_instance_ids": sorted(
                    {*requested.loaded_instance_ids, instance_id}
                ),
            }
        )
        _write_selection(
            self.settings,
            model_id=instance_id,
            key=requested.key,
            display_name=requested.display_name,
            filename=requested.filename,
        )
        return LMStudioModelActivateResponse(
            status="active",
            active_model_id=instance_id,
            loaded=True,
            load_time_seconds=load_time_seconds,
            model=selected_model,
        )
