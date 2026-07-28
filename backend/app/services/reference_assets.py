"""Managed planning-media reference asset service (Storyboard Phase 1).

Safety guarantees:
- Fixed managed root under settings.storage_root (no arbitrary paths).
- Generated on-disk names only; original filename is metadata only.
- MIME + extension allowlist per asset kind.
- Bounded upload size.
- SHA-256 content hashing with per-project, per-kind duplicate detection (never cloning).
- Optional image/audio metadata extraction from safe existing deps / stdlib.
- Soft archive + constrained delete policy with audit trail.
- Clients receive asset IDs and controlled streams — never filesystem paths.
"""

from __future__ import annotations

import binascii
import hashlib
import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import uuid
import wave
import zlib
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.base import (
    AuditLog,
    Chapter,
    Character,
    CharacterReferenceAsset,
    PlanningMediaAsset,
    Project,
    Scene,
    Shot,
    Story,
    VoicePreview,
    VoiceProfile,
)


class ReferenceAssetError(ValueError):
    """Domain validation / policy failure (typically HTTP 422)."""


class ReferenceAssetNotFoundError(ReferenceAssetError):
    """Missing entity (typically HTTP 404)."""


class ReferenceAssetConflictError(Exception):
    """Conflict such as duplicate link order (typically HTTP 409)."""


# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

MANAGED_SUBDIR = "planning_media"
MANAGED_URI_SCHEME = "cineforge-planning"

ASSET_KINDS = frozenset(
    {
        "character_reference",
        "art_direction_reference",
        "starting_image",
        "video_source",
        "voice_source",
        "story_document",
    }
)

ACTIVE_APPROVAL_STATES = frozenset({"draft", "in_review", "approved", "blocked"})

# Per-kind allowlists: MIME types, extensions (lowercase with dot), max bytes.
KIND_POLICY: dict[str, dict] = {
    "character_reference": {
        "mimes": frozenset({"image/png", "image/jpeg", "image/webp"}),
        "extensions": frozenset({".png", ".jpg", ".jpeg", ".webp"}),
        "max_bytes": 25 * 1024 * 1024,
        "category": "image",
    },
    "art_direction_reference": {
        "mimes": frozenset({"image/png", "image/jpeg", "image/webp"}),
        "extensions": frozenset({".png", ".jpg", ".jpeg", ".webp"}),
        "max_bytes": 25 * 1024 * 1024,
        "category": "image",
    },
    "starting_image": {
        "mimes": frozenset({"image/png", "image/jpeg", "image/webp"}),
        "extensions": frozenset({".png", ".jpg", ".jpeg", ".webp"}),
        "max_bytes": 25 * 1024 * 1024,
        "category": "image",
    },
    "voice_source": {
        "mimes": frozenset(
            {
                "audio/wav",
                "audio/x-wav",
                "audio/wave",
                "audio/mpeg",
                "audio/mp3",
                "audio/ogg",
                "audio/flac",
            }
        ),
        "extensions": frozenset({".wav", ".mp3", ".ogg", ".flac"}),
        "max_bytes": 50 * 1024 * 1024,
        "category": "audio",
    },
    "video_source": {
        "mimes": frozenset(
            {
                "video/mp4",
                "video/quicktime",
                "video/x-matroska",
                "video/webm",
            }
        ),
        "extensions": frozenset({".mp4", ".mov", ".mkv", ".webm"}),
        "max_bytes": 4 * 1024 * 1024 * 1024,
        "category": "video",
    },
    "story_document": {
        "mimes": frozenset(
            {
                "text/plain",
                "text/markdown",
                "text/x-markdown",
                "application/pdf",
                "application/json",
            }
        ),
        "extensions": frozenset({".txt", ".md", ".markdown", ".pdf", ".json"}),
        "max_bytes": 10 * 1024 * 1024,
        "category": "document",
    },
}

# Normalize common browser MIME aliases onto canonical allowlist entries.
MIME_ALIASES: dict[str, str] = {
    "image/jpg": "image/jpeg",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/mp3": "audio/mpeg",
    "text/x-markdown": "text/markdown",
}

_SAFE_ORIGINAL_NAME = re.compile(r"[^A-Za-z0-9._\- ]+")


# ---------------------------------------------------------------------------
# Managed root / path safety
# ---------------------------------------------------------------------------


def managed_root() -> Path:
    """Fixed managed root abstraction under settings.storage_root."""
    root = (get_settings().storage_root / MANAGED_SUBDIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _project_dir(project_id: UUID) -> Path:
    path = managed_root() / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _kind_dir(project_id: UUID, kind: str) -> Path:
    path = _project_dir(project_id) / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_managed_uri(project_id: UUID, kind: str, stored_name: str) -> str:
    """Logical URI only — never a raw filesystem path for clients."""
    return f"{MANAGED_URI_SCHEME}://{project_id}/{kind}/{stored_name}"


def resolve_managed_path(asset: PlanningMediaAsset) -> Path:
    """Resolve an asset's on-disk path strictly under the managed root."""
    uri = asset.managed_uri or ""
    prefix = f"{MANAGED_URI_SCHEME}://"
    if not uri.startswith(prefix):
        raise ReferenceAssetError("Asset managed_uri is not a recognized managed URI.")
    remainder = uri[len(prefix) :]
    parts = remainder.split("/")
    if len(parts) != 3:
        raise ReferenceAssetError("Asset managed_uri has unexpected shape.")
    project_part, kind_part, name_part = parts
    if project_part != str(asset.project_id):
        raise ReferenceAssetError("Asset managed_uri project mismatch.")
    if kind_part != asset.kind:
        raise ReferenceAssetError("Asset managed_uri kind mismatch.")
    if ".." in name_part or "/" in name_part or "\\" in name_part or not name_part:
        raise ReferenceAssetError("Asset managed_uri name is unsafe.")

    root = managed_root()
    candidate = (root / project_part / kind_part / name_part).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ReferenceAssetError("Resolved path escapes managed root.") from exc
    return candidate


# ---------------------------------------------------------------------------
# Filename / MIME helpers
# ---------------------------------------------------------------------------


def _sanitize_original_filename(name: str | None) -> str | None:
    if not name:
        return None
    base = Path(name).name  # strip any path components
    cleaned = _SAFE_ORIGINAL_NAME.sub("_", base).strip(" .")
    if not cleaned:
        return None
    return cleaned[:240]


def _extension_for(original_filename: str | None, mime_type: str | None) -> str:
    if original_filename:
        ext = Path(original_filename).suffix.lower()
        if ext:
            return ext
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type.split(";")[0].strip())
        if guessed == ".jpe":
            return ".jpg"
        if guessed:
            return guessed.lower()
    return ""


