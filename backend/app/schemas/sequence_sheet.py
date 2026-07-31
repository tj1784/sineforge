"""Strict contracts for the LTX-only Sequence Sheet authoring surface.

The sheet is an import/export format.  These models are the canonical,
preflight-ready representation used after parsing CSV or JSON.  They contain
no database, filesystem, ComfyUI, or network behavior.
"""

from __future__ import annotations

from enum import StrEnum
import json
import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


SEQUENCE_SHEET_SCHEMA_VERSION = "sineforge.sequence-sheet/v1"
LTX_SEGMENT_PLAN_SCHEMA_VERSION = "sineforge.ltx-segment-plan/v1"
LTX_SEQUENCE_PLAN_SCHEMA_VERSION = "sineforge.ltx-sequence-plan/v1"
MIN_LTX_ROW_DURATION_SEC = 8.0
MAX_LTX_ROW_DURATION_SEC = 15.0
MAX_SEQUENCE_ROWS = 5_000
MAX_SEED = (2**63) - 1

_OUTPUT_BASENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


OpaqueId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$",
    ),
]
TemplateVersion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$",
    ),
]
Sha256Hex = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[0-9a-fA-F]{64}$",
    ),
]


class StrictSequenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ContinuitySource(StrEnum):
    NONE = "none"
    PREVIOUS_LAST_FRAME = "previous_last_frame"
    ASSET = "asset"
    ROW_LAST_FRAME = "row-last-frame"


class LtxGenerationMode(StrEnum):
    IMAGE_TO_VIDEO = "i2v"
    TEXT_TO_VIDEO = "t2v"


class SeedOrigin(StrEnum):
    EXPLICIT = "explicit"
    DERIVED = "derived"


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class SequenceSheetDiagnostic(StrictSequenceModel):
    """One actionable parser or semantic validation problem."""

    severity: DiagnosticSeverity
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1_000)
    source_row: int | None = Field(default=None, ge=1)
    column: str | None = Field(default=None, min_length=1, max_length=128)
    row_id: str | None = Field(default=None, min_length=1, max_length=128)


class SequenceSheetRow(StrictSequenceModel):
    """One normalized LTX workflow invocation in editorial order."""

    row_id: OpaqueId
    order: int = Field(ge=1, le=MAX_SEQUENCE_ROWS)
    workflow_template_id: OpaqueId
    workflow_version: TemplateVersion
    workflow_sha256: Sha256Hex | None = None
    production_profile_ref: OpaqueId
    generation_mode: LtxGenerationMode = LtxGenerationMode.IMAGE_TO_VIDEO
    duration_sec: float = Field(
        ge=MIN_LTX_ROW_DURATION_SEC,
        le=MAX_LTX_ROW_DURATION_SEC,
        allow_inf_nan=False,
    )
    prompt: str = Field(min_length=1, max_length=16_000)
    negative_prompt: str = Field(default="", max_length=8_000)
    seed: int | Literal["derive"] = Field(default="derive")
    continuity_source: ContinuitySource = ContinuitySource.NONE
    continuity_asset_id: OpaqueId | None = None
    continuity_row_id: OpaqueId | None = None
    depends_on_row_ids: tuple[OpaqueId, ...] = Field(
        default_factory=tuple,
        max_length=256,
    )
    character_ids: tuple[OpaqueId, ...] = Field(
        default_factory=tuple,
        max_length=256,
    )
    asset_ids: tuple[OpaqueId, ...] = Field(
        default_factory=tuple,
        max_length=512,
    )
    reference_asset_ids: tuple[OpaqueId, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )
    output_basename: str = Field(min_length=1, max_length=120)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("prompt must not be blank")
        return normalized

    @field_validator("negative_prompt")
    @classmethod
    def normalize_negative_prompt(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "depends_on_row_ids",
        "character_ids",
        "asset_ids",
        "reference_asset_ids",
    )
    @classmethod
    def reject_duplicate_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("identifier list must not contain duplicates")
        return value

    @field_validator("seed")
    @classmethod
    def validate_seed(cls, value: int | str) -> int | str:
        if isinstance(value, bool):
            raise ValueError("seed must be an integer or 'derive'")
        if isinstance(value, int) and not 0 <= value <= MAX_SEED:
            raise ValueError(f"seed must be between 0 and {MAX_SEED}")
        return value

    @field_validator("output_basename")
    @classmethod
    def validate_output_basename(cls, value: str) -> str:
        normalized = value.strip()
        if (
            not _OUTPUT_BASENAME_PATTERN.fullmatch(normalized)
            or ".." in normalized
        ):
            raise ValueError(
                "output_basename must be a safe filename stem using only "
                "letters, digits, underscore, hyphen, or dot"
            )
        reserved_stem = normalized.split(".", 1)[0].upper()
        if reserved_stem in _WINDOWS_RESERVED_NAMES:
            raise ValueError("output_basename is a reserved Windows filename")
        return normalized

    @field_validator("production_profile_ref")
    @classmethod
    def validate_ltx_profile_reference(cls, value: str) -> str:
        if value.casefold().startswith("wan"):
            raise ValueError(
                "WAN profiles are on hold; Sequence Sheet v1 is LTX-only"
            )
        if "@" not in value:
            raise ValueError(
                "production_profile_ref must be a versioned reference such as "
                "'ltx_base@1'"
            )
        return value

    @model_validator(mode="after")
    def validate_continuity_binding(self) -> "SequenceSheetRow":
        if self.continuity_source is ContinuitySource.ASSET:
            if self.continuity_asset_id is None:
                raise ValueError(
                    "continuity_asset_id is required when continuity_source is asset"
                )
            if self.continuity_row_id is not None:
                raise ValueError(
                    "continuity_row_id is not valid when continuity_source is asset"
                )
        elif self.continuity_source is ContinuitySource.ROW_LAST_FRAME:
            if self.continuity_row_id is None:
                raise ValueError(
                    "continuity_row_id is required when continuity_source is "
                    "row-last-frame"
                )
            if self.continuity_asset_id is not None:
                raise ValueError(
                    "continuity_asset_id is not valid when continuity_source is "
                    "row-last-frame"
                )
        elif self.continuity_asset_id is not None or self.continuity_row_id is not None:
            raise ValueError(
                "continuity asset/row identifiers require a matching continuity_source"
            )
        if (
            self.generation_mode is LtxGenerationMode.TEXT_TO_VIDEO
            and self.continuity_source is not ContinuitySource.NONE
        ):
            raise ValueError("t2v rows cannot consume an image continuity source")
        if (
            self.generation_mode is LtxGenerationMode.IMAGE_TO_VIDEO
            and self.continuity_source is ContinuitySource.NONE
        ):
            raise ValueError(
                "i2v rows require asset, previous_last_frame, or "
                "row-last-frame continuity"
            )
        return self


