"""Validate and losslessly concatenate a completed LTX operator run."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.base import (  # noqa: E402
    SequenceExecutionRun,
    SequenceRowExecution,
)
from backend.app.db.session import SessionLocal  # noqa: E402


RUN_ID = UUID("ed796b7d-cbb4-4f96-91fb-5d6d8f1bb92c")
MANIFEST_PATH = (
    ROOT / "outputs" / "i2v_sheet_processed_20260729" / "ltx_operator_run.json"
)
CONCAT_PATH = (
    ROOT / "outputs" / "i2v_sheet_processed_20260729" / "ltx_concat_inputs.txt"
)
COMFY_OUTPUT = Path(r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\output")
FINAL_PATH = (
    COMFY_OUTPUT
    / "cineforge"
    / "23e4f49a-4d70-400f-ad2b-d37baac75dfc"
    / "ltx_sequence"
    / "Drive_Home_LTX_Continuous_16x10s.mp4"
)


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if any(row.get("status") != "completed" for row in manifest["rows"]):
        raise RuntimeError("Every LTX row must complete before assembly.")

    paths: list[Path] = []
    segment_media: list[dict] = []
    for row in sorted(manifest["rows"], key=lambda item: int(item["order"])):
        output = row["outputs"]["75"]["images"][0]
        path = COMFY_OUTPUT / output["subfolder"] / output["filename"]
        if not path.is_file():
            raise FileNotFoundError(path)
        media = probe(path)
        video = next(
            stream for stream in media["streams"] if stream["codec_type"] == "video"
        )
        audio = next(
            stream for stream in media["streams"] if stream["codec_type"] == "audio"
        )
        if (
            video["codec_name"] != "h264"
            or video["width"] != 768
            or video["height"] != 448
            or video["r_frame_rate"] != "24/1"
            or audio["codec_name"] != "aac"
            or audio["sample_rate"] != "48000"
        ):
            raise RuntimeError(f"Row {row['row_id']} media contract failed: {media}")
        row["output_path"] = str(path)
        row["sha256"] = sha256(path)
        row["media"] = {
            "duration_sec": float(media["format"]["duration"]),
            "video": "h264 768x448 24fps",
            "audio": f"aac {audio['sample_rate']}Hz {audio.get('channels')}ch",
        }
        paths.append(path)
        segment_media.append(row["media"])

    lines = [
        "file '" + str(path).replace("\\", "/").replace("'", "'\\''") + "'"
        for path in paths
    ]
    CONCAT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    FINAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(CONCAT_PATH),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(FINAL_PATH),
        ],
        check=True,
    )
    final_media = probe(FINAL_PATH)
    final_video = next(
        stream
        for stream in final_media["streams"]
        if stream["codec_type"] == "video"
    )
    final_audio = next(
        stream
        for stream in final_media["streams"]
        if stream["codec_type"] == "audio"
    )
    if (
        final_video["codec_name"] != "h264"
        or final_video["width"] != 768
        or final_video["height"] != 448
        or final_audio["codec_name"] != "aac"
    ):
        raise RuntimeError("Final concatenated media contract failed.")

    completed_at = datetime.now(timezone.utc)
    with SessionLocal() as db:
        run = db.get(SequenceExecutionRun, RUN_ID)
        if run is None:
            raise RuntimeError(f"Sequence execution run {RUN_ID} is missing.")
        executions = list(
            db.scalars(
                select(SequenceRowExecution).where(
                    SequenceRowExecution.sequence_execution_run_id == RUN_ID
                )
            )
        )
        if len(executions) != len(paths):
            raise RuntimeError(
                f"Expected {len(paths)} row ledgers; found {len(executions)}."
            )
        for execution in executions:
            execution.status = "succeeded"
            execution.current_attempt = 1
            execution.lease_owner = None
            execution.lease_expires_at = None
        run.status = "completed"
        run.started_at = run.started_at or completed_at
        run.completed_at = completed_at
        db.commit()

    manifest["status"] = "completed"
    manifest["completed_at"] = completed_at.isoformat()
    manifest["segments"] = segment_media
    manifest["final_output"] = {
        "path": str(FINAL_PATH),
        "sha256": sha256(FINAL_PATH),
        "duration_sec": float(final_media["format"]["duration"]),
        "video": (
            f"{final_video['codec_name']} {final_video['width']}x"
            f"{final_video['height']} {final_video['r_frame_rate']}"
        ),
        "audio": (
            f"{final_audio['codec_name']} {final_audio['sample_rate']}Hz "
            f"{final_audio.get('channels')}ch"
        ),
        "assembly": "ffmpeg concat demuxer, stream copy",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest["final_output"], indent=2), flush=True)


if __name__ == "__main__":
    main()
