from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.app.db.base import Base
from backend.app.db.session import enable_sqlite_foreign_keys


REQUIRED_TABLES = {
    "hardware_profiles",
    "projects",
    "campaigns",
    "tracks",
    "timeline_slots",
    "prompts",
    "negative_prompts",
    "models",
    "model_variants",
    "quantizations",
    "text_encoders",
    "vaes",
    "loras",
    "lora_combinations",
    "lora_combination_items",
    "workflow_templates",
    "clips",
    "clip_iterations",
    "workflow_runs",
    "comfy_jobs",
    "generated_assets",
    "file_outputs",
    "benchmark_runs",
    "ffmpeg_jobs",
    "audit_logs",
    "error_logs",
    "ai_proposal_records",
    "autonomy_runs",
    "autonomy_run_events",
    "autonomy_policies",
    "qa_reports",
    "retry_attempts",
    "creative_review_notes",
    "candidate_scores",
}

STORYBOARD_PHASE1_TABLES = {
    "project_storyboard_settings",
    "orchestration_runs",
    "orchestration_steps",
    "orchestration_events",
    "provider_invocations",
    "voice_recipes",
    "voice_previews",
    "gpu_resource_leases",
}

PRODUCTION_CONTRACT_TABLES = {
    "production_phases",
    "production_phase_versions",
}

COMFY_JOB_WORKER_COLUMNS = {
    "worker_id",
    "reserved_at",
    "heartbeat_at",
    "attempt_count",
    "last_state_change_at",
    "recovery_metadata",
}

PHASE1_EXTENDED_COLUMNS = {
    "model_variants": {
        "native_voice_capability",
        "native_voice_capability_source",
        "native_voice_capability_metadata_json",
        "native_voice_capability_checked_at",
    },
    "provider_profiles": {
        "capabilities_checked_at",
        "health_checked_at",
        "capability_source",
    },
    "planning_media_assets": {
        "original_filename",
        "size_bytes",
        "archived_at",
    },
    "storyboard_versions": {
        "base_version_id",
        "content_hash",
    },
    "voice_profiles": {
        "setup_mode",
        "provider_model_id",
        "recipe_name",
        "recipe_description",
        "design_description",
        "design_metadata_json",
        "selected_preview_asset_id",
        "preview_text",
        "gender_presentation",
        "pitch",
        "style",
        "provider_configuration_status",
    },
    "ai_proposal_records": {
        "story_id",
        "orchestration_run_id",
        "base_storyboard_version_id",
        "schema_name",
        "content_hash",
        "validation_status",
        "validation_report_json",
        "warnings_json",
        "superseded_by_id",
        "reviewed_by",
        "reviewed_at",
        "applied_at",
        "rejected_at",
        "rejection_reason",
    },
}


def test_required_schema_tables_exist():
    assert REQUIRED_TABLES.issubset(set(Base.metadata.tables))


def test_storyboard_phase1_tables_exist_in_metadata():
    assert STORYBOARD_PHASE1_TABLES.issubset(set(Base.metadata.tables))


def test_eight_phase_production_tables_exist_in_metadata():
    assert PRODUCTION_CONTRACT_TABLES.issubset(set(Base.metadata.tables))


def test_sqlite_connections_enforce_foreign_keys():
    sqlite_engine = create_engine("sqlite://", future=True)
    enable_sqlite_foreign_keys(sqlite_engine)
    try:
        with sqlite_engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE child ("
                    "id INTEGER PRIMARY KEY, "
                    "parent_id INTEGER REFERENCES parent(id)"
                    ")"
                )
            )

        with pytest.raises(IntegrityError):
            with sqlite_engine.begin() as connection:
                connection.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 999)"))
    finally:
        sqlite_engine.dispose()


def test_queue_worker_fields_exist_in_metadata():
    comfy_job_columns = set(Base.metadata.tables["comfy_jobs"].columns.keys())

    assert COMFY_JOB_WORKER_COLUMNS.issubset(comfy_job_columns)


def test_phase1_extended_columns_exist_in_metadata():
    for table_name, expected_columns in PHASE1_EXTENDED_COLUMNS.items():
        columns = set(Base.metadata.tables[table_name].columns.keys())
        assert expected_columns.issubset(columns), table_name


def test_alembic_upgrade_creates_required_tables(tmp_path):
    db_path = tmp_path / "cineforge_alembic_test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(config, "head")

    engine = create_engine(db_url)
    try:
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert REQUIRED_TABLES.issubset(table_names)
    assert STORYBOARD_PHASE1_TABLES.issubset(table_names)
    assert PRODUCTION_CONTRACT_TABLES.issubset(table_names)


def test_alembic_upgrade_includes_worker_ownership_fields(tmp_path):
    db_path = tmp_path / "cineforge_alembic_worker_fields_test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(config, "head")

    engine = create_engine(db_url)
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("comfy_jobs")}
    finally:
        engine.dispose()
    assert COMFY_JOB_WORKER_COLUMNS.issubset(columns)


def test_alembic_upgrade_includes_phase1_extended_columns(tmp_path):
    db_path = tmp_path / "cineforge_alembic_phase1_columns_test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(config, "head")

    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        for table_name, expected_columns in PHASE1_EXTENDED_COLUMNS.items():
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            assert expected_columns.issubset(columns), table_name
    finally:
        engine.dispose()
