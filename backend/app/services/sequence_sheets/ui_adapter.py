"""Boundary adapter from the Studio Sequence UI payload to the canonical sheet."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from backend.app.schemas.sequence_sheet import (
    DiagnosticSeverity,
    SEQUENCE_SHEET_SCHEMA_VERSION,
    SequenceSheetDiagnostic,
    SequenceSheetImportResult,
)
from backend.app.core.errors import UnsafePathError
from backend.app.services.production_profiles import (
    ProductionProfileError,
    canonical_production_profile_ref,
)
from backend.app.services.sequence_sheets.importers import (
    import_sequence_sheet_json,
)
from backend.app.utils.path_safety import sanitize_output_prefix


_ROW_LAST_FRAME = re.compile(r"^row:(.+):last_frame$")
_UI_ROW_FIELDS = frozenset(
    {
        "row_id",
        "order",
        "enabled",
        "scene_id",
        "subscene_id",
        "template_key",
        "workflow_version",
        "workflow_sha256",
        "model_profile",
        "mode",
        "generation_mode",
        "duration_sec",
        "prompt",
        "negative_prompt",
        "seed",
        "continuity_source",
        "input_asset_id",
        "depends_on_row_ids",
        "character_ids",
        "asset_ids",
        "reference_asset_ids",
        "output_name",
        "max_attempts",
        "on_error",
    }
)


def _error(
    *,
    code: str,
    message: str,
    source_row: int | None = None,
    column: str | None = None,
    row_id: str | None = None,
) -> SequenceSheetDiagnostic:
    return SequenceSheetDiagnostic(
        severity=DiagnosticSeverity.ERROR,
        code=code,
        message=message,
        source_row=source_row,
        column=column,
        row_id=row_id,
    )


def adapt_studio_sequence_payload(
    source: Mapping[str, Any],
    *,
    workflow_versions: Mapping[str, str] | None = None,
    default_workflow_version: str = "1.0",
) -> SequenceSheetImportResult:
    """Normalize current Studio field names and inline continuity references.

    Disabled UI rows are intentionally omitted before dependency validation, so
    ``previous_last_frame`` means the preceding enabled row.  ``scene_id`` and
    ``subscene_id`` are validated but remain route-owned metadata in v1;
    ``max_attempts`` and ``on_error`` are likewise validated here and consumed
    by the orchestration adapter rather than the render contract.
    """

    if not isinstance(source, Mapping):
        return SequenceSheetImportResult(
            valid=False,
            diagnostics=(
                _error(
                    code="invalid_ui_document",
                    message="Studio Sequence payload must be an object",
                ),
            ),
        )
    unknown_document_fields = sorted(set(source) - {"schema_version", "rows"})
    diagnostics = [
        _error(
            code="unknown_ui_document_field",
            message=f"Unknown Studio document field {field_name!r}",
            column=field_name,
        )
        for field_name in unknown_document_fields
    ]
    raw_rows = source.get("rows")
    if not isinstance(raw_rows, list):
        diagnostics.append(
            _error(
                code="invalid_ui_rows",
                message="Studio Sequence rows must be an array",
                column="rows",
            )
        )
        return SequenceSheetImportResult(
            valid=False,
            diagnostics=tuple(diagnostics),
        )

    canonical_rows: list[dict[str, Any]] = []
    versions = dict(workflow_versions or {})
    for source_row, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, Mapping):
            diagnostics.append(
                _error(
                    code="invalid_ui_row",
                    message="Studio Sequence row must be an object",
                    source_row=source_row,
                )
            )
            continue
        row_id = raw.get("row_id") if isinstance(raw.get("row_id"), str) else None
        unknown_fields = sorted(set(raw) - _UI_ROW_FIELDS)
        diagnostics.extend(
            _error(
                code="unknown_ui_row_field",
                message=f"Unknown Studio row field {field_name!r}",
                source_row=source_row,
                column=field_name,
                row_id=row_id,
            )
            for field_name in unknown_fields
        )
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            diagnostics.append(
                _error(
                    code="invalid_enabled",
                    message="enabled must be a boolean",
                    source_row=source_row,
                    column="enabled",
                    row_id=row_id,
                )
            )
            continue
        if not enabled:
            continue

        for field_name in ("scene_id", "subscene_id"):
            field_value = raw.get(field_name)
            if field_value is not None and (
                not isinstance(field_value, str) or not field_value.strip()
            ):
                diagnostics.append(
                    _error(
                        code=f"invalid_{field_name}",
                        message=f"{field_name} must be a non-empty string or null",
                        source_row=source_row,
                        column=field_name,
                        row_id=row_id,
                    )
                )

        max_attempts = raw.get("max_attempts", 2)
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or not 1 <= max_attempts <= 5
        ):
            diagnostics.append(
                _error(
                    code="invalid_max_attempts",
                    message="max_attempts must be an integer from 1 through 5",
                    source_row=source_row,
                    column="max_attempts",
                    row_id=row_id,
                )
            )
        on_error = raw.get("on_error", "stop")
        if on_error not in {"stop", "skip"}:
            diagnostics.append(
                _error(
                    code="invalid_on_error",
                    message="on_error must be 'stop' or 'skip'",
                    source_row=source_row,
                    column="on_error",
                    row_id=row_id,
                )
            )

        template_key = raw.get("template_key")
        model_profile = raw.get("model_profile")
        output_name = raw.get("output_name")
        for field_name, value in (
            ("template_key", template_key),
            ("model_profile", model_profile),
            ("output_name", output_name),
        ):
            if not isinstance(value, str) or not value.strip():
                diagnostics.append(
                    _error(
                        code=f"invalid_{field_name}",
                        message=f"{field_name} must be a non-empty string",
                        source_row=source_row,
                        column=field_name,
                        row_id=row_id,
                    )
                )
        if (
            not isinstance(template_key, str)
            or not template_key.strip()
            or not isinstance(model_profile, str)
            or not model_profile.strip()
            or not isinstance(output_name, str)
            or not output_name.strip()
        ):
            continue

        generation_mode = raw.get(
            "mode",
            raw.get("generation_mode", "i2v"),
        )
        if (
            "mode" in raw
            and "generation_mode" in raw
            and raw.get("mode") != raw.get("generation_mode")
        ):
            diagnostics.append(
                _error(
                    code="conflicting_generation_mode",
                    message="mode and generation_mode must match when both are present",
                    source_row=source_row,
                    column="mode",
                    row_id=row_id,
                )
            )
            continue
        if generation_mode not in {"i2v", "t2v"}:
            diagnostics.append(
                _error(
                    code="invalid_mode",
                    message="mode must be 'i2v' or 't2v'",
                    source_row=source_row,
                    column="mode",
                    row_id=row_id,
                )
            )
            continue

        try:
            profile_ref = canonical_production_profile_ref(model_profile)
        except ProductionProfileError as exc:
            diagnostics.append(
                _error(
                    code="invalid_model_profile",
                    message=str(exc),
                    source_row=source_row,
                    column="model_profile",
                    row_id=row_id,
                )
            )
            continue

        continuity_value = raw.get("continuity_source", "none")
        input_asset_id = raw.get("input_asset_id")
        if not isinstance(continuity_value, str):
            diagnostics.append(
                _error(
                    code="invalid_continuity_source",
                    message="continuity_source must be a string",
                    source_row=source_row,
                    column="continuity_source",
                    row_id=row_id,
                )
            )
            continue
        if input_asset_id is not None and (
            not isinstance(input_asset_id, str) or not input_asset_id.strip()
        ):
            diagnostics.append(
                _error(
                    code="invalid_input_asset_id",
                    message="input_asset_id must be a non-empty string or null",
                    source_row=source_row,
                    column="input_asset_id",
                    row_id=row_id,
                )
            )
            continue

        continuity_source = continuity_value
        continuity_asset_id: str | None = None
        continuity_row_id: str | None = None
        if continuity_value.startswith("asset:"):
            continuity_asset_id = continuity_value.removeprefix("asset:").strip()
            if not continuity_asset_id:
                diagnostics.append(
                    _error(
                        code="invalid_continuity_source",
                        message="asset continuity must include an asset identifier",
                        source_row=source_row,
                        column="continuity_source",
                        row_id=row_id,
                    )
                )
                continue
            continuity_source = "asset"
            if input_asset_id and input_asset_id.strip() != continuity_asset_id:
                diagnostics.append(
                    _error(
                        code="conflicting_input_asset",
                        message=(
                            "input_asset_id does not match the inline asset "
                            "continuity identifier"
                        ),
                        source_row=source_row,
                        column="input_asset_id",
                        row_id=row_id,
                    )
                )
                continue
        else:
            row_match = _ROW_LAST_FRAME.fullmatch(continuity_value)
            if row_match:
                continuity_source = "row-last-frame"
                continuity_row_id = row_match.group(1).strip()
                if not continuity_row_id:
                    diagnostics.append(
                        _error(
                            code="invalid_continuity_source",
                            message=(
                                "row continuity must include a row identifier"
                            ),
                            source_row=source_row,
                            column="continuity_source",
                            row_id=row_id,
                        )
                    )
                    continue
            elif continuity_value == "none" and input_asset_id:
                continuity_source = "asset"
                continuity_asset_id = input_asset_id.strip()
            elif continuity_value not in {"none", "previous_last_frame"}:
                diagnostics.append(
                    _error(
                        code="invalid_continuity_source",
                        message=(
                            "continuity_source must be none, "
                            "previous_last_frame, asset:<id>, or "
                            "row:<id>:last_frame"
                        ),
                        source_row=source_row,
                        column="continuity_source",
                        row_id=row_id,
                    )
                )
                continue

        if (
            input_asset_id
            and continuity_source in {"previous_last_frame", "row-last-frame"}
        ):
            diagnostics.append(
                _error(
                    code="conflicting_input_asset",
                    message=(
                        "input_asset_id cannot be combined with row-frame continuity"
                    ),
                    source_row=source_row,
                    column="input_asset_id",
                    row_id=row_id,
                )
            )
            continue

        version = raw.get("workflow_version")
        if version is None:
            version = versions.get(template_key, default_workflow_version)
        try:
            output_basename = sanitize_output_prefix(output_name)
        except UnsafePathError as exc:
            diagnostics.append(
                _error(
                    code="invalid_output_name",
                    message=str(exc),
                    source_row=source_row,
                    column="output_name",
                    row_id=row_id,
                )
            )
            continue

        canonical_rows.append(
            {
                "row_id": raw.get("row_id"),
                "order": raw.get("order"),
                "workflow_template_id": template_key,
                "workflow_version": version,
                "workflow_sha256": raw.get("workflow_sha256"),
                "production_profile_ref": profile_ref,
                "generation_mode": generation_mode,
                "duration_sec": raw.get("duration_sec"),
                "prompt": raw.get("prompt"),
                "negative_prompt": raw.get("negative_prompt") or "",
                "seed": raw.get("seed", "derive"),
                "continuity_source": continuity_source,
                "continuity_asset_id": continuity_asset_id,
                "continuity_row_id": continuity_row_id,
                "depends_on_row_ids": raw.get("depends_on_row_ids", []),
                "character_ids": raw.get("character_ids", []),
                "asset_ids": raw.get("asset_ids", []),
                "reference_asset_ids": raw.get("reference_asset_ids", []),
                "output_basename": output_basename,
            }
        )

    if diagnostics:
        return SequenceSheetImportResult(
            valid=False,
            diagnostics=tuple(diagnostics),
        )
    return import_sequence_sheet_json(
        {
            "schema_version": SEQUENCE_SHEET_SCHEMA_VERSION,
            "rows": canonical_rows,
        }
    )
