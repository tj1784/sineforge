"""Phase 6 local ComfyUI starting-image execution.

This is a local/offline personal-use connector. Phase 6 may generate still
starting images through the user's local ComfyUI instance, attach the result as a
managed ``starting_image`` asset, and leave the candidate in review for QA.

The supplied workflow is a ComfyUI UI graph. UI-only nodes are not executable via
``/prompt``, so this module uses a faithful executable API conversion of the
render spine: Flux model loader -> text conditioning -> Flux guidance -> sampler
-> VAE decode -> SaveImage. The original workflow path is preserved in generated
asset metadata for provenance.
"""

from __future__ import annotations

import re
import copy
import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.base import (
    AuditLog,
    Character,
    CharacterReferenceAsset,
    Chapter,
    PlanningMediaAsset,
    ProductionPhase,
    Scene,
    Shot,
    ShotCharacter,
    ShotPromptPackage,
    Story,
)
from backend.app.services import reference_assets


SOURCE_WORKFLOW_PATH = r"C:\Users\razer\Documents\FLUX2.json"

DEFAULT_FLUX_IMAGE_MODEL = "flux2_dev_fp8mixed.safetensors"
FALLBACK_FLUX_IMAGE_MODEL = "flux2_dev.safetensors"
DEFAULT_FLUX_TEXT_ENCODER = "mistral_3_small_flux2_bf16.safetensors"
DEFAULT_FLUX_VAE = "full_encoder_small_decoder.safetensors"
DEFAULT_FLUX1_CLIP_L = "clip_l.safetensors"
DEFAULT_FLUX1_T5 = "t5xxl_fp16.safetensors"
DEFAULT_FLUX1_VAE = "ae.safetensors"
DETAIL_HAND_LORA = "Detailed_Hands-000001.safetensors"

DEFAULT_STEPS = 30
DEFAULT_GUIDANCE = 1.0
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 576
DEFAULT_SAMPLER = "euler"

DEFAULT_NEGATIVE_PROMPT = (
    "cartoon, illustration, painting, plastic skin, waxy skin, anime, fantasy armor, blood, gore, red face marks, wounds, bruises, injuries, violence, children, snow, ash, floating white particles, "
    "modern clothing, modern buildings, bad hands, extra fingers, missing fingers, "
    "deformed fingers, fused fingers, duplicate limbs, distorted face, low detail, "
    "blurry, text, watermark"
)
GENERIC_DEFAULT_NEGATIVE_PROMPT = (
    "cartoon, illustration, painting, anime, CGI look, plastic skin, waxy skin, "
    "bad hands, extra fingers, missing fingers, deformed fingers, fused fingers, "
    "duplicate limbs, duplicated subject, distorted face, low detail, blurry, "
    "overprocessed HDR, oversaturation, text, captions, logo, watermark"
)

STYLE_LOCK = (
    "documentary photoreal historical cinema in ancient 1st-century Judea, "
    "working family farmstead, rough low limestone courtyard, mud plaster, timber beams, "
    "woven shade cloth, clay jars, baskets, sheep or goats, olive trees, vineyard rows, "
    "worn earth-toned imperfect lived-in agricultural household"
)
QUALITY_LOCK = (
    "natural warm sunlight, realistic skin pores, sweat, weathered hands, dusty ground, "
    "coarse woven linen and wool, restrained emotional performance, cinematic depth of field, "
    "asymmetric practical composition, not glamorous, not staged, no direct eye contact with camera"
)
FATHER_COLOR_LOCK = "Father in dignified cool blue, muted teal, cream, restrained gold"
YOUNGER_BEFORE_COLOR_LOCK = "Younger Son in deep crimson, burgundy, or wine-colored outer garment"
YOUNGER_RETURN_COLOR_LOCK = "Returned Younger Son in faded, torn, dirty neutral garments"
OLDER_COLOR_LOCK = "Older Son in ochre, mustard, sun-baked gold, or muted brown"
POSITIVE_AVOIDANCE_LOCK = (
    "avoid every modern or European element: no palace, no luxury villa, no manor, no castle, "
    "no religious skyline, no church, no chapel, no monastery, no bell tower, no watchtower, "
    "no tower, no dome, no crosses, no wall lanterns, no street lamps, no glass windows, "
    "no chimneys, no suits, no ties, no jackets, no dresses, no buttons, no zippers, no cars, "
    "no modern furniture, no Renaissance religious staging, no snow, no ash, no floating white particles, no crowd, no duplicate Father; "
    "avoid front-facing catalog portraits, avoid two men standing shoulder-to-shoulder staring at camera, "
    "avoid posed costume lineup"
)
NO_UNREQUESTED_COLLAPSE_LOCK = (
    "do not depict anyone collapsed, prone, lying facedown, dead, injured, or unconscious "
    "unless the shot explicitly calls for collapse, kneeling, falling, or lying down"
)
NEGATIVE_HISTORICAL_GUARDRAIL = (
    "modern suit, tie, blazer, business dress, European country house, manor, castle, "
    "church, chapel, monastery, bell tower, Christian cross, chimney, glass windows, "
    "street lamp, car, modern table, buttons, zipper, medieval Europe, Renaissance painting, "
    "fantasy robe"
)


class PhaseSixImageError(ValueError):
    pass


@dataclass(frozen=True)
class ShotRow:
    chapter: Chapter
    scene: Scene
    shot: Shot
    scene_number: int
    shot_number: int


@dataclass(frozen=True)
class AssetReferenceTarget:
    label: str
    target_type: str
    name: str
    prompt: str
    scene_ids: tuple[str, ...]
    shot_ids: tuple[str, ...]


def _story(db: Session, story_id: UUID) -> Story:
    row = db.get(Story, story_id)
    if row is None:
        raise PhaseSixImageError("Story not found.")
    return row


def _shot_rows(db: Session, story_id: UUID) -> list[ShotRow]:
    rows = list(
        db.execute(
            select(Chapter, Scene, Shot)
            .join(Scene, Scene.chapter_id == Chapter.id)
            .join(Shot, Shot.scene_id == Scene.id)
            .where(
                Chapter.story_id == story_id,
                Chapter.archived_at.is_(None),
                Scene.archived_at.is_(None),
                Shot.archived_at.is_(None),
            )
            .order_by(Chapter.order_index, Scene.order_index, Shot.order_index)
        )
    )
    deduped: list[ShotRow] = []
    seen: set[UUID] = set()
    scene_numbers: dict[UUID, int] = {}
    current_scene_number = 0
    current_scene_id: UUID | None = None
    shot_numbers_by_scene: dict[UUID, int] = {}
    for chapter, scene, shot in rows:
        if shot.id in seen:
            continue
        seen.add(shot.id)
        if scene.id != current_scene_id:
            current_scene_id = scene.id
            if scene.id not in scene_numbers:
                current_scene_number += 1
                scene_numbers[scene.id] = current_scene_number
        shot_numbers_by_scene[scene.id] = shot_numbers_by_scene.get(scene.id, 0) + 1
        deduped.append(
            ShotRow(
                chapter=chapter,
                scene=scene,
                shot=shot,
                scene_number=scene_numbers[scene.id],
                shot_number=shot_numbers_by_scene[scene.id],
            )
        )
    return deduped


def _shots(db: Session, story_id: UUID) -> list[Shot]:
    return [row.shot for row in _shot_rows(db, story_id)]


def _characters(db: Session, story_id: UUID) -> list[Character]:
    return list(
        db.scalars(
            select(Character)
            .where(
                Character.story_id == story_id,
                Character.archived_at.is_(None),
            )
            .order_by(Character.name.asc(), Character.id.asc())
        )
    )


def _character_label_map(db: Session, story_id: UUID) -> dict[UUID, str]:
    return {
        character.id: f"CHAR-{index:02d} {character.name}"
        for index, character in enumerate(_characters(db, story_id), start=1)
    }


def _metadata_payload(asset: PlanningMediaAsset) -> dict[str, Any]:
    metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
    client = metadata.get("client")
    merged = dict(client) if isinstance(client, dict) else {}
    merged.update(metadata)
    return merged


def _merge_asset_runtime_metadata(
    db: Session,
    asset: PlanningMediaAsset,
    metadata: Mapping[str, Any],
) -> None:
    """Expose generated label metadata both top-level and under legacy client."""

    existing = dict(asset.metadata_json or {})
    existing_client = existing.get("client")
    client = dict(existing_client) if isinstance(existing_client, dict) else {}
    client.update(dict(metadata))
    existing.update(dict(metadata))
    existing["client"] = client
    asset.metadata_json = existing
    db.add(asset)


