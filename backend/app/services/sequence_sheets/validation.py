"""Semantic validation and dependency resolution for Sequence Sheet v1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.app.schemas.sequence_sheet import (
    ContinuitySource,
    DiagnosticSeverity,
    SequenceSheet,
    SequenceSheetDiagnostic,
    SequenceSheetRow,
)
from backend.app.services.production_profiles import (
    ProductionProfileError,
    resolve_production_profile,
)


def _error(
    *,
    code: str,
    message: str,
    row: SequenceSheetRow | None = None,
    source_rows: Mapping[str, int] | None = None,
    column: str | None = None,
) -> SequenceSheetDiagnostic:
    row_id = row.row_id if row is not None else None
    return SequenceSheetDiagnostic(
        severity=DiagnosticSeverity.ERROR,
        code=code,
        message=message,
        source_row=source_rows.get(row_id) if source_rows and row_id else None,
        column=column,
        row_id=row_id,
    )


def _warning(
    *,
    code: str,
    message: str,
    row: SequenceSheetRow,
    source_rows: Mapping[str, int] | None = None,
    column: str | None = None,
) -> SequenceSheetDiagnostic:
    return SequenceSheetDiagnostic(
        severity=DiagnosticSeverity.WARNING,
        code=code,
        message=message,
        source_row=source_rows.get(row.row_id) if source_rows else None,
        column=column,
        row_id=row.row_id,
    )


def resolved_dependency_row_ids(
    rows: Sequence[SequenceSheetRow],
    row: SequenceSheetRow,
) -> tuple[str, ...]:
    """Resolve explicit and continuity dependencies in deterministic order."""

    editorial_rows = sorted(rows, key=lambda item: (item.order, item.row_id))
    predecessor_by_id: dict[str, str | None] = {}
    previous: str | None = None
    for item in editorial_rows:
        predecessor_by_id[item.row_id] = previous
        previous = item.row_id

    dependencies = set(row.depends_on_row_ids)
    if row.continuity_source is ContinuitySource.PREVIOUS_LAST_FRAME:
        predecessor = predecessor_by_id.get(row.row_id)
        if predecessor is not None:
            dependencies.add(predecessor)
    elif row.continuity_source is ContinuitySource.ROW_LAST_FRAME:
        if row.continuity_row_id is not None:
            dependencies.add(row.continuity_row_id)
    return tuple(
        dependency
        for dependency in (
            item.row_id for item in editorial_rows
        )
        if dependency in dependencies
    )


def validate_sequence_rows(
    rows: Sequence[SequenceSheetRow],
    *,
    source_rows: Mapping[str, int] | None = None,
) -> tuple[SequenceSheetDiagnostic, ...]:
    """Return all actionable sheet-level problems with source-row locations."""

    diagnostics: list[SequenceSheetDiagnostic] = []
    by_id: dict[str, SequenceSheetRow] = {}
    by_order: dict[int, SequenceSheetRow] = {}
    by_output_basename: dict[str, SequenceSheetRow] = {}

    for row in rows:
        existing_id = by_id.get(row.row_id)
        if existing_id is not None:
            diagnostics.append(
                _error(
                    code="duplicate_row_id",
                    message=(
                        f"row_id {row.row_id!r} is duplicated; every row_id must "
                        "remain stable and unique"
                    ),
                    row=row,
                    source_rows=source_rows,
                    column="row_id",
                )
            )
        else:
            by_id[row.row_id] = row

        existing_order = by_order.get(row.order)
        if existing_order is not None:
            diagnostics.append(
                _error(
                    code="duplicate_order",
                    message=(
                        f"order {row.order} is already used by row "
                        f"{existing_order.row_id!r}"
                    ),
                    row=row,
                    source_rows=source_rows,
                    column="order",
                )
            )
        else:
            by_order[row.order] = row

        output_key = row.output_basename.casefold()
        existing_output = by_output_basename.get(output_key)
        if existing_output is not None:
            diagnostics.append(
                _error(
                    code="duplicate_output_basename",
                    message=(
                        f"output_basename {row.output_basename!r} is already used "
                        f"by row {existing_output.row_id!r}"
                    ),
                    row=row,
                    source_rows=source_rows,
                    column="output_basename",
                )
            )
        else:
            by_output_basename[output_key] = row

        try:
            profile = resolve_production_profile(row.production_profile_ref)
        except ProductionProfileError as exc:
            diagnostics.append(
                _error(
                    code="unknown_production_profile",
                    message=str(exc),
                    row=row,
                    source_rows=source_rows,
                    column="production_profile_ref",
                )
            )
        else:
            if profile.model_family != "ltx":
                diagnostics.append(
                    _error(
                        code="non_ltx_profile",
                        message=(
                            f"production profile {profile.ref!r} is "
                            f"{profile.model_family}; Sequence Sheet v1 accepts "
                            "only LTX profiles"
                        ),
                        row=row,
                        source_rows=source_rows,
                        column="production_profile_ref",
                    )
                )
            else:
                try:
                    profile.frame_policy.require_subscene_duration(row.duration_sec)
                except ProductionProfileError as exc:
                    diagnostics.append(
                        _error(
                            code="profile_duration_mismatch",
                            message=str(exc),
                            row=row,
                            source_rows=source_rows,
                            column="duration_sec",
                        )
                    )
            if profile.model_family == "ltx" and not profile.execution_qualified:
                diagnostics.append(
                    _warning(
                        code="ltx_profile_requires_qualification",
                        message=(
                            f"production profile {profile.ref!r} may be authored "
                            "and dry-run, but cannot be queued until its runtime "
                            "qualification gate passes"
                        ),
                        row=row,
                        source_rows=source_rows,
                        column="production_profile_ref",
                    )
                )

    if any(
        diagnostic.code in {"duplicate_row_id", "duplicate_order"}
        for diagnostic in diagnostics
    ):
        return tuple(diagnostics)

    editorial_rows = sorted(rows, key=lambda item: (item.order, item.row_id))
    predecessor_by_id: dict[str, str | None] = {}
    previous: str | None = None
    for row in editorial_rows:
        predecessor_by_id[row.row_id] = previous
        previous = row.row_id

    graph: dict[str, set[str]] = {row.row_id: set() for row in rows}
    for row in rows:
        dependencies = set(row.depends_on_row_ids)
        if row.continuity_source is ContinuitySource.PREVIOUS_LAST_FRAME:
            predecessor = predecessor_by_id[row.row_id]
            if predecessor is None:
                diagnostics.append(
                    _error(
                        code="missing_previous_row",
                        message=(
                            "previous_last_frame is invalid on the first row in "
                            "editorial order"
                        ),
                        row=row,
                        source_rows=source_rows,
                        column="continuity_source",
                    )
                )
            else:
                dependencies.add(predecessor)
        elif row.continuity_source is ContinuitySource.ROW_LAST_FRAME:
            if row.continuity_row_id is not None:
                dependencies.add(row.continuity_row_id)

        for dependency in sorted(dependencies):
            if dependency not in by_id:
                diagnostics.append(
                    _error(
                        code="unknown_dependency",
                        message=f"dependency row {dependency!r} does not exist",
                        row=row,
                        source_rows=source_rows,
                        column=(
                            "continuity_row_id"
                            if dependency == row.continuity_row_id
                            else "depends_on_row_ids"
                        ),
                    )
                )
            elif dependency == row.row_id:
                diagnostics.append(
                    _error(
                        code="self_dependency",
                        message="a row cannot depend on itself",
                        row=row,
                        source_rows=source_rows,
                        column="depends_on_row_ids",
                    )
                )
            elif (
                row.continuity_source is ContinuitySource.ROW_LAST_FRAME
                and dependency == row.continuity_row_id
                and by_id[dependency].order >= row.order
            ):
                diagnostics.append(
                    _error(
                        code="continuity_row_not_earlier",
                        message=(
                            "row-last-frame continuity must reference an earlier "
                            "row in editorial order"
                        ),
                        row=row,
                        source_rows=source_rows,
                        column="continuity_row_id",
                    )
                )
            else:
                graph[row.row_id].add(dependency)

    if any(
        diagnostic.code
        in {
            "missing_previous_row",
            "unknown_dependency",
            "self_dependency",
            "continuity_row_not_earlier",
        }
        for diagnostic in diagnostics
    ):
        return tuple(diagnostics)

    visiting: set[str] = set()
    visited: set[str] = set()
    cycle_reported = False

    def visit(row_id: str, path: tuple[str, ...]) -> None:
        nonlocal cycle_reported
        if cycle_reported or row_id in visited:
            return
        if row_id in visiting:
            cycle_start = path.index(row_id)
            cycle = (*path[cycle_start:], row_id)
            diagnostics.append(
                _error(
                    code="dependency_cycle",
                    message=f"dependency cycle detected: {' -> '.join(cycle)}",
                    row=by_id[row_id],
                    source_rows=source_rows,
                    column="depends_on_row_ids",
                )
            )
            cycle_reported = True
            return
        visiting.add(row_id)
        for dependency in sorted(graph[row_id]):
            visit(dependency, (*path, row_id))
        visiting.remove(row_id)
        visited.add(row_id)

    for row in editorial_rows:
        visit(row.row_id, ())
        if cycle_reported:
            break
    return tuple(diagnostics)


def topological_rows(sheet: SequenceSheet) -> tuple[SequenceSheetRow, ...]:
    """Return dependency-safe rows with editorial order as the stable tie-break."""

    rows = sheet.rows_in_editorial_order()
    dependencies = {
        row.row_id: set(resolved_dependency_row_ids(rows, row))
        for row in rows
    }
    by_id = {row.row_id: row for row in rows}
    completed: set[str] = set()
    result: list[SequenceSheetRow] = []

    while len(result) < len(rows):
        ready = [
            row
            for row in rows
            if row.row_id not in completed
            and dependencies[row.row_id].issubset(completed)
        ]
        if not ready:
            # A SequenceSheet has already passed DAG validation.  This guard
            # protects callers if a future model construction path bypasses it.
            raise ValueError("Sequence Sheet dependency graph cannot be scheduled")
        selected = ready[0]
        result.append(by_id[selected.row_id])
        completed.add(selected.row_id)
    return tuple(result)