def _semantic_row_errors(rows: tuple[SequenceSheetRow, ...]) -> list[str]:
    """Return sheet-level errors without source-location decoration."""

    errors: list[str] = []
    row_ids = [row.row_id for row in rows]
    orders = [row.order for row in rows]
    output_basenames = [row.output_basename.casefold() for row in rows]
    if len(row_ids) != len(set(row_ids)):
        errors.append("row_id values must be unique")
    if len(orders) != len(set(orders)):
        errors.append("order values must be unique")
    if len(output_basenames) != len(set(output_basenames)):
        errors.append("output_basename values must be unique")
    if errors:
        return errors

    by_id = {row.row_id: row for row in rows}
    sorted_rows = sorted(rows, key=lambda row: (row.order, row.row_id))
    predecessor_by_id: dict[str, str | None] = {}
    previous: str | None = None
    for row in sorted_rows:
        predecessor_by_id[row.row_id] = previous
        previous = row.row_id

    graph: dict[str, set[str]] = {row.row_id: set() for row in rows}
    for row in rows:
        dependencies = set(row.depends_on_row_ids)
        if row.continuity_source is ContinuitySource.PREVIOUS_LAST_FRAME:
            predecessor = predecessor_by_id[row.row_id]
            if predecessor is None:
                errors.append(
                    f"row {row.row_id} cannot use previous_last_frame because "
                    "it is first in editorial order"
                )
            else:
                dependencies.add(predecessor)
        elif row.continuity_source is ContinuitySource.ROW_LAST_FRAME:
            assert row.continuity_row_id is not None
            dependencies.add(row.continuity_row_id)

        for dependency in dependencies:
            if dependency not in by_id:
                errors.append(
                    f"row {row.row_id} references unknown dependency {dependency}"
                )
            elif dependency == row.row_id:
                errors.append(f"row {row.row_id} cannot depend on itself")
            else:
                graph[row.row_id].add(dependency)

    if errors:
        return errors

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(row_id: str, path: tuple[str, ...]) -> None:
        if row_id in visiting:
            cycle_start = path.index(row_id)
            cycle = (*path[cycle_start:], row_id)
            errors.append(f"dependency cycle detected: {' -> '.join(cycle)}")
            return
        if row_id in visited:
            return
        visiting.add(row_id)
        for dependency in sorted(graph[row_id]):
            visit(dependency, (*path, row_id))
        visiting.remove(row_id)
        visited.add(row_id)

    for row_id in sorted(graph):
        visit(row_id, ())
        if errors:
            break
    return errors