def status(db: Session, story_id: UUID, *, runtime_reachable: bool | None = None) -> dict[str, Any]:
    _story(db, story_id)
    shots = _shots(db, story_id)
    asset_ids = [shot.starting_image_asset_id for shot in shots if shot.starting_image_asset_id]
    assets = (
        {
            row.id: row
            for row in db.scalars(
                select(PlanningMediaAsset).where(PlanningMediaAsset.id.in_(asset_ids))
            )
        }
        if asset_ids
        else {}
    )
    assigned = 0
    approved = 0
    in_review = 0
    for shot in shots:
        asset = assets.get(shot.starting_image_asset_id)
        if asset is not None and asset.kind == "starting_image" and asset.archived_at is None:
            assigned += 1
            if asset.approval_state == "approved":
                approved += 1
            elif asset.approval_state == "in_review":
                in_review += 1
    phase7 = db.scalar(
        select(ProductionPhase).where(
            ProductionPhase.story_id == story_id,
            ProductionPhase.phase_number == 7,
        )
    )
    required = sum(1 for shot in shots if shot.starting_image_required)
    return {
        "shot_count": len(shots),
        "required_count": required,
        "assigned_count": assigned,
        "approved_count": approved,
        "in_review_count": in_review,
        "missing_count": max(len(shots) - assigned, 0),
        "complete": bool(shots) and required == len(shots) and approved == len(shots),
        "phase_7_locked": bool(phase7.is_locked) if phase7 is not None else None,
        "runtime_reachable": runtime_reachable,
    }


def prepare(db: Session, story_id: UUID, *, requested_by: str) -> dict[str, Any]:
    story = _story(db, story_id)
    shots = _shots(db, story_id)
    if not shots:
        raise PhaseSixImageError("Phase 6 has no shots to prepare.")
    for shot in shots:
        shot.starting_image_required = True

    phases = list(
        db.scalars(
            select(ProductionPhase)
            .where(ProductionPhase.story_id == story_id)
            .order_by(ProductionPhase.phase_number)
        )
    )
    phase6 = next((p for p in phases if p.phase_number == 6), None)
    phase7 = next((p for p in phases if p.phase_number == 7), None)
    if phase6 is None or phase7 is None:
        raise PhaseSixImageError("Production phase ledger is incomplete.")

    phase6.lifecycle_state = "drafting"
    phase6.approved_at = None
    phase6.is_stale = True
    phase6.stale_reason = "Starting-image generation, assignment, and QA are in progress."
    phase6.is_locked = False
    phase6.locked_reason = None
    phase7.is_locked = False
    phase7.locked_reason = None
    db.add(
        AuditLog(
            entity_type="production_phase",
            entity_id=phase6.id,
            action="phase_six_images_prepared",
            details={
                "story_id": str(story.id),
                "project_id": str(story.project_id),
                "required_shot_count": len(shots),
                "requested_by": requested_by,
                "phase_7_relocked": False,
                "media_execution": "local_comfyui_enabled",
            },
        )
    )
    db.commit()
    return status(db, story_id)


def _slug(value: str, *, fallback: str = "Starting_Image") -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    text = re.sub(r"_+", "_", text)
    return text[:72] or fallback


def _shot_code(row: ShotRow) -> str:
    for value in (row.shot.title, getattr(row.shot, "display_label", None)):
        if not value:
            continue
        match = re.search(r"\bS\d{2}[A-Z]\b", str(value), flags=re.IGNORECASE)
        if match:
            return match.group(0).upper()
    letter = chr(64 + row.shot_number) if 1 <= row.shot_number <= 26 else str(row.shot_number)
    return f"S{row.scene_number:02d}{letter}"


def _canonical_filename(row: ShotRow) -> str:
    code = _shot_code(row)
    title = re.split(r"\s*[—–-]\s*", row.shot.title, maxsplit=1)
    descriptive = title[1] if len(title) > 1 else row.shot.title
    return f"{code}_{_slug(descriptive)}.png"


def _image_archetype(title: str) -> dict[str, Any]:
    text = title.lower()
    if any(token in text for token in ("detail", "hand", "tactile", "object", "feet", "sandals")):
        return {
            "id": "CF-IMG-04-DETAIL",
            "label": "Tactile detail",
            "prompt": "macro cinematic detail, emotionally meaningful hands or objects, tactile dust and fabric",
            "width": DEFAULT_WIDTH,
            "height": DEFAULT_HEIGHT,
            "lora_name": DETAIL_HAND_LORA,
            "lora_strength": 0.6,
        }
    if any(token in text for token in ("reaction", "restrained", "face", "witness", "watching")):
        return {
            "id": "CF-IMG-02-REACTION",
            "label": "Restrained reaction",
            "prompt": "intimate reaction framing, expressive eyes, restrained emotion, shallow depth of field",
            "width": DEFAULT_WIDTH,
            "height": DEFAULT_HEIGHT,
        }
    if any(token in text for token in ("action", "runs", "embrace", "arrival", "departure", "cross", "walk")):
        return {
            "id": "CF-IMG-02-ACTION",
            "label": "Principal action",
            "prompt": "clear human action, cinematic blocking, readable body language, grounded movement",
            "width": DEFAULT_WIDTH,
            "height": DEFAULT_HEIGHT,
        }
    if any(token in text for token in ("portrait", "close", "principal")):
        return {
            "id": "CF-IMG-03-PORTRAIT",
            "label": "Character portrait",
            "prompt": "intimate character portrait, realistic face, natural skin texture, emotional specificity",
            "width": DEFAULT_WIDTH,
            "height": DEFAULT_HEIGHT,
        }
    return {
        "id": "CF-IMG-01-WIDE",
        "label": "Wide establishing",
        "prompt": "wide cinematic geography, strong foreground middle-ground background depth, lived-in environment",
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
    }


def _latest_prompt_package(db: Session, shot_id: UUID) -> ShotPromptPackage | None:
    return db.scalar(
        select(ShotPromptPackage)
        .where(ShotPromptPackage.shot_id == shot_id)
        .order_by(ShotPromptPackage.version.desc(), ShotPromptPackage.created_at.desc())
    )


def _character_metadata(db: Session, row: ShotRow) -> list[dict[str, Any]]:
    character_labels = _character_label_map(db, row.chapter.story_id)
    links = list(
        db.execute(
            select(ShotCharacter, Character)
            .join(Character, Character.id == ShotCharacter.character_id)
            .where(ShotCharacter.shot_id == row.shot.id)
            .order_by(ShotCharacter.order_index.asc(), Character.name.asc())
        )
    )
    if not links:
        return [
            {
                "character_id": None,
                "name": "Principal Story Subject",
                "label": "SUBJECT-01 Principal Story Subject",
                "role": "unassigned",
                "role_in_shot": "principal story subject",
                "order_index": 0,
                "continuity_notes": "No explicit character link was assigned to this shot.",
                "consistency_prompt": row.shot.visual_description or row.shot.story_purpose or row.shot.title,
                "negative_identity_prompt": "identity drift, inconsistent wardrobe",
                "asset_ids": [],
                "approved_asset_ids": [],
                "reference_assets": [],
                "asset_status": "pending_reference_asset",
            }
        ]

    metadata: list[dict[str, Any]] = []
    for link, character in links:
        character_label = character_labels.get(character.id, f"CHAR-?? {character.name}")
        references = []
        for reference, asset in db.execute(
            select(CharacterReferenceAsset, PlanningMediaAsset)
            .join(PlanningMediaAsset, PlanningMediaAsset.id == CharacterReferenceAsset.asset_id)
            .where(
                CharacterReferenceAsset.character_id == character.id,
                PlanningMediaAsset.archived_at.is_(None),
            )
            .order_by(
                CharacterReferenceAsset.approved.desc(),
                CharacterReferenceAsset.order_index.asc(),
            )
        ):
            asset_metadata = _metadata_payload(asset)
            references.append(
                {
                    "link_id": str(reference.id),
                    "asset_id": str(reference.asset_id),
                    "asset_label": asset_metadata.get("label")
                    or asset_metadata.get("primary_label")
                    or character_label,
                    "reference_role": reference.reference_role,
                    "approved": bool(reference.approved),
                    "order_index": int(reference.order_index),
                    "asset_approval_state": asset.approval_state,
                    "managed_uri": asset.managed_uri,
                    "original_filename": asset.original_filename,
                }
            )
        approved_asset_ids = [
            item["asset_id"]
            for item in references
            if item["approved"] and item["asset_approval_state"] == "approved"
        ]
        metadata.append(
            {
                "character_id": str(character.id),
                "name": character.name,
                "label": character_label,
                "role": character.role,
                "role_in_shot": link.role_in_shot,
                "order_index": int(link.order_index),
                "continuity_notes": link.continuity_notes,
                "physical_description": character.physical_description,
                "wardrobe": character.wardrobe,
                "consistency_prompt": character.consistency_prompt,
                "negative_identity_prompt": character.negative_identity_prompt,
                "asset_ids": [item["asset_id"] for item in references],
                "approved_asset_ids": approved_asset_ids,
                "reference_assets": references,
                "asset_status": "approved_reference_assets" if approved_asset_ids else "pending_reference_asset",
            }
        )
    return metadata


