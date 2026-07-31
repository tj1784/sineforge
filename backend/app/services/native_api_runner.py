"""First-party SineForge ComfyUI API workflow analysis and state helpers.

This module deliberately does not import or call the separately supervised
ComfyAPI Runner.  Native Runner workflows live in their own operator-owned
library and are submitted directly to the configured ComfyUI instance by the
route layer.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from backend.app.services.api_workflows import (
    WORKFLOW_SCHEMA,
    ApiWorkflowError,
    ApiWorkflowLibrary,
    ApiWorkflowNotFound,
    ApiWorkflowValidationError,
    normalize_api_workflow,
    workflow_sha256,
)


NATIVE_RUNNER_SCHEMA = "sineforge.native-api-runner/v1"
MODEL_INPUT_MARKERS = (
    "audio_vae",
    "base_model",
    "checkpoint",
    "ckpt",
    "clip_",
    "clip_name",
    "control_net",
    "diffusion_model",
    "lora",
    "model_name",
    "text_encoder",
    "unet",
    "upscale_model",
    "vae",
    "vae_name",
)
PROMPT_INPUT_MARKERS = (
    "prompt",
    "positive",
    "negative",
    "request_json",
    "text",
)
MEDIA_INPUT_NAMES = frozenset({"audio", "image", "images", "mask", "video"})
MEDIA_INPUT_PREFIXES = (
    "end_",
    "init_",
    "input_",
    "reference_",
    "source_",
    "start_",
)
MEDIA_INPUT_SUFFIXES = ("_file", "_filename", "_path")


class NativeRepositoryWorkflowReadOnly(ApiWorkflowError):
    """Raised when a caller tries to mutate a bundled workflow record."""


class NativeApiWorkflowLibrary(ApiWorkflowLibrary):
    """Repository-backed shared library isolated from the legacy API Caller.

    Repository records are immutable and authoritative. Operator-created
    workflows remain editable and archivable in runtime storage.
    """

    def __init__(
        self,
        storage_root: Path,
        *,
        include_repository: bool = True,
    ) -> None:
        super().__init__(storage_root)
        root = Path(storage_root).expanduser().resolve()
        self.storage_root = root
        self.root = (root / "native_api_runner" / "workflows").resolve()
        self.archive_root = (root / "native_api_runner" / "archive").resolve()
        self.tombstone_root = (root / "native_api_runner" / "tombstones").resolve()
        self.repository_root = (
            (
                Path(__file__).resolve().parents[1]
                / "resources"
                / "native_workflow_library"
                / "records"
            ).resolve()
            if include_repository
            else (root / "native_api_runner" / "disabled_repository").resolve()
        )
        self._lock = threading.RLock()

    def _ensure_roots(self) -> None:
        super()._ensure_roots()
        self.tombstone_root.mkdir(parents=True, exist_ok=True)

    def _repository_path(self, workflow_id: str | uuid.UUID) -> Path:
        safe_id = self._safe_id(workflow_id)
        path = (self.repository_root / f"{safe_id}.json").resolve()
        if path.parent != self.repository_root:
            raise ApiWorkflowNotFound("Workflow was not found.")
        return path

    def _tombstone_path(self, workflow_id: str | uuid.UUID) -> Path:
        safe_id = self._safe_id(workflow_id)
        path = (self.tombstone_root / f"{safe_id}.json").resolve()
        if path.parent != self.tombstone_root:
            raise ApiWorkflowNotFound("Workflow was not found.")
        return path

    def _is_tombstoned(self, workflow_id: str | uuid.UUID) -> bool:
        return self._tombstone_path(workflow_id).is_file()

    def _existing_path(self, workflow_id: str | uuid.UUID) -> tuple[Path, bool]:
        repository_path = self._repository_path(workflow_id)
        if repository_path.is_file():
            return repository_path, True
        runtime_path = self._path(workflow_id)
        if runtime_path.is_file():
            return runtime_path, False
        raise ApiWorkflowNotFound("Workflow was not found.")

    @staticmethod
    def _catalog_fields(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "category": record.get("category") or "Uncategorized",
            "subcategory": record.get("subcategory") or "General",
            "episode": record.get("episode"),
            "instructions": record.get("instructions"),
            "tags": list(record.get("tags") or []),
            "requirements": dict(record.get("requirements") or {}),
            "workflow_status": record.get("workflow_status") or "converted",
            "repository_managed": bool(record.get("repository_managed")),
            "is_overridden": bool(record.get("is_overridden")),
            "source_archive": record.get("source_archive"),
            "source_entry": record.get("source_entry"),
        }

    @classmethod
    def _summary(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            **ApiWorkflowLibrary._summary(record),
            **cls._catalog_fields(record),
        }

    @classmethod
    def _detail(cls, record: dict[str, Any]) -> dict[str, Any]:
        return {
            **cls._summary(record),
            "workflow": record["workflow"],
            "source_workflow": record.get("source_workflow"),
            "source_workflow_sha256": record.get("source_workflow_sha256"),
        }

    def list(self) -> list[dict[str, Any]]:
        self._ensure_roots()
        records_by_id: dict[str, dict[str, Any]] = {}
        with self._lock:
            if self.repository_root.is_dir():
                for path in self.repository_root.glob("*.json"):
                    record = self._read_path(path)
                    records_by_id[record["id"]] = record
            for path in self.root.glob("*.json"):
                record = self._read_path(path)
                if record["id"] not in records_by_id:
                    records_by_id[record["id"]] = record
        records = list(records_by_id.values())
        records.sort(
            key=lambda item: (
                str(item.get("category") or "").casefold(),
                str(item.get("subcategory") or "").casefold(),
                str(item.get("episode") or ""),
                str(item.get("name") or "").casefold(),
            )
        )
        return [self._summary(record) for record in records]

    def get(self, workflow_id: str | uuid.UUID) -> dict[str, Any]:
        with self._lock:
            path, _ = self._existing_path(workflow_id)
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
        category: str = "Uncategorized",
        subcategory: str = "General",
        episode: str | None = None,
        instructions: str | None = None,
        tags: list[str] | None = None,
        requirements: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cleaned_name = name.strip()
        cleaned_version = version.strip()
        if not cleaned_name:
            raise ApiWorkflowValidationError("Workflow name is required.")
        if not cleaned_version:
            raise ApiWorkflowValidationError("Workflow version is required.")
        normalized = normalize_api_workflow(workflow)
        now = datetime.now(UTC).isoformat()
        record = {
            "schema": WORKFLOW_SCHEMA,
            "id": str(uuid.uuid4()),
            "name": cleaned_name,
            "version": cleaned_version,
            "description": description.strip() if description and description.strip() else None,
            "category": category.strip() or "Uncategorized",
            "subcategory": subcategory.strip() or "General",
            "episode": episode.strip() if episode and episode.strip() else None,
            "instructions": instructions.strip() if instructions and instructions.strip() else None,
            "tags": sorted({tag.strip() for tag in tags or [] if tag.strip()}),
            "requirements": requirements or {},
            "workflow_status": "converted",
            "repository_managed": False,
            "is_overridden": False,
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
        category: str | None = None,
        subcategory: str | None = None,
        episode: str | None = None,
        instructions: str | None = None,
        tags: list[str] | None = None,
        requirements: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            path, repository_record = self._existing_path(workflow_id)
            if repository_record:
                raise NativeRepositoryWorkflowReadOnly(
                    "Repository workflows are read-only. Use Save as copy to create "
                    "an editable operator workflow."
                )
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
            if category is not None:
                record["category"] = category.strip() or "Uncategorized"
            if subcategory is not None:
                record["subcategory"] = subcategory.strip() or "General"
            if episode is not None:
                record["episode"] = episode.strip() or None
            if instructions is not None:
                record["instructions"] = instructions.strip() or None
            if tags is not None:
                record["tags"] = sorted(
                    {tag.strip() for tag in tags if tag.strip()}
                )
            if requirements is not None:
                record["requirements"] = requirements
            if workflow is not None:
                normalized = normalize_api_workflow(workflow)
                record["workflow"] = normalized
                record["sha256"] = workflow_sha256(normalized)
                record["workflow_status"] = (
                    "requires_custom_nodes"
                    if any(
                        str(node.get("class_type") or "").startswith("UNRESOLVED::")
                        for node in normalized.values()
                    )
                    else "converted"
                )
            record["updated_at"] = datetime.now(UTC).isoformat()
            self._write_record(record)
            return self._detail(record)

    def remove(self, workflow_id: str | uuid.UUID) -> dict[str, Any]:
        with self._lock:
            path, repository_record = self._existing_path(workflow_id)
            if repository_record:
                raise NativeRepositoryWorkflowReadOnly(
                    "Repository workflows are read-only and cannot be archived."
                )
            return super().remove(workflow_id)


class NativeApiRunnerStateStore:
    """Durable ownership and idempotency records for native ComfyUI prompts.

    This small SQLite database is deliberately separate from both workflow
    libraries.  It makes an accepted render discoverable after a backend
    restart and prevents the same idempotency key from submitting an expensive
    duplicate graph from another SineForge worker.
    """

    def __init__(self, storage_root: Path) -> None:
        root = Path(storage_root).expanduser().resolve()
        state_root = (root / "native_api_runner").resolve()
        state_root.mkdir(parents=True, exist_ok=True)
        self.path = state_root / "state.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    idempotency_key TEXT PRIMARY KEY,
                    workflow_sha256 TEXT NOT NULL,
                    prompt_id TEXT UNIQUE,
                    client_id TEXT NOT NULL,
                    response_json TEXT,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    ix_native_runner_submissions_prompt_id
                ON submissions(prompt_id)
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        response: dict[str, Any] | None = None
        raw_response = row["response_json"]
        if isinstance(raw_response, str) and raw_response:
            parsed = json.loads(raw_response)
            response = parsed if isinstance(parsed, dict) else None
        return {
            "idempotency_key": str(row["idempotency_key"]),
            "workflow_sha256": str(row["workflow_sha256"]),
            "prompt_id": (
                str(row["prompt_id"]) if row["prompt_id"] is not None else None
            ),
            "client_id": str(row["client_id"]),
            "response": response,
            "state": str(row["state"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def get_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT idempotency_key, workflow_sha256, prompt_id, client_id,
                       response_json, state, created_at, updated_at
                FROM submissions
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
        return self._row(row)

    def get_by_prompt_id(self, prompt_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT idempotency_key, workflow_sha256, prompt_id, client_id,
                       response_json, state, created_at, updated_at
                FROM submissions
                WHERE prompt_id = ?
                """,
                (prompt_id,),
            ).fetchone()
        return self._row(row)

    def reserve(
        self,
        *,
        idempotency_key: str,
        workflow_sha256: str,
        client_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        """Atomically reserve an idempotency key across backend processes."""

        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT idempotency_key, workflow_sha256, prompt_id, client_id,
                       response_json, state, created_at, updated_at
                FROM submissions
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                connection.commit()
                existing = self._row(row)
                assert existing is not None
                return False, existing
            connection.execute(
                """
                INSERT INTO submissions (
                    idempotency_key, workflow_sha256, prompt_id, client_id,
                    response_json, state, created_at, updated_at
                )
                VALUES (?, ?, NULL, ?, NULL, 'submitting', ?, ?)
                """,
                (idempotency_key, workflow_sha256, client_id, now, now),
            )
            connection.commit()
        created = self.get_by_idempotency_key(idempotency_key)
        assert created is not None
        return True, created

    def complete_submission(
        self,
        *,
        idempotency_key: str,
        workflow_sha256: str,
        prompt_id: str,
        client_id: str,
        response: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        encoded = json.dumps(response, separators=(",", ":"), sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET workflow_sha256 = ?, prompt_id = ?, client_id = ?,
                    response_json = ?, state = 'pending', updated_at = ?
                WHERE idempotency_key = ?
                """,
                (
                    workflow_sha256,
                    prompt_id,
                    client_id,
                    encoded,
                    now,
                    idempotency_key,
                ),
            )

    def release_unsubmitted_reservation(
        self,
        *,
        idempotency_key: str,
        client_id: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM submissions
                WHERE idempotency_key = ?
                  AND client_id = ?
                  AND prompt_id IS NULL
                  AND state = 'submitting'
                """,
                (idempotency_key, client_id),
            )

    def update_prompt_state(self, prompt_id: str, state: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET state = ?, updated_at = ?
                WHERE prompt_id = ?
                """,
                (state, now, prompt_id),
            )


def _node_title(node: dict[str, Any]) -> str:
    metadata = node.get("_meta")
    if isinstance(metadata, dict):
        title = metadata.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return str(node.get("class_type") or "Unknown node")


def _editable_field(
    *,
    node_id: str,
    node: dict[str, Any],
    input_name: str,
    value: str | int | float | bool,
) -> dict[str, Any]:
    if isinstance(value, bool):
        value_type = "bool"
    elif isinstance(value, int):
        value_type = "int"
    elif isinstance(value, float):
        value_type = "float"
    else:
        value_type = "str"
    title = _node_title(node)
    return {
        "nodeId": node_id,
        "classType": str(node["class_type"]),
        "title": title,
        "input": input_name,
        "value": value,
        "valueType": value_type,
        "label": f"{node_id} | {title} | {input_name}",
    }


def _issue(
    severity: Literal["error", "warning", "info"],
    code: str,
    message: str,
    *,
    node_id: str | None = None,
    input_name: str | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "nodeId": node_id,
        "input": input_name,
    }


def _declared_inputs(class_info: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    input_info = class_info.get("input")
    if not isinstance(input_info, dict):
        return {}, {}
    required = input_info.get("required")
    optional = input_info.get("optional")
    return (
        required if isinstance(required, dict) else {},
        optional if isinstance(optional, dict) else {},
    )


def _allowed_values(input_definition: Any) -> list[str] | None:
    if not isinstance(input_definition, (list, tuple)) or not input_definition:
        return None
    values = input_definition[0]
    if not isinstance(values, (list, tuple)):
        return None
    return [str(value) for value in values]


def _declared_input_type(input_definition: Any) -> str | None:
    if not isinstance(input_definition, (list, tuple)) or not input_definition:
        return None
    declared_type = input_definition[0]
    return declared_type if isinstance(declared_type, str) else None


def _is_model_input(input_key: str) -> bool:
    return any(marker in input_key for marker in MODEL_INPUT_MARKERS)


def _is_media_input(input_key: str) -> bool:
    """Identify actual media paths without treating media settings as files.

    The old substring check classified ``audio_vae``, ``video_size``,
    ``ratio_from_image``, and ``override_audio`` as upload targets.
    """

    if input_key in MEDIA_INPUT_NAMES:
        return True
    if any(input_key.endswith(suffix) for suffix in MEDIA_INPUT_SUFFIXES):
        return any(media in input_key for media in MEDIA_INPUT_NAMES)
    return any(
        input_key.startswith(prefix)
        and input_key.removeprefix(prefix) in MEDIA_INPUT_NAMES
        for prefix in MEDIA_INPUT_PREFIXES
    )


def _link_types_compatible(source_type: Any, target_type: str | None) -> bool:
    if not isinstance(source_type, str) or target_type is None:
        return True
    if source_type == target_type:
        return True
    if source_type in {"*", "ANY"} or target_type in {"*", "ANY"}:
        return True
    # A few custom nodes advertise unions as comma-delimited strings. The
    # live ComfyUI validator remains authoritative for those definitions.
    if "," in source_type or "," in target_type:
        return True
    return False


def analyze_native_workflow(
    value: object,
    object_info: dict[str, Any],
) -> dict[str, Any]:
    """Validate one API graph against the live ComfyUI node registry."""

    workflow = normalize_api_workflow(value)
    editable: list[dict[str, Any]] = []
    prompt_fields: list[dict[str, Any]] = []
    media_targets: list[dict[str, Any]] = []
    model_refs: list[dict[str, Any]] = []
    output_nodes: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for node_id, raw_node in workflow.items():
        node = raw_node if isinstance(raw_node, dict) else {}
        class_type = str(node.get("class_type") or "")
        title = _node_title(node)
        class_info = object_info.get(class_type)
        if not isinstance(class_info, dict):
            issues.append(
                _issue(
                    "error",
                    "NODE_CLASS_UNAVAILABLE",
                    f"{class_type} is not installed in the connected ComfyUI runtime.",
                    node_id=node_id,
                )
            )
            continue

        required, optional = _declared_inputs(class_info)
        inputs = node.get("inputs")
        node_inputs = inputs if isinstance(inputs, dict) else {}
        for required_name in required:
            if required_name not in node_inputs:
                issues.append(
                    _issue(
                        "error",
                        "REQUIRED_INPUT_MISSING",
                        f"{title} is missing required input {required_name}.",
                        node_id=node_id,
                        input_name=required_name,
                    )
                )

        declared = {**required, **optional}
        for input_name, input_value in node_inputs.items():
            input_key = input_name.casefold()
            if input_name not in declared:
                issues.append(
                    _issue(
                        "warning",
                        "INPUT_NOT_DECLARED",
                        f"{title}.{input_name} is not declared by the live node definition.",
                        node_id=node_id,
                        input_name=input_name,
                    )
                )

            if (
                isinstance(input_value, list)
                and len(input_value) == 2
                and isinstance(input_value[0], (str, int))
                and isinstance(input_value[1], int)
                and not isinstance(input_value[1], bool)
            ):
                source_node_id = str(input_value[0])
                output_index = input_value[1]
                if source_node_id not in workflow:
                    issues.append(
                        _issue(
                            "error",
                            "LINK_SOURCE_MISSING",
                            (
                                f"{title}.{input_name} references missing "
                                f"node {source_node_id}."
                            ),
                            node_id=node_id,
                            input_name=input_name,
                        )
                    )
                elif source_node_id == node_id:
                    issues.append(
                        _issue(
                            "error",
                            "LINK_SELF_REFERENCE",
                            f"{title}.{input_name} cannot reference its own node.",
                            node_id=node_id,
                            input_name=input_name,
                        )
                    )
                else:
                    source_node = workflow.get(source_node_id)
                    source_class = (
                        str(source_node.get("class_type") or "")
                        if isinstance(source_node, dict)
                        else ""
                    )
                    source_info = object_info.get(source_class)
                    source_outputs = (
                        source_info.get("output")
                        if isinstance(source_info, dict)
                        else None
                    )
                    if (
                        isinstance(source_outputs, (list, tuple))
                        and output_index >= len(source_outputs)
                    ):
                        issues.append(
                            _issue(
                                "error",
                                "LINK_OUTPUT_INVALID",
                                (
                                    f"{title}.{input_name} references output "
                                    f"{output_index} on {source_node_id}, but that node "
                                    f"declares {len(source_outputs)} outputs."
                                ),
                                node_id=node_id,
                                input_name=input_name,
                            )
                        )
                    elif isinstance(source_outputs, (list, tuple)):
                        source_type = source_outputs[output_index]
                        target_type = _declared_input_type(
                            declared.get(input_name)
                        )
                        if not _link_types_compatible(source_type, target_type):
                            issues.append(
                                _issue(
                                    "error",
                                    "LINK_TYPE_MISMATCH",
                                    (
                                        f"{title}.{input_name} expects "
                                        f"{target_type}, but {source_node_id} "
                                        f"output {output_index} provides "
                                        f"{source_type}."
                                    ),
                                    node_id=node_id,
                                    input_name=input_name,
                                )
                            )
                if output_index < 0:
                    issues.append(
                        _issue(
                            "error",
                            "LINK_OUTPUT_INVALID",
                            (
                                f"{title}.{input_name} references invalid "
                                f"output index {output_index}."
                            ),
                            node_id=node_id,
                            input_name=input_name,
                        )
                    )

            if isinstance(input_value, (str, int, float, bool)):
                field = _editable_field(
                    node_id=node_id,
                    node=node,
                    input_name=input_name,
                    value=input_value,
                )
                editable.append(field)
                if any(marker in input_key for marker in PROMPT_INPUT_MARKERS):
                    prompt_fields.append(field)
                if _is_media_input(input_key):
                    media_targets.append(field)

            if isinstance(input_value, str) and _is_model_input(input_key):
                allowed = _allowed_values(declared.get(input_name))
                available = None if allowed is None else input_value in allowed
                model_refs.append(
                    {
                        "nodeId": node_id,
                        "title": title,
                        "classType": class_type,
                        "input": input_name,
                        "name": input_value,
                        "available": available,
                    }
                )
                if available is False:
                    issues.append(
                        _issue(
                            "error",
                            "MODEL_REFERENCE_UNAVAILABLE",
                            f"{input_value} is not available for {title}.{input_name}.",
                            node_id=node_id,
                            input_name=input_name,
                        )
                    )

        if bool(class_info.get("output_node")):
            output_nodes.append(
                {
                    "nodeId": node_id,
                    "classType": class_type,
                    "title": title,
                }
            )

    if not output_nodes:
        issues.append(
            _issue(
                "error",
                "OUTPUT_NODE_MISSING",
                "The graph has no live ComfyUI output node.",
            )
        )

    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    return {
        "schema": NATIVE_RUNNER_SCHEMA,
        "ok": error_count == 0,
        "format": "comfyui_api",
        "queueable": error_count == 0,
        "workflowSha256": workflow_sha256(workflow),
        "nodeCount": len(workflow),
        "editable": editable,
        "mediaTargets": media_targets,
        "promptFields": prompt_fields,
        "outputNodes": output_nodes,
        "modelRefs": model_refs,
        "issues": issues,
        "errorCount": error_count,
        "warningCount": warning_count,
    }


def summarize_queue(queue: object) -> dict[str, Any]:
    payload = queue if isinstance(queue, dict) else {}

    def summarize(rows: object, state: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, list):
                continue
            prompt_id = str(row[1]) if len(row) > 1 else ""
            if not prompt_id:
                continue
            extra = row[3] if len(row) > 3 and isinstance(row[3], dict) else {}
            result.append(
                {
                    "promptId": prompt_id,
                    "queueNumber": row[0] if row else None,
                    "state": state,
                    "clientId": extra.get("client_id"),
                }
            )
        return result

    running = summarize(payload.get("queue_running"), "running")
    pending = summarize(payload.get("queue_pending"), "pending")
    return {
        "running": running,
        "pending": pending,
        "runningCount": len(running),
        "pendingCount": len(pending),
    }


def _output_files(outputs: object) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    if not isinstance(outputs, dict):
        return result
    for node_id, node_outputs in outputs.items():
        if not isinstance(node_outputs, dict):
            continue
        for output_kind, entries in node_outputs.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
                    continue
                key = (
                    entry["filename"],
                    str(entry.get("subfolder") or ""),
                    str(entry.get("type") or "output"),
                )
                if key in seen:
                    continue
                seen.add(key)
                result.append(
                    {
                        "nodeId": str(node_id),
                        "kind": str(output_kind),
                        "filename": key[0],
                        "subfolder": key[1],
                        "type": key[2],
                    }
                )
    return result


def summarize_history(
    prompt_id: str,
    history: object,
    queue: object,
) -> dict[str, Any]:
    queue_summary = summarize_queue(queue)
    queued = next(
        (
            item
            for item in [*queue_summary["running"], *queue_summary["pending"]]
            if item["promptId"] == prompt_id
        ),
        None,
    )
    payload = history if isinstance(history, dict) else {}
    record = payload.get(prompt_id)
    if isinstance(record, dict):
        status = record.get("status")
        status_info = status if isinstance(status, dict) else {}
        status_text = str(status_info.get("status_str") or "").casefold()
        messages = status_info.get("messages")
        message_rows = messages if isinstance(messages, list) else []
        failed = status_text in {
            "error",
            "failed",
            "interrupted",
            "cancelled",
            "canceled",
        } or any(
            isinstance(message, (list, tuple))
            and message
            and str(message[0]).casefold() in {"execution_error", "execution_interrupted"}
            for message in message_rows
        )
        state = (
            "failed"
            if failed
            else "completed"
            if status_info.get("completed")
            else queued["state"]
            if queued is not None
            else "running"
        )
        return {
            "promptId": prompt_id,
            "state": state,
            "completed": bool(status_info.get("completed")),
            "status": status_info.get("status_str"),
            "outputs": _output_files(record.get("outputs")),
            "messages": message_rows[-20:],
        }
    if queued is not None:
        return {
            "promptId": prompt_id,
            "state": queued["state"],
            "completed": False,
            "status": queued["state"],
            "outputs": [],
            "messages": [],
        }
    return {
        "promptId": prompt_id,
        "state": "unknown",
        "completed": False,
        "status": "not_found",
        "outputs": [],
        "messages": [],
    }
