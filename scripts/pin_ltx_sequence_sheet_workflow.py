"""Pin the admitted LTX workflow into a generated Sequence Sheet artifact."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHEET_PATH = (
    ROOT
    / "outputs"
    / "i2v_sheet_processed_20260729"
    / "sineforge_sequence_sheet.json"
)
WORKFLOW_VERSION = "1.0"
WORKFLOW_SHA256 = (
    "c928366ccf42a2d47a81a51c478079c385d1d6e72fe50ed8ff96d51c4dbb68bc"
)


def main() -> None:
    payload = json.loads(SHEET_PATH.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Sequence Sheet does not contain rows.")
    for row in rows:
        row["workflow_version"] = WORKFLOW_VERSION
        row["workflow_sha256"] = WORKFLOW_SHA256
    SHEET_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Pinned {len(rows)} rows to {WORKFLOW_VERSION} / {WORKFLOW_SHA256}.")


if __name__ == "__main__":
    main()