def _scene_metadata(row: ShotRow) -> dict[str, Any]:
    return {
        "chapter_id": str(row.chapter.id),
        "chapter_title": row.chapter.title,
        "scene_id": str(row.scene.id),
        "scene_number": row.scene_number,
        "scene_title": row.scene.title,
        "scene_label": f"Scene {row.scene_number:02d}: {row.scene.title}",
        "shot_id": str(row.shot.id),
        "shot_number": row.shot_number,
        "shot_code": _shot_code(row),
        "shot_title": row.shot.title,
    }


def _row_asset_context(row: ShotRow) -> str:
    parts = [
        row.chapter.title,
        row.chapter.summary,
        row.scene.title,
        row.scene.summary,
        row.scene.narrative_purpose,
        row.scene.location,
        row.scene.conflict_or_beat,
        row.shot.title,
        row.shot.visual_description,
        row.shot.story_purpose,
        row.shot.location,
        row.shot.camera_direction,
        row.shot.motion_direction,
        getattr(row.shot, "narration", None),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _asset_reference_targets(db: Session, story_id: UUID) -> list[AssetReferenceTarget]:
    rows = _shot_rows(db, story_id)
    story = _story(db, story_id)
    location_rows: dict[str, list[ShotRow]] = {}
    location_names: dict[str, str] = {}
    for row in rows:
        location = _visual_text(row.shot.location or row.scene.location or row.scene.title)
        if not location:
            continue
        key = re.sub(r"\s+", " ", location.lower()).strip()
        location_rows.setdefault(key, []).append(row)
        location_names.setdefault(key, location)

    targets: list[AssetReferenceTarget] = []
    for index, key in enumerate(location_rows, start=1):
        target_rows = location_rows[key]
        name = location_names[key]
        scene_ids = tuple(dict.fromkeys(str(row.scene.id) for row in target_rows))
        shot_ids = tuple(dict.fromkeys(str(row.shot.id) for row in target_rows))
        targets.append(
            AssetReferenceTarget(
                label=f"LOC-{index:02d} {name}",
                target_type="location",
                name=name,
                prompt=(
                    f"CineForge reusable location reference for {name}. "
                    "Create a clear cinematic art-direction plate with consistent geography, lighting, materials, "
                    "color palette, practical set dressing, and scale. No text, no watermark, no logo. "
                    "Prefer an empty or lightly populated environment so it can guide multiple scenes."
                ),
                scene_ids=scene_ids,
                shot_ids=shot_ids,
            )
        )

    all_context = " ".join(_row_asset_context(row) for row in rows)
    key_asset_specs: list[tuple[str, str, str, tuple[str, ...]]] = []
    if any(token in all_context for token in ("car", "sedan", "vehicle", "drive", "driving", "parking")):
        key_asset_specs.append(
            (
                "Recurring vehicle",
                "vehicle",
                (
                    "CineForge reusable hero vehicle reference. A single production-consistent car/sedan, "
                    "three-quarter view, practical lighting, clear body shape, material detail, no people, "
                    "no text, no watermark."
                ),
                ("car", "sedan", "vehicle", "drive", "driving", "parking"),
            )
        )
    if any(token in all_context for token in ("bag", "satchel", "case", "briefcase", "luggage")):
        key_asset_specs.append(
            (
                "Recurring bag or carried case",
                "prop",
                (
                    "CineForge reusable prop reference for the recurring carried bag/case. Isolated practical "
                    "cinematic product-style frame, readable shape, material wear, no hands, no text, no watermark."
                ),
                ("bag", "satchel", "case", "briefcase", "luggage"),
            )
        )
    if any(token in all_context for token in ("phone", "tablet", "laptop", "device", "screen")):
        key_asset_specs.append(
            (
                "Recurring device",
                "prop",
                (
                    "CineForge reusable prop reference for the recurring device/screen. Practical cinematic "
                    "lighting, readable silhouette, no UI text, no logos, no hands, no watermark."
                ),
                ("phone", "tablet", "laptop", "device", "screen"),
            )
        )

    for index, (name, target_type, prompt, tokens) in enumerate(key_asset_specs, start=1):
        target_rows = [row for row in rows if any(token in _row_asset_context(row) for token in tokens)]
        if not target_rows:
            target_rows = rows
        targets.append(
            AssetReferenceTarget(
                label=f"ASSET-{index:02d} {name}",
                target_type=target_type,
                name=name,
                prompt=prompt,
                scene_ids=tuple(dict.fromkeys(str(row.scene.id) for row in target_rows)),
                shot_ids=tuple(dict.fromkeys(str(row.shot.id) for row in target_rows)),
            )
        )

    if not targets:
        targets.append(
            AssetReferenceTarget(
                label="ASSET-01 Overall art direction reference",
                target_type="art_direction",
                name=story.visual_style or story.title,
                prompt=(
                    "CineForge reusable art-direction reference for the whole production. Create one concise "
                    "cinematic style frame that establishes palette, lighting, texture, lens language, and "
                    "production design. No text, no watermark, no logo."
                ),
                scene_ids=tuple(dict.fromkeys(str(row.scene.id) for row in rows)),
                shot_ids=tuple(dict.fromkeys(str(row.shot.id) for row in rows)),
            )
        )
    return targets


def _asset_reference_metadata(db: Session, story: Story, row: ShotRow) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for asset in db.scalars(
        select(PlanningMediaAsset)
        .where(
            PlanningMediaAsset.project_id == story.project_id,
            PlanningMediaAsset.kind == "art_direction_reference",
            PlanningMediaAsset.archived_at.is_(None),
        )
        .order_by(PlanningMediaAsset.created_at.desc())
    ):
        metadata = _metadata_payload(asset)
        if metadata.get("story_id") != str(story.id):
            continue
        scene_ids = metadata.get("scene_ids")
        shot_ids = metadata.get("shot_ids")
        applies_to_scene = isinstance(scene_ids, list) and str(row.scene.id) in scene_ids
        applies_to_shot = isinstance(shot_ids, list) and str(row.shot.id) in shot_ids
        applies_globally = not scene_ids and not shot_ids
        if not (applies_to_scene or applies_to_shot or applies_globally):
            continue
        references.append(
            {
                "asset_id": str(asset.id),
                "label": metadata.get("label") or metadata.get("primary_label") or asset.original_filename,
                "target_type": metadata.get("target_type") or "art_direction",
                "name": metadata.get("name") or asset.original_filename,
                "approval_state": asset.approval_state,
                "managed_uri": asset.managed_uri,
                "original_filename": asset.original_filename,
                "scene_ids": scene_ids if isinstance(scene_ids, list) else [],
                "shot_ids": shot_ids if isinstance(shot_ids, list) else [],
            }
        )
    references.sort(key=lambda item: str(item.get("label") or ""))
    return references


def _scene_attachment_labels(
    scene_metadata: Mapping[str, Any],
    characters: list[dict[str, Any]],
    asset_references: list[dict[str, Any]],
) -> dict[str, Any]:
    character_labels = [
        {
            "entity_type": "character",
            "entity_id": character.get("character_id"),
            "label": character.get("label") or character.get("name"),
            "name": character.get("name"),
            "asset_ids": character.get("asset_ids") or [],
            "approved_asset_ids": character.get("approved_asset_ids") or [],
        }
        for character in characters
    ]
    asset_labels = [
        {
            "entity_type": "asset_reference",
            "entity_id": reference.get("asset_id"),
            "label": reference.get("label"),
            "target_type": reference.get("target_type"),
            "name": reference.get("name"),
        }
        for reference in asset_references
    ]
    return {
        "primary": scene_metadata.get("shot_code"),
        "scene": scene_metadata.get("scene_label"),
        "shot": scene_metadata.get("shot_code"),
        "characters": character_labels,
        "assets": asset_labels,
        "attachments": [
            {
                "entity_type": "scene",
                "entity_id": scene_metadata.get("scene_id"),
                "label": scene_metadata.get("scene_label"),
            },
            {
                "entity_type": "shot",
                "entity_id": scene_metadata.get("shot_id"),
                "label": scene_metadata.get("shot_code"),
            },
            *character_labels,
            *asset_labels,
        ],
    }


def _identity_prompt_text(row: ShotRow, characters: list[dict[str, Any]]) -> str:
    scene = _scene_metadata(row)
    chunks = [f"Scene label: {scene['scene_label']}", f"Shot label: {scene['shot_code']}"]
    character_chunks: list[str] = []
    for character in characters:
        name = str(character.get("name") or "Unnamed Character")
        label = str(character.get("label") or name)
        approved_assets = character.get("approved_asset_ids")
        all_assets = character.get("asset_ids")
        asset_ids = approved_assets if isinstance(approved_assets, list) and approved_assets else all_assets
        if isinstance(asset_ids, list) and asset_ids:
            asset_text = ", ".join(str(asset_id) for asset_id in asset_ids)
        else:
            asset_text = "no approved reference asset yet"
        descriptors = [
            f"{label} ({name})",
            f"role: {character.get('role_in_shot') or character.get('role') or 'story character'}",
            f"asset IDs: {asset_text}",
        ]
        for key in ("consistency_prompt", "wardrobe", "continuity_notes"):
            value = _visual_text(str(character.get(key) or ""))
            if value:
                descriptors.append(value[:180])
        character_chunks.append("; ".join(descriptors))
    chunks.append("Character identity locks: " + " | ".join(character_chunks))
    return ". ".join(chunks)


def _shot_context_text(row: ShotRow) -> str:
    parts = [
        row.chapter.title,
        row.scene.title,
        row.shot.title,
        row.shot.story_purpose,
        row.shot.visual_description,
        row.shot.location,
        getattr(row.shot, "narration", None),
    ]
    return " ".join(part for part in parts if part).lower()


def _character_color_lock(row: ShotRow) -> str:
    text = _shot_context_text(row)
    return_terms = (
        "return",
        "returned",
        "embrace",
        "embraces",
        "robe",
        "ring",
        "sandals",
        "famine",
        "pig",
        "swine",
        "hunger",
        "collapse",
        "collapsed",
        "dirty",
        "ragged",
        "torn",
    )
    younger_lock = (
        YOUNGER_RETURN_COLOR_LOCK if any(term in text for term in return_terms) else YOUNGER_BEFORE_COLOR_LOCK
    )
    return f"{FATHER_COLOR_LOCK}; {younger_lock}; {OLDER_COLOR_LOCK}"


def _action_boundary_lock(row: ShotRow) -> str:
    text = _shot_context_text(row)
    prone_terms = (
        "collapse",
        "collapsed",
        "fall",
        "falls",
        "facedown",
        "face down",
        "kneel",
        "kneeling",
        "prostrate",
        "lying",
        "lies",
    )
    if any(term in text for term in prone_terms):
        return ""
    return NO_UNREQUESTED_COLLAPSE_LOCK


VISUAL_PROMPT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("family estate", "working Judean family farmstead"),
    ("estate", "working Judean household farmstead"),
    ("limestone courtyard", "rough low limestone household courtyard"),
    ("prosperous", "modestly prosperous worked and inhabited"),
)


