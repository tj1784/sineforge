"""Run BlokeyUI's ComfyUI source with an explicitly selected Python runtime.

The proven LTX Python environment includes ``../ComfyUI`` in python311._pth.
Without this bootstrap, invoking BlokeyUI's main.py from that interpreter can
silently import the older LTX ComfyUI source.  Put the requested source tree at
the front of sys.path before importing any ComfyUI module.
"""

from __future__ import annotations

import os
import runpy
import sys
import time
from pathlib import Path


def _wait_for_windows_job_assignment() -> None:
    """Keep the child inert until its parent attaches the process-tree Job."""

    marker_value = os.environ.get("CINEFORGE_ENGINE_JOB_HANDSHAKE")
    if os.name != "nt" or not marker_value:
        return
    marker = Path(marker_value)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            if marker.read_text(encoding="ascii").strip() == str(os.getpid()):
                marker.unlink(missing_ok=True)
                return
        except (FileNotFoundError, OSError, UnicodeError):
            pass
        time.sleep(0.025)
    raise SystemExit("Sineforge did not confirm ComfyUI Job Object ownership.")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: run_blokeyui_engine.py PATH_TO_MAIN [COMFYUI_ARGS...]")

    comfy_main = Path(sys.argv[1]).expanduser().resolve()
    if not comfy_main.is_file() or comfy_main.name != "main.py":
        raise SystemExit(f"BlokeyUI ComfyUI main.py was not found: {comfy_main}")

    _wait_for_windows_job_assignment()

    source_root = str(comfy_main.parent)
    sys.path[:] = [
        entry
        for entry in sys.path
        if not entry or str(Path(entry).resolve()).casefold() != source_root.casefold()
    ]
    sys.path.insert(0, source_root)
    sys.argv = [str(comfy_main), *sys.argv[2:]]
    runpy.run_path(str(comfy_main), run_name="__main__")


if __name__ == "__main__":
    main()
