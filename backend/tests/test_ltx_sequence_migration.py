from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


REPO_ROOT = Path(__file__).resolve().parents[2]
SEQUENCE_REVISION = "d0e1f2a3b4c5"
SEQUENCE_TABLES = {
    "sequence_plans",
    "sequence_plan_revisions",
    "sequence_rows",
    "sequence_row_dependencies",
    "sequence_execution_runs",
    "sequence_row_executions",
    "sequence_row_attempts",
    "continuity_packets",
}


def _config(database_path: Path) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(REPO_ROOT / "backend" / "alembic"),
    )
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{database_path.as_posix()}",
    )
    return config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_sequence_migration_is_additive_and_enforces_ltx_row_contract(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ltx-sequence.db"
    config = _config(database_path)
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    inspector = inspect(engine)
    assert SEQUENCE_TABLES.issubset(set(inspector.get_table_names()))

    project_id = str(uuid4())
    plan_id = str(uuid4())
    revision_id = str(uuid4())
    valid_row_id = str(uuid4())
    now = _now()
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text(
                """
                INSERT INTO projects (id, name, description, created_at)
                VALUES (:id, 'Sequence Test', NULL, :now)
                """
            ),
            {"id": project_id, "now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO sequence_plans (
                    id, created_at, updated_at, project_id, name, status
                )
                VALUES (
                    :id, :now, :now, :project_id, 'LTX plan', 'validated'
                )
                """
            ),
            {
                "id": plan_id,
                "now": now,
                "project_id": project_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO sequence_plan_revisions (
                    id, created_at, updated_at, sequence_plan_id, revision,
                    schema_version, profile_ref, source_kind,
                    canonical_sha256, status, source_json, canonical_json,
                    compiled_plan_json, validation_json
                )
                VALUES (
                    :id, :now, :now, :plan_id, 1,
                    'sineforge.sequence-sheet/v1', 'ltx_base@2', 'json',
                    :sha, 'validated', '{}', '{}', '{}', '{}'
                )
                """
            ),
            {
                "id": revision_id,
                "now": now,
                "plan_id": plan_id,
                "sha": "a" * 64,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO sequence_rows (
                    id, created_at, updated_at, sequence_plan_revision_id,
                    row_id, row_revision, order_index, enabled,
                    workflow_template_key, workflow_version, profile_ref,
                    generation_mode, prompt, negative_prompt,
                    requested_duration_sec, compiled_frame_count,
                    compiled_duration_sec, fps_numerator, fps_denominator,
                    concrete_seed, seed_origin, continuity_source,
                    character_ids_json, asset_ids_json,
                    reference_asset_ids_json, output_basename,
                    canonical_row_sha256, compiled_segment_json
                )
                VALUES (
                    :id, :now, :now, :revision_id,
                    'row-001', 1, 1, 1,
                    'ltx-i2v', '1.0', 'ltx_base@2',
                    'i2v', 'A valid row', '',
                    8, 193,
                    8.0416667, 24, 1,
                    42, 'explicit', 'asset',
                    '[]', '[]', '[]', 'row-001',
                    :sha, '{}'
                )
                """
            ),
            {
                "id": valid_row_id,
                "now": now,
                "revision_id": revision_id,
                "sha": "b" * 64,
            },
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(
                text(
                    """
                    INSERT INTO sequence_rows (
                        id, created_at, updated_at, sequence_plan_revision_id,
                        row_id, row_revision, order_index, enabled,
                        workflow_template_key, workflow_version, profile_ref,
                        generation_mode, prompt, negative_prompt,
                        requested_duration_sec, compiled_frame_count,
                        compiled_duration_sec, fps_numerator, fps_denominator,
                        concrete_seed, seed_origin, continuity_source,
                        character_ids_json, asset_ids_json,
                        reference_asset_ids_json, output_basename,
                        canonical_row_sha256, compiled_segment_json
                    )
                    VALUES (
                        :id, :now, :now, :revision_id,
                        'row-too-long', 1, 2, 1,
                        'ltx-i2v', '1.0', 'ltx_base@2',
                        'i2v', 'Invalid duration', '',
                        15.001, 369,
                        15.375, 24, 1,
                        43, 'explicit', 'none',
                        '[]', '[]', '[]', 'row-too-long',
                        :sha, '{}'
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "now": now,
                    "revision_id": revision_id,
                    "sha": "c" * 64,
                },
            )

    engine.dispose()

def test_sequence_migration_has_a_non_destructive_downgrade_boundary(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ltx-sequence-downgrade.db"
    config = _config(database_path)
    command.upgrade(config, "head")
    command.downgrade(config, "c9d0e1f2a3b4")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    table_names = set(inspect(engine).get_table_names())
    assert not (SEQUENCE_TABLES & table_names)
    assert {"projects", "stories", "project_storyboard_settings"}.issubset(
        table_names
    )
    engine.dispose()
