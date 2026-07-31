"""Focused contract and importer tests for LTX Sequence Sheet v1."""

from __future__ import annotations

import csv
import io

import pytest

from backend.app.schemas.sequence_sheet import (
    ContinuitySource,
    MAX_LTX_ROW_DURATION_SEC,
    MIN_LTX_ROW_DURATION_SEC,
    SEQUENCE_SHEET_SCHEMA_VERSION,
)
from backend.app.services.sequence_sheets import (
    adapt_studio_sequence_payload,
    import_sequence_sheet_csv,
    import_sequence_sheet_json,
)


def _row(**overrides):
    value = {
        "row_id": "row-001",
        "order": 1,
        "workflow_template_id": "ltx-i2v-quality",
        "workflow_version": "1.0",
        "workflow_sha256": "a" * 64,
        "production_profile_ref": "ltx_base@2",
        "generation_mode": "i2v",
        "duration_sec": 8,
        "prompt": "The identified character walks toward the identified car.",
        "negative_prompt": "blur, distorted anatomy",
        "seed": "derive",
        "continuity_source": "asset",
        "continuity_asset_id": "asset-start-001",
        "continuity_row_id": None,
        "depends_on_row_ids": [],
        "character_ids": ["character-worker"],
        "asset_ids": ["asset-car"],
        "reference_asset_ids": ["asset-worker-reference"],
        "output_basename": "row_001_worker_to_car",
    }
    value.update(overrides)
    return value


def _document(*rows):
    return {
        "schema_version": SEQUENCE_SHEET_SCHEMA_VERSION,
        "rows": list(rows),
    }


def test_json_import_builds_canonical_named_ltx_sheet_with_diagnostics_contract():
    result = import_sequence_sheet_json(
        _document(
            _row(),
            _row(
                row_id="row-002",
                order=2,
                duration_sec=15,
                continuity_source="previous_last_frame",
                continuity_asset_id=None,
                output_basename="row_002_drive",
            ),
        )
    )

    assert result.valid is True
    assert result.diagnostics == ()
    assert result.sheet is not None
    assert result.canonical_json == result.sheet.canonical_json()
    assert result.sheet.rows[0].duration_sec == MIN_LTX_ROW_DURATION_SEC
    assert result.sheet.rows[1].duration_sec == MAX_LTX_ROW_DURATION_SEC
    assert (
        result.sheet.rows[1].continuity_source
        is ContinuitySource.PREVIOUS_LAST_FRAME
    )
    assert result.sheet.rows[0].character_ids == ("character-worker",)


