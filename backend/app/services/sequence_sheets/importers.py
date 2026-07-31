"""Named CSV and JSON importers for the LTX-only Sequence Sheet contract."""

from __future__ import annotations

import csv
import io
import json
import math
import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from backend.app.schemas.sequence_sheet import (
    ContinuitySource,
    DiagnosticSeverity,
    LtxGenerationMode,
    MAX_SEQUENCE_ROWS,
    SEQUENCE_SHEET_SCHEMA_VERSION,
    SequenceSheet,
    SequenceSheetDiagnostic,
    SequenceSheetImportResult,
    SequenceSheetRow,
)
from backend.app.services.sequence_sheets.validation import validate_sequence_rows


MAX_SEQUENCE_SHEET_BYTES = 4 * 1024 * 1024

REQUIRED_ROW_FIELDS = frozenset(
    {
        "row_id",
        "order",
        "workflow_template_id",
        "workflow_version",
        "production_profile_ref",
        "duration_sec",
        "prompt",
        "seed",
        "continuity_source",
        "output_basename",
    }
)
OPTIONAL_ROW_FIELDS = frozenset(
    {
        "workflow_sha256",
        "generation_mode",
        "negative_prompt",
        "continuity_asset_id",
        "continuity_row_id",
        "depends_on_row_ids",
        "character_ids",
        "asset_ids",
        "reference_asset_ids",
    }
)
ROW_FIELDS = REQUIRED_ROW_FIELDS | OPTIONAL_ROW_FIELDS
CSV_REQUIRED_HEADERS = REQUIRED_ROW_FIELDS | {"schema_version"}
CSV_ALLOWED_HEADERS = ROW_FIELDS | {"schema_version"}

_STRICT_INTEGER = re.compile(r"0|[1-9][0-9]*")
_STRICT_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")


class _CellValueError(ValueError):
    def __init__(self, column: str, message: str) -> None:
        super().__init__(message)
        self.column = column


