"""Persistent, operator-owned ComfyUI API workflow library.

The runtime catalog remains an evidence registry.  This library is a separate
mutable surface for workflows that an operator imports, edits, and explicitly
submits through the local ComfyAPI Runner.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WORKFLOW_SCHEMA = "sineforge.api-caller-workflow.v1"
MAX_WORKFLOW_BYTES = 8 * 1024 * 1024


class ApiWorkflowError(ValueError):
    """Base error for the local API workflow library."""


class ApiWorkflowNotFound(ApiWorkflowError):
    pass


class ApiWorkflowValidationError(ApiWorkflowError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def workflow_sha256(workflow: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(workflow).encode("utf-8")).hexdigest()


def normalize_api_workflow(value: object) -> dict[str, Any]:
    """Accept common API wrappers and return a validated API prompt graph."""

    if not isinstance(value, dict):
        raise ApiWorkflowValidationError("Workflow JSON must be an object.")

    candidate: object = value
    if isinstance(value.get("prompt"), dict):
        candidate = value["prompt"]
    elif (
        isinstance(value.get("workflow"), dict)
        and not any(
            isinstance(node, dict) and "class_type" in node
            for node in value.values()
        )
    ):
        candidate = value["workflow"]

    if not isinstance(candidate, dict) or not candidate:
        raise ApiWorkflowValidationError("Workflow must contain at least one API node.")

    normalized: dict[str, Any] = {}
    errors: list[str] = []
    for raw_node_id, raw_node in candidate.items():
        node_id = str(raw_node_id)
        if not isinstance(raw_node, dict):
            errors.append(f"Node {node_id} must be an object.")
            continue
        class_type = raw_node.get("class_type")
        inputs = raw_node.get("inputs")
        if not isinstance(class_type, str) or not class_type.strip():
            errors.append(f"Node {node_id} is missing class_type.")
        if not isinstance(inputs, dict):
            errors.append(f"Node {node_id} is missing an inputs object.")
        normalized[node_id] = raw_node

    if errors:
        preview = " ".join(errors[:8])
        if len(errors) > 8:
            preview += f" (+{len(errors) - 8} more)"
        raise ApiWorkflowValidationError(
            f"Only ComfyUI API-format workflow JSON can be queued. {preview}"
        )

    encoded = _stable_json(normalized).encode("utf-8")
    if len(encoded) > MAX_WORKFLOW_BYTES:
        raise ApiWorkflowValidationError(
            f"Workflow exceeds the {MAX_WORKFLOW_BYTES // (1024 * 1024)} MiB library limit."
        )
    return normalized


class ApiWorkflowLibrary:
    """JSON-file library with atomic writes and recoverable removal."""

    def __init__(self, storage_root: Path) -> None:
        root = Path(storage_root).expanduser().resolve()
        self.root = (root / "api_workflows").resolve()
        self.archive_root = (root / "api_workflow_archive").resolve()
        self._lock = threading.RLock()

    def _ensure_roots(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.archive_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_id(workflow_id: str | uuid.UUID) -> str:
        try:
            return str(uuid.UUID(str(workflow_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ApiWorkflowNotFound("Workflow was not found.") from exc

    def _path(self, workflow_id: str | uuid.UUID) -> Path:
        safe_id = self._safe_id(workflow_id)
        path = (self.root / f"{safe_id}.json").resolve()
        if path.parent != self.root:
            raise ApiWorkflowNotFound("Workflow was not found.")
        return path

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        workflow = record["workflow"]
        return {
            "id": record["id"],
            "name": record["name"],
            "version": record["version"],
            "description": record.get("description"),
            "source_kind": record.get("source_kind"),
            "source_id": record.get("source_id"),
            "source_filename": record.get("source_filename"),
            "node_count": len(workflow),
            "sha256": record["sha256"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }

    @classmethod
    def _detail(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {**cls._summary(record), "workflow": record["workflow"]}

    def _read_path(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApiWorkflowValidationError(
                f"Stored workflow {path.name} could not be read: {exc}"
            ) from exc
        if not isinstance(payload, dict) or payload.get("schema") != WORKFLOW_SCHEMA:
            raise ApiWorkflowValidationError(
                f"Stored workflow {path.name} has an unsupported schema."
            )
        payload["workflow"] = normalize_api_workflow(payload.get("workflow"))
        return payload

    def _write_record(self, record: dict[str, Any]) -> None:
        self._ensure_roots()
        destination = self._path(record["id"])
        temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)

    def list(self) -> list[dict[str, Any]]:
        self._ensure_roots()
        records: list[dict[str, Any]] = []
        with self._lock:
            for path in self.root.glob("*.json"):
                records.append(self._read_path(path))
        records.sort(
            key=lambda item: (
                str(item.get("updated_at") or ""),
                str(item.get("name") or "").casefold(),
            ),
            reverse=True,
        )
        return [self._summary(record) for record in records]

    def get(self, workflow_id: str | uuid.UUID) -> dict[str, Any]:
        path = self._path(workflow_id)
        with self._lock:
            if not path.is_file():
                raise ApiWorkflowNotFound("Workflow was not found.")
            return self._detail(self._read_path(path))

    def create(
        self,
        *,
        name: str,
        version: str,
        description: str | None,
        workflow: object,
        source_kind: str | None = None,
        source_id: str | None = None,
        source_filename: str | None = None,
    ) -> dict[str, Any]:
        cleaned_name = name.strip()
        cleaned_version = version.strip()
        if not cleaned_name:
            raise ApiWorkflowValidationError("Workflow name is required.")
        if not cleaned_version:
            raise ApiWorkflowValidationError("Workflow version is required.")
        normalized = normalize_api_workflow(workflow)
        now = _utc_now()
        record = {
            "schema": WORKFLOW_SCHEMA,
            "id": str(uuid.uuid4()),
            "name": cleaned_name,
            "version": cleaned_version,
            "description": description.strip() if description and description.strip() else None,
            "source_kind": source_kind,
            "source_id": source_id,
            "source_filename": source_filename,
            "workflow": normalized,
            "sha256": workflow_sha256(normalized),
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._write_record(record)
        return self._detail(record)

    def update(
        self,
        workflow_id: str | uuid.UUID,
        *,
        name: str | None = None,
        version: str | None = None,
        description: str | None = None,
        workflow: object | None = None,
    ) -> dict[str, Any]:
        path = self._path(workflow_id)
        with self._lock:
            if not path.is_file():
                raise ApiWorkflowNotFound("Workflow was not found.")
            record = self._read_path(path)
            if name is not None:
                if not name.strip():
                    raise ApiWorkflowValidationError("Workflow name cannot be empty.")
                record["name"] = name.strip()
            if version is not None:
                if not version.strip():
                    raise ApiWorkflowValidationError("Workflow version cannot be empty.")
                record["version"] = version.strip()
            if description is not None:
                record["description"] = description.strip() or None
            if workflow is not None:
                normalized = normalize_api_workflow(workflow)
                record["workflow"] = normalized
                record["sha256"] = workflow_sha256(normalized)
            record["updated_at"] = _utc_now()
            self._write_record(record)
            return self._detail(record)

    def upsert_runner_workflow(
        self,
        *,
        source_id: str,
        name: str,
        description: str | None,
        workflow: object,
        source_filename: str | None,
    ) -> tuple[dict[str, Any], bool]:
        with self._lock:
            existing = next(
                (
                    item
                    for item in self.list()
                    if item.get("source_kind") == "comfy_api_runner_static"
                    and item.get("source_id") == source_id
                ),
                None,
            )
            if existing is None:
                return (
                    self.create(
                        name=name,
                        version="1.0",
                        description=description,
                        workflow=workflow,
                        source_kind="comfy_api_runner_static",
                        source_id=source_id,
                        source_filename=source_filename,
                    ),
                    True,
                )
            return (
                self.update(
                    existing["id"],
                    name=name,
                    description=description or "",
                    workflow=workflow,
                ),
                False,
            )

    def remove(self, workflow_id: str | uuid.UUID) -> dict[str, Any]:
        path = self._path(workflow_id)
        with self._lock:
            if not path.is_file():
                raise ApiWorkflowNotFound("Workflow was not found.")
            record = self._read_path(path)
            self._ensure_roots()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            archive_path = (
                self.archive_root / f"{record['id']}-{timestamp}.json"
            ).resolve()
            if archive_path.parent != self.archive_root:
                raise ApiWorkflowError("Archive target was rejected.")
            os.replace(path, archive_path)
            return {
                "ok": True,
                "id": record["id"],
                "name": record["name"],
                "archived": True,
            }