class SequenceSheet(StrictSequenceModel):
    """Validated canonical sheet; row order is stable and dependencies form a DAG."""

    schema_version: Literal[SEQUENCE_SHEET_SCHEMA_VERSION] = (
        SEQUENCE_SHEET_SCHEMA_VERSION
    )
    rows: tuple[SequenceSheetRow, ...] = Field(
        min_length=1,
        max_length=MAX_SEQUENCE_ROWS,
    )

    @model_validator(mode="after")
    def validate_rows(self) -> "SequenceSheet":
        errors = _semantic_row_errors(self.rows)
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def rows_in_editorial_order(self) -> tuple[SequenceSheetRow, ...]:
        return tuple(sorted(self.rows, key=lambda row: (row.order, row.row_id)))

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class SequenceSheetImportResult(StrictSequenceModel):
    valid: bool
    sheet: SequenceSheet | None = None
    diagnostics: tuple[SequenceSheetDiagnostic, ...] = ()
    canonical_json: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "SequenceSheetImportResult":
        has_errors = any(
            diagnostic.severity is DiagnosticSeverity.ERROR
            for diagnostic in self.diagnostics
        )
        if self.valid:
            if has_errors or self.sheet is None or self.canonical_json is None:
                raise ValueError("valid import result requires a canonical sheet")
        elif self.sheet is not None or self.canonical_json is not None:
            raise ValueError("invalid import result must not expose a canonical sheet")
        return self


class LtxContinuityBinding(StrictSequenceModel):
    source: ContinuitySource
    asset_id: OpaqueId | None = None
    row_id: OpaqueId | None = None


class LtxSegmentPlan(StrictSequenceModel):
    """One provider-safe LTX render request compiled from one sheet row."""

    schema_version: Literal[LTX_SEGMENT_PLAN_SCHEMA_VERSION] = (
        LTX_SEGMENT_PLAN_SCHEMA_VERSION
    )
    source_sequence_schema_version: Literal[SEQUENCE_SHEET_SCHEMA_VERSION] = (
        SEQUENCE_SHEET_SCHEMA_VERSION
    )
    row_id: OpaqueId
    order: int = Field(ge=1, le=MAX_SEQUENCE_ROWS)
    workflow_template_id: OpaqueId
    workflow_version: TemplateVersion
    workflow_sha256: Sha256Hex | None = None
    production_profile_ref: OpaqueId
    provider_family: Literal["ltx"] = "ltx"
    generation_mode: LtxGenerationMode
    requested_duration_sec: float = Field(
        ge=MIN_LTX_ROW_DURATION_SEC,
        le=MAX_LTX_ROW_DURATION_SEC,
        allow_inf_nan=False,
    )
    fps_numerator: int = Field(gt=0, le=1_000)
    fps_denominator: int = Field(gt=0, le=1_001)
    frame_count: int = Field(gt=0, le=1_000_000)
    frame_multiple: Literal[8] = 8
    frame_remainder: Literal[1] = 1
    generated_duration_sec: float = Field(gt=0, allow_inf_nan=False)
    duration_delta_sec: float = Field(allow_inf_nan=False)
    requires_timing_approval: bool
    trim_to_duration_sec: float = Field(gt=0, allow_inf_nan=False)
    seed: int = Field(ge=0, le=MAX_SEED)
    seed_origin: SeedOrigin
    prompt: str = Field(min_length=1, max_length=16_000)
    negative_prompt: str = Field(max_length=8_000)
    output_basename: str = Field(min_length=1, max_length=120)
    continuity: LtxContinuityBinding
    dependency_row_ids: tuple[OpaqueId, ...] = Field(max_length=256)
    character_ids: tuple[OpaqueId, ...] = Field(max_length=256)
    asset_ids: tuple[OpaqueId, ...] = Field(max_length=512)
    reference_asset_ids: tuple[OpaqueId, ...] = Field(max_length=64)
    runtime_parameters: dict[str, Any]
    preflight_requirements: tuple[str, ...]
    plan_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_frame_rule(self) -> "LtxSegmentPlan":
        if self.frame_count % self.frame_multiple != self.frame_remainder:
            raise ValueError("LTX frame_count must satisfy 8n+1")
        if self.generated_duration_sec < self.trim_to_duration_sec:
            raise ValueError(
                "generated duration must cover the requested trim duration"
            )
        expected_delta = (
            self.generated_duration_sec - self.requested_duration_sec
        )
        if abs(expected_delta - self.duration_delta_sec) > 1e-9:
            raise ValueError(
                "duration_delta_sec must equal generated minus requested duration"
            )
        if self.trim_to_duration_sec > self.requested_duration_sec:
            raise ValueError(
                "trim duration must not exceed the requested editorial duration"
            )
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class CompiledLtxSequencePlan(StrictSequenceModel):
    schema_version: Literal[LTX_SEQUENCE_PLAN_SCHEMA_VERSION] = (
        LTX_SEQUENCE_PLAN_SCHEMA_VERSION
    )
    source_sequence_schema_version: Literal[SEQUENCE_SHEET_SCHEMA_VERSION] = (
        SEQUENCE_SHEET_SCHEMA_VERSION
    )
    segments: tuple[LtxSegmentPlan, ...] = Field(
        min_length=1,
        max_length=MAX_SEQUENCE_ROWS,
    )
    plan_sha256: Sha256Hex

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