def _diagnostic(
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


def _invalid(
    diagnostics: list[SequenceSheetDiagnostic],
) -> SequenceSheetImportResult:
    return SequenceSheetImportResult(
        valid=False,
        diagnostics=tuple(diagnostics),
    )


def _valid(
    sheet: SequenceSheet,
    diagnostics: list[SequenceSheetDiagnostic],
) -> SequenceSheetImportResult:
    return SequenceSheetImportResult(
        valid=True,
        sheet=sheet,
        diagnostics=tuple(diagnostics),
        canonical_json=sheet.canonical_json(),
    )


def _pydantic_diagnostics(
    exc: PydanticValidationError,
    *,
    source_row: int,
    row_id: str | None,
) -> list[SequenceSheetDiagnostic]:
    diagnostics: list[SequenceSheetDiagnostic] = []
    for error in exc.errors(include_url=False):
        location = error.get("loc") or ()
        column = str(location[0]) if location else None
        diagnostics.append(
            _diagnostic(
                code=f"invalid_{column or 'row'}",
                message=str(error.get("msg") or "invalid value"),
                source_row=source_row,
                column=column,
                row_id=row_id,
            )
        )
    return diagnostics


def _strict_csv_integer(value: str, field_name: str) -> int:
    normalized = value.strip()
    if not _STRICT_INTEGER.fullmatch(normalized):
        raise _CellValueError(
            field_name,
            f"{field_name} must be an unsigned base-10 integer",
        )
    return int(normalized)


def _strict_csv_float(value: str, field_name: str) -> float:
    normalized = value.strip()
    if not _STRICT_DECIMAL.fullmatch(normalized):
        raise _CellValueError(
            field_name,
            f"{field_name} must be a finite base-10 number",
        )
    parsed = float(normalized)
    if not math.isfinite(parsed):
        raise _CellValueError(field_name, f"{field_name} must be finite")
    return parsed


def _strict_csv_ids(value: str, field_name: str) -> tuple[str, ...]:
    normalized = value.strip()
    if not normalized:
        return ()
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise _CellValueError(
            field_name,
            f"{field_name} must be a JSON array of identifier strings"
        ) from exc
    if (
        not isinstance(parsed, list)
        or any(not isinstance(item, str) or not item.strip() for item in parsed)
    ):
        raise _CellValueError(
            field_name,
            f"{field_name} must be a JSON array of identifier strings",
        )
    return tuple(item.strip() for item in parsed)


def _enum_value(enum_type: type, value: str, field_name: str) -> Any:
    normalized = value.strip()
    try:
        return enum_type(normalized)
    except ValueError as exc:
        options = ", ".join(item.value for item in enum_type)
        raise _CellValueError(
            field_name,
            f"{field_name} must be one of: {options}",
        ) from exc


def _csv_row_payload(
    values: Mapping[str, str],
) -> dict[str, Any]:
    seed_text = values["seed"].strip()
    seed: int | str
    if seed_text == "derive":
        seed = "derive"
    else:
        seed = _strict_csv_integer(seed_text, "seed")

    optional_text = lambda name: values.get(name, "").strip() or None
    return {
        "row_id": values["row_id"].strip(),
        "order": _strict_csv_integer(values["order"], "order"),
        "workflow_template_id": values["workflow_template_id"].strip(),
        "workflow_version": values["workflow_version"].strip(),
        "workflow_sha256": optional_text("workflow_sha256"),
        "production_profile_ref": values["production_profile_ref"].strip(),
        "generation_mode": _enum_value(
            LtxGenerationMode,
            values.get("generation_mode", "").strip()
            or LtxGenerationMode.IMAGE_TO_VIDEO.value,
            "generation_mode",
        ),
        "duration_sec": _strict_csv_float(values["duration_sec"], "duration_sec"),
        "prompt": values["prompt"],
        "negative_prompt": values.get("negative_prompt", ""),
        "seed": seed,
        "continuity_source": _enum_value(
            ContinuitySource,
            values["continuity_source"],
            "continuity_source",
        ),
        "continuity_asset_id": optional_text("continuity_asset_id"),
        "continuity_row_id": optional_text("continuity_row_id"),
        "depends_on_row_ids": _strict_csv_ids(
            values.get("depends_on_row_ids", ""),
            "depends_on_row_ids",
        ),
        "character_ids": _strict_csv_ids(
            values.get("character_ids", ""),
            "character_ids",
        ),
        "asset_ids": _strict_csv_ids(
            values.get("asset_ids", ""),
            "asset_ids",
        ),
        "reference_asset_ids": _strict_csv_ids(
            values.get("reference_asset_ids", ""),
            "reference_asset_ids",
        ),
        "output_basename": values["output_basename"].strip(),
    }


def _json_id_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise _CellValueError(
            field_name,
            f"{field_name} must be an array of identifier strings",
        )
    return tuple(item.strip() for item in value)


def _json_row_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    order = value.get("order")
    if not isinstance(order, int) or isinstance(order, bool):
        raise _CellValueError("order", "order must be an integer")

    duration = value.get("duration_sec")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not math.isfinite(float(duration))
    ):
        raise _CellValueError(
            "duration_sec",
            "duration_sec must be a finite number",
        )

    seed = value.get("seed")
    if (
        not (isinstance(seed, int) and not isinstance(seed, bool))
        and seed != "derive"
    ):
        raise _CellValueError(
            "seed",
            "seed must be an integer or 'derive'",
        )

    continuity_value = value.get("continuity_source")
    generation_mode_value = value.get(
        "generation_mode",
        LtxGenerationMode.IMAGE_TO_VIDEO.value,
    )
    if not isinstance(continuity_value, str):
        raise _CellValueError(
            "continuity_source",
            "continuity_source must be a string",
        )
    if not isinstance(generation_mode_value, str):
        raise _CellValueError(
            "generation_mode",
            "generation_mode must be a string",
        )

    optional_string_fields = (
        "workflow_sha256",
        "continuity_asset_id",
        "continuity_row_id",
    )
    for field_name in optional_string_fields:
        item = value.get(field_name)
        if item is not None and not isinstance(item, str):
            raise _CellValueError(
                field_name,
                f"{field_name} must be a string or null",
            )

    required_strings = (
        "row_id",
        "workflow_template_id",
        "workflow_version",
        "production_profile_ref",
        "prompt",
        "output_basename",
    )
    for field_name in required_strings:
        if not isinstance(value.get(field_name), str):
            raise _CellValueError(
                field_name,
                f"{field_name} must be a string",
            )
    negative_prompt = value.get("negative_prompt", "")
    if not isinstance(negative_prompt, str):
        raise _CellValueError(
            "negative_prompt",
            "negative_prompt must be a string",
        )

    return {
        "row_id": value["row_id"].strip(),
        "order": order,
        "workflow_template_id": value["workflow_template_id"].strip(),
        "workflow_version": value["workflow_version"].strip(),
        "workflow_sha256": (
            value.get("workflow_sha256", "").strip()
            if isinstance(value.get("workflow_sha256"), str)
            and value.get("workflow_sha256", "").strip()
            else None
        ),
        "production_profile_ref": value["production_profile_ref"].strip(),
        "generation_mode": _enum_value(
            LtxGenerationMode,
            generation_mode_value,
            "generation_mode",
        ),
        "duration_sec": float(duration),
        "prompt": value["prompt"],
        "negative_prompt": negative_prompt,
        "seed": seed,
        "continuity_source": _enum_value(
            ContinuitySource,
            continuity_value,
            "continuity_source",
        ),
        "continuity_asset_id": (
            value.get("continuity_asset_id", "").strip()
            if isinstance(value.get("continuity_asset_id"), str)
            and value.get("continuity_asset_id", "").strip()
            else None
        ),
        "continuity_row_id": (
            value.get("continuity_row_id", "").strip()
            if isinstance(value.get("continuity_row_id"), str)
            and value.get("continuity_row_id", "").strip()
            else None
        ),
        "depends_on_row_ids": _json_id_tuple(
            value.get("depends_on_row_ids"),
            "depends_on_row_ids",
        ),
        "character_ids": _json_id_tuple(
            value.get("character_ids"),
            "character_ids",
        ),
        "asset_ids": _json_id_tuple(value.get("asset_ids"), "asset_ids"),
        "reference_asset_ids": _json_id_tuple(
            value.get("reference_asset_ids"),
            "reference_asset_ids",
        ),
        "output_basename": value["output_basename"].strip(),
    }


