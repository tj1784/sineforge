"""Phase 7 local video queue handoff through ComfyAPI Runner.

This service does not perform audio, stitching, FFmpeg muxing, or picture lock.
It submits one local image-to-video job per approved starting image to the
trusted ComfyAPI Runner, then records the batch in the audit log.
"""

from __future__ import annotations

import copy
import json
import re
import secrets
import shutil
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import REPO_ROOT, get_settings
from backend.app.db.base import (
    AuditLog,
    Chapter,
    PlanningMediaAsset,
    Scene,
    Shot,
    ShotPromptPackage,
    Story,
)
from backend.app.services import reference_assets


class PhaseSevenVideoError(ValueError):
    pass


DEFAULT_PHASE7_WORKFLOW_LABEL = "CineForge Phase 7 WAN 2.1 LightX2V I2V 480p"
DEFAULT_PHASE7_WORKFLOW_SOURCE = "configured_phase7_wan21_lightx2v_i2v480p_api_spine"
DEFAULT_PHASE7_VIDEO_WORKFLOW_PATHS = (
    REPO_ROOT
    / "storage"
    / "handoff_workflows"
    / "cineforge-phase7-wan21-lightx2v-i2v480p.api.json",
    Path(r"C:\ComfyUI\BlokeyUI\ComfyAPI-Runner\static_workflows\cineforge-phase7-wan21-lightx2v-i2v480p.api.json"),
)
DEFAULT_COMFY_INPUT_DIR = Path(r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\input")
DEFAULT_VIDEO_FPS = 16.0
DEFAULT_VIDEO_NEGATIVE_PROMPT = (
    "static frozen frame, identity drift, different person, changed age, changed hair, "
    "wardrobe change, extra people, duplicated person, duplicate limbs, malformed hands, "
    "distorted face, waxy skin, plastic skin, illustration, anime, CGI look, low detail, "
    "blur, overprocessed HDR, oversaturation, text, captions, logos, watermark, "
    "camera discontinuity, teleportation, impossible reflections, day-night mismatch, "
    "jerky motion, flicker, warping, melting"
)


def _story(db: Session, story_id: UUID) -> Story:
    row = db.get(Story, story_id)
    if row is None:
        raise PhaseSevenVideoError("Story not found.")
    return row


def _shot_code(scene_number: int, shot_number: int, shot: Shot) -> str:
    for value in (shot.title, getattr(shot, "display_label", None)):
        if not value:
            continue
        match = re.search(r"\bS\d{2}[A-Z]\b", str(value), flags=re.IGNORECASE)
        if match:
            return match.group(0).upper()
    letter = chr(64 + shot_number) if 1 <= shot_number <= 26 else str(shot_number)
    return f"S{scene_number:02d}{letter}"


def _slug(value: str, *, fallback: str = "video") -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    text = re.sub(r"_+", "_", text)
    return text[:72] or fallback


def _shot_rows(db: Session, story_id: UUID) -> list[tuple[Chapter, Scene, Shot, int, int]]:
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
    result: list[tuple[Chapter, Scene, Shot, int, int]] = []
    current_scene_id: UUID | None = None
    scene_number = 0
    shot_number_by_scene: dict[UUID, int] = {}
    seen: set[UUID] = set()
    for chapter, scene, shot in rows:
        if shot.id in seen:
            continue
        seen.add(shot.id)
        if scene.id != current_scene_id:
            current_scene_id = scene.id
            scene_number += 1
        shot_number_by_scene[scene.id] = shot_number_by_scene.get(scene.id, 0) + 1
        result.append((chapter, scene, shot, scene_number, shot_number_by_scene[scene.id]))
    return result


def _latest_prompt_package(db: Session, shot_id: UUID) -> ShotPromptPackage | None:
    return db.scalar(
        select(ShotPromptPackage)
        .where(ShotPromptPackage.shot_id == shot_id)
        .order_by(ShotPromptPackage.version.desc(), ShotPromptPackage.created_at.desc())
    )


def _metadata_payload(asset: PlanningMediaAsset) -> dict[str, Any]:
    metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
    client = metadata.get("client")
    merged = dict(client) if isinstance(client, dict) else {}
    merged.update(metadata)
    return merged


def _load_workflow(workflow_api_json: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if workflow_api_json is not None:
        workflow = copy.deepcopy(dict(workflow_api_json))
        if "nodes" in workflow:
            raise PhaseSevenVideoError("Uploaded video workflow must be ComfyUI API JSON, not UI graph JSON.")
        return workflow
    for path in DEFAULT_PHASE7_VIDEO_WORKFLOW_PATHS:
        if path.exists() and path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and "nodes" not in loaded:
                return loaded
    raise PhaseSevenVideoError(
        "Phase 7 video workflow API JSON was not found. Add the static workflow or upload one."
    )


def _copy_starting_image_to_comfy_input(
    story: Story,
    shot_code: str,
    asset: PlanningMediaAsset,
    input_dir: Path = DEFAULT_COMFY_INPUT_DIR,
) -> str:
    source_path = reference_assets.resolve_managed_path(asset)
    extension = source_path.suffix.lower() or ".png"
    relative_name = Path("cineforge") / str(story.project_id) / "phase7" / f"{_slug(shot_code).lower()}_{asset.id}{extension}"
    destination = (input_dir / relative_name).resolve()
    input_root = input_dir.resolve()
    try:
        destination.relative_to(input_root)
    except ValueError as exc:
        raise PhaseSevenVideoError("Computed ComfyUI input path escapes the input folder.") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.stat().st_size != source_path.stat().st_size:
        shutil.copy2(source_path, destination)
    return str(relative_name).replace("/", "\\")


def _frame_count(duration_sec: float | None) -> int:
    duration = float(duration_sec or 8.0)
    if duration <= 6.75:
        return 97
    if duration >= 8.75:
        return 161
    return 121


def _build_video_prompt(
    story: Story,
    scene: Scene,
    shot: Shot,
    shot_code: str,
    starting_asset: PlanningMediaAsset,
    package: ShotPromptPackage | None,
) -> tuple[str, str]:
    metadata = _metadata_payload(starting_asset)
    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    character_labels = []
    asset_labels = []
    if isinstance(labels, dict):
        for item in labels.get("characters") or []:
            if isinstance(item, dict) and item.get("label"):
                character_labels.append(str(item["label"]))
        for item in labels.get("assets") or []:
            if isinstance(item, dict) and item.get("label"):
                asset_labels.append(str(item["label"]))
    positive_parts = [
        f"[PROJECT_ID:{story.project_id}]",
        f"[STORY_ID:{story.id}]",
        f"[SCENE_ID:{scene.id}]",
        f"[SHOT_ID:{shot.id}]",
        f"[SHOT_TAG:{shot_code}]",
        f"[STARTING_IMAGE_ASSET_ID:{starting_asset.id}]",
        f"[CHARACTER_LABELS:{', '.join(character_labels)}]" if character_labels else "",
        f"[ASSET_LABELS:{', '.join(asset_labels)}]" if asset_labels else "",
        package.video_prompt if package else None,
        shot.motion_direction,
        shot.camera_direction,
        shot.visual_description,
        shot.story_purpose,
        f"Scene: {scene.title}",
        f"Location: {shot.location or scene.location}",
        "Preserve the exact approved starting frame as the first frame. Keep character identity, wardrobe, geography, lighting, and reusable asset continuity locked to the approved references.",
        "Natural human motion, realistic weight and inertia, restrained cinematic camera movement, no sudden continuity changes.",
    ]
    positive = " ".join(str(part).strip() for part in positive_parts if str(part or "").strip())
    negative_parts = [DEFAULT_VIDEO_NEGATIVE_PROMPT]
    if package and package.negative_prompt:
        negative_parts.append(package.negative_prompt)
    negative = ", ".join(part for part in negative_parts if part)
    return re.sub(r"\s+", " ", positive).strip()[:3200], re.sub(r"\s+", " ", negative).strip()[:1400]


def _patch_video_workflow(
    workflow: Mapping[str, Any],
    *,
    positive_prompt: str,
    negative_prompt: str,
    seed: int,
    input_image: str,
    frame_count: int,
    output_prefix: str,
) -> dict[str, Any]:
    patched = copy.deepcopy(dict(workflow))
    try:
        patched["5"]["inputs"]["text"] = positive_prompt
        patched["6"]["inputs"]["text"] = negative_prompt
        patched["8"]["inputs"]["image"] = input_image
        patched["10"]["inputs"]["length"] = frame_count
        patched["11"]["inputs"]["noise_seed"] = seed
        patched["13"]["inputs"]["filename_prefix"] = output_prefix
    except KeyError as exc:
        raise PhaseSevenVideoError(f"Phase 7 workflow is missing required patch node/input: {exc}") from exc
    return patched


def _post_runner_job(
    workflow: Mapping[str, Any],
    *,
    workflow_name: str,
    input_dir: Path = DEFAULT_COMFY_INPUT_DIR,
) -> str:
    runner_url = str(get_settings().comfy_api_runner_base_url).rstrip("/")
    payload = {
        "workflow": workflow,
        "workflowName": workflow_name,
        "comfyUrl": str(get_settings().comfyui_base_url).rstrip("/"),
        "inputDir": str(input_dir),
        "queueCount": 1,
        "runMode": "direct",
        "mergeMovie": False,
        "varySeed": False,
        "saveLatents": False,
    }
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        response = client.post(f"{runner_url}/api/run", json=payload)
        response.raise_for_status()
        data = response.json()
    job_id = data.get("jobId")
    if not isinstance(job_id, str) or not job_id:
        raise PhaseSevenVideoError(f"ComfyAPI Runner did not return a jobId: {data}")
    return job_id


def queue_story_videos(
    db: Session,
    story_id: UUID,
    *,
    requested_by: str,
    seed: int | None = None,
    workflow_label: str | None = None,
    workflow_source: str | None = None,
    workflow_api_json: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    story = _story(db, story_id)
    rows = _shot_rows(db, story_id)
    if not rows:
        raise PhaseSevenVideoError("Phase 7 has no shots to queue.")

    blockers: list[str] = []
    eligible: list[tuple[Chapter, Scene, Shot, int, int, PlanningMediaAsset]] = []
    for chapter, scene, shot, scene_number, shot_number in rows:
        shot_code = _shot_code(scene_number, shot_number, shot)
        if not shot.starting_image_asset_id:
            blockers.append(f"{shot_code}: no starting image is assigned.")
            continue
        asset = db.get(PlanningMediaAsset, shot.starting_image_asset_id)
        if asset is None or asset.archived_at is not None or asset.kind != "starting_image":
            blockers.append(f"{shot_code}: assigned starting image is missing or invalid.")
            continue
        if asset.approval_state != "approved":
            blockers.append(f"{shot_code}: starting image is {asset.approval_state}, not approved.")
            continue
        eligible.append((chapter, scene, shot, scene_number, shot_number, asset))

    if blockers:
        return {
            "queued_count": 0,
            "blocked_count": len(blockers),
            "required_count": len(rows),
            "message": "Video queue blocked until every planned shot has an approved starting image.",
            "runner_url": str(get_settings().comfy_api_runner_base_url).rstrip("/"),
            "workflow_label": workflow_label or DEFAULT_PHASE7_WORKFLOW_LABEL,
            "jobs": [],
            "blockers": blockers,
        }

    base_workflow = _load_workflow(workflow_api_json)
    base_seed = seed if seed is not None else secrets.randbits(31)
    jobs: list[dict[str, Any]] = []
    for index, (_chapter, scene, shot, scene_number, shot_number, asset) in enumerate(eligible):
        shot_code = _shot_code(scene_number, shot_number, shot)
        chosen_seed = max(1, (base_seed + index) % ((2**31) - 1))
        frame_count = _frame_count(float(shot.duration_sec or 8.0))
        package = _latest_prompt_package(db, shot.id)
        positive_prompt, negative_prompt = _build_video_prompt(
            story, scene, shot, shot_code, asset, package
        )
        input_image = _copy_starting_image_to_comfy_input(story, shot_code, asset)
        output_prefix = f"cineforge\\{story.project_id}\\phase7\\{_slug(shot_code).lower()}_video"
        patched = _patch_video_workflow(
            base_workflow,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            seed=chosen_seed,
            input_image=input_image,
            frame_count=frame_count,
            output_prefix=output_prefix,
        )
        runner_job_id = _post_runner_job(
            patched,
            workflow_name=f"{shot_code} {shot.title}",
        )
        jobs.append(
            {
                "shot_id": shot.id,
                "starting_image_asset_id": asset.id,
                "runner_job_id": runner_job_id,
                "shot_code": shot_code,
                "prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "seed": chosen_seed,
                "frame_count": frame_count,
                "input_image": input_image,
                "output_prefix": output_prefix,
            }
        )

    db.add(
        AuditLog(
            entity_type="story",
            entity_id=story.id,
            action="phase_seven_video_jobs_queued",
            details={
                "story_id": str(story.id),
                "project_id": str(story.project_id),
                "requested_by": requested_by,
                "queued_count": len(jobs),
                "base_seed": base_seed,
                "runner_url": str(get_settings().comfy_api_runner_base_url).rstrip("/"),
                "workflow_label": workflow_label or DEFAULT_PHASE7_WORKFLOW_LABEL,
                "workflow_source": workflow_source
                or ("uploaded_api_json" if workflow_api_json is not None else DEFAULT_PHASE7_WORKFLOW_SOURCE),
                "runner_job_ids": [item["runner_job_id"] for item in jobs],
            },
        )
    )
    db.commit()
    return {
        "queued_count": len(jobs),
        "blocked_count": 0,
        "required_count": len(rows),
        "message": f"Queued {len(jobs)} Phase 7 video prompt{'' if len(jobs) == 1 else 's'} in ComfyAPI Runner.",
        "runner_url": str(get_settings().comfy_api_runner_base_url).rstrip("/"),
        "workflow_label": workflow_label or DEFAULT_PHASE7_WORKFLOW_LABEL,
        "jobs": jobs,
        "blockers": [],
    }