def _normalize_mime(content_type: str | None, extension: str) -> str | None:
    raw = (content_type or "").split(";")[0].strip().lower() or None
    if raw:
        raw = MIME_ALIASES.get(raw, raw)
        return raw
    if extension:
        guessed, _ = mimetypes.guess_type(f"file{extension}")
        if guessed:
            return MIME_ALIASES.get(guessed, guessed)
    return None


def _validate_kind_and_payload(
    kind: str,
    *,
    size_bytes: int,
    mime_type: str | None,
    extension: str,
) -> dict:
    if kind not in ASSET_KINDS:
        raise ReferenceAssetError(
            f"Unsupported asset kind '{kind}'. Allowed: {sorted(ASSET_KINDS)}."
        )
    policy = KIND_POLICY[kind]
    if size_bytes <= 0:
        raise ReferenceAssetError("Upload is empty.")
    if size_bytes > policy["max_bytes"]:
        raise ReferenceAssetError(
            f"Upload exceeds maximum size of {policy['max_bytes']} bytes for kind '{kind}'."
        )
    if extension not in policy["extensions"]:
        raise ReferenceAssetError(
            f"Extension '{extension or '(none)'}' is not allowed for kind '{kind}'. "
            f"Allowed: {sorted(policy['extensions'])}."
        )
    if not mime_type or mime_type not in policy["mimes"]:
        raise ReferenceAssetError(
            f"MIME type '{mime_type or '(none)'}' is not allowed for kind '{kind}'. "
            f"Allowed: {sorted(policy['mimes'])}."
        )
    return policy


