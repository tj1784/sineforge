"""Migration coverage for backward-compatible project themes."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "e2f3a4b5c6d7"
THEME_REVISION = "f4c5d6e7a8b9"


def _config(database_path: Path) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_theme_migration_backfills_default_without_touching_project_content(tmp_path: Path) -> None:
    database_path = tmp_path / "project-theme.db"
    config = _config(database_path)
    command.upgrade(config, PREVIOUS_REVISION)

    project_id = str(uuid4())
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO projects (id, name, description, workflow_lane, created_at)
                VALUES (:id, :name, :description, 'cineforge_studio', :created_at)
                """
            ),
            {
                "id": project_id,
                "name": "Existing Project",
                "description": "Untouched description",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    engine.dispose()

    command.upgrade(config, THEME_REVISION)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    columns = {column["name"]: column for column in inspect(engine).get_columns("projects")}
    assert columns["theme_id"]["nullable"] is False
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT name, description, theme_id, theme_version, theme_context_json "
                "FROM projects WHERE id = :id"
            ),
            {"id": project_id},
        ).mappings().one()
    actual = dict(row)
    actual["theme_context_json"] = json.loads(actual["theme_context_json"])
    assert actual == {
        "name": "Existing Project",
        "description": "Untouched description",
        "theme_id": "default",
        "theme_version": "1.0.0",
        "theme_context_json": {},
    }
    engine.dispose()

    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    assert "theme_id" not in {column["name"] for column in inspect(engine).get_columns("projects")}
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT name FROM projects WHERE id = :id"), {"id": project_id}) == "Existing Project"
    engine.dispose()