def _visual_text(value: str | None) -> str:
    text = (value or "").strip()
    for old, new in VISUAL_PROMPT_REPLACEMENTS:
        text = re.sub(rf"\b{re.escape(old)}\b", new, text, flags=re.IGNORECASE)
    text = re.sub(
        r"\bMaintain Photoreal cinematic realism with readable human action and natural material detail\.?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", text).strip()


def _package_style_text(value: str | None) -> str:
    text = _visual_text(value)
    if not text:
        return ""
    # Project packages often repeat generic style phrases. Keep only a compact reminder so
    # the executable positive prompt stays inside the useful attention window.
    return text[:180]


def _narrative_action_overlay(row: ShotRow, archetype: Mapping[str, Any]) -> str:
    context = _shot_context_text(row)
    archetype_id = str(archetype.get("id") or "")
    if "inheritance demand" in context or ("estate" in context and "family tension" in context):
        if archetype_id.endswith("WIDE"):
            return (
                "candid wide blocking of all three principal family members separated by space: "
                "Father in blue-teal near household doorway, Younger Son in burgundy at courtyard edge, "
                "Older Son in ochre near work tools or sheep, exactly three adult men visible, no bystanders, visible emotional distance, no one posing"
            )
        if archetype_id.endswith("ACTION"):
            return (
                "exactly three adult men visible, no bystanders: Younger Son in burgundy actively demands his inheritance with tense hand extended, "
                "Father in blue-teal answers with grave restrained sadness, Older Son in ochre watches from the working courtyard, no second Father, no crowd, "
                "mid-action candid frame, clean uninjured faces, no blood, no red marks, no injuries, no children, not a posed portrait"
            )
        if archetype_id.endswith("REACTION"):
            return (
                "restrained reaction after the demand: Father in blue-teal shows grave sadness in silence, eyes lowered or turned aside, "
                "Younger Son in burgundy remains tense out of focus, Older Son in ochre watches with contained resentment, clean uninjured faces"
            )
        if archetype_id.endswith("DETAIL"):
            return (
                "close tactile detail of inheritance tension: weathered hands, clay ledger or small coins, dusty woven sleeve, "
                "Father hesitates before surrendering property, no full-body portrait"
            )
        return (
            "relationship tension in the working courtyard: Father, Younger Son, and Older Son hold different positions, "
            "grief, demand, and resentment visible through body language"
        )
    return "candid observed moment, characters focused on each other and the story action, not looking at the camera"


def _prompt(
    db: Session,
    row: ShotRow,
    archetype: Mapping[str, Any],
    characters: list[dict[str, Any]],
) -> tuple[str, str]:
    package = _latest_prompt_package(db, row.shot.id)
    image_prompt = _visual_text(
        (package.image_prompt if package else None) or row.shot.visual_description or row.shot.title
    )
    package_negative = (package.negative_prompt if package else None) or ""
    context = _shot_context_text(row)
    legacy_historical_story = any(
        marker in context
        for marker in (
            "prodigal",
            "younger son",
            "older son",
            "inheritance demand",
            "first-century jude",
            "1st-century jude",
        )
    )
    negative_parts = [
        DEFAULT_NEGATIVE_PROMPT
        if legacy_historical_story
        else GENERIC_DEFAULT_NEGATIVE_PROMPT
    ]
    if legacy_historical_story:
        negative_parts.append(NEGATIVE_HISTORICAL_GUARDRAIL)
    if package_negative:
        negative_parts.append(package_negative)
    negative_prompt = ", ".join(negative_parts)
    package_style_lock = _package_style_text(package.style_lock_prompt if package else None)
    action_boundary = _action_boundary_lock(row)
    location = _visual_text(row.shot.location or row.scene.title)
    story_purpose = _visual_text(row.shot.story_purpose or row.scene.title)
    identity_prompt = _identity_prompt_text(row, characters)
    positive_parts = [identity_prompt]
    if legacy_historical_story:
        positive_parts.extend(
            [
                f"CineForge shot must show this exact story moment: {_narrative_action_overlay(row, archetype)}",
                _character_color_lock(row),
                "exactly three adult men visible, no bystanders, no crowd, no floating white particles, clean uninjured faces, no blood, no red face marks, no wounds, no bruises, no injuries, no children",
                f"Composition: {archetype['prompt']}",
                STYLE_LOCK,
                QUALITY_LOCK,
                action_boundary,
                f"Shot brief: {image_prompt}",
                POSITIVE_AVOIDANCE_LOCK,
            ]
        )
    else:
        positive_parts.extend(
            [
                "CineForge shot must show the exact action and subjects in the persisted shot brief",
                f"Shot brief: {image_prompt}",
                f"Composition: {archetype['prompt']}",
            ]
        )
    positive_parts.extend(
        [
            f"Location: {location}",
            f"Purpose: {story_purpose}",
            package_style_lock,
        ]
    )
    positive = ". ".join(part for part in positive_parts if part)
    positive = re.sub(r"\s+", " ", positive).strip()
    negative_prompt = re.sub(r"\s+", " ", negative_prompt).strip()
    prompt_limit = 1400 if legacy_historical_story else 2600
    return positive[:prompt_limit], negative_prompt[:1200]