def _finish_import(
    rows: list[SequenceSheetRow],
    diagnostics: list[SequenceSheetDiagnostic],
    source_rows: dict[str, int],
) -> SequenceSheetImportResult:
    if any(
        item.severity is DiagnosticSeverity.ERROR
        for item in diagnostics
    ):
        return _invalid(diagnostics)
    diagnostics.extend(
        validate_sequence_rows(rows, source_rows=source_rows)
    )
    if any(
        item.severity is DiagnosticSeverity.ERROR
        for item in diagnostics
    ):
        return _invalid(diagnostics)
    try:
        sheet = SequenceSheet(rows=tuple(rows))
    except PydanticValidationError as exc:
        diagnostics.extend(
            _pydantic_diagnostics(exc, source_row=1, row_id=None)
        )
        return _invalid(diagnostics)
    return _valid(sheet, diagnostics)


def import_sequence_sheet_csv(
    source: str | bytes,
) -> SequenceSheetImportResult:
    """Parse strict named CSV; list-valued cells must contain JSON arrays."""

    if isinstance(source, bytes):
        if len(source) > MAX_SEQUENCE_SHEET_BYTES:
            return _invalid(
                [
                    _diagnostic(
                        code="source_too_large",
                        message="Sequence Sheet exceeds the 4 MiB import limit",
                    )
                ]
            )
        try:
            text = source.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            return _invalid(
                [
                    _diagnostic(
                        code="invalid_encoding",
                        message=f"Sequence Sheet must be UTF-8: {exc}",
                    )
                ]
            )
    elif isinstance(source, str):
        if len(source.encode("utf-8")) > MAX_SEQUENCE_SHEET_BYTES:
            return _invalid(
                [
                    _diagnostic(
                        code="source_too_large",
                        message="Sequence Sheet exceeds the 4 MiB import limit",
                    )
                ]
            )
        text = source.removeprefix("\ufeff")
    else:
        return _invalid(
            [
                _diagnostic(
                    code="invalid_source_type",
                    message="CSV source must be text or UTF-8 bytes",
                )
            ]
        )

    diagnostics: list[SequenceSheetDiagnostic] = []
    try:
        records = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(records)
    except StopIteration:
        return _invalid(
            [_diagnostic(code="empty_source", message="Sequence Sheet CSV is empty")]
        )
    except csv.Error as exc:
        return _invalid(
            [_diagnostic(code="invalid_csv", message=f"Invalid CSV: {exc}")]
        )

    duplicate_headers = sorted(
        {name for name in header if header.count(name) > 1}
    )
    for name in duplicate_headers:
        diagnostics.append(
            _diagnostic(
                code="duplicate_header",
                message=f"CSV header {name!r} is duplicated",
                source_row=1,
                column=name or None,
            )
        )
    missing_headers = sorted(CSV_REQUIRED_HEADERS - set(header))
    unknown_headers = sorted(set(header) - CSV_ALLOWED_HEADERS)
    for name in missing_headers:
        diagnostics.append(
            _diagnostic(
                code="missing_header",
                message=f"Required CSV header {name!r} is missing",
                source_row=1,
                column=name,
            )
        )
    for name in unknown_headers:
        diagnostics.append(
            _diagnostic(
                code="unknown_header",
                message=f"Unknown CSV header {name!r}",
                source_row=1,
                column=name or None,
            )
        )
    if diagnostics:
        return _invalid(diagnostics)

    rows: list[SequenceSheetRow] = []
    source_rows: dict[str, int] = {}
    try:
        for source_row, record in enumerate(records, start=2):
            if not record or all(not cell.strip() for cell in record):
                continue
            if len(rows) >= MAX_SEQUENCE_ROWS:
                diagnostics.append(
                    _diagnostic(
                        code="too_many_rows",
                        message=f"Sequence Sheet supports at most {MAX_SEQUENCE_ROWS} rows",
                        source_row=source_row,
                    )
                )
                break
            if len(record) != len(header):
                diagnostics.append(
                    _diagnostic(
                        code="column_count_mismatch",
                        message=(
                            f"CSV row has {len(record)} cells but header has "
                            f"{len(header)}"
                        ),
                        source_row=source_row,
                    )
                )
                continue
            values = dict(zip(header, record, strict=True))
            raw_row_id = values.get("row_id", "").strip() or None
            if values["schema_version"].strip() != SEQUENCE_SHEET_SCHEMA_VERSION:
                diagnostics.append(
                    _diagnostic(
                        code="unsupported_schema_version",
                        message=(
                            f"schema_version must be "
                            f"{SEQUENCE_SHEET_SCHEMA_VERSION!r}"
                        ),
                        source_row=source_row,
                        column="schema_version",
                        row_id=raw_row_id,
                    )
                )
                continue
            blank_required = sorted(
                field_name
                for field_name in REQUIRED_ROW_FIELDS
                if not values[field_name].strip()
            )
            if blank_required:
                diagnostics.extend(
                    _diagnostic(
                        code="blank_required_cell",
                        message=f"{field_name} must not be blank",
                        source_row=source_row,
                        column=field_name,
                        row_id=raw_row_id,
                    )
                    for field_name in blank_required
                )
                continue
            try:
                payload = _csv_row_payload(values)
                row = SequenceSheetRow.model_validate(payload)
            except ValueError as exc:
                if isinstance(exc, PydanticValidationError):
                    diagnostics.extend(
                        _pydantic_diagnostics(
                            exc,
                            source_row=source_row,
                            row_id=raw_row_id,
                        )
                    )
                elif isinstance(exc, _CellValueError):
                    diagnostics.append(
                        _diagnostic(
                            code=f"invalid_{exc.column}",
                            message=str(exc),
                            source_row=source_row,
                            column=exc.column,
                            row_id=raw_row_id,
                        )
                    )
                else:
                    diagnostics.append(
                        _diagnostic(
                            code="invalid_cell",
                            message=str(exc),
                            source_row=source_row,
                            row_id=raw_row_id,
                        )
                    )
                continue
            rows.append(row)
            source_rows[row.row_id] = source_row
    except csv.Error as exc:
        diagnostics.append(
            _diagnostic(
                code="invalid_csv",
                message=f"Invalid CSV near row {records.line_num}: {exc}",
                source_row=max(records.line_num, 1),
            )
        )

    if not rows and not diagnostics:
        diagnostics.append(
            _diagnostic(
                code="no_rows",
                message="Sequence Sheet must contain at least one data row",
            )
        )
    return _finish_import(rows, diagnostics, source_rows)


