from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


REPO_ROOT = Path(__file__).resolve().parents[2]


def _config(database_path: Path) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location", str(REPO_ROOT / "backend" / "alembic")
    )
    config.set_main_option(
        "sqlalchemy.url", f"sqlite:///{database_path.as_posix()}"
    )
    return config


def test_phase_eight_migration_backfills_existing_story_and_settings(tmp_path) -> None:
    database_path = tmp_path / "phase-eight-upgrade.db"
    config = _config(database_path)
    command.upgrade(config, "b7c8d9e0f1a2")

    project_id = str(uuid4())
    story_id = str(uuid4())
    settings_id = str(uuid4())
    phase_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO projects (id, name, description, created_at)
                VALUES (:id, :name, NULL, :now)
                """
            ),
            {"id": project_id, "name": "Legacy Project", "now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO stories (
                    id, project_id, title, base_story, target_duration_sec,
                    approval_state, created_at, updated_at
                )
                VALUES (
                    :id, :project_id, :title, :base_story, 30,
                    'draft', :now, :now
                )
                """
            ),
            {
                "id": story_id,
                "project_id": project_id,
                "title": "Legacy Story",
                "base_story": "Legacy content",
                "now": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO project_storyboard_settings (
                    id, project_id, shot_duration_min_sec, shot_duration_max_sec,
                    preview_width, preview_height, final_width, final_height, fps,
                    created_at, updated_at
                )
                VALUES (
                    :id, :project_id, 6, 12,
                    1280, 720, 1920, 1080, 24,
                    :now, :now
                )
                """
            ),
            {
                "id": settings_id,
                "project_id": project_id,
                "now": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO production_phases (
                    id, story_id, phase_number, name, lifecycle_state,
                    is_locked, is_stale, created_at, updated_at
                )
                VALUES (
                    :id, :story_id, 7,
                    'Video Generation, Assembly, and Final QA',
                    'not_started', 1, 0, :now, :now
                )
                """
            ),
            {"id": phase_id, "story_id": story_id, "now": now},
        )
    engine.dispose()

    command.upgrade(config, "head")

    upgraded = create_engine(
        f"sqlite:///{database_path.as_posix()}", future=True
    )
    with upgraded.connect() as connection:
        phases = connection.execute(
            text(
                """
                SELECT phase_number, name, lifecycle_state, is_locked
                FROM production_phases
                WHERE story_id = :story_id
                ORDER BY phase_number
                """
            ),
            {"story_id": story_id},
        ).all()
        settings = connection.execute(
            text(
                """
                SELECT production_profile_key, production_profile_snapshot_json,
                       stitch_stage
                FROM project_storyboard_settings
                WHERE id = :settings_id
                """
            ),
            {"settings_id": settings_id},
        ).one()

    assert phases == [
        (
            7,
            "Video Generation, Continuity, Assembly, and Picture Lock",
            "not_started",
            1,
        ),
        (
            8,
            "Foley, Audio Mix, Final Mux, and Delivery QA",
            "not_started",
            1,
        ),
    ]
    assert settings[0] == "ltx_base@1"
    snapshot = json.loads(settings[1]) if isinstance(settings[1], str) else settings[1]
    assert snapshot["ref"] == "ltx_base@1"
    assert snapshot["execution_qualified"] is True
    assert snapshot["approved_video_models"] == [
        "ltx-2.3-22b-distilled-1.1-fp8.safetensors"
    ]
    assert settings[2] == "phase7_before_audio"

    column_names = {
        column["name"]
        for column in inspect(upgraded).get_columns(
            "project_storyboard_settings"
        )
    }
    assert {
        "production_profile_key",
        "production_profile_snapshot_json",
        "stitch_stage",
    }.issubset(column_names)
    upgraded.dispose()