def _load_source_api_workflow() -> dict[str, Any] | None:
    path = Path(SOURCE_WORKFLOW_PATH)
    if not path.exists() or not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        return None
    if "nodes" in loaded:
        return None
    if not any(isinstance(node, dict) and "class_type" in node for node in loaded.values()):
        return None
    return loaded


def _patch_source_api_workflow(
    source_workflow: Mapping[str, Any],
    *,
    positive_prompt: str,
    negative_prompt: str,
    seed: int,
    filename_prefix: str,
    model_name: str,
) -> dict[str, Any]:
    workflow = copy.deepcopy(dict(source_workflow))
    patched_prompt = False
    patched_seed = False
    patched_save = False
    patched_model = False
    patched_guidance = False
    patched_steps = False

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or "")
        if class_type == "CLIPTextEncode" and "text" in inputs:
            inputs["text"] = positive_prompt
            patched_prompt = True
        elif class_type == "RandomNoise" and "noise_seed" in inputs:
            inputs["noise_seed"] = seed
            patched_seed = True
        elif class_type == "SaveImage" and "filename_prefix" in inputs:
            inputs["filename_prefix"] = filename_prefix
            patched_save = True
        elif class_type in {"UNETLoader", "UNETLoaderGGUF"} and "unet_name" in inputs:
            inputs["unet_name"] = model_name
            patched_model = True
        elif class_type == "FluxGuidance" and "guidance" in inputs:
            inputs["guidance"] = DEFAULT_GUIDANCE
            patched_guidance = True
        elif class_type == "PrimitiveInt" and "value" in inputs:
            value = inputs.get("value")
            if isinstance(value, int) and value in {8, 24, 30, 50}:
                inputs["value"] = DEFAULT_STEPS
                patched_steps = True
        elif class_type == "Flux2Scheduler" and isinstance(inputs.get("steps"), int):
            inputs["steps"] = DEFAULT_STEPS
            patched_steps = True

    if not patched_prompt:
        raise PhaseSixImageError("Supplied FLUX2 workflow has no patchable CLIPTextEncode text input.")
    if not patched_seed:
        raise PhaseSixImageError("Supplied FLUX2 workflow has no patchable RandomNoise seed input.")
    if not patched_save:
        raise PhaseSixImageError("Supplied FLUX2 workflow has no patchable SaveImage filename_prefix input.")
    if not patched_model:
        raise PhaseSixImageError("Supplied FLUX2 workflow has no patchable Flux UNETLoader input.")
    if not patched_guidance:
        raise PhaseSixImageError("Supplied FLUX2 workflow has no patchable FluxGuidance input.")
    if not patched_steps:
        raise PhaseSixImageError("Supplied FLUX2 workflow has no patchable step-count input.")

    return workflow


def _fallback_workflow(
    positive_prompt: str,
    negative_prompt: str,
    seed: int,
    filename_prefix: str,
    reference_image: str | None = None,
    reference_strength: float = 0.0,
    *,
    archetype: Mapping[str, Any] | None = None,
    model_name: str = DEFAULT_FLUX_IMAGE_MODEL,
) -> dict[str, dict[str, Any]]:
    """Fallback executable API conversion of the configured Flux UI workflow.

    ``reference_image``/``reference_strength`` are accepted for provenance and
    future conditioning. They intentionally do not inject a source image unless a
    concrete executable conditioning path is added.
    """

    archetype = archetype or _image_archetype("")
    if not _is_flux2_model(model_name):
        return _flux1_fallback_workflow(
            positive_prompt,
            negative_prompt,
            seed,
            filename_prefix,
            archetype=archetype,
            model_name=model_name,
        )
    width = int(archetype.get("width") or DEFAULT_WIDTH)
    height = int(archetype.get("height") or DEFAULT_HEIGHT)
    model_ref: Any = ["1", 0]
    clip_ref: Any = ["2", 0]

    workflow: dict[str, dict[str, Any]] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": model_name, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": DEFAULT_FLUX_TEXT_ENCODER,
                "type": "flux2",
                "device": "default",
            },
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": DEFAULT_FLUX_VAE}},
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": negative_prompt},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": clip_ref, "text": positive_prompt},
        },
        "7": {
            "class_type": "FluxGuidance",
            "inputs": {"conditioning": ["6", 0], "guidance": DEFAULT_GUIDANCE},
        },
        "8": {
            "class_type": "BasicGuider",
            "inputs": {"model": model_ref, "conditioning": ["7", 0]},
        },
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": DEFAULT_SAMPLER}},
        "11": {
            "class_type": "Flux2Scheduler",
            "inputs": {
                "model": model_ref,
                "steps": DEFAULT_STEPS,
                "width": width,
                "height": height,
            },
        },
        "12": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "13": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["9", 0],
                "guider": ["8", 0],
                "sampler": ["10", 0],
                "sigmas": ["11", 0],
                "latent_image": ["12", 0],
            },
        },
        "14": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["13", 0], "vae": ["3", 0]},
        },
        "15": {
            "class_type": "SaveImage",
            "inputs": {"images": ["14", 0], "filename_prefix": filename_prefix},
        },
    }

    lora_name = archetype.get("lora_name")
    if isinstance(lora_name, str) and lora_name:
        strength = float(archetype.get("lora_strength") or 0.6)
        workflow["21"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["2", 0],
                "lora_name": lora_name,
                "strength_model": strength,
                "strength_clip": 0.0,
            },
        }
        model_ref = ["21", 0]
        clip_ref = ["21", 1]
        workflow["6"]["inputs"]["clip"] = clip_ref
        workflow["8"]["inputs"]["model"] = model_ref
        workflow["11"]["inputs"]["model"] = model_ref

    if reference_image and reference_strength:
        workflow["20"] = {
            "class_type": "Note",
            "inputs": {
                "text": (
                    "Reference conditioning requested but not inserted in the "
                    f"executable Flux2 API spine: {reference_image} @ {reference_strength}."
                )
            },
        }

    return workflow


def _is_flux2_model(model_name: str) -> bool:
    normalized = model_name.lower().replace("\\", "/")
    return "flux2" in normalized or "flux.2" in normalized


def _flux1_fallback_workflow(
    positive_prompt: str,
    negative_prompt: str,
    seed: int,
    filename_prefix: str,
    *,
    archetype: Mapping[str, Any],
    model_name: str,
) -> dict[str, dict[str, Any]]:
    """Executable FLUX.1 spine for installations with the original Dev stack."""

    width = int(archetype.get("width") or DEFAULT_WIDTH)
    height = int(archetype.get("height") or DEFAULT_HEIGHT)
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": model_name, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": DEFAULT_FLUX1_CLIP_L,
                "clip_name2": DEFAULT_FLUX1_T5,
                "type": "flux",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": DEFAULT_FLUX1_VAE},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": positive_prompt},
        },
        "5": {
            "class_type": "FluxGuidance",
            "inputs": {"conditioning": ["4", 0], "guidance": 3.5},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": negative_prompt},
        },
        "7": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": seed,
                "steps": DEFAULT_STEPS,
                "cfg": 1.0,
                "sampler_name": DEFAULT_SAMPLER,
                "scheduler": "simple",
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0],
                "denoise": 1.0,
            },
        },
        "9": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["8", 0], "vae": ["3", 0]},
        },
        "10": {
            "class_type": "SaveImage",
            "inputs": {"images": ["9", 0], "filename_prefix": filename_prefix},
        },
    }