# ---------------------------------------------------------------------------
# Metadata extraction (safe / optional)
# ---------------------------------------------------------------------------


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        return None
    i = 2
    length = len(data)
    while i + 9 < length:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        i += 2
        if marker in {0xD8, 0xD9}:
            continue
        if i + 2 > length:
            return None
        seg_len = struct.unpack(">H", data[i : i + 2])[0]
        if seg_len < 2:
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if i + 7 > length:
                return None
            height, width = struct.unpack(">HH", data[i + 3 : i + 7])
            return int(width), int(height)
        i += seg_len
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30:
        # Lossy bitstream: width/height in frame header (14-bit little endian).
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return int(width), int(height)
    if chunk == b"VP8L" and len(data) >= 25:
        b0, b1, b2, b3 = data[21:25]
        width = 1 + (((b1 & 0x3F) << 8) | b0)
        height = 1 + (((b3 & 0xF) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return int(width), int(height)
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return int(width), int(height)
    return None


def _image_dimensions(data: bytes, mime_type: str | None) -> tuple[int | None, int | None]:
    # Prefer lightweight header parsing; fall back to Pillow if present.
    dims = None
    if mime_type == "image/png" or data[:8] == b"\x89PNG\r\n\x1a\n":
        dims = _png_dimensions(data)
    elif mime_type == "image/jpeg" or data[:2] == b"\xff\xd8":
        dims = _jpeg_dimensions(data)
    elif mime_type == "image/webp" or (len(data) >= 12 and data[8:12] == b"WEBP"):
        dims = _webp_dimensions(data)

    if dims is None:
        try:
            from io import BytesIO

            from PIL import Image  # type: ignore

            with Image.open(BytesIO(data)) as img:
                dims = (int(img.width), int(img.height))
        except Exception:
            dims = None

    if dims is None:
        return None, None
    return dims[0], dims[1]


def _image_bytes_are_decodable(data: bytes, mime_type: str | None) -> bool:
    """Verify supported image bytes without requiring an external decoder.

    Pillow is used when installed. The dependency-free fallbacks validate the
    complete PNG chunk stream (including CRCs and compressed pixel data), the
    JPEG framing/dimensions, or the WebP RIFF envelope/dimensions.
    """
    try:
        from io import BytesIO

        from PIL import Image  # type: ignore

        with Image.open(BytesIO(data)) as image:
            image.load()
        return True
    except ImportError:
        pass
    except Exception:
        return False

    width, height = _image_dimensions(data, mime_type)
    if width is None or height is None or width <= 0 or height <= 0:
        return False

    if mime_type == "image/png" or data[:8] == b"\x89PNG\r\n\x1a\n":
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        offset = 8
        idat = bytearray()
        saw_ihdr = saw_iend = False
        try:
            while offset + 12 <= len(data):
                length = struct.unpack(">I", data[offset : offset + 4])[0]
                chunk_type = data[offset + 4 : offset + 8]
                chunk_end = offset + 12 + length
                if chunk_end > len(data):
                    return False
                chunk_data = data[offset + 8 : offset + 8 + length]
                recorded_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
                actual_crc = binascii.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
                if recorded_crc != actual_crc:
                    return False
                if chunk_type == b"IHDR":
                    saw_ihdr = True
                elif chunk_type == b"IDAT":
                    idat.extend(chunk_data)
                elif chunk_type == b"IEND":
                    saw_iend = True
                    offset = chunk_end
                    break
                offset = chunk_end
            if not saw_ihdr or not saw_iend or not idat:
                return False
            return bool(zlib.decompress(bytes(idat))) and offset == len(data)
        except (ValueError, struct.error, zlib.error):
            return False

    if mime_type == "image/jpeg" or data[:2] == b"\xff\xd8":
        return data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"

    if mime_type == "image/webp" or (len(data) >= 12 and data[8:12] == b"WEBP"):
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            return False
        return int.from_bytes(data[4:8], "little") + 8 == len(data)

    return False


def _wav_duration_sec(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if rate <= 0:
                return None
            return round(frames / float(rate), 6)
    except Exception:
        return None


def _extract_metadata(
    *,
    category: str,
    data: bytes,
    mime_type: str | None,
    path: Path | None = None,
) -> dict:
    meta: dict = {"extraction": "none"}
    width = height = None
    duration_sec = None

    if category == "image":
        width, height = _image_dimensions(data, mime_type)
        if width is not None:
            meta["extraction"] = "image_headers_or_pillow"
    elif category == "audio":
        if mime_type in {"audio/wav", "audio/x-wav", "audio/wave"} and path is not None:
            duration_sec = _wav_duration_sec(path)
            if duration_sec is not None:
                meta["extraction"] = "stdlib_wave"
        # Intentionally no FFmpeg / ffprobe — never call external media tools.

    return {
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "metadata_json": meta,
    }


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------


def _project_or_error(db: Session, project_id: UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise ReferenceAssetNotFoundError("Project not found.")
    return project


def _asset_or_error(db: Session, asset_id: UUID, *, include_archived: bool = True) -> PlanningMediaAsset:
    asset = db.get(PlanningMediaAsset, asset_id)
    if asset is None:
        raise ReferenceAssetNotFoundError("Asset not found.")
    if not include_archived and asset.archived_at is not None:
        raise ReferenceAssetNotFoundError("Asset is archived.")
    return asset


def _audit(
    db: Session,
    *,
    entity_id: UUID | None,
    action: str,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            entity_type="planning_media_asset",
            entity_id=entity_id,
            action=action,
            details=details or {},
        )
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_integrity_failure(
    db: Session,
    asset: PlanningMediaAsset,
    *,
    actual_sha256: str | None,
    operation: str,
) -> None:
    _audit(
        db,
        entity_id=asset.id,
        action="planning_media_asset_integrity_failure",
        details={
            "kind": asset.kind,
            "managed_uri": asset.managed_uri,
            "expected_sha256": asset.sha256,
            "actual_sha256": actual_sha256,
            "operation": operation,
            "fail_closed": True,
        },
    )
    db.commit()


def _atomic_restore_missing(path: Path, data: bytes, expected_sha256: str) -> None:
    """Atomically install verified bytes only while the destination is absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.repair")
    try:
        with temporary_path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_sha = sha256_file(temporary_path)
        if temporary_sha != expected_sha256:
            raise ReferenceAssetError(
                "Rehydration temporary file failed SHA-256 verification."
            )
        if path.exists():
            actual_sha = sha256_file(path) if path.is_file() else None
            if actual_sha != expected_sha256:
                raise ReferenceAssetError(
                    "Managed asset appeared during rehydration with unexpected bytes."
                )
            return
        temporary_path.replace(path)
        if sha256_file(path) != expected_sha256:
            raise ReferenceAssetError(
                "Rehydrated managed file failed final SHA-256 verification."
            )
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def rehydrate_missing_asset(
    db: Session,
    asset: PlanningMediaAsset,
    *,
    source_data: bytes,
    source_sha256: str,
    source_label: str,
) -> bool:
    """Restore absent managed bytes while preserving the row and approval state.

    Existing files are never overwritten. A wrong existing SHA is audited and
    rejected. The caller must supply bytes from a manifest-verified source.
    """
    expected_sha = asset.sha256
    if not expected_sha:
        raise ReferenceAssetError("Asset database row has no SHA-256 value.")
    actual_source_sha = sha256_bytes(source_data)
    if source_sha256 != expected_sha or actual_source_sha != expected_sha:
        raise ReferenceAssetError(
            "Rehydration source SHA-256 does not match the database asset SHA-256."
        )

    policy = KIND_POLICY.get(asset.kind)
    if policy and policy["category"] == "image" and not _image_bytes_are_decodable(
        source_data, asset.mime_type
    ):
        raise ReferenceAssetError("Rehydration source image could not be decoded.")

    path = resolve_managed_path(asset)
    if path.exists():
        actual_sha = sha256_file(path) if path.is_file() else None
        if actual_sha != expected_sha:
            _record_integrity_failure(
                db,
                asset,
                actual_sha256=actual_sha,
                operation="rehydrate_missing_asset",
            )
            raise ReferenceAssetError(
                "Managed asset bytes do not match the database SHA-256; refusing to overwrite."
            )
        return False

    _atomic_restore_missing(path, source_data, expected_sha)
    _audit(
        db,
        entity_id=asset.id,
        action="planning_media_asset_bytes_rehydrated",
        details={
            "kind": asset.kind,
            "managed_uri": asset.managed_uri,
            "sha256": expected_sha,
            "size_bytes": len(source_data),
            "source_label": source_label,
            "atomic_replace": True,
            "approval_state_preserved": asset.approval_state,
        },
    )
    db.commit()
    db.refresh(asset)
    return True


def repair_duplicate_asset_bytes(
    db: Session,
    asset: PlanningMediaAsset,
    *,
    data: bytes,
    digest: str,
    mime_type: str | None,
    policy: dict,
    extra_metadata: dict | None,
) -> bool:
    """Self-heal a duplicate row's absent or corrupt managed bytes in place."""
    path = resolve_managed_path(asset)
    repair_reasons: list[str] = []
    if not path.exists():
        repair_reasons.append("managed_file_missing")
    elif not path.is_file():
        raise ReferenceAssetError("Managed asset path is not a file.")
    else:
        actual_sha = sha256_file(path)
        if actual_sha != digest:
            repair_reasons.append("sha256_mismatch")
        elif policy["category"] == "image" and not _image_bytes_are_decodable(
            path.read_bytes(), mime_type
        ):
            repair_reasons.append("image_decode_failed")

    if not repair_reasons:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.repair")
    try:
        with temporary_path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(temporary_path) != digest:
            raise ReferenceAssetError(
                "Repaired asset temporary file failed SHA-256 verification."
            )
        temporary_path.replace(path)
        if sha256_file(path) != digest:
            raise ReferenceAssetError(
                "Repaired managed asset failed final SHA-256 verification."
            )
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass

    extracted = _extract_metadata(
        category=policy["category"],
        data=data,
        mime_type=mime_type,
        path=path,
    )
    metadata = dict(asset.metadata_json or {})
    metadata.update(extracted["metadata_json"])
    if extra_metadata:
        metadata["client"] = extra_metadata
    if asset.kind == "voice_source":
        metadata["consent_confirmed"] = True

    asset.sha256 = digest
    asset.mime_type = mime_type
    asset.width = extracted["width"]
    asset.height = extracted["height"]
    asset.duration_sec = extracted["duration_sec"]
    asset.metadata_json = metadata
    asset.size_bytes = len(data)
    _audit(
        db,
        entity_id=asset.id,
        action="planning_media_asset_bytes_repaired",
        details={
            "kind": asset.kind,
            "sha256": digest,
            "size_bytes": len(data),
            "mime_type": mime_type,
            "repair_reasons": repair_reasons,
        },
    )
    db.commit()
    db.refresh(asset)
    return True


def find_duplicate(
    db: Session,
    project_id: UUID,
    kind: str,
    digest: str,
) -> PlanningMediaAsset | None:
    return db.scalar(
        select(PlanningMediaAsset).where(
            PlanningMediaAsset.project_id == project_id,
            PlanningMediaAsset.kind == kind,
            PlanningMediaAsset.sha256 == digest,
        )
    )


def _story_ids_referencing_asset(db: Session, asset_id: UUID) -> set[UUID]:
    """Resolve every story whose canonical plan directly references an asset."""
    story_ids = set(
        db.scalars(
            select(Chapter.story_id)
            .join(Scene, Scene.chapter_id == Chapter.id)
            .join(Shot, Shot.scene_id == Scene.id)
            .where(Shot.starting_image_asset_id == asset_id)
        )
    )
    story_ids.update(
        db.scalars(
            select(Character.story_id)
            .join(
                CharacterReferenceAsset,
                CharacterReferenceAsset.character_id == Character.id,
            )
            .where(CharacterReferenceAsset.asset_id == asset_id)
        )
    )
    story_ids.update(
        db.scalars(
            select(VoiceProfile.story_id).where(
                (VoiceProfile.source_asset_id == asset_id)
                | (VoiceProfile.selected_preview_asset_id == asset_id)
            )
        )
    )
    story_ids.update(
        db.scalars(
            select(VoiceProfile.story_id)
            .join(VoicePreview, VoicePreview.voice_profile_id == VoiceProfile.id)
            .where(VoicePreview.planning_media_asset_id == asset_id)
        )
    )
    return story_ids


def _mark_stories_draft(db: Session, story_ids: set[UUID]) -> None:
    if not story_ids:
        return
    changed_at = datetime.utcnow()
    stories = db.scalars(
        select(Story)
        .where(Story.id.in_(story_ids))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    for story in stories:
        story.approval_state = "draft"
        story.updated_at = changed_at


def upload_asset(
    db: Session,
    *,
    project_id: UUID,
    kind: str,
    data: bytes,
    original_filename: str | None = None,
    content_type: str | None = None,
    source_type: str = "user_upload",
    approval_state: str = "draft",
    extra_metadata: dict | None = None,
    consent_confirmed: bool | None = None,
) -> tuple[PlanningMediaAsset, bool]:
    """Store a managed asset.

    Returns (asset, created) where created=False means a same-project, same-kind
    SHA-256 duplicate was returned without cloning bytes or creating a second row.
    """
    _project_or_error(db, project_id)

    if kind == "voice_source" and consent_confirmed is not True:
        raise ReferenceAssetError(
            "Voice source uploads require explicit consent_confirmed=true."
        )

    safe_name = _sanitize_original_filename(original_filename)
    extension = _extension_for(safe_name, content_type)
    mime_type = _normalize_mime(content_type, extension)
    policy = _validate_kind_and_payload(
        kind,
        size_bytes=len(data),
        mime_type=mime_type,
        extension=extension,
    )
    if policy["category"] == "image" and not _image_bytes_are_decodable(data, mime_type):
        raise ReferenceAssetError("Image payload could not be decoded.")

    digest = sha256_bytes(data)
    existing = find_duplicate(db, project_id, kind, digest)
    if existing is not None:
        # Never clone. A verified duplicate payload is also the recovery source
        # for an absent or corrupt managed file at the existing safe path.
        repaired = repair_duplicate_asset_bytes(
            db,
            existing,
            data=data,
            digest=digest,
            mime_type=mime_type,
            policy=policy,
            extra_metadata=extra_metadata,
        )

        # Byte repair preserves approval/archive state. Legacy duplicate-upload
        # unarchiving remains available only when bytes were already healthy.
        if existing.archived_at is not None and not repaired:
            affected_story_ids = _story_ids_referencing_asset(db, existing.id)
            existing.archived_at = None
            if existing.approval_state == "archived":
                existing.approval_state = "draft"
            _mark_stories_draft(db, affected_story_ids)
            _audit(
                db,
                entity_id=existing.id,
                action="planning_media_asset_duplicate_reused_unarchived",
                details={
                    "sha256": digest,
                    "kind": kind,
                    "stories_marked_draft": sorted(
                        str(story_id) for story_id in affected_story_ids
                    ),
                },
            )
        elif not repaired:
            _audit(
                db,
                entity_id=existing.id,
                action="planning_media_asset_duplicate_reused",
                details={"sha256": digest, "kind": kind, "requested_kind": kind},
            )
        if not repaired:
            db.commit()
            db.refresh(existing)
        return existing, False

    stored_name = f"{uuid.uuid4().hex}{extension}"
    dest_dir = _kind_dir(project_id, kind)
    dest_path = (dest_dir / stored_name).resolve()
    try:
        dest_path.relative_to(managed_root())
    except ValueError as exc:
        raise ReferenceAssetError("Generated path escapes managed root.") from exc

    # Generated names still use exclusive creation so a collision can never
    # overwrite an existing managed file.
    with dest_path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if sha256_file(dest_path) != digest:
        dest_path.unlink(missing_ok=True)
        raise ReferenceAssetError("Managed asset failed SHA-256 verification after write.")
    try:
        extracted = _extract_metadata(
            category=policy["category"],
            data=data,
            mime_type=mime_type,
            path=dest_path,
        )
        metadata = dict(extracted["metadata_json"])
        if extra_metadata:
            metadata["client"] = extra_metadata
        if kind == "voice_source":
            metadata["consent_confirmed"] = True

        asset = PlanningMediaAsset(
            project_id=project_id,
            kind=kind,
            source_type=source_type,
            managed_uri=build_managed_uri(project_id, kind, stored_name),
            sha256=digest,
            mime_type=mime_type,
            width=extracted["width"],
            height=extracted["height"],
            duration_sec=extracted["duration_sec"],
            approval_state=approval_state,
            metadata_json=metadata,
            original_filename=safe_name,
            size_bytes=len(data),
        )
        db.add(asset)
        db.flush()
        _audit(
            db,
            entity_id=asset.id,
            action="planning_media_asset_uploaded",
            details={
                "kind": kind,
                "sha256": digest,
                "size_bytes": len(data),
                "mime_type": mime_type,
                "original_filename": safe_name,
            },
        )
        db.commit()
        db.refresh(asset)
        return asset, True
    except Exception:
        # Best-effort cleanup of orphaned bytes on failure.
        try:
            if dest_path.exists():
                dest_path.unlink()
        except OSError:
            pass
        db.rollback()
        raise


def stage_asset_for_transaction(
    db: Session,
    *,
    project_id: UUID,
    kind: str,
    data: bytes,
    original_filename: str,
    content_type: str,
    source_type: str = "imported",
    approval_state: str = "draft",
    extra_metadata: dict | None = None,
) -> tuple[PlanningMediaAsset, bool, Path | None]:
    """Stage one managed asset without committing so a caller can own the transaction.

    The returned path is non-null only for newly written bytes. The caller must
    delete that path if its wider transaction rolls back. Existing managed bytes
    are verified and never repaired or overwritten by this boundary.
    """
    _project_or_error(db, project_id)
    safe_name = _sanitize_original_filename(original_filename)
    extension = _extension_for(safe_name, content_type)
    mime_type = _normalize_mime(content_type, extension)
    policy = _validate_kind_and_payload(
        kind,
        size_bytes=len(data),
        mime_type=mime_type,
        extension=extension,
    )
    if policy["category"] == "image" and not _image_bytes_are_decodable(data, mime_type):
        raise ReferenceAssetError("Image payload could not be decoded.")

    digest = sha256_bytes(data)
    existing = find_duplicate(db, project_id, kind, digest)
    if existing is not None:
        if existing.archived_at is not None:
            raise ReferenceAssetError("Matching managed asset is archived; refusing implicit reuse.")
        path = resolve_managed_path(existing)
        if not path.is_file() or sha256_file(path) != digest:
            raise ReferenceAssetError(
                "Matching managed asset bytes are missing or changed; refusing implicit repair."
            )
        if existing.approval_state != approval_state:
            raise ReferenceAssetError(
                "Matching managed asset has a different approval state; refusing to change it."
            )
        return existing, False, None

    stored_name = f"{uuid.uuid4().hex}{extension}"
    dest_path = (_kind_dir(project_id, kind) / stored_name).resolve()
    try:
        dest_path.relative_to(managed_root())
    except ValueError as exc:
        raise ReferenceAssetError("Generated path escapes managed root.") from exc

    try:
        with dest_path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(dest_path) != digest:
            raise ReferenceAssetError("Managed asset failed SHA-256 verification after write.")
        extracted = _extract_metadata(
            category=policy["category"],
            data=data,
            mime_type=mime_type,
            path=dest_path,
        )
        metadata = dict(extracted["metadata_json"])
        if extra_metadata:
            metadata["client"] = extra_metadata
        asset = PlanningMediaAsset(
            project_id=project_id,
            kind=kind,
            source_type=source_type,
            managed_uri=build_managed_uri(project_id, kind, stored_name),
            sha256=digest,
            mime_type=mime_type,
            width=extracted["width"],
            height=extracted["height"],
            duration_sec=extracted["duration_sec"],
            approval_state=approval_state,
            metadata_json=metadata,
            original_filename=safe_name,
            size_bytes=len(data),
        )
        db.add(asset)
        db.flush()
        return asset, True, dest_path
    except Exception:
        try:
            dest_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def upload_asset_from_fileobj(
    db: Session,
    *,
    project_id: UUID,
    kind: str,
    fileobj: BinaryIO,
    original_filename: str | None = None,
    content_type: str | None = None,
    max_read_bytes: int | None = None,
    source_type: str = "user_upload",
    consent_confirmed: bool | None = None,
    extra_metadata: dict | None = None,
) -> tuple[PlanningMediaAsset, bool]:
    """Read a file object with an upper bound, then delegate to upload_asset."""
    if kind not in ASSET_KINDS:
        raise ReferenceAssetError(
            f"Unsupported asset kind '{kind}'. Allowed: {sorted(ASSET_KINDS)}."
        )
    limit = max_read_bytes or KIND_POLICY[kind]["max_bytes"]
    # Read one extra byte to detect oversize without trusting client Content-Length.
    data = fileobj.read(limit + 1)
    if data is None:
        data = b""
    if len(data) > limit:
        raise ReferenceAssetError(
            f"Upload exceeds maximum size of {limit} bytes for kind '{kind}'."
        )
    return upload_asset(
        db,
        project_id=project_id,
        kind=kind,
        data=data,
        original_filename=original_filename,
        content_type=content_type,
        source_type=source_type,
        consent_confirmed=consent_confirmed,
        extra_metadata=extra_metadata,
    )


def _probe_video_path(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ReferenceAssetError(
            "ffprobe is required to ingest a managed video source."
        )
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReferenceAssetError("Video probe could not be completed.") from error
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise ReferenceAssetError(
            f"Video source failed ffprobe validation{f': {detail}' if detail else '.'}"
        )
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise ReferenceAssetError("Video probe returned invalid JSON.") from error

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise ReferenceAssetError("Video probe did not return a stream list.")
    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if not isinstance(video_stream, dict):
        raise ReferenceAssetError("Uploaded media does not contain a video stream.")
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ReferenceAssetError("Video stream dimensions are missing or invalid.")

    format_payload = payload.get("format")
    format_payload = format_payload if isinstance(format_payload, dict) else {}
    duration_value = format_payload.get("duration") or video_stream.get("duration")
    try:
        duration_sec = float(duration_value)
    except (TypeError, ValueError) as error:
        raise ReferenceAssetError("Video duration is missing or invalid.") from error
    if not duration_sec > 0:
        raise ReferenceAssetError("Video duration must be positive.")

    audio_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        None,
    )
    return {
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "metadata_json": {
            "extraction": "ffprobe",
            "technical_qa": "probe_passed",
            "full_decode_required_before_picture_lock": True,
            "video_stream": {
                "codec_name": video_stream.get("codec_name"),
                "codec_long_name": video_stream.get("codec_long_name"),
                "profile": video_stream.get("profile"),
                "pix_fmt": video_stream.get("pix_fmt"),
                "avg_frame_rate": video_stream.get("avg_frame_rate"),
                "r_frame_rate": video_stream.get("r_frame_rate"),
                "time_base": video_stream.get("time_base"),
                "nb_frames": video_stream.get("nb_frames"),
            },
            "audio_stream_present": audio_stream is not None,
            "audio_stream": (
                {
                    "codec_name": audio_stream.get("codec_name"),
                    "sample_rate": audio_stream.get("sample_rate"),
                    "channels": audio_stream.get("channels"),
                    "channel_layout": audio_stream.get("channel_layout"),
                    "time_base": audio_stream.get("time_base"),
                }
                if isinstance(audio_stream, dict)
                else None
            ),
        },
    }


def upload_video_asset_from_fileobj(
    db: Session,
    *,
    project_id: UUID,
    fileobj: BinaryIO,
    original_filename: str | None,
    content_type: str | None,
    source_type: str = "user_upload",
    max_read_bytes: int | None = None,
) -> tuple[PlanningMediaAsset, bool]:
    """Stream a bounded video into managed storage and persist probe evidence.

    The file object is copied in chunks; the complete video is never loaded into
    application memory. The original upload is retained byte-for-byte under a
    generated managed name. Full decode remains a required Phase 7 QA gate.
    """

    _project_or_error(db, project_id)
    kind = "video_source"
    policy = KIND_POLICY[kind]
    safe_name = _sanitize_original_filename(original_filename)
    extension = _extension_for(safe_name, content_type)
    mime_type = _normalize_mime(content_type, extension)
    if extension not in policy["extensions"]:
        raise ReferenceAssetError(
            f"Extension '{extension or '(none)'}' is not allowed for video_source."
        )
    if not mime_type or mime_type not in policy["mimes"]:
        raise ReferenceAssetError(
            f"MIME type '{mime_type or '(none)'}' is not allowed for video_source."
        )

    limit = int(max_read_bytes or policy["max_bytes"])
    if limit <= 0 or limit > int(policy["max_bytes"]):
        raise ReferenceAssetError("Video upload byte limit is invalid.")

    token = uuid.uuid4().hex
    destination_dir = _kind_dir(project_id, kind)
    partial_path = (destination_dir / f".{token}.partial").resolve()
    final_path = (destination_dir / f"{token}{extension}").resolve()
    root = managed_root()
    for candidate in (partial_path, final_path):
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ReferenceAssetError(
                "Generated video path escapes managed storage."
            ) from error

    digest = hashlib.sha256()
    received = 0
    try:
        with partial_path.open("xb") as handle:
            while True:
                chunk = fileobj.read(min(1024 * 1024, limit - received + 1))
                if not chunk:
                    break
                received += len(chunk)
                if received > limit:
                    raise ReferenceAssetError(
                        f"Upload exceeds the {limit}-byte video_source limit."
                    )
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        _validate_kind_and_payload(
            kind,
            size_bytes=received,
            mime_type=mime_type,
            extension=extension,
        )
        content_hash = digest.hexdigest()
        if sha256_file(partial_path) != content_hash:
            raise ReferenceAssetError(
                "Managed video failed SHA-256 verification after streaming."
            )
        probe = _probe_video_path(partial_path)

        existing = find_duplicate(db, project_id, kind, content_hash)
        if existing is not None:
            existing_path = resolve_managed_path(existing)
            if (
                not existing_path.is_file()
                or sha256_file(existing_path) != content_hash
            ):
                raise ReferenceAssetError(
                    "Matching managed video bytes are missing or changed; "
                    "refusing implicit replacement."
                )
            partial_path.unlink(missing_ok=True)
            _audit(
                db,
                entity_id=existing.id,
                action="managed_video_duplicate_reused",
                details={"sha256": content_hash, "size_bytes": received},
            )
            db.commit()
            db.refresh(existing)
            return existing, False

        partial_path.replace(final_path)
        asset = PlanningMediaAsset(
            project_id=project_id,
            kind=kind,
            source_type=source_type,
            managed_uri=build_managed_uri(
                project_id, kind, final_path.name
            ),
            sha256=content_hash,
            mime_type=mime_type,
            width=probe["width"],
            height=probe["height"],
            duration_sec=probe["duration_sec"],
            approval_state="draft",
            metadata_json=probe["metadata_json"],
            original_filename=safe_name,
            size_bytes=received,
        )
        db.add(asset)
        db.flush()
        _audit(
            db,
            entity_id=asset.id,
            action="managed_video_source_uploaded",
            details={
                "sha256": content_hash,
                "size_bytes": received,
                "mime_type": mime_type,
                "duration_sec": probe["duration_sec"],
                "width": probe["width"],
                "height": probe["height"],
                "full_decode_required_before_picture_lock": True,
            },
        )
        db.commit()
        db.refresh(asset)
        return asset, True
    except Exception:
        db.rollback()
        for candidate in (partial_path, final_path):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def get_asset(
    db: Session,
    asset_id: UUID,
    *,
    include_archived: bool = True,
) -> PlanningMediaAsset:
    return _asset_or_error(db, asset_id, include_archived=include_archived)


def list_assets(
    db: Session,
    project_id: UUID,
    *,
    kind: str | None = None,
    include_archived: bool = False,
) -> list[PlanningMediaAsset]:
    _project_or_error(db, project_id)
    query = select(PlanningMediaAsset).where(PlanningMediaAsset.project_id == project_id)
    if kind is not None:
        if kind not in ASSET_KINDS:
            raise ReferenceAssetError(
                f"Unsupported asset kind '{kind}'. Allowed: {sorted(ASSET_KINDS)}."
            )
        query = query.where(PlanningMediaAsset.kind == kind)
    if not include_archived:
        query = query.where(PlanningMediaAsset.archived_at.is_(None))
    query = query.order_by(PlanningMediaAsset.created_at.desc())
    return list(db.scalars(query))


def transition_starting_image_approval(
    db: Session,
    asset_id: UUID,
    *,
    approval_state: str,
    expected_approval_state: str,
    reason: str | None = None,
    changed_by: str | None = None,
) -> PlanningMediaAsset:
    """Persist an optimistic approval-state transition on one managed starting image.

    This deliberately updates the existing asset row only. It never copies bytes,
    creates a generation job, unarchives an asset, or invokes a media runtime.
    """
    asset = _asset_or_error(db, asset_id, include_archived=True)
    if asset.kind != "starting_image":
        raise ReferenceAssetError(
            "Only starting_image assets may be changed through starting-image approval."
        )
    if asset.archived_at is not None or asset.approval_state == "archived":
        raise ReferenceAssetConflictError(
            "Archived starting-image assets cannot be reviewed or approved."
        )
    if approval_state not in ACTIVE_APPROVAL_STATES:
        raise ReferenceAssetError(
            f"Unsupported active approval state '{approval_state}'."
        )
    if expected_approval_state not in ACTIVE_APPROVAL_STATES:
        raise ReferenceAssetError(
            f"Unsupported expected approval state '{expected_approval_state}'."
        )

    current_state = asset.approval_state
    if current_state != expected_approval_state:
        raise ReferenceAssetConflictError(
            "Starting-image approval changed since it was loaded "
            f"(expected '{expected_approval_state}', found '{current_state}'). Refresh and retry."
        )

    if current_state == approval_state:
        return asset

    if approval_state == "approved":
        path = resolve_managed_path(asset)
        if not path.exists() or not path.is_file():
            raise ReferenceAssetError(
                "Starting-image bytes are unavailable in managed storage; approval was not changed."
            )

    affected_story_ids = _story_ids_referencing_asset(db, asset.id)
    asset.approval_state = approval_state
    _mark_stories_draft(db, affected_story_ids)
    _audit(
        db,
        entity_id=asset.id,
        action="planning_media_asset_approval_transitioned",
        details={
            "kind": asset.kind,
            "previous_approval_state": current_state,
            "approval_state": approval_state,
            "reason": reason,
            "changed_by": changed_by,
            "stories_marked_draft": sorted(str(story_id) for story_id in affected_story_ids),
        },
    )
    db.commit()
    db.refresh(asset)
    return asset


def archive_asset(
    db: Session,
    asset_id: UUID,
    *,
    reason: str | None = None,
) -> PlanningMediaAsset:
    asset = _asset_or_error(db, asset_id, include_archived=True)
    if asset.archived_at is not None:
        return asset
    affected_story_ids = _story_ids_referencing_asset(db, asset.id)
    asset.archived_at = datetime.utcnow()
    asset.approval_state = "archived"
    _mark_stories_draft(db, affected_story_ids)
    _audit(
        db,
        entity_id=asset.id,
        action="planning_media_asset_archived",
        details={
            "reason": reason,
            "kind": asset.kind,
            "stories_marked_draft": sorted(str(story_id) for story_id in affected_story_ids),
        },
    )
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(
    db: Session,
    asset_id: UUID,
    *,
    reason: str | None = None,
    force: bool = False,
) -> None:
    """Delete policy:

    - Prefer archive over delete.
    - Hard delete only when archived (or force=True for draft assets).
    - Removes managed file when path resolves safely under managed root.
    """
    asset = _asset_or_error(db, asset_id, include_archived=True)
    is_draft = (asset.approval_state or "") in {"draft", "archived"}
    if asset.archived_at is None and not (force and is_draft):
        raise ReferenceAssetError(
            "Hard delete requires the asset to be archived first "
            "(or force=true on a draft asset). Prefer archive."
        )

    path: Path | None = None
    try:
        path = resolve_managed_path(asset)
    except ReferenceAssetError:
        path = None

    details = {
        "reason": reason,
        "kind": asset.kind,
        "sha256": asset.sha256,
        "force": force,
        "file_removed": False,
    }

    affected_story_ids = _story_ids_referencing_asset(db, asset.id)
    _mark_stories_draft(db, affected_story_ids)
    details["stories_marked_draft"] = sorted(
        str(story_id) for story_id in affected_story_ids
    )

    # Detach character reference links first (FK is CASCADE, but be explicit).
    links = list(
        db.scalars(
            select(CharacterReferenceAsset).where(CharacterReferenceAsset.asset_id == asset_id)
        )
    )
    for link in links:
        db.delete(link)

    db.delete(asset)
    _audit(
        db,
        entity_id=asset_id,
        action="planning_media_asset_deleted",
        details=details,
    )
    db.commit()

    if path is not None and path.exists() and path.is_file():
        try:
            path.unlink()
            details["file_removed"] = True
        except OSError:
            # DB row is gone; leftover file is non-fatal. Log via audit already committed.
            pass


def open_asset_for_stream(
    db: Session,
    asset_id: UUID,
) -> tuple[PlanningMediaAsset, Path]:
    """Resolve a controlled stream path for an asset ID (no path input from client)."""
    asset = _asset_or_error(db, asset_id, include_archived=False)
    path = resolve_managed_path(asset)
    if not path.exists() or not path.is_file():
        raise ReferenceAssetNotFoundError("Asset bytes are not available on disk.")
    actual_sha = sha256_file(path)
    if not asset.sha256 or actual_sha != asset.sha256:
        _record_integrity_failure(
            db,
            asset,
            actual_sha256=actual_sha,
            operation="stream_asset_content",
        )
        raise ReferenceAssetError(
            "Asset bytes failed SHA-256 verification and will not be streamed."
        )
    return asset, path


def to_public_dict(asset: PlanningMediaAsset, *, is_duplicate: bool = False) -> dict:
    """Serialize without exposing filesystem paths."""
    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "kind": asset.kind,
        "source_type": asset.source_type,
        "managed_uri": asset.managed_uri,
        "sha256": asset.sha256,
        "mime_type": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "duration_sec": float(asset.duration_sec) if asset.duration_sec is not None else None,
        "approval_state": asset.approval_state,
        "metadata_json": asset.metadata_json or {},
        "original_filename": asset.original_filename,
        "size_bytes": asset.size_bytes,
        "archived_at": asset.archived_at,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
        "is_duplicate": is_duplicate,
    }


# ---------------------------------------------------------------------------
# Character reference linking
# ---------------------------------------------------------------------------


def link_character_reference(
    db: Session,
    *,
    character_id: UUID,
    asset_id: UUID,
    reference_role: str = "primary",
    approved: bool = False,
    order_index: int = 0,
) -> CharacterReferenceAsset:
    character = db.get(Character, character_id)
    if character is None:
        raise ReferenceAssetNotFoundError("Character not found.")
    asset = _asset_or_error(db, asset_id, include_archived=False)
    if asset.kind != "character_reference":
        raise ReferenceAssetError("Only character_reference assets may be linked to characters.")

    # Asset must belong to the same project as the character's story.
    story = db.get(Story, character.story_id)
    if story is None or story.project_id != asset.project_id:
        raise ReferenceAssetError("Asset project must match the character's story project.")

    existing_order = db.scalar(
        select(CharacterReferenceAsset).where(
            CharacterReferenceAsset.character_id == character_id,
            CharacterReferenceAsset.order_index == order_index,
        )
    )
    if existing_order is not None:
        raise ReferenceAssetConflictError(
            f"Character already has a reference at order_index={order_index}."
        )

    link = CharacterReferenceAsset(
        character_id=character_id,
        asset_id=asset_id,
        reference_role=reference_role,
        approved=approved,
        order_index=order_index,
    )
    db.add(link)
    db.flush()
    _mark_stories_draft(db, {story.id})
    _audit(
        db,
        entity_id=asset_id,
        action="character_reference_linked",
        details={
            "character_id": str(character_id),
            "reference_role": reference_role,
            "order_index": order_index,
            "link_id": str(link.id),
            "stories_marked_draft": [str(story.id)],
        },
    )
    db.commit()
    db.refresh(link)
    return link


def list_character_references(
    db: Session,
    character_id: UUID,
) -> list[CharacterReferenceAsset]:
    character = db.get(Character, character_id)
    if character is None:
        raise ReferenceAssetNotFoundError("Character not found.")
    return list(
        db.scalars(
            select(CharacterReferenceAsset)
            .where(CharacterReferenceAsset.character_id == character_id)
            .order_by(CharacterReferenceAsset.order_index)
        )
    )


def unlink_character_reference(db: Session, link_id: UUID) -> None:
    link = db.get(CharacterReferenceAsset, link_id)
    if link is None:
        raise ReferenceAssetNotFoundError("Character reference link not found.")
    asset_id = link.asset_id
    character_id = link.character_id
    character = db.get(Character, character_id)
    affected_story_ids = {character.story_id} if character is not None else set()
    db.delete(link)
    _mark_stories_draft(db, affected_story_ids)
    _audit(
        db,
        entity_id=asset_id,
        action="character_reference_unlinked",
        details={
            "character_id": str(character_id),
            "link_id": str(link_id),
            "stories_marked_draft": sorted(
                str(story_id) for story_id in affected_story_ids
            ),
        },
    )
    db.commit()