def test_csv_import_is_named_strict_and_supports_json_identifier_arrays():
    headers = [
        "schema_version",
        "row_id",
        "order",
        "workflow_template_id",
        "workflow_version",
        "workflow_sha256",
        "production_profile_ref",
        "generation_mode",
        "duration_sec",
        "prompt",
        "negative_prompt",
        "seed",
        "continuity_source",
        "continuity_asset_id",
        "continuity_row_id",
        "depends_on_row_ids",
        "character_ids",
        "asset_ids",
        "reference_asset_ids",
        "output_basename",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerow(
        {
            "schema_version": SEQUENCE_SHEET_SCHEMA_VERSION,
            "row_id": "row-001",
            "order": "1",
            "workflow_template_id": "ltx-i2v-quality",
            "workflow_version": "1.0",
            "workflow_sha256": "a" * 64,
            "production_profile_ref": "ltx_base@2",
            "generation_mode": "i2v",
            "duration_sec": "12.5",
            "prompt": "A single, chronological LTX shot.",
            "negative_prompt": "",
            "seed": "123",
            "continuity_source": "asset",
            "continuity_asset_id": "asset-start",
            "continuity_row_id": "",
            "depends_on_row_ids": "[]",
            "character_ids": '["character-a"]',
            "asset_ids": '["asset-car"]',
            "reference_asset_ids": '["asset-reference"]',
            "output_basename": "shot_001",
        }
    )

    result = import_sequence_sheet_csv(output.getvalue())

    assert result.valid is True
    assert result.sheet is not None
    row = result.sheet.rows[0]
    assert row.duration_sec == 12.5
    assert row.seed == 123
    assert row.reference_asset_ids == ("asset-reference",)


@pytest.mark.parametrize(
    ("field", "value", "expected_column"),
    [
        ("duration_sec", 7.999, "duration_sec"),
        ("duration_sec", 15.001, "duration_sec"),
        ("output_basename", "../escape", "output_basename"),
        ("seed", "1.0", "seed"),
        ("production_profile_ref", "wan_base@1", "production_profile_ref"),
    ],
)
def test_invalid_cells_include_source_row_and_column_diagnostics(
    field,
    value,
    expected_column,
):
    result = import_sequence_sheet_json(_document(_row(**{field: value})))

    assert result.valid is False
    assert result.sheet is None
    assert result.diagnostics
    assert result.diagnostics[0].source_row == 1
    if expected_column is not None:
        assert result.diagnostics[0].column == expected_column


def test_json_types_and_unknown_fields_fail_closed():
    row = _row(duration_sec="8")
    row["surprise"] = "silently accepting this would be unsafe"

    result = import_sequence_sheet_json(_document(row))

    assert result.valid is False
    assert {item.code for item in result.diagnostics} == {
        "unknown_row_field"
    }
    assert result.diagnostics[0].source_row == 1
    assert result.diagnostics[0].column == "surprise"


def test_dependency_cycle_and_missing_previous_row_are_actionable():
    cyclic = import_sequence_sheet_json(
        _document(
                _row(
                    row_id="row-a",
                    order=1,
                    continuity_source="asset",
                    continuity_asset_id="asset-a",
                depends_on_row_ids=["row-b"],
                output_basename="row_a",
            ),
                _row(
                    row_id="row-b",
                    order=2,
                    continuity_source="asset",
                    continuity_asset_id="asset-b",
                depends_on_row_ids=["row-a"],
                output_basename="row_b",
            ),
        )
    )
    first_previous = import_sequence_sheet_json(
        _document(
            _row(
                continuity_source="previous_last_frame",
                continuity_asset_id=None,
            )
        )
    )

    assert cyclic.valid is False
    assert any(item.code == "dependency_cycle" for item in cyclic.diagnostics)
    assert first_previous.valid is False
    assert any(
        item.code == "missing_previous_row"
        for item in first_previous.diagnostics
    )


def test_row_last_frame_requires_existing_target_and_adds_dependency():
    result = import_sequence_sheet_json(
        _document(
            _row(
                row_id="row-a",
                continuity_source="asset",
                continuity_asset_id="asset-a",
                output_basename="row_a",
            ),
            _row(
                row_id="row-b",
                order=2,
                continuity_source="row-last-frame",
                continuity_asset_id=None,
                continuity_row_id="row-a",
                output_basename="row_b",
            ),
        )
    )

    assert result.valid is True
    assert result.sheet is not None
    assert result.sheet.rows[1].continuity_row_id == "row-a"


def test_i2v_requires_an_image_source_and_row_handoff_must_point_backward():
    no_source = import_sequence_sheet_json(
        _document(
            _row(
                continuity_source="none",
                continuity_asset_id=None,
            )
        )
    )
    forward_handoff = import_sequence_sheet_json(
        _document(
            _row(
                row_id="row-a",
                order=1,
                continuity_source="row-last-frame",
                continuity_asset_id=None,
                continuity_row_id="row-b",
                output_basename="row_a",
            ),
            _row(
                row_id="row-b",
                order=2,
                continuity_source="asset",
                continuity_asset_id="asset-b",
                output_basename="row_b",
            ),
        )
    )

    assert no_source.valid is False
    assert any("i2v rows require" in item.message for item in no_source.diagnostics)
    assert forward_handoff.valid is False
    assert any(
        item.code == "continuity_row_not_earlier"
        for item in forward_handoff.diagnostics
    )

    t2v_without_image = import_sequence_sheet_json(
        _document(
            _row(
                generation_mode="t2v",
                continuity_source="none",
                continuity_asset_id=None,
            )
        )
    )
    assert t2v_without_image.valid is True


def test_selected_profile_duration_policy_prevents_legacy_v1_mislabeling():
    result = import_sequence_sheet_json(
        _document(
            _row(
                production_profile_ref="ltx_base@1",
                duration_sec=15,
            )
        )
    )

    assert result.valid is False
    diagnostic = next(
        item
        for item in result.diagnostics
        if item.code == "profile_duration_mismatch"
    )
    assert diagnostic.column == "duration_sec"
    assert diagnostic.source_row == 1


def test_studio_adapter_maps_inline_continuity_and_omits_disabled_rows():
    result = adapt_studio_sequence_payload(
        {
            "rows": [
                {
                    "row_id": "disabled",
                    "order": 1,
                    "enabled": False,
                    "template_key": "ltx-i2v-quality",
                    "model_profile": "ltx_base@2",
                    "mode": "i2v",
                    "duration_sec": 8,
                    "prompt": "Not compiled.",
                    "continuity_source": "none",
                    "output_name": "disabled",
                },
                {
                    "row_id": "row-a",
                    "order": 2,
                    "enabled": True,
                    "template_key": "ltx-i2v-quality",
                    "model_profile": "ltx_base@2",
                    "mode": "i2v",
                    "scene_id": "scene-drive-home",
                    "subscene_id": "subscene-car-entry",
                    "duration_sec": 8,
                    "prompt": "First active row.",
                    "negative_prompt": None,
                    "continuity_source": "asset:start-image",
                    "input_asset_id": "start-image",
                    "output_name": "Row A",
                    "max_attempts": 3,
                    "on_error": "stop",
                },
                {
                    "row_id": "row-b",
                    "order": 3,
                    "enabled": True,
                    "template_key": "ltx-i2v-quality",
                    "model_profile": "ltx_base@2",
                    "mode": "i2v",
                    "duration_sec": 15,
                    "prompt": "Continue from row A.",
                    "continuity_source": "row:row-a:last_frame",
                    "output_name": "row_b",
                    "max_attempts": 2,
                    "on_error": "skip",
                },
            ]
        },
        workflow_versions={"ltx-i2v-quality": "2.3.0"},
    )

    assert result.valid is True
    assert result.sheet is not None
    assert [row.row_id for row in result.sheet.rows] == ["row-a", "row-b"]
    assert result.sheet.rows[0].production_profile_ref == "ltx_base@2"
    assert result.sheet.rows[0].workflow_version == "2.3.0"
    assert result.sheet.rows[0].continuity_asset_id == "start-image"
    assert result.sheet.rows[0].output_basename == "Row_A"
    assert result.sheet.rows[1].continuity_row_id == "row-a"


def test_studio_adapter_rejects_conflicting_inline_and_input_assets():
    result = adapt_studio_sequence_payload(
        {
            "rows": [
                {
                    "row_id": "row-a",
                    "order": 1,
                    "template_key": "ltx-i2v-quality",
                    "model_profile": "ltx_base@2",
                    "duration_sec": 8,
                    "prompt": "Conflict should be visible.",
                    "continuity_source": "asset:asset-a",
                    "input_asset_id": "asset-b",
                    "output_name": "row_a",
                }
            ]
        }
    )

    assert result.valid is False
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "conflicting_input_asset"
    assert diagnostic.source_row == 1
    assert diagnostic.column == "input_asset_id"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("max_attempts", 0, "invalid_max_attempts"),
        ("max_attempts", 6, "invalid_max_attempts"),
        ("on_error", "continue", "invalid_on_error"),
        ("mode", "wan", "invalid_mode"),
    ],
)
def test_studio_adapter_validates_route_only_policy_fields(
    field,
    value,
    expected_code,
):
    row = {
        "row_id": "row-a",
        "order": 1,
        "template_key": "ltx-i2v-quality",
        "model_profile": "ltx_base@2",
        "mode": "i2v",
        "duration_sec": 8,
        "prompt": "Validate route-only fields.",
        "continuity_source": "asset:asset-a",
        "input_asset_id": "asset-a",
        "output_name": "row_a",
        "max_attempts": 2,
        "on_error": "stop",
    }
    row[field] = value

    result = adapt_studio_sequence_payload({"rows": [row]})

    assert result.valid is False
    assert any(item.code == expected_code for item in result.diagnostics)
