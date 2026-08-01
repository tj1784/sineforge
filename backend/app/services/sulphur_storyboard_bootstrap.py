"""Bootstrap usable Phase 2-5 planning records from a Sulphur Phase 1 package.

This is a local/private starter plan: one generated clip-sized shot per planned
scene, plus narration and prompt-package rows so phases 2-5 have concrete
records to review and regenerate.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import (
    AuditLog,
    Chapter,
    Character,
    Scene,
    Shot,
    ShotModelRecommendation,
    ShotNarration,
    ShotPromptPackage,
    Story,
    StoryboardVersion,
    VoiceProfile,
)
from backend.app.schemas.proposals import StoryboardProposalPayload
from backend.app.services import storyboard_mutations as mutations
from backend.app.services import storyboard_snapshot
from backend.app.services.clip_planning import plan_scenes_for_duration


PRIMARY_CHARACTER_CLIENT_ID = "character-lead"
PRIMARY_CHARACTER_NAME = "Principal Story Subject"
PRIMARY_CHARACTER_ASSET_LABEL = "character-lead:no-approved-reference-asset-yet"


def _clean(value: Any, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or fallback


def _sentences(value: str) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _slice_text(items: list[str], index: int, fallback: str) -> str:
    if not items:
        return fallback
    return items[index % len(items)]


def _chapter_scene_counts(scene_count: int, chapter_count: int) -> list[int]:
    count = max(1, min(scene_count, chapter_count))
    base = scene_count // count
    remainder = scene_count % count
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _chapter_titles(
    phase_one_package: dict[str, Any],
    chapter_count: int,
    chapter_intake: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    intake_by_index = {
        int(item.get("order_index", index)): item
        for index, item in enumerate(chapter_intake)
        if isinstance(item, dict)
    }
    structure = phase_one_package.get("narrative_structure")
    movements = []
    if isinstance(structure, dict):
        movements = [
            _clean(structure.get(key))
            for key in ("opening", "middle", "climax", "resolution")
            if _clean(structure.get(key))
        ]
    titles: list[tuple[str, str]] = []
    for index in range(chapter_count):
        intake = intake_by_index.get(index) or {}
        title = _clean(intake.get("title")) or f"Chapter {index + 1}"
        summary = (
            _clean(intake.get("summary"))
            or _slice_text(movements, index, _clean(phase_one_package.get("short_synopsis"), title))
        )
        titles.append((title, summary))
    return titles


def _build_story_payload(
    story: Story,
    phase_one_package: dict[str, Any],
    *,
    requested_chapter_count: int,
    chapter_intake: list[dict[str, Any]],
) -> dict[str, Any]:
    plan = plan_scenes_for_duration(float(story.target_duration_sec))
    scene_durations = list(phase_one_package.get("scene_duration_plan_sec") or [])
    if len(scene_durations) != plan.planned_scene_count:
        scene_durations = list(plan.scene_duration_plan_sec)

    chapter_counts = _chapter_scene_counts(plan.planned_scene_count, requested_chapter_count)
    chapter_titles = _chapter_titles(phase_one_package, len(chapter_counts), chapter_intake)
    treatment_sentences = _sentences(str(phase_one_package.get("detailed_treatment") or ""))
    narration_sentences = _sentences(str(phase_one_package.get("narration_script") or ""))
    style = _clean(story.visual_style, "Photoreal cinematic realism")
    tone = _clean(story.tone, "grounded cinematic")
    title = _clean(story.title, "CineForge Project")
    character_identity_line = (
        f"Characters: {PRIMARY_CHARACTER_NAME}. "
        f"Character assets: {PRIMARY_CHARACTER_ASSET_LABEL}. "
        "Use the character workspace consistency prompt until approved reference assets are attached."
    )

    scene_index = 0
    chapters: list[dict[str, Any]] = []
    previous_shot_client_id: str | None = None
    for chapter_index, scene_count in enumerate(chapter_counts):
        chapter_title, chapter_summary = chapter_titles[chapter_index]
        scenes: list[dict[str, Any]] = []
        for local_scene_index in range(scene_count):
            duration = float(scene_durations[scene_index])
            scene_number = scene_index + 1
            scene_beat = _slice_text(
                treatment_sentences,
                scene_index,
                f"{title} story beat {scene_number}",
            )
            scene_title = f"Scene {scene_number:02d} - {scene_beat[:72].rstrip('.:,;')}"
            scene_label = f"Scene {scene_number:02d}: {scene_title}"
            scene_identity_line = f"Scene label: {scene_label}. {character_identity_line}"
            shot_client_id = f"shot-{scene_number:03d}"
            narration_text = _slice_text(
                narration_sentences,
                scene_index,
                scene_beat,
            )
            continuity_type = "previous_shot" if previous_shot_client_id else "none"
            scenes.append(
                {
                    "client_id": f"scene-{scene_number:03d}",
                    "order_index": local_scene_index,
                    "title": scene_title,
                    "summary": scene_beat,
                    "narrative_purpose": f"Advance {chapter_title} with clip-sized visual beat {scene_number}.",
                    "location": "Primary story location",
                    "conflict_or_beat": scene_beat,
                    "shots": [
                        {
                            "client_id": shot_client_id,
                            "order_index": 0,
                            "title": f"S{scene_number:02d}A - {scene_beat[:76].rstrip('.:,;')}",
                            "duration_sec": duration,
                            "story_purpose": scene_beat,
                            "visual_description": (
                                f"{scene_identity_line}. {scene_beat}. "
                                f"{style}; {tone}; readable human action."
                            ),
                            "location": "Primary story location",
                            "continuity_source_type": continuity_type,
                            "continuity_source_shot_client_id": previous_shot_client_id,
                            "starting_image_required": False,
                            "characters": [
                                {
                                    "character_client_id": PRIMARY_CHARACTER_CLIENT_ID,
                                    "role_in_shot": "principal story subject",
                                    "order_index": 0,
                                    "continuity_notes": (
                                        f"{character_identity_line} Preserve identity, wardrobe, and emotional state."
                                    ),
                                }
                            ],
                            "narration": {
                                "client_id": f"narration-{scene_number:03d}",
                                "narration_text": narration_text,
                                "voice_client_id": "voice-narrator",
                                "start_offset_sec": 0,
                                "expected_duration_sec": min(duration, 8.0),
                            },
                            "prompt_package": {
                                "image_prompt": (
                                    f"{scene_identity_line}. {scene_beat}. {style}; "
                                    "cinematic still frame; tactile materials; natural light."
                                ),
                                "video_prompt": (
                                    f"{scene_identity_line}. {scene_beat}. Controlled {duration:g}-second motion; "
                                    "coherent physical action; no jump cuts."
                                ),
                                "negative_prompt": "text, watermark, plastic skin, distorted hands, duplicate limbs, blurry, incoherent action",
                                "continuity_instructions": (
                                    f"{scene_identity_line}. Preserve identity, wardrobe, screen direction, "
                                    "lighting, location, and emotional continuity."
                                ),
                                "style_lock_prompt": style,
                            },
                            "model_recommendations": [
                                {
                                    "recommendation_type": "workflow",
                                    "provider_identifier": "local_comfyui",
                                    "provider_model_id": "flux2_dev_fp8mixed.safetensors",
                                    "rationale": (
                                        "Local/private starting-image workflow candidate for Phase 6. "
                                        f"Inject scene label and character asset metadata: {scene_label}; "
                                        f"{PRIMARY_CHARACTER_NAME}; {PRIMARY_CHARACTER_ASSET_LABEL}."
                                    ),
                                    "availability_status": "available",
                                    "benchmark_status": "unknown",
                                    "risk_status": "needs_visual_review",
                                }
                            ],
                        }
                    ],
                }
            )
            previous_shot_client_id = shot_client_id
            scene_index += 1
        chapters.append(
            {
                "client_id": f"chapter-{chapter_index + 1:02d}",
                "order_index": chapter_index,
                "title": chapter_title,
                "summary": chapter_summary,
                "scenes": scenes,
            }
        )

    return {
        "client_id": "story-sulphur-bootstrap",
        "existing_id": story.id,
        "title": story.title,
        "base_story": story.base_story,
        "target_duration_sec": float(story.target_duration_sec),
        "logline": phase_one_package.get("logline") or story.logline,
        "synopsis": phase_one_package.get("short_synopsis") or story.synopsis,
        "audience": story.audience,
        "tone": story.tone,
        "genre": story.genre,
        "visual_style": story.visual_style,
        "point_of_view": story.point_of_view,
        "production_notes": story.production_notes,
        "voices": [
            {
                "client_id": "voice-narrator",
                "name": "Narrator",
                "source_type": "manual",
                "setup_mode": "manual",
                "language": "English",
                "tone": tone,
                "consent_required": False,
                "consent_confirmed": False,
            }
        ],
        "characters": [
            {
                "client_id": PRIMARY_CHARACTER_CLIENT_ID,
                "name": PRIMARY_CHARACTER_NAME,
                "role": "lead",
                "physical_description": "Defined by the source story and reviewed character workspace.",
                "personality": tone,
                "wardrobe": "Continuity-locked during character review.",
                "consistency_prompt": (
                    f"Preserve {PRIMARY_CHARACTER_NAME} from {title}; {style}. "
                    f"Reference assets: {PRIMARY_CHARACTER_ASSET_LABEL}."
                ),
                "negative_identity_prompt": "identity drift, face swap, inconsistent wardrobe",
            }
        ],
        "chapters": chapters,
    }


def _approve_planning_records(db: Session, story_id) -> None:
    for row in db.scalars(select(Chapter).where(Chapter.story_id == story_id)):
        row.approval_state = "approved"
    for row in db.scalars(select(Character).where(Character.story_id == story_id)):
        row.approval_state = "approved"
    for row in db.scalars(select(VoiceProfile).where(VoiceProfile.story_id == story_id)):
        row.approval_state = "approved"

    scene_ids = [
        row.id
        for row in db.scalars(
            select(Scene)
            .join(Chapter, Scene.chapter_id == Chapter.id)
            .where(Chapter.story_id == story_id)
        )
    ]
    if scene_ids:
        for row in db.scalars(select(Scene).where(Scene.id.in_(scene_ids))):
            row.approval_state = "approved"
        for row in db.scalars(select(Shot).where(Shot.scene_id.in_(scene_ids))):
            row.approval_state = "approved"

    shot_ids = [
        row.id
        for row in db.scalars(
            select(Shot)
            .join(Scene, Shot.scene_id == Scene.id)
            .join(Chapter, Scene.chapter_id == Chapter.id)
            .where(Chapter.story_id == story_id)
        )
    ]
    if shot_ids:
        for model in (ShotNarration, ShotPromptPackage, ShotModelRecommendation):
            for row in db.scalars(select(model).where(model.shot_id.in_(shot_ids))):
                row.approval_state = "approved"
    db.flush()


def approve_generated_planning_records(
    db: Session,
    story: Story,
    *,
    created_by: str,
) -> StoryboardVersion:
    """Approve a locally generated Phase 2-5 graph and retain a new snapshot.

    This is used only after the selected local planning agent has completed and
    its validated proposal has been applied.  It never mutates an older
    StoryboardVersion snapshot.
    """

    _approve_planning_records(db, story.id)
    story.approval_state = "approved"
    story.updated_at = datetime.utcnow()
    db.flush()

    snapshot, digest = storyboard_snapshot.build_snapshot_with_hash(db, story.id)
    current_number = (
        db.scalar(
            select(StoryboardVersion.version_number)
            .where(StoryboardVersion.story_id == story.id)
            .order_by(StoryboardVersion.version_number.desc())
            .limit(1)
        )
        or 0
    )
    version = StoryboardVersion(
        id=uuid4(),
        story_id=story.id,
        version_number=int(current_number) + 1,
        status="approved",
        snapshot_json=snapshot,
        content_hash=digest,
        created_by=created_by,
        approved_by=created_by,
        approved_at=datetime.utcnow(),
        base_version_id=story.active_storyboard_version_id,
    )
    db.add(version)
    db.flush()
    story.active_storyboard_version_id = version.id
    snapshot["story"]["approval_state"] = "approved"
    snapshot["story"]["active_storyboard_version_id"] = str(version.id)
    version.snapshot_json = snapshot
    db.add(
        AuditLog(
            entity_type="story",
            entity_id=story.id,
            action="local_phase_two_through_five_plan_approved",
            details={
                "storyboard_version_id": str(version.id),
                "version_number": version.version_number,
                "created_by": created_by,
                "phases_completed": [2, 3, 4, 5],
                "media_generated": False,
            },
        )
    )
    db.flush()
    return version


def bootstrap_from_phase_one(
    db: Session,
    story: Story,
    phase_one_package: dict[str, Any],
    *,
    requested_chapter_count: int,
    chapter_intake: list[dict[str, Any]],
    created_by: str,
    approve_records: bool = True,
) -> StoryboardVersion:
    """Create a complete initial storyboard/prompt plan without committing."""

    story_payload = _build_story_payload(
        story,
        phase_one_package,
        requested_chapter_count=requested_chapter_count,
        chapter_intake=chapter_intake,
    )
    proposal_payload = {
        "schema_name": "storyboard_proposal_v1",
        "project_id": story.project_id,
        "story": story_payload,
    }
    StoryboardProposalPayload.model_validate(proposal_payload)

    mutations.upsert_story_fields(story, story_payload)
    voices = mutations.upsert_voices(db, story.id, story_payload["voices"])
    characters = mutations.upsert_characters(db, story.id, story_payload["characters"], voices)
    mutations.upsert_hierarchy(
        db,
        story.id,
        story_payload["chapters"],
        characters,
        voices,
        replace_identities=True,
    )
    if approve_records:
        _approve_planning_records(db, story.id)
    story.approval_state = "approved" if approve_records else "draft"
    story.updated_at = datetime.utcnow()
    db.flush()

    snapshot, digest = storyboard_snapshot.build_snapshot_with_hash(db, story.id)
    snapshot["story"]["approval_state"] = story.approval_state
    current_number = (
        db.scalar(
            select(StoryboardVersion.version_number)
            .where(StoryboardVersion.story_id == story.id)
            .order_by(StoryboardVersion.version_number.desc())
            .limit(1)
        )
        or 0
    )
    version = StoryboardVersion(
        id=uuid4(),
        story_id=story.id,
        version_number=int(current_number) + 1,
        status="approved" if approve_records else "draft",
        snapshot_json=snapshot,
        content_hash=digest,
        created_by=created_by,
        approved_by=created_by if approve_records else None,
        approved_at=datetime.utcnow() if approve_records else None,
    )
    db.add(version)
    db.flush()
    story.active_storyboard_version_id = version.id
    snapshot["story"]["active_storyboard_version_id"] = str(version.id)
    version.snapshot_json = snapshot
    db.add(
        AuditLog(
            entity_type="story",
            entity_id=story.id,
            action="sulphur_storyboard_bootstrap_created",
            details={
                "storyboard_version_id": str(version.id),
                "version_number": version.version_number,
                "created_by": created_by,
                "phases_bootstrapped": [2, 3, 4, 5],
                "media_generated": False,
            },
        )
    )
    db.flush()
    return version