def import_sequence_sheet_json(
    source: str | bytes | Mapping[str, Any],
) -> SequenceSheetImportResult:
    """Parse a strict JSON object with ``schema_version`` and ``rows``."""

    diagnostics: list[SequenceSheetDiagnostic] = []
    payload: Any
    if isinstance(source, bytes):
        if len(source) > MAX_SEQUENCE_SHEET_BYTES:
            return _invalid(
                [
                    _diagnostic(
                        code="source_too_large",
                        message="Sequence Sheet exceeds the 4 MiB import limit",
                    )
                ]
            )
        try:
            payload = json.loads(source.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _invalid(
                [_diagnostic(code="invalid_json", message=f"Invalid JSON: {exc}")]
            )
    elif isinstance(source, str):
        if len(source.encode("utf-8")) > MAX_SEQUENCE_SHEET_BYTES:
            return _invalid(
                [
                    _diagnostic(
                        code="source_too_large",
                        message="Sequence Sheet exceeds the 4 MiB import limit",
                    )
                ]
            )
        try:
            payload = json.loads(source.removeprefix("\ufeff"))
        except json.JSONDecodeError as exc:
            return _invalid(
                [
                    _diagnostic(
                        code="invalid_json",
                        message=f"Invalid JSON at line {exc.lineno}: {exc.msg}",
                        source_row=exc.lineno,
                    )
                ]
            )
    elif isinstance(source, Mapping):
        payload = dict(source)
    else:
        return _invalid(
            [
                _diagnostic(
                    code="invalid_source_type",
                    message="JSON source must be an object, text, or UTF-8 bytes",
                )
            ]
        )

    if not isinstance(payload, dict):
        return _invalid(
            [
                _diagnostic(
                    code="invalid_document",
                    message="Sequence Sheet JSON must be an object",
                )
            ]
        )
    unknown_document_fields = sorted(
        set(payload) - {"schema_version", "rows"}
    )
    for field_name in unknown_document_fields:
        diagnostics.append(
            _diagnostic(
                code="unknown_document_field",
                message=f"Unknown document field {field_name!r}",
                column=field_name,
            )
        )
    if payload.get("schema_version") != SEQUENCE_SHEET_SCHEMA_VERSION:
        diagnostics.append(
            _diagnostic(
                code="unsupported_schema_version",
                message=(
                    f"schema_version must be {SEQUENCE_SHEET_SCHEMA_VERSION!r}"
                ),
                column="schema_version",
            )
        )
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        diagnostics.append(
            _diagnostic(
                code="invalid_rows",
                message="rows must be an array",
                column="rows",
            )
        )
        return _invalid(diagnostics)
    if not raw_rows:
        diagnostics.append(
            _diagnostic(
                code="no_rows",
                message="Sequence Sheet must contain at least one row",
                column="rows",
            )
        )
        return _invalid(diagnostics)
    if len(raw_rows) > MAX_SEQUENCE_ROWS:
        diagnostics.append(
            _diagnostic(
                code="too_many_rows",
                message=f"Sequence Sheet supports at most {MAX_SEQUENCE_ROWS} rows",
                column="rows",
            )
        )
        return _invalid(diagnostics)

    rows: list[SequenceSheetRow] = []
    source_rows: dict[str, int] = {}
    for index, raw_row in enumerate(raw_rows, start=1):
        if not isinstance(raw_row, dict):
            diagnostics.append(
                _diagnostic(
                    code="invalid_row",
                    message="row must be an object",
                    source_row=index,
                )
            )
            continue
        raw_row_id = (
            raw_row.get("row_id")
            if isinstance(raw_row.get("row_id"), str)
            else None
        )
        unknown_fields = sorted(set(raw_row) - ROW_FIELDS)
        missing_fields = sorted(REQUIRED_ROW_FIELDS - set(raw_row))
        for field_name in unknown_fields:
            diagnostics.append(
                _diagnostic(
                    code="unknown_row_field",
                    message=f"Unknown row field {field_name!r}",
                    source_row=index,
                    column=field_name,
                    row_id=raw_row_id,
                )
            )
        for field_name in missing_fields:
            diagnostics.append(
                _diagnostic(
                    code="missing_row_field",
                    message=f"Required row field {field_name!r} is missing",
                    source_row=index,
                    column=field_name,
                    row_id=raw_row_id,
                )
            )
        if unknown_fields or missing_fields:
            continue
        try:
            normalized = _json_row_payload(raw_row)
            row = SequenceSheetRow.model_validate(normalized)
        except ValueError as exc:
            if isinstance(exc, PydanticValidationError):
                diagnostics.extend(
                    _pydantic_diagnostics(
                        exc,
                        source_row=index,
                        row_id=raw_row_id,
                    )
                )
            elif isinstance(exc, _CellValueError):
                diagnostics.append(
                    _diagnostic(
                        code=f"invalid_{exc.column}",
                        message=str(exc),
                        source_row=index,
                        column=exc.column,
                        row_id=raw_row_id,
                    )
                )
            else:
                diagnostics.append(
                    _diagnostic(
                        code="invalid_row_value",
                        message=str(exc),
                        source_row=index,
                        row_id=raw_row_id,
                    )
                )
            continue
        rows.append(row)
        source_rows[row.row_id] = index

    return _finish_import(rows, diagnostics, source_rows)
