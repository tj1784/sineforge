"""Migration coverage for durable project workflow-lane selection."""

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
PREVIOUS_REVISION = "d0e1f2a3b4c5"
WORKFLOW_LANE_REVISION = "e2f3a4b5c6d7"


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


def test_workflow_lane_migration_defaults_legacy_projects_and_checks_values(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "project-workflow-lane.db"
    config = _config(database_path)
    command.upgrade(config, PREVIOUS_REVISION)

    project_id = str(uuid4())
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO projects (id, name, description, created_at)
                VALUES (:id, 'Legacy Project', NULL, :created_at)
                """
            ),
            {
                "id": project_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    engine.dispose()

    command.upgrade(config, WORKFLOW_LANE_REVISION)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("projects")}
    assert columns["workflow_lane"]["nullable"] is False
    checks = {
        check["name"]: check["sqltext"]
        for check in inspector.get_check_constraints("projects")
    }
    assert "ck_projects_workflow_lane" in checks
    assert "agentless" in checks["ck_projects_workflow_lane"]

    with engine.begin() as connection:
        lane = connection.scalar(
            text("SELECT workflow_lane FROM projects WHERE id = :id"),
            {"id": project_id},
        )
    assert lane == "cineforge_studio"

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE projects
                    SET workflow_lane = 'autonomous'
                    WHERE id = :id
                    """
                ),
                {"id": project_id},
            )
    engine.dispose()

    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    assert "workflow_lane" not in {
        column["name"] for column in inspect(engine).get_columns("projects")
    }
    with engine.begin() as connection:
        assert (
            connection.scalar(
                text("SELECT name FROM projects WHERE id = :id"),
                {"id": project_id},
            )
            == "Legacy Project"
        )
    engine.dispose()
