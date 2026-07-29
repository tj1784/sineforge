"""Per-project storyboard settings service (Phase 1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import Project, ProjectStoryboardSettings, Story
from backend.app.schemas.storyboard_settings import (
    DEFAULT_APPROVAL_POLICY,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_CONTINUITY_POLICY,
    DEFAULT_FINAL_HEIGHT,
    DEFAULT_FINAL_WIDTH,
    DEFAULT_FPS,
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_WIDTH,
    DEFAULT_PRODUCTION_PROFILE_KEY,
    DEFAULT_PROMPTING_POLICY,
    DEFAULT_SHOT_DURATION_MAX_SEC,
    DEFAULT_SHOT_DURATION_MIN_SEC,
    DEFAULT_SPEAKING_RATE,
    DEFAULT_STITCH_STAGE,
    DEFAULT_VOICE_POLICY,
    ProjectStoryboardSettingsUpdate,
)
from backend.app.services.production_profiles import (
    ProductionProfile,
    select_production_profile,
)


class StoryboardSettingsError(ValueError):
    pass


class StoryboardSettingsConflictError(Exception):
    pass


def _profile_snapshot(profile: ProductionProfile) -> dict:
    return {
        "ref": profile.ref,
        "key": profile.key,
        "version": profile.version,
        "display_name": profile.display_name,
        "model_family": profile.model_family,
        "status": profile.status,
        "execution_qualified": profile.execution_qualified,
        "approved_video_model_keys": sorted(profile.approved_video_model_keys),
        "approved_video_models": sorted(profile.approved_video_models),
        "capabilities": {
            "text_to_video": profile.capabilities.text_to_video,
            "image_to_video": profile.capabilities.image_to_video,
            "video_to_video": profile.capabilities.video_to_video,
            "continuation": profile.capabilities.continuation,
            "native_audio": profile.capabilities.native_audio,
            "external_foley": profile.capabilities.external_foley,
            "high_low_noise_pair": profile.capabilities.high_low_noise_pair,
        },
        "frame_policy": {
            "frame_multiple": profile.frame_policy.frame_multiple,
            "frame_remainder": profile.frame_policy.frame_remainder,
            "nominal_segment_duration_sec": (
                profile.frame_policy.nominal_segment_duration_sec
            ),
            "min_segment_duration_sec": profile.frame_policy.min_segment_duration_sec,
            "max_segment_duration_sec": profile.frame_policy.max_segment_duration_sec,
            "min_subscene_duration_sec": profile.frame_policy.min_subscene_duration_sec,
            "max_subscene_duration_sec": profile.frame_policy.max_subscene_duration_sec,
            "allow_shorter_subscene_with_reason": (
                profile.frame_policy.allow_shorter_subscene_with_reason
            ),
        },
        "qualification_notes": list(profile.qualification_notes),
    }


def production_profile_settings_values(profile_ref: str | None) -> dict:
    profile = select_production_profile(profile_ref, allow_unqualified=True)
    return {
        "production_profile_key": profile.ref,
        "production_profile_snapshot_json": _profile_snapshot(profile),
    }


def _project_or_error(db: Session, project_id: UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise StoryboardSettingsError("Project not found.")
    return project


def default_settings_values() -> dict:
    values = {
        "shot_duration_min_sec": DEFAULT_SHOT_DURATION_MIN_SEC,
        "shot_duration_max_sec": DEFAULT_SHOT_DURATION_MAX_SEC,
        "continuity_policy_json": dict(DEFAULT_CONTINUITY_POLICY),
        "prompting_policy_json": dict(DEFAULT_PROMPTING_POLICY),
        "voice_policy_json": dict(DEFAULT_VOICE_POLICY),
        "approval_policy_json": dict(DEFAULT_APPROVAL_POLICY),
        "speaking_rate": DEFAULT_SPEAKING_RATE,
        "aspect_ratio": DEFAULT_ASPECT_RATIO,
        "preview_width": DEFAULT_PREVIEW_WIDTH,
        "preview_height": DEFAULT_PREVIEW_HEIGHT,
        "final_width": DEFAULT_FINAL_WIDTH,
        "final_height": DEFAULT_FINAL_HEIGHT,
        "fps": DEFAULT_FPS,
        "captions_enabled": True,
        "audio_enabled": True,
        "stitch_stage": DEFAULT_STITCH_STAGE,
        "prefer_hosted_providers": False,
        "prefer_local_providers": True,
        "allow_model_download": True,
        "allow_rendering": True,
        "require_voice_consent": True,
        "require_production_plan_approval": True,
        "settings_version": 1,
    }
    values.update(production_profile_settings_values(DEFAULT_PRODUCTION_PROFILE_KEY))
    return values


def get_settings_row(db: Session, project_id: UUID) -> ProjectStoryboardSettings | None:
    return db.scalar(
        select(ProjectStoryboardSettings).where(ProjectStoryboardSettings.project_id == project_id)
    )


def get_or_create_settings(db: Session, project_id: UUID) -> ProjectStoryboardSettings:
    _project_or_error(db, project_id)
    existing = get_settings_row(db, project_id)
    if existing is not None:
        return existing
    row = ProjectStoryboardSettings(project_id=project_id, **default_settings_values())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_settings(db: Session, project_id: UUID) -> ProjectStoryboardSettings:
    _project_or_error(db, project_id)
    existing = get_settings_row(db, project_id)
    if existing is not None:
        return existing
    # Reads use effective defaults without mutating the database.  The first
    # PUT is the explicit creation boundary.
    return ProjectStoryboardSettings(project_id=project_id, **default_settings_values())


def put_settings(
    db: Session, project_id: UUID, payload: ProjectStoryboardSettingsUpdate
) -> ProjectStoryboardSettings:
    _project_or_error(db, project_id)
    stories = list(
        db.scalars(
            select(Story)
            .where(Story.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    row = db.scalar(
        select(ProjectStoryboardSettings)
        .where(ProjectStoryboardSettings.project_id == project_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    data = payload.model_dump(
        exclude={"expected_settings_version", "production_profile_snapshot_json"}
    )
    data.update(production_profile_settings_values(payload.production_profile_key))

    if row is None:
        if payload.expected_settings_version is not None:
            raise StoryboardSettingsConflictError(
                "Storyboard settings revision conflict: settings do not exist yet."
            )
        row = ProjectStoryboardSettings(project_id=project_id, settings_version=1, **data)
        db.add(row)
    else:
        if (
            payload.expected_settings_version is not None
            and payload.expected_settings_version != row.settings_version
        ):
            raise StoryboardSettingsConflictError(
                "Storyboard settings revision conflict: stale settings_version."
            )
        for field, value in data.items():
            setattr(row, field, value)
        row.settings_version = int(row.settings_version) + 1

    for story in stories:
        story.approval_state = "draft"
        story.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    return row


def settings_public_dict(row: ProjectStoryboardSettings) -> dict:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "shot_duration_min_sec": float(row.shot_duration_min_sec),
        "shot_duration_max_sec": float(row.shot_duration_max_sec),
        "continuity_policy_json": dict(row.continuity_policy_json or {}),
        "prompting_policy_json": dict(row.prompting_policy_json or {}),
        "voice_policy_json": dict(row.voice_policy_json or {}),
        "approval_policy_json": dict(row.approval_policy_json or {}),
        "speaking_rate": float(row.speaking_rate),
        "aspect_ratio": row.aspect_ratio,
        "preview_width": int(row.preview_width),
        "preview_height": int(row.preview_height),
        "final_width": int(row.final_width),
        "final_height": int(row.final_height),
        "fps": float(row.fps),
        "captions_enabled": bool(row.captions_enabled),
        "audio_enabled": bool(row.audio_enabled),
        "production_profile_key": row.production_profile_key,
        "production_profile_snapshot_json": dict(
            row.production_profile_snapshot_json or {}
        ),
        "stitch_stage": row.stitch_stage,
        "prefer_hosted_providers": bool(row.prefer_hosted_providers),
        "prefer_local_providers": bool(row.prefer_local_providers),
        "allow_model_download": bool(row.allow_model_download),
        "allow_rendering": bool(row.allow_rendering),
        "require_voice_consent": bool(row.require_voice_consent),
        "require_production_plan_approval": bool(row.require_production_plan_approval),
        "settings_version": int(row.settings_version),
    }


def settings_snapshot_fragment(row: ProjectStoryboardSettings | None) -> dict | None:
    """Stable subset embedded in production-plan content hashes."""
    if row is None:
        return None
    return {
        "shot_duration_min_sec": float(row.shot_duration_min_sec),
        "shot_duration_max_sec": float(row.shot_duration_max_sec),
        "continuity_policy_json": dict(row.continuity_policy_json or {}),
        "prompting_policy_json": dict(row.prompting_policy_json or {}),
        "voice_policy_json": dict(row.voice_policy_json or {}),
        "approval_policy_json": dict(row.approval_policy_json or {}),
        "speaking_rate": float(row.speaking_rate),
        "aspect_ratio": row.aspect_ratio,
        "preview_width": int(row.preview_width),
        "preview_height": int(row.preview_height),
        "final_width": int(row.final_width),
        "final_height": int(row.final_height),
        "fps": float(row.fps),
        "captions_enabled": bool(row.captions_enabled),
        "audio_enabled": bool(row.audio_enabled),
        "production_profile_key": row.production_profile_key,
        "production_profile_snapshot_json": dict(
            row.production_profile_snapshot_json or {}
        ),
        "stitch_stage": row.stitch_stage,
        "prefer_hosted_providers": bool(row.prefer_hosted_providers),
        "prefer_local_providers": bool(row.prefer_local_providers),
        "allow_model_download": bool(row.allow_model_download),
        "allow_rendering": bool(row.allow_rendering),
        "require_voice_consent": bool(row.require_voice_consent),
        "require_production_plan_approval": bool(row.require_production_plan_approval),
        "settings_version": int(row.settings_version),
    }
