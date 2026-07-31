"""Submit and monitor the admitted 16-row Sulphur 2 LTX Sequence Sheet."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any
from urllib import error, request
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "23e4f49a-4d70-400f-ad2b-d37baac75dfc"
COMFY_URL = "http://127.0.0.1:8888"
SHEET_PATH = (
    ROOT / "outputs" / "i2v_sheet_processed_20260729" / "sineforge_sequence_sheet.json"
)
SOURCE_MANIFEST_PATH = (
    ROOT / "outputs" / "i2v_sheet_processed_20260729" / "processing_manifest.json"
)
WORKFLOW_PATH = (
    ROOT
    / "Workflows"
    / "Sulphur2"
    / "Sulphur2_LTX23_I2V_NativeAudio_API.json"
)
RUN_MANIFEST_PATH = (
    ROOT / "outputs" / "i2v_sheet_processed_20260729" / "ltx_operator_run.json"
)
OUTPUT_ROOT = Path(
    rf"C:\ComfyUI\LTX\ComfyUI\ComfyUI\output\cineforge\{PROJECT_ID}\ltx_sequence\rows"
)
DEFAULT_NEGATIVE = (
    "identity drift, different person, face morph, scene change, camera jump, "
    "lighting shift, robotic motion, stiff movement, jitter, temporal flicker, "
    "frame inconsistency, duplicate limbs, malformed anatomy, blurry, soft focus, "
    "low detail, low quality, compression artifacts, oversmoothed skin, plastic skin, "
    "cartoon, illustration, CGI, watermark, text, subtitles, overlay"
)


def http_json(method: str, path: str, payload: object | None = None) -> Any:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(COMFY_URL + path, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({exc.code}): {detail}") from exc


def load_inputs() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    sheet = json.loads(SHEET_PATH.read_text(encoding="utf-8"))
    source = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    asset_files = {item["assetId"]: item["filename"] for item in source["assets"]}
    return workflow, sheet["rows"], asset_files


def patched_workflow(
    source_workflow: dict[str, Any],
    row: dict[str, Any],
    image_filename: str,
) -> dict[str, Any]:
    workflow = deepcopy(source_workflow)
    workflow["269"]["inputs"]["image"] = image_filename
    workflow["320:319"]["inputs"]["value"] = row["prompt"]
    workflow["320:313"]["inputs"]["text"] = (
        row.get("negative_prompt") or DEFAULT_NEGATIVE
    )
    workflow["320:301"]["inputs"]["value"] = int(row["duration_sec"])
    workflow["320:300"]["inputs"]["value"] = 24
    workflow["320:312"]["inputs"]["value"] = 768
    workflow["320:299"]["inputs"]["value"] = 448
    seed = int.from_bytes(row["row_id"].encode("utf-8"), "little") % (2**63 - 1)
    workflow["320:276"]["inputs"]["noise_seed"] = seed
    workflow["320:277"]["inputs"]["noise_seed"] = (seed + 1) % (2**63 - 1)
    workflow["75"]["inputs"]["filename_prefix"] = (
        f"cineforge/{PROJECT_ID}/ltx_sequence/rows/"
        f"{int(row['order']):02d}_{row['output_name']}"
    )
    return workflow


def submit() -> None:
    source_workflow, rows, asset_files = load_inputs()
    client_id = f"sineforge-ltx-operator-{uuid4()}"
    submissions: list[dict[str, Any]] = []
    for row in rows:
        asset_id = row.get("input_asset_id")
        image_filename = asset_files.get(asset_id)
        if not image_filename:
            raise RuntimeError(
                f"Row {row['row_id']} has no source filename for asset {asset_id}."
            )
        result = http_json(
            "POST",
            "/prompt",
            {
                "client_id": client_id,
                "prompt": patched_workflow(source_workflow, row, image_filename),
            },
        )
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return a prompt id: {result}")
        submission = {
            "row_id": row["row_id"],
            "order": row["order"],
            "output_name": row["output_name"],
            "image_filename": image_filename,
            "prompt_id": prompt_id,
            "status": "queued",
        }
        submissions.append(submission)
        print(
            f"queued {int(row['order']):02d}/{len(rows)} "
            f"{row['row_id']} -> {prompt_id}",
            flush=True,
        )
    manifest = {
        "schema_version": "sineforge.ltx-operator-run/v1",
        "project_id": PROJECT_ID,
        "sequence_execution_run_id": "ed796b7d-cbb4-4f96-91fb-5d6d8f1bb92c",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "workflow_sha256": rows[0]["workflow_sha256"],
        "resolution": "768x448",
        "fps": 24,
        "rows": submissions,
    }
    RUN_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"manifest: {RUN_MANIFEST_PATH}", flush=True)


def status(*, wait: bool) -> int:
    manifest = json.loads(RUN_MANIFEST_PATH.read_text(encoding="utf-8"))
    while True:
        completed = 0
        failed = 0
        for row in manifest["rows"]:
            history = http_json("GET", f"/history/{row['prompt_id']}")
            record = history.get(row["prompt_id"])
            if not record:
                continue
            status_record = record.get("status", {})
            completed_ok = status_record.get("completed") is True
            messages = status_record.get("messages", [])
            execution_error = next(
                (
                    message
                    for message in messages
                    if isinstance(message, list)
                    and message
                    and message[0] == "execution_error"
                ),
                None,
            )
            if execution_error:
                row["status"] = "failed"
                row["error"] = execution_error[1]
                failed += 1
                continue
            if completed_ok:
                row["status"] = "completed"
                row["outputs"] = record.get("outputs", {})
                completed += 1
        manifest["checked_at"] = datetime.now(timezone.utc).isoformat()
        RUN_MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        queue = http_json("GET", "/queue")
        running = len(queue.get("queue_running", []))
        pending = len(queue.get("queue_pending", []))
        print(
            f"completed={completed}/{len(manifest['rows'])} failed={failed} "
            f"running={running} queued={pending}",
            flush=True,
        )
        if failed:
            return 1
        if completed == len(manifest["rows"]):
            return 0
        if not wait:
            return 2
        time.sleep(15)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("submit", "status", "wait"))
    args = parser.parse_args()
    if args.command == "submit":
        submit()
        return 0
    return status(wait=args.command == "wait")


if __name__ == "__main__":
    raise SystemExit(main())