def _workflow(
    positive_prompt: str,
    negative_prompt: str,
    seed: int,
    filename_prefix: str,
    reference_image: str | None = None,
    reference_strength: float = 0.0,
    *,
    archetype: Mapping[str, Any] | None = None,
    model_name: str = DEFAULT_FLUX_IMAGE_MODEL,
    source_workflow_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if source_workflow_override is not None:
        if "nodes" in source_workflow_override:
            raise PhaseSixImageError(
                "Uploaded workflow must be ComfyUI API JSON, not UI graph JSON."
            )
        source_workflow = dict(source_workflow_override)
    else:
        source_workflow = _load_source_api_workflow()
    if source_workflow is not None:
        return _patch_source_api_workflow(
            source_workflow,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            filename_prefix=filename_prefix,
            model_name=model_name,
        )
    return _fallback_workflow(
        positive_prompt,
        negative_prompt,
        seed,
        filename_prefix,
        reference_image,
        reference_strength,
        archetype=archetype,
        model_name=model_name,
    )


def _first_output_image(history_entry: Mapping[str, Any]) -> dict[str, str]:
    outputs = history_entry.get("outputs")
    if not isinstance(outputs, Mapping):
        raise PhaseSixImageError("ComfyUI history did not include outputs.")
    for output in outputs.values():
        if not isinstance(output, Mapping):
            continue
        images = output.get("images")
        if not isinstance(images, list):
            continue
        for image in images:
            if isinstance(image, Mapping) and isinstance(image.get("filename"), str):
                return {
                    "filename": image["filename"],
                    "subfolder": str(image.get("subfolder") or ""),
                    "type": str(image.get("type") or "output"),
                }
    raise PhaseSixImageError("ComfyUI finished but no output image was found.")


def _raise_for_node_errors(response_json: Mapping[str, Any]) -> None:
    node_errors = response_json.get("node_errors")
    if node_errors:
        raise PhaseSixImageError(f"ComfyUI rejected workflow node(s): {node_errors}")


def _generate_bytes(workflow: dict[str, Any], *, timeout_sec: int = 300) -> tuple[bytes, dict[str, Any]]:
    client_id = f"cineforge-phase6-{uuid4()}"
    timeout = httpx.Timeout(10.0, connect=5.0, read=30.0)
    comfyui_base_url = str(get_settings().comfyui_base_url).rstrip("/")
    with httpx.Client(base_url=comfyui_base_url, timeout=timeout) as client:
        try:
            health = client.get("/")
            health.raise_for_status()
        except httpx.HTTPError as exc:
            raise PhaseSixImageError(
                f"Local ComfyUI is not reachable at {comfyui_base_url}: {exc}"
            ) from exc

        response = client.post("/prompt", json={"prompt": workflow, "client_id": client_id})
        response.raise_for_status()
        response_json = response.json()
        _raise_for_node_errors(response_json)
        prompt_id = response_json.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise PhaseSixImageError("ComfyUI did not return a prompt_id.")

        deadline = time.monotonic() + timeout_sec
        history_entry: Mapping[str, Any] | None = None
        while time.monotonic() < deadline:
            history_response = client.get(f"/history/{prompt_id}")
            history_response.raise_for_status()
            history = history_response.json()
            maybe_entry = history.get(prompt_id) if isinstance(history, Mapping) else None
            if isinstance(maybe_entry, Mapping):
                history_entry = maybe_entry
                break
            time.sleep(1.0)

        if history_entry is None:
            raise PhaseSixImageError(
                f"ComfyUI did not finish prompt {prompt_id} within {timeout_sec} seconds."
            )

        output = _first_output_image(history_entry)
        image_response = client.get("/view", params=output)
        image_response.raise_for_status()
        return image_response.content, {
            "prompt_id": prompt_id,
            "client_id": client_id,
            "comfyui_base_url": comfyui_base_url,
            "output": output,
        }


def _workflow_model_name(workflow: Mapping[str, Any]) -> str:
    for node in workflow.values():
        if not isinstance(node, Mapping):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, Mapping):
            continue
        if node.get("class_type") in {"UNETLoader", "UNETLoaderGGUF"}:
            value = inputs.get("unet_name")
            if isinstance(value, str):
                return value
    return DEFAULT_FLUX_IMAGE_MODEL


def _set_workflow_model_name(workflow: dict[str, Any], model_name: str) -> None:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if node.get("class_type") in {"UNETLoader", "UNETLoaderGGUF"} and "unet_name" in inputs:
            inputs["unet_name"] = model_name


def _generate_with_flux_fallback(workflow: dict[str, Any]) -> tuple[bytes, dict[str, Any], str]:
    model_name = _workflow_model_name(workflow)
    try:
        data, runtime = _generate_bytes(workflow)
        return data, runtime, str(model_name)
    except (httpx.HTTPError, PhaseSixImageError) as exc:
        if model_name == FALLBACK_FLUX_IMAGE_MODEL:
            raise
        _set_workflow_model_name(workflow, FALLBACK_FLUX_IMAGE_MODEL)
        try:
            data, runtime = _generate_bytes(workflow)
            runtime["fallback_reason"] = str(exc)
            return data, runtime, FALLBACK_FLUX_IMAGE_MODEL
        except Exception:
            _set_workflow_model_name(workflow, model_name)
            raise exc


def _assert_flux_model(model_name: str) -> None:
    if not model_name.lower().startswith("flux"):
        raise PhaseSixImageError(
            f"Phase 6 still images require a Flux-family image model; got {model_name}."
        )


def _offset_seed(seed: int, offset: int) -> int:
    return max(1, (int(seed) + offset) % ((2**63) - 1))


