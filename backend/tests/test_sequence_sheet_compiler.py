"""Deterministic LTX compiler tests for Sequence Sheet v1."""

from __future__ import annotations

import json

import pytest

from backend.app.schemas.sequence_sheet import SeedOrigin
from backend.app.services.sequence_sheets import (
    compile_ltx_row,
    compile_ltx_sequence,
    derive_ltx_seed,
    import_sequence_sheet_json,
)
from backend.app.services.sequence_sheets.compiler import (
    LtxCompileOptions,
    LtxSequenceCompilationError,
)


def _sheet():
    result = import_sequence_sheet_json(
        {
            "schema_version": "sineforge.sequence-sheet/v1",
            "rows": [
                {
                    "row_id": "row-001",
                    "order": 1,
                    "workflow_template_id": "ltx-i2v-quality",
                    "workflow_version": "1.0",
                    "workflow_sha256": "a" * 64,
                    "production_profile_ref": "ltx_base@2",
                    "generation_mode": "i2v",
                    "duration_sec": 8,
                    "prompt": "The worker enters the identified car.",
                    "negative_prompt": "blur",
                    "seed": 42,
                    "continuity_source": "asset",
                    "continuity_asset_id": "asset-start",
                    "depends_on_row_ids": [],
                    "character_ids": ["character-worker"],
                    "asset_ids": ["asset-car"],
                    "reference_asset_ids": ["asset-worker-ref"],
                    "output_basename": "worker_enters_car",
                },
                {
                    "row_id": "row-002",
                    "order": 2,
                    "workflow_template_id": "ltx-i2v-quality",
                    "workflow_version": "1.0",
                    "workflow_sha256": "a" * 64,
                    "production_profile_ref": "ltx_base@2",
                    "generation_mode": "i2v",
                    "duration_sec": 15,
                    "prompt": "The same worker drives the same car home.",
                    "negative_prompt": "blur",
                    "seed": "derive",
                    "continuity_source": "previous_last_frame",
                    "depends_on_row_ids": [],
                    "character_ids": ["character-worker"],
                    "asset_ids": ["asset-car"],
                    "reference_asset_ids": ["asset-worker-ref"],
                    "output_basename": "worker_drives_home",
                },
            ],
        }
    )
    assert result.valid is True
    assert result.sheet is not None
    return result.sheet


def test_compiler_emits_one_ltx_8n_plus_1_plan_per_row():
    compiled = compile_ltx_sequence(_sheet())

    assert [segment.row_id for segment in compiled.segments] == [
        "row-001",
        "row-002",
    ]
    assert [segment.frame_count for segment in compiled.segments] == [193, 361]
    assert all(
        segment.frame_count % 8 == 1
        for segment in compiled.segments
    )
    assert compiled.segments[0].generated_duration_sec == pytest.approx(
        192 / 24
    )
    assert compiled.segments[1].generated_duration_sec == pytest.approx(
        360 / 24
    )
    assert compiled.segments[1].trim_to_duration_sec == 15
    assert compiled.segments[1].dependency_row_ids == ("row-001",)


def test_compile_row_preserves_explicit_seed_and_normalizes_derived_seed():
    sheet = _sheet()
    explicit = compile_ltx_row(sheet, "row-001")
    derived_once = compile_ltx_row(sheet, "row-002")
    derived_twice = compile_ltx_row(sheet, "row-002")

    assert explicit.seed == 42
    assert explicit.seed_origin is SeedOrigin.EXPLICIT
    assert derived_once.seed_origin is SeedOrigin.DERIVED
    assert derived_once.seed == derive_ltx_seed(sheet.rows[1])
    assert derived_once.seed == derived_twice.seed
    assert derived_once.plan_sha256 == derived_twice.plan_sha256


def test_compiled_plan_is_preflight_ready_and_canonical_json_is_stable():
    segment = compile_ltx_row(_sheet(), "row-002")
    payload = json.loads(segment.canonical_json())

    assert payload["provider_family"] == "ltx"
    assert payload["production_profile_ref"] == "ltx_base@2"
    assert "production_profile_status:qualified" in payload["preflight_requirements"]
    assert payload["runtime_parameters"]["frame_count"] == 361
    assert payload["runtime_parameters"]["continuity_row_id"] == "row-001"
    assert "workflow_template:ltx-i2v-quality@1.0" in payload[
        "preflight_requirements"
    ]
    assert "asset:asset-car" in payload["preflight_requirements"]
    assert "asset:asset-worker-ref" in payload["preflight_requirements"]
    assert len(payload["plan_sha256"]) == 64


def test_custom_ltx_timing_options_remain_8n_plus_1_and_cover_duration():
    plan = compile_ltx_row(
        _sheet(),
        "row-001",
        options=LtxCompileOptions(fps_numerator=25),
    )

    assert plan.frame_count == 201
    assert plan.frame_count % 8 == 1
    assert plan.generated_duration_sec >= plan.requested_duration_sec


@pytest.mark.parametrize(
    (
        "duration_sec",
        "expected_frame_count",
        "expected_generated_duration",
        "requires_approval",
    ),
    [
        (12.05, 289, 12.0, False),
        (12.2, 297, 296 / 24, True),
    ],
)
def test_compiler_uses_nearest_admitted_timing_and_exposes_delta(
    duration_sec,
    expected_frame_count,
    expected_generated_duration,
    requires_approval,
):
    source = json.loads(_sheet().canonical_json())
    source["rows"] = [source["rows"][0]]
    source["rows"][0]["duration_sec"] = duration_sec
    result = import_sequence_sheet_json(source)
    assert result.valid is True
    assert result.sheet is not None

    plan = compile_ltx_row(result.sheet, "row-001")

    assert plan.frame_count == expected_frame_count
    assert plan.generated_duration_sec == pytest.approx(
        expected_generated_duration
    )
    assert plan.duration_delta_sec == pytest.approx(
        expected_generated_duration - duration_sec
    )
    assert plan.requires_timing_approval is requires_approval


def test_compiler_rejects_non_ltx_frame_policy_and_unknown_row():
    with pytest.raises(LtxSequenceCompilationError, match="8n\\+1"):
        LtxCompileOptions(frame_multiple=4)

    with pytest.raises(LtxSequenceCompilationError, match="not present"):
        compile_ltx_row(_sheet(), "missing-row")
