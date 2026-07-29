"""Start LM Studio's loopback API and load SineForge's selected planning GGUF.

This administrator-owned bootstrap accepts configuration only through local
environment variables. It executes fixed ``lms`` argv lists without a shell
and never downloads, imports, or modifies model files.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_LMS_EXECUTABLE = Path.home() / ".lmstudio" / "bin" / "lms.exe"
DEFAULT_MODEL_PATH = (
    Path.home()
    / ".lmstudio"
    / "models"
    / "SulphurAI"
    / "Sulphur-2-base"
    / "sulphur_prompt_enhancer_model-q8_0.gguf"
)
DEFAULT_QWEN_MODEL_PATH = (
    Path.home()
    / ".lmstudio"
    / "models"
    / "DavidAU"
    / "Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-GGUF"
    / "Qwen3.6-40B-Deck-Opus-NEO-CODE-HERE-2T-OT-Q4_K_S.gguf"
)
DEFAULT_QWEN_MODEL_ID = (
    "qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-"
    "neo-code-di-imatrix-max"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
SAFE_MODEL_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


def _configured_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, str(default))
    if any(character in raw for character in "\r\n&|<>^`\"%'!()"):
        raise ValueError(f"{name} contains shell metacharacters")
    return Path(raw).expanduser().resolve()


def _safe_model_value(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip()
    if not SAFE_MODEL_KEY.fullmatch(value) or "\\" in value:
        raise ValueError(f"{name} must be a safe LM Studio model identifier")
    return value


def _run(
    lms: Path,
    *args: str,
    capture: bool = False,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(lms), *args],
        check=True,
        shell=False,
        text=True,
        capture_output=capture,
        timeout=timeout,
    )


def _loaded_models(lms: Path) -> list[dict[str, Any]]:
    result = _run(lms, "ps", "--json", capture=True, timeout=30)
    payload = json.loads(result.stdout or "[]")
    return payload if isinstance(payload, list) else []


def _selected_model() -> tuple[Path, str, str]:
    sulphur_path = _configured_path("CINEFORGE_SULPHUR_MODEL_PATH", DEFAULT_MODEL_PATH)
    sulphur_key = _safe_model_value(
        "CINEFORGE_SULPHUR_MODEL_KEY",
        "sulphur-2-base",
    )
    sulphur_id = _safe_model_value(
        "CINEFORGE_SULPHUR_MODEL_ID",
        "sulphur-2-base",
    )
    qwen_path = _configured_path(
        "CINEFORGE_QWEN_MODEL_PATH",
        DEFAULT_QWEN_MODEL_PATH,
    )
    qwen_id = _safe_model_value(
        "CINEFORGE_QWEN_MODEL_ID",
        DEFAULT_QWEN_MODEL_ID,
    )
    storage_root = _configured_path(
        "CINEFORGE_STORAGE_ROOT",
        REPO_ROOT / "storage",
    )
    selection_path = storage_root / "runtime" / "lm-studio-model-selection.json"
    try:
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        selection = {}
    selected_id = selection.get("model_id") if isinstance(selection, dict) else None
    if selected_id == qwen_id and qwen_path.is_file():
        return qwen_path, qwen_id, qwen_id
    return sulphur_path, sulphur_key, sulphur_id


def main() -> int:
    lms = _configured_path("CINEFORGE_LMS_EXECUTABLE", DEFAULT_LMS_EXECUTABLE)
    model_path, model_key, model_id = _selected_model()

    if not lms.is_file():
        raise FileNotFoundError(f"LM Studio CLI is missing: {lms}")
    if not model_path.is_file() or model_path.suffix.casefold() != ".gguf":
        raise FileNotFoundError(f"Configured planning GGUF is missing: {model_path}")

    _run(
        lms,
        "server",
        "start",
        "--port",
        "1234",
        "--bind",
        "127.0.0.1",
        timeout=60,
    )

    loaded = _loaded_models(lms)
    exact_model_loaded = any(
        item.get("identifier") == model_id
        and Path(str(item.get("path") or "")).name.casefold() == model_path.name.casefold()
        for item in loaded
        if isinstance(item, dict)
    )
    if exact_model_loaded:
        print(f"Planning model ready: {model_id} ({model_path.name})")
        return 0

    known_model_ids = {
        _safe_model_value("CINEFORGE_SULPHUR_MODEL_ID", "sulphur-2-base"),
        _safe_model_value(
            "CINEFORGE_QWEN_MODEL_ID",
            DEFAULT_QWEN_MODEL_ID,
        ),
    }
    for item in loaded:
        loaded_id = item.get("identifier") if isinstance(item, dict) else None
        if (
            isinstance(loaded_id, str)
            and loaded_id in known_model_ids
            and loaded_id != model_id
        ):
            _run(lms, "unload", loaded_id, timeout=120)

    _run(
        lms,
        "load",
        model_key,
        "--gpu",
        "max",
        "--context-length",
        "8192",
        "--parallel",
        "1",
        "--identifier",
        model_id,
        "--yes",
        timeout=600,
    )
    loaded = _loaded_models(lms)
    if not any(
        item.get("identifier") == model_id
        and Path(str(item.get("path") or "")).name.casefold() == model_path.name.casefold()
        for item in loaded
        if isinstance(item, dict)
    ):
        raise RuntimeError("LM Studio did not report the selected planning model as loaded")
    print(f"Planning model loaded with CUDA offload: {model_id} ({model_path.name})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Planning-model bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
