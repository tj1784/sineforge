"""Deterministic metadata for retryable Foley inference attempts."""

from __future__ import annotations

import hashlib
import json

from .contracts import AttemptMetadata, FoleyWindowPlan, PictureLockError


def build_attempt_metadata(
    window: FoleyWindowPlan,
    *,
    current_picture_lock_hash: str,
    attempt_number: int,
    base_seed: int,
    model_id: str,
    model_hash: str,
    workflow_hash: str,
    prompt_hash: str,
) -> AttemptMetadata:
    if window.picture_lock_hash != current_picture_lock_hash:
        raise PictureLockError(
            "cannot create Foley attempt metadata for a stale picture lock"
        )
    if attempt_number < 1:
        raise ValueError("attempt_number must be at least 1")
    required = {
        "model_id": model_id,
        "model_hash": model_hash,
        "workflow_hash": workflow_hash,
        "prompt_hash": prompt_hash,
    }
    empty = sorted(key for key, value in required.items() if not value.strip())
    if empty:
        raise ValueError(f"attempt metadata fields must be non-empty: {', '.join(empty)}")

    identity = {
        "window_id": window.window_id,
        "picture_lock_hash": window.picture_lock_hash,
        "attempt_number": attempt_number,
        "base_seed": base_seed,
        **required,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    # Keep the seed in ComfyUI's common non-negative signed 63-bit range.
    seed = int(digest[:16], 16) & ((1 << 63) - 1)
    return AttemptMetadata(
        attempt_id=digest,
        window_id=window.window_id,
        picture_lock_hash=window.picture_lock_hash,
        attempt_number=attempt_number,
        seed=seed,
        model_id=model_id,
        model_hash=model_hash,
        workflow_hash=workflow_hash,
        prompt_hash=prompt_hash,
    )

