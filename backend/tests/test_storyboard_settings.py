"""Tests for project storyboard settings service."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base, Project, Story
from backend.app.schemas.storyboard_settings import ProjectStoryboardSettingsUpdate
from backend.app.services import storyboard_settings as settings_service


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _project(db):
    project = Project(name="Settings Project", description=None)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_get_settings_returns_defaults_without_persisting(db_session):
    project = _project(db_session)
    row = settings_service.get_settings(db_session, project.id)
    assert row.project_id == project.id
    assert float(row.shot_duration_min_sec) == 6.0
    assert float(row.shot_duration_max_sec) == 12.0
    assert int(row.settings_version) == 1
    assert row.prefer_local_providers is True
    assert row.allow_rendering is True
    assert row.allow_model_download is True
    assert row.production_profile_key == "ltx_base@1"
    assert row.production_profile_snapshot_json["execution_qualified"] is True
    assert row.stitch_stage == "phase7_before_audio"
    assert row.voice_policy_json["allow_placeholder_for_approval"] is True
    assert row.approval_policy_json["require_prompt_package_or_exception"] is True
    assert row.approval_policy_json["require_model_recommendation_or_exception"] is True
    assert settings_service.get_settings_row(db_session, project.id) is None


def test_put_settings_updates_and_increments_version(db_session):
    project = _project(db_session)
    created = settings_service.get_or_create_settings(db_session, project.id)
    previous_version = int(created.settings_version)
    payload = ProjectStoryboardSettingsUpdate(
        shot_duration_min_sec=6,
        shot_duration_max_sec=12,
        speaking_rate=1.1,
        aspect_ratio="16:9",
        preview_width=1280,
        preview_height=720,
        final_width=1920,
        final_height=1080,
        fps=24,
        captions_enabled=False,
        audio_enabled=True,
        prefer_hosted_providers=True,
        prefer_local_providers=False,
        allow_model_download=False,
        allow_rendering=False,
        require_voice_consent=True,
        require_production_plan_approval=True,
        expected_settings_version=created.settings_version,
        voice_policy_json={
            "allow_placeholder_for_approval": True,
            "allow_manual_for_approval": True,
            "require_consent_when_required": True,
            "block_unresolved_provider_voices": False,
        },
    )
    updated = settings_service.put_settings(db_session, project.id, payload)
    assert float(updated.speaking_rate) == 1.1
    assert updated.captions_enabled is False
    assert int(updated.settings_version) == previous_version + 1


def test_put_settings_stale_version_conflicts(db_session):
    project = _project(db_session)
    settings_service.get_or_create_settings(db_session, project.id)
    payload = ProjectStoryboardSettingsUpdate(
        expected_settings_version=999,
    )
    with pytest.raises(settings_service.StoryboardSettingsConflictError):
        settings_service.put_settings(db_session, project.id, payload)


def test_put_settings_persists_canonical_wan_planning_snapshot(db_session):
    project = _project(db_session)
    created = settings_service.get_or_create_settings(db_session, project.id)

    updated = settings_service.put_settings(
        db_session,
        project.id,
        ProjectStoryboardSettingsUpdate(
            production_profile_key="wan_base@1",
            production_profile_snapshot_json={"forged": True},
            stitch_stage="phase8_before_foley",
            expected_settings_version=created.settings_version,
        ),
    )

    assert updated.production_profile_key == "wan_base@1"
    assert updated.production_profile_snapshot_json["status"] == "on_hold"
    assert updated.production_profile_snapshot_json["hold_reason"] == (
        "Local WAN dry run did not complete successfully."
    )
    assert updated.production_profile_snapshot_json["execution_qualified"] is False
    assert "forged" not in updated.production_profile_snapshot_json
    assert updated.stitch_stage == "phase8_before_foley"


def test_put_settings_rejects_unknown_project(db_session):
    payload = ProjectStoryboardSettingsUpdate()
    with pytest.raises(settings_service.StoryboardSettingsError):
        settings_service.put_settings(db_session, uuid.uuid4(), payload)


def test_settings_snapshot_fragment_is_stable(db_session):
    project = _project(db_session)
    row = settings_service.get_or_create_settings(db_session, project.id)
    fragment = settings_service.settings_snapshot_fragment(row)
    assert fragment is not None
    assert "id" not in fragment
    assert fragment["settings_version"] == 1
    assert fragment["shot_duration_min_sec"] == 6.0


def test_put_settings_reopens_all_project_stories(db_session):
    project = _project(db_session)
    stories = [
        Story(
            project_id=project.id,
            title=f"Story {index}",
            base_story="Approved content",
            target_duration_sec=8,
            approval_state="approved",
        )
        for index in range(2)
    ]
    db_session.add_all(stories)
    db_session.commit()

    settings_service.put_settings(
        db_session,
        project.id,
        ProjectStoryboardSettingsUpdate(speaking_rate=1.1),
    )

    assert all(db_session.get(Story, story.id).approval_state == "draft" for story in stories)