def generate_shot(
    db: Session,
    story_id: UUID,
    shot_id: UUID,
    *,
    requested_by: str,
    seed: int | None = None,
    model_name: str = DEFAULT_FLUX_IMAGE_MODEL,
    workflow_template_id: UUID | None = None,
    workflow_label: str | None = None,
    workflow_source: str | None = None,
    workflow_api_json: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    story = _story(db, story_id)
    row = next((candidate for candidate in _shot_rows(db, story_id) if candidate.shot.id == shot_id), None)
    if row is None:
        raise PhaseSixImageError("Shot not found for this story.")

    _assert_flux_model(model_name)

    chosen_seed = seed if seed is not None else secrets.randbits(63)
    archetype = _image_archetype(row.shot.title)
    character_metadata = _character_metadata(db, row)
    scene_metadata = _scene_metadata(row)
    asset_reference_metadata = _asset_reference_metadata(db, story, row)
    positive_prompt, negative_prompt = _prompt(db, row, archetype, character_metadata)
    if asset_reference_metadata:
        asset_label_text = "; ".join(
            f"{reference.get('label')} asset ID {reference.get('asset_id')}"
            for reference in asset_reference_metadata
            if reference.get("label") and reference.get("asset_id")
        )
        if asset_label_text:
            positive_prompt = re.sub(
                r"\s+",
                " ",
                (
                    f"{positive_prompt}. Reusable asset/reference labels attached to this shot: "
                    f"{asset_label_text}. Match these references for scene continuity."
                ),
            ).strip()[:2600]
    labels = _scene_attachment_labels(scene_metadata, character_metadata, asset_reference_metadata)
    filename_prefix = f"cineforge/{story.project_id}/phase6/{_slug(_shot_code(row)).lower()}"
    workflow = _workflow(
        positive_prompt,
        negative_prompt,
        chosen_seed,
        filename_prefix,
        archetype=archetype,
        model_name=model_name,
        source_workflow_override=workflow_api_json,
    )
    image_bytes, runtime, used_model = _generate_with_flux_fallback(workflow)
    original_filename = _canonical_filename(row)
    workflow_selection = {
        "workflow_template_id": str(workflow_template_id) if workflow_template_id else None,
        "workflow_label": workflow_label,
        "workflow_source": workflow_source
        or ("uploaded_api_json" if workflow_api_json is not None else "configured_phase6_flux2_api_spine"),
        "uploaded_workflow_supplied": workflow_api_json is not None,
    }
    runtime_metadata = {
        "source": "phase_6_local_comfyui",
        "requested_by": requested_by,
        "story_id": str(story.id),
        "shot_id": str(row.shot.id),
        "shot_code": _shot_code(row),
        "scene_id": str(row.scene.id),
        "scene_number": row.scene_number,
        "label": scene_metadata["shot_code"],
        "primary_label": scene_metadata["shot_code"],
        "scene_label": scene_metadata["scene_label"],
        "labels": labels,
        "scene": scene_metadata,
        "characters": character_metadata,
        "character_names": [item["name"] for item in character_metadata],
        "character_labels": [item.get("label") for item in character_metadata],
        "character_asset_ids": [
            asset_id
            for item in character_metadata
            for asset_id in (item.get("approved_asset_ids") or item.get("asset_ids") or [])
        ],
        "asset_references": asset_reference_metadata,
        "asset_reference_ids": [
            item.get("asset_id") for item in asset_reference_metadata if item.get("asset_id")
        ],
        "asset_reference_labels": [
            item.get("label") for item in asset_reference_metadata if item.get("label")
        ],
        "shot_number": row.shot_number,
        "original_comfy_output": runtime.get("output"),
        "comfy_prompt_id": runtime.get("prompt_id"),
        "comfy_client_id": runtime.get("client_id"),
        "workflow_source_path": SOURCE_WORKFLOW_PATH,
        "workflow_selection": workflow_selection,
        "workflow_conversion": "ui_graph_to_executable_flux2_api_spine",
        "model_name": used_model,
        "seed": chosen_seed,
        "steps": DEFAULT_STEPS,
        "guidance": DEFAULT_GUIDANCE,
        "archetype": dict(archetype),
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "fallback_reason": runtime.get("fallback_reason"),
    }
    asset, created = reference_assets.upload_asset(
        db,
        project_id=story.project_id,
        kind="starting_image",
        data=image_bytes,
        original_filename=original_filename,
        content_type="image/png",
        source_type="comfyui_generated",
        approval_state="in_review",
        extra_metadata=runtime_metadata,
    )
    _merge_asset_runtime_metadata(db, asset, runtime_metadata)

    previous_asset_id = row.shot.starting_image_asset_id
    row.shot.starting_image_required = True
    row.shot.starting_image_asset_id = asset.id
    db.add(
        AuditLog(
            entity_type="shot",
            entity_id=row.shot.id,
            action="phase_six_starting_image_generated",
            details={
                "story_id": str(story.id),
                "project_id": str(story.project_id),
                "asset_id": str(asset.id),
                "previous_asset_id": str(previous_asset_id) if previous_asset_id else None,
                "created": created,
                "requested_by": requested_by,
                "model_name": used_model,
                "seed": chosen_seed,
                "workflow_source_path": SOURCE_WORKFLOW_PATH,
                "workflow_selection": workflow_selection,
                "scene": scene_metadata,
                "characters": character_metadata,
                "asset_references": asset_reference_metadata,
                "labels": labels,
            },
        )
    )
    db.commit()
    db.refresh(asset)
    db.refresh(row.shot)
    return {
        "asset": reference_assets.to_public_dict(asset, is_duplicate=not created),
        "created": created,
        "duplicate_of_existing": not created,
        "shot_id": row.shot.id,
        "previous_asset_id": previous_asset_id,
        "status": status(db, story_id, runtime_reachable=True),
        "prompt_id": runtime.get("prompt_id"),
        "model_name": used_model,
        "seed": chosen_seed,
    }


def generate_character_reference(
    db: Session,
    story_id: UUID,
    character_id: UUID,
    *,
    requested_by: str,
    seed: int | None = None,
    model_name: str = DEFAULT_FLUX_IMAGE_MODEL,
    workflow_template_id: UUID | None = None,
    workflow_label: str | None = None,
    workflow_source: str | None = None,
    workflow_api_json: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    story = _story(db, story_id)
    character = db.get(Character, character_id)
    if character is None or character.story_id != story_id or character.archived_at is not None:
        raise PhaseSixImageError("Character not found for this story.")
    _assert_flux_model(model_name)

    label = _character_label_map(db, story_id).get(character.id, f"CHAR-?? {character.name}")
    chosen_seed = seed if seed is not None else secrets.randbits(63)
    archetype = _image_archetype("principal portrait")
    positive_parts = [
        f"CineForge character reference label: {label}",
        "single character identity reference image, one person only, waist-up portrait or clean full-body plate, neutral readable pose, consistent face, hair, wardrobe, and silhouette",
        f"Production title: {story.title}",
        f"Visual style: {_visual_text(story.visual_style)}",
        f"Tone: {_visual_text(story.tone)}",
        f"Character name: {character.name}",
        f"Role: {_visual_text(character.role)}",
        f"Age range: {_visual_text(character.age_range)}",
        f"Physical description: {_visual_text(character.physical_description)}",
        f"Wardrobe: {_visual_text(character.wardrobe)}",
        f"Identity consistency: {_visual_text(character.consistency_prompt)}",
        "no other characters, no split screen, no text, no watermark, no logo",
    ]
    positive_prompt = re.sub(r"\s+", " ", ". ".join(part for part in positive_parts if part)).strip()[:2600]
    negative_prompt = re.sub(
        r"\s+",
        " ",
        ", ".join(
            part
            for part in (
                GENERIC_DEFAULT_NEGATIVE_PROMPT,
                "multiple people, crowd, duplicate subject, text label, caption, logo, watermark",
                character.negative_identity_prompt,
            )
            if part
        ),
    ).strip()[:1200]
    filename_prefix = f"cineforge/{story.project_id}/phase5/characters/{_slug(label).lower()}"
    workflow = _workflow(
        positive_prompt,
        negative_prompt,
        chosen_seed,
        filename_prefix,
        archetype=archetype,
        model_name=model_name,
        source_workflow_override=workflow_api_json,
    )
    image_bytes, runtime, used_model = _generate_with_flux_fallback(workflow)
    workflow_selection = {
        "workflow_template_id": str(workflow_template_id) if workflow_template_id else None,
        "workflow_label": workflow_label,
        "workflow_source": workflow_source
        or ("uploaded_api_json" if workflow_api_json is not None else "configured_phase6_flux2_api_spine"),
        "uploaded_workflow_supplied": workflow_api_json is not None,
    }
    labels = {
        "primary": label,
        "characters": [
            {
                "entity_type": "character",
                "entity_id": str(character.id),
                "label": label,
                "name": character.name,
            }
        ],
        "attachments": [
            {
                "entity_type": "character",
                "entity_id": str(character.id),
                "label": label,
                "name": character.name,
            }
        ],
    }
    runtime_metadata = {
        "source": "phase_5_local_comfyui_character_reference",
        "requested_by": requested_by,
        "story_id": str(story.id),
        "character_id": str(character.id),
        "character_name": character.name,
        "label": label,
        "primary_label": label,
        "labels": labels,
        "original_comfy_output": runtime.get("output"),
        "comfy_prompt_id": runtime.get("prompt_id"),
        "comfy_client_id": runtime.get("client_id"),
        "workflow_source_path": SOURCE_WORKFLOW_PATH,
        "workflow_selection": workflow_selection,
        "workflow_conversion": "ui_graph_to_executable_flux2_api_spine",
        "model_name": used_model,
        "seed": chosen_seed,
        "steps": DEFAULT_STEPS,
        "guidance": DEFAULT_GUIDANCE,
        "archetype": dict(archetype),
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "fallback_reason": runtime.get("fallback_reason"),
    }
    asset, created = reference_assets.upload_asset(
        db,
        project_id=story.project_id,
        kind="character_reference",
        data=image_bytes,
        original_filename=f"{_slug(label)}.png",
        content_type="image/png",
        source_type="comfyui_generated",
        approval_state="in_review",
        extra_metadata=runtime_metadata,
    )
    labels["characters"][0]["asset_ids"] = [str(asset.id)]
    labels["attachments"][0]["asset_ids"] = [str(asset.id)]
    runtime_metadata["asset_id"] = str(asset.id)
    runtime_metadata["labels"] = labels
    _merge_asset_runtime_metadata(db, asset, runtime_metadata)

    existing_link = db.scalar(
        select(CharacterReferenceAsset).where(
            CharacterReferenceAsset.character_id == character.id,
            CharacterReferenceAsset.asset_id == asset.id,
        )
    )
    if existing_link is None:
        next_order = (
            db.scalar(
                select(func.max(CharacterReferenceAsset.order_index)).where(
                    CharacterReferenceAsset.character_id == character.id
                )
            )
            or -1
        ) + 1
        db.add(
            CharacterReferenceAsset(
                character_id=character.id,
                asset_id=asset.id,
                reference_role="generated_phase5",
                approved=False,
                order_index=next_order,
            )
        )

    db.add(
        AuditLog(
            entity_type="character",
            entity_id=character.id,
            action="phase_five_character_reference_generated",
            details={
                "story_id": str(story.id),
                "project_id": str(story.project_id),
                "asset_id": str(asset.id),
                "created": created,
                "requested_by": requested_by,
                "model_name": used_model,
                "seed": chosen_seed,
                "workflow_selection": workflow_selection,
                "label": label,
            },
        )
    )
    db.commit()
    db.refresh(asset)
    return {
        "asset": reference_assets.to_public_dict(asset, is_duplicate=not created),
        "created": created,
        "duplicate_of_existing": not created,
        "entity_type": "character",
        "entity_id": character.id,
        "label": label,
        "prompt_id": runtime.get("prompt_id"),
        "model_name": used_model,
        "seed": chosen_seed,
    }


def generate_asset_reference(
    db: Session,
    story_id: UUID,
    target: AssetReferenceTarget,
    *,
    requested_by: str,
    seed: int | None = None,
    model_name: str = DEFAULT_FLUX_IMAGE_MODEL,
    workflow_template_id: UUID | None = None,
    workflow_label: str | None = None,
    workflow_source: str | None = None,
    workflow_api_json: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    story = _story(db, story_id)
    _assert_flux_model(model_name)
    chosen_seed = seed if seed is not None else secrets.randbits(63)
    archetype = _image_archetype("wide establishing")
    positive_parts = [
        f"CineForge reusable asset/reference label: {target.label}",
        target.prompt,
        f"Production title: {story.title}",
        f"Visual style: {_visual_text(story.visual_style)}",
        f"Tone: {_visual_text(story.tone)}",
        "production reference plate, continuity guide, clean composition, practical cinematic lighting",
    ]
    positive_prompt = re.sub(r"\s+", " ", ". ".join(part for part in positive_parts if part)).strip()[:2600]
    negative_prompt = re.sub(
        r"\s+",
        " ",
        ", ".join(
            (
                GENERIC_DEFAULT_NEGATIVE_PROMPT,
                "text label, caption, logo, watermark, duplicate objects, confusing scale, random unrelated props",
            )
        ),
    ).strip()[:1200]
    filename_prefix = f"cineforge/{story.project_id}/phase5/assets/{_slug(target.label).lower()}"
    workflow = _workflow(
        positive_prompt,
        negative_prompt,
        chosen_seed,
        filename_prefix,
        archetype=archetype,
        model_name=model_name,
        source_workflow_override=workflow_api_json,
    )
    image_bytes, runtime, used_model = _generate_with_flux_fallback(workflow)
    workflow_selection = {
        "workflow_template_id": str(workflow_template_id) if workflow_template_id else None,
        "workflow_label": workflow_label,
        "workflow_source": workflow_source
        or ("uploaded_api_json" if workflow_api_json is not None else "configured_phase6_flux2_api_spine"),
        "uploaded_workflow_supplied": workflow_api_json is not None,
    }
    labels = {
        "primary": target.label,
        "assets": [
            {
                "entity_type": "asset_reference",
                "entity_id": None,
                "label": target.label,
                "target_type": target.target_type,
                "name": target.name,
            }
        ],
        "attachments": [
            {
                "entity_type": "asset_reference",
                "entity_id": None,
                "label": target.label,
                "target_type": target.target_type,
                "name": target.name,
            },
            *[
                {
                    "entity_type": "scene",
                    "entity_id": scene_id,
                    "label": "scene attachment",
                }
                for scene_id in target.scene_ids
            ],
        ],
    }
    runtime_metadata = {
        "source": "phase_5_local_comfyui_asset_reference",
        "requested_by": requested_by,
        "story_id": str(story.id),
        "label": target.label,
        "primary_label": target.label,
        "target_type": target.target_type,
        "name": target.name,
        "scene_ids": list(target.scene_ids),
        "shot_ids": list(target.shot_ids),
        "labels": labels,
        "original_comfy_output": runtime.get("output"),
        "comfy_prompt_id": runtime.get("prompt_id"),
        "comfy_client_id": runtime.get("client_id"),
        "workflow_source_path": SOURCE_WORKFLOW_PATH,
        "workflow_selection": workflow_selection,
        "workflow_conversion": "ui_graph_to_executable_flux2_api_spine",
        "model_name": used_model,
        "seed": chosen_seed,
        "steps": DEFAULT_STEPS,
        "guidance": DEFAULT_GUIDANCE,
        "archetype": dict(archetype),
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "fallback_reason": runtime.get("fallback_reason"),
    }
    asset, created = reference_assets.upload_asset(
        db,
        project_id=story.project_id,
        kind="art_direction_reference",
        data=image_bytes,
        original_filename=f"{_slug(target.label)}.png",
        content_type="image/png",
        source_type="comfyui_generated",
        approval_state="in_review",
        extra_metadata=runtime_metadata,
    )
    labels["assets"][0]["entity_id"] = str(asset.id)
    labels["attachments"][0]["entity_id"] = str(asset.id)
    runtime_metadata["asset_id"] = str(asset.id)
    runtime_metadata["labels"] = labels
    _merge_asset_runtime_metadata(db, asset, runtime_metadata)
    db.add(
        AuditLog(
            entity_type="story",
            entity_id=story.id,
            action="phase_five_asset_reference_generated",
            details={
                "story_id": str(story.id),
                "project_id": str(story.project_id),
                "asset_id": str(asset.id),
                "created": created,
                "requested_by": requested_by,
                "model_name": used_model,
                "seed": chosen_seed,
                "workflow_selection": workflow_selection,
                "label": target.label,
                "target_type": target.target_type,
                "scene_ids": list(target.scene_ids),
                "shot_ids": list(target.shot_ids),
            },
        )
    )
    db.commit()
    db.refresh(asset)
    return {
        "asset": reference_assets.to_public_dict(asset, is_duplicate=not created),
        "created": created,
        "duplicate_of_existing": not created,
        "entity_type": "asset_reference",
        "entity_id": None,
        "label": target.label,
        "prompt_id": runtime.get("prompt_id"),
        "model_name": used_model,
        "seed": chosen_seed,
    }


def generate_phase_five_handoff(
    db: Session,
    story_id: UUID,
    *,
    requested_by: str,
    seed: int | None = None,
    model_name: str = DEFAULT_FLUX_IMAGE_MODEL,
    workflow_template_id: UUID | None = None,
    workflow_label: str | None = None,
    workflow_source: str | None = None,
    workflow_api_json: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    story = _story(db, story_id)
    _assert_flux_model(model_name)
    prepare(db, story_id, requested_by=requested_by)

    base_seed = seed if seed is not None else secrets.randbits(31)
    character_results: list[dict[str, Any]] = []
    for index, character in enumerate(_characters(db, story_id), start=0):
        character_results.append(
            generate_character_reference(
                db,
                story_id,
                character.id,
                requested_by=requested_by,
                seed=_offset_seed(base_seed, index),
                model_name=model_name,
                workflow_template_id=workflow_template_id,
                workflow_label=workflow_label,
                workflow_source=workflow_source,
                workflow_api_json=workflow_api_json,
            )
        )

    asset_results: list[dict[str, Any]] = []
    for index, target in enumerate(_asset_reference_targets(db, story_id), start=0):
        asset_results.append(
            generate_asset_reference(
                db,
                story_id,
                target,
                requested_by=requested_by,
                seed=_offset_seed(base_seed, 1000 + index),
                model_name=model_name,
                workflow_template_id=workflow_template_id,
                workflow_label=workflow_label,
                workflow_source=workflow_source,
                workflow_api_json=workflow_api_json,
            )
        )

    scene_results: list[dict[str, Any]] = []
    for index, row in enumerate(_shot_rows(db, story_id), start=0):
        scene_results.append(
            generate_shot(
                db,
                story_id,
                row.shot.id,
                requested_by=requested_by,
                seed=_offset_seed(base_seed, 2000 + index),
                model_name=model_name,
                workflow_template_id=workflow_template_id,
                workflow_label=workflow_label,
                workflow_source=workflow_source,
                workflow_api_json=workflow_api_json,
            )
        )

    final_status = status(db, story_id, runtime_reachable=True)
    db.add(
        AuditLog(
            entity_type="story",
            entity_id=story.id,
            action="phase_five_handoff_batch_generated",
            details={
                "story_id": str(story.id),
                "project_id": str(story.project_id),
                "requested_by": requested_by,
                "model_name": model_name,
                "base_seed": base_seed,
                "character_count": len(character_results),
                "asset_count": len(asset_results),
                "scene_count": len(scene_results),
                "workflow_template_id": str(workflow_template_id) if workflow_template_id else None,
                "workflow_label": workflow_label,
                "workflow_source": workflow_source
                or ("uploaded_api_json" if workflow_api_json is not None else "configured_phase6_flux2_api_spine"),
            },
        )
    )
    db.commit()
    return {
        "status": final_status,
        "message": (
            "Phase 5 handoff complete: "
            f"{len(character_results)} character reference"
            f"{'' if len(character_results) == 1 else 's'}, "
            f"{len(asset_results)} reusable asset reference"
            f"{'' if len(asset_results) == 1 else 's'}, and "
            f"{len(scene_results)} scene starting image"
            f"{'' if len(scene_results) == 1 else 's'} generated and labeled."
        ),
        "character_count": len(character_results),
        "asset_count": len(asset_results),
        "scene_count": len(scene_results),
        "generated": {
            "characters": character_results,
            "assets": asset_results,
            "scenes": scene_results,
        },
    }


def assert_phase_six_complete(db: Session, story_id: UUID) -> None:
    """Compatibility no-op.

    The local/private connector must not block local generation or downstream
    operation behind an artificial Phase 6 approval gate. Status still reports
    completeness, and QA can approve candidates explicitly.
    """

    _story(db, story_id)
