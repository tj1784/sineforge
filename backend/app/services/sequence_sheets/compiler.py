"""Deterministic compiler from Sequence Sheet rows to LTX segment plans."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
from typing import Any

from backend.app.schemas.sequence_sheet import (
    CompiledLtxSequencePlan,
    ContinuitySource,
    LtxContinuityBinding,
    LtxSegmentPlan,
    MAX_SEED,
    SeedOrigin,
    SequenceSheet,
    SequenceSheetRow,
)
from backend.app.services.production_profiles import (
    ProductionProfileError,
    resolve_production_profile,
)
from backend.app.services.sequence_sheets.validation import (
    resolved_dependency_row_ids,
    topological_rows,
)


class LtxSequenceCompilationError(ValueError):
    """The canonical sheet cannot be compiled into an admitted LTX request."""


@dataclass(frozen=True, slots=True)
class LtxCompileOptions:
    """Provider timing policy for one LTX invocation.

    LTX video frame counts must satisfy ``8n+1``.  The compiler selects the
    nearest admitted count, preferring the longer count on an exact tie, and
    exposes any timing delta for review and deterministic EDL handling.
    """

    fps_numerator: int = 24
    fps_denominator: int = 1
    frame_multiple: int = 8
    frame_remainder: int = 1
    max_frames: int = 4_097
    material_duration_delta_sec: float = 0.1

    def __post_init__(self) -> None:
        for field_name in (
            "fps_numerator",
            "fps_denominator",
            "frame_multiple",
            "max_frames",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise LtxSequenceCompilationError(
                    f"{field_name} must be a positive integer"
                )
        if self.frame_multiple != 8 or self.frame_remainder != 1:
            raise LtxSequenceCompilationError(
                "Sequence Sheet v1 requires the LTX 8n+1 frame policy"
            )
        if self.frame_remainder < 0 or self.frame_remainder >= self.frame_multiple:
            raise LtxSequenceCompilationError(
                "frame_remainder must be within the frame multiple"
            )
        if (
            not isinstance(self.material_duration_delta_sec, (int, float))
            or isinstance(self.material_duration_delta_sec, bool)
            or not math.isfinite(float(self.material_duration_delta_sec))
            or self.material_duration_delta_sec < 0
        ):
            raise LtxSequenceCompilationError(
                "material_duration_delta_sec must be a finite non-negative number"
            )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def derive_ltx_seed(row: SequenceSheetRow) -> int:
    """Derive a stable signed-64-bit-safe seed from immutable row references."""

    digest = hashlib.sha256(
        _canonical_json(
            {
                "contract": "sineforge.sequence-sheet.seed/v1",
                "row_id": row.row_id,
                "workflow_template_id": row.workflow_template_id,
                "workflow_version": row.workflow_version,
                "workflow_sha256": row.workflow_sha256,
                "production_profile_ref": row.production_profile_ref,
            }
        ).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) & MAX_SEED


def _ltx_frame_count(
    duration_sec: float,
    options: LtxCompileOptions,
) -> int:
    requested_intervals = (
        Fraction(str(duration_sec))
        * options.fps_numerator
        / options.fps_denominator
    )
    lower_intervals = (
        requested_intervals // options.frame_multiple
    ) * options.frame_multiple
    upper_intervals = (
        lower_intervals
        if Fraction(lower_intervals) == requested_intervals
        else lower_intervals + options.frame_multiple
    )
    effective_intervals = min(
        (lower_intervals, upper_intervals),
        key=lambda candidate: (
            abs(Fraction(candidate) - requested_intervals),
            -candidate,
        ),
    )
    frame_count = effective_intervals + options.frame_remainder
    if frame_count <= 0 or frame_count > options.max_frames:
        raise LtxSequenceCompilationError(
            f"LTX frame count {frame_count} exceeds the admitted range"
        )
    return frame_count


def _continuity_binding(
    sheet: SequenceSheet,
    row: SequenceSheetRow,
) -> LtxContinuityBinding:
    if row.continuity_source is ContinuitySource.ASSET:
        return LtxContinuityBinding(
            source=row.continuity_source,
            asset_id=row.continuity_asset_id,
        )
    if row.continuity_source is ContinuitySource.ROW_LAST_FRAME:
        return LtxContinuityBinding(
            source=row.continuity_source,
            row_id=row.continuity_row_id,
        )
    if row.continuity_source is ContinuitySource.PREVIOUS_LAST_FRAME:
        rows = sheet.rows_in_editorial_order()
        predecessor = next(
            (
                rows[index - 1].row_id
                for index, item in enumerate(rows)
                if item.row_id == row.row_id and index > 0
            ),
            None,
        )
        if predecessor is None:
            raise LtxSequenceCompilationError(
                f"row {row.row_id} has no previous row for continuity"
            )
        return LtxContinuityBinding(
            source=row.continuity_source,
            row_id=predecessor,
        )
    return LtxContinuityBinding(source=ContinuitySource.NONE)


def compile_ltx_row(
    sheet: SequenceSheet,
    row: SequenceSheetRow | str,
    *,
    options: LtxCompileOptions | None = None,
) -> LtxSegmentPlan:
    """Compile exactly one canonical row into one provider-safe LTX plan."""

    selected: SequenceSheetRow
    if isinstance(row, str):
        selected = next(
            (candidate for candidate in sheet.rows if candidate.row_id == row),
            None,
        )
        if selected is None:
            raise LtxSequenceCompilationError(
                f"row {row!r} is not present in the Sequence Sheet"
            )
    else:
        selected = row
        if not any(candidate == selected for candidate in sheet.rows):
            raise LtxSequenceCompilationError(
                f"row {selected.row_id!r} is not present in the Sequence Sheet"
            )

    try:
        profile = resolve_production_profile(selected.production_profile_ref)
    except ProductionProfileError as exc:
        raise LtxSequenceCompilationError(str(exc)) from exc
    if profile.model_family != "ltx":
        raise LtxSequenceCompilationError(
            f"profile {profile.ref!r} is not an LTX profile"
        )
    try:
        profile.frame_policy.require_subscene_duration(selected.duration_sec)
    except ProductionProfileError as exc:
        raise LtxSequenceCompilationError(str(exc)) from exc
    if (
        profile.frame_policy.frame_multiple != 8
        or profile.frame_policy.frame_remainder != 1
    ):
        raise LtxSequenceCompilationError(
            f"profile {profile.ref!r} does not declare the LTX 8n+1 frame policy"
        )

    compile_options = options or LtxCompileOptions()
    frame_count = _ltx_frame_count(selected.duration_sec, compile_options)
    generated_duration = float(
        Fraction(
            (frame_count - 1) * compile_options.fps_denominator,
            compile_options.fps_numerator,
        )
    )
    duration_delta = generated_duration - selected.duration_sec
    requires_timing_approval = (
        abs(duration_delta) > compile_options.material_duration_delta_sec
    )
    trim_to_duration = min(selected.duration_sec, generated_duration)

    if selected.seed == "derive":
        seed = derive_ltx_seed(selected)
        seed_origin = SeedOrigin.DERIVED
    else:
        seed = selected.seed
        seed_origin = SeedOrigin.EXPLICIT

    continuity = _continuity_binding(sheet, selected)
    dependencies = resolved_dependency_row_ids(sheet.rows, selected)
    runtime_parameters: dict[str, Any] = {
        "positive_prompt": selected.prompt,
        "negative_prompt": selected.negative_prompt,
        "seed": seed,
        "frame_count": frame_count,
        "fps_numerator": compile_options.fps_numerator,
        "fps_denominator": compile_options.fps_denominator,
        "requested_duration_sec": selected.duration_sec,
        "generated_duration_sec": generated_duration,
        "duration_delta_sec": duration_delta,
        "requires_timing_approval": requires_timing_approval,
        "trim_to_duration_sec": trim_to_duration,
        "output_prefix": selected.output_basename,
        "generation_mode": selected.generation_mode.value,
        "continuity_source": continuity.source.value,
        "continuity_asset_id": continuity.asset_id,
        "continuity_row_id": continuity.row_id,
        "character_ids": list(selected.character_ids),
        "asset_ids": list(selected.asset_ids),
        "reference_asset_ids": list(selected.reference_asset_ids),
    }
    preflight_requirements = [
        f"workflow_template:{selected.workflow_template_id}@{selected.workflow_version}",
        f"production_profile:{profile.ref}",
        f"production_profile_status:{profile.status}",
        "provider_family:ltx",
        "frame_policy:8n+1",
        (
            "timing_approval:required"
            if requires_timing_approval
            else "timing_approval:not_required"
        ),
    ]
    if selected.workflow_sha256 is not None:
        preflight_requirements.append(
            f"workflow_sha256:{selected.workflow_sha256}"
        )
    else:
        preflight_requirements.append("workflow_sha256:resolve-before-submit")
    if continuity.asset_id is not None:
        preflight_requirements.append(f"asset:{continuity.asset_id}")
    if continuity.row_id is not None:
        preflight_requirements.append(
            f"row_output:{continuity.row_id}:last_frame"
        )
    preflight_requirements.extend(
        f"asset:{asset_id}"
        for asset_id in (
            *selected.asset_ids,
            *selected.reference_asset_ids,
        )
    )

    payload: dict[str, Any] = {
        "schema_version": "sineforge.ltx-segment-plan/v1",
        "source_sequence_schema_version": sheet.schema_version,
        "row_id": selected.row_id,
        "order": selected.order,
        "workflow_template_id": selected.workflow_template_id,
        "workflow_version": selected.workflow_version,
        "workflow_sha256": selected.workflow_sha256,
        "production_profile_ref": profile.ref,
        "provider_family": "ltx",
        "generation_mode": selected.generation_mode,
        "requested_duration_sec": selected.duration_sec,
        "fps_numerator": compile_options.fps_numerator,
        "fps_denominator": compile_options.fps_denominator,
        "frame_count": frame_count,
        "frame_multiple": compile_options.frame_multiple,
        "frame_remainder": compile_options.frame_remainder,
        "generated_duration_sec": generated_duration,
        "duration_delta_sec": duration_delta,
        "requires_timing_approval": requires_timing_approval,
        "trim_to_duration_sec": trim_to_duration,
        "seed": seed,
        "seed_origin": seed_origin,
        "prompt": selected.prompt,
        "negative_prompt": selected.negative_prompt,
        "output_basename": selected.output_basename,
        "continuity": continuity,
        "dependency_row_ids": dependencies,
        "character_ids": selected.character_ids,
        "asset_ids": selected.asset_ids,
        "reference_asset_ids": selected.reference_asset_ids,
        "runtime_parameters": runtime_parameters,
        "preflight_requirements": tuple(dict.fromkeys(preflight_requirements)),
    }
    hash_payload = {
        **payload,
        "generation_mode": selected.generation_mode.value,
        "seed_origin": seed_origin.value,
        "continuity": continuity.model_dump(mode="json", exclude_none=True),
    }
    payload["plan_sha256"] = _sha256(hash_payload)
    return LtxSegmentPlan.model_validate(payload)


def compile_ltx_sequence(
    sheet: SequenceSheet,
    *,
    options: LtxCompileOptions | None = None,
) -> CompiledLtxSequencePlan:
    """Compile all rows in stable topological order without submitting work."""

    segments = tuple(
        compile_ltx_row(sheet, row, options=options)
        for row in topological_rows(sheet)
    )
    hash_payload = {
        "schema_version": "sineforge.ltx-sequence-plan/v1",
        "source_sequence_schema_version": sheet.schema_version,
        "segments": [
            segment.model_dump(mode="json", exclude_none=True)
            for segment in segments
        ],
    }
    return CompiledLtxSequencePlan(
        segments=segments,
        plan_sha256=_sha256(hash_payload),
    )
