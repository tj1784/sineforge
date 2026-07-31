"""Admit the exact runtime-qualified Sulphur 2 LTX API workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.base import WorkflowTemplate  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402


WORKFLOW_PATH = (
    ROOT
    / "Workflows"
    / "Sulphur2"
    / "Sulphur2_LTX23_I2V_NativeAudio_API.json"
)
QUALIFICATION_PATH = (
    ROOT
    / "Workflows"
    / "Sulphur2"
    / "Sulphur2_LTX23_I2V_NativeAudio_QUALIFICATION.json"
)
NAME = "ltx-i2v"
VERSION = "1.0"


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
    sha256 = canonical_sha256(workflow)
    expected = qualification["workflow"]["canonical_sha256"]
    if sha256 != expected:
        raise RuntimeError(
            f"Workflow content SHA-256 {sha256} does not match qualification {expected}."
        )

    manifest = {
        "schema_version": "sineforge.workflow-admission/v1",
        "api_format": True,
        "runtime_qualified": True,
        "production_profile_ref": "ltx_base@2",
        "native_audio": True,
        "qualification_path": str(QUALIFICATION_PATH.relative_to(ROOT)),
        "qualification_runs": qualification["qualification_runs"],
    }
    with SessionLocal() as db:
        records = list(
            db.scalars(
                select(WorkflowTemplate).where(
                    WorkflowTemplate.name == NAME,
                    WorkflowTemplate.version == VERSION,
                )
            )
        )
        if len(records) > 1:
            raise RuntimeError(f"Multiple {NAME}@{VERSION} records already exist.")
        record = records[0] if records else WorkflowTemplate(name=NAME, version=VERSION)
        record.workflow_api_json = workflow
        record.manifest_json = manifest
        record.sha256 = sha256
        record.comfyui_commit = qualification["runtime"]["comfyui_commit"]
        record.custom_node_snapshot = {
            "qualification": "local",
            "workflow_node_count": len(workflow),
        }
        db.add(record)
        db.commit()
        db.refresh(record)
        print(
            json.dumps(
                {
                    "id": str(record.id),
                    "name": record.name,
                    "version": record.version,
                    "sha256": record.sha256,
                    "runtime_qualified": record.manifest_json["runtime_qualified"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
