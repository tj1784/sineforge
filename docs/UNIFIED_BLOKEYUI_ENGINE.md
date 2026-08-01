# Unified BlokeyUI Engine

## Outcome

Sineforge and BlokeyUI run as one application from the operator's perspective:

- Sineforge is the only frontend.
- FastAPI is the only lifecycle owner.
- BlokeyUI ComfyUI 0.29.2 is the engine core.
- Native Sineforge routes validate and submit workflows directly to ComfyUI.
- The engine's web canvas is not part of the supported product flow.
- The old external ComfyAPI Runner is not started or required.

The repositories remain separate Git trees. “Single app” describes runtime,
process ownership, data flow, and UX—not a destructive Git-history merge.

## Runtime topology

```text
Browser
  -> Sineforge React :5174
      -> Sineforge FastAPI :8010
          -> owned BlokeyUI/ComfyUI subprocess :8190
              -> BlokeyUI/ComfyUI/models (default model inventory)
              -> Sineforge storage inputs/outputs/user/temp
```

FastAPI launches ComfyUI by argument array with no shell. The launcher sets
`CINEFORGE_COMFYUI_BACKEND_MANAGED=true` only in the backend child environment.
An ordinary test or manually launched Uvicorn process therefore cannot
implicitly claim the GPU engine.

The engine manager holds:

- an async lifecycle lock across complete restart operations;
- an OS-backed cross-process owner lock;
- a Windows kill-on-close Job Object for the process tree;
- bounded rotating stdout/stderr logs;
- restart operation records;
- automatic capped-backoff recovery after a confirmed child-process exit;
- the PID, exit code, timestamps, and last error.

The outer Sineforge supervisor separately watches FastAPI and Vite. Three
consecutive liveness failures, or a confirmed child exit, replace only that
owned service generation. Every replacement backend must again prove managed
BlokeyUI ownership and required-node readiness before it is recorded ready.
Windows Job Objects guarantee forced process-tree cleanup, so an orphaned
listener cannot satisfy readiness for a replacement generation.

## Compatibility decision

BlokeyUI includes Python 3.13.14 with 89 installed packages. A compatibility
audit against the installed production nodes had 20 top-level failures,
including LTXVideo, VideoHelperSuite, GGUF, NVIDIA, Impact Pack, ControlNet Aux,
MMAudio, PuLID, RES4LYF, and WAS.

The proven runtime is:

```text
C:\ComfyUI\LTX\ComfyUI\python_embeded\python.exe
Python 3.11.9
Torch 2.12.0 + CUDA 13.0
```

Using that dependency environment with BlokeyUI 0.29.2 source loaded the curated
non-Manager node set with zero top-level `IMPORT FAILED` entries. Directly
passing BlokeyUI `main.py` is unsafe because the runtime's `python311._pth`
contains `../ComfyUI`, which resolves to the older LTX core. The tracked
`scripts/run_blokeyui_engine.py` bootstrap inserts the BlokeyUI source root
before any ComfyUI import and then executes its `main.py`.

The final command uses explicit data directories, SQLite URL, model-path files,
custom-node disable/allowlist flags, loopback host and port, and no browser
auto-launch. Startup environment disables user-site leakage, pip indexes,
telemetry, and remote Hugging Face/Transformers access.

## Required-node identity gate

HTTP reachability alone is not readiness. Each probe requires:

1. `GET /api/system_stats` succeeds.
2. `GET /sineforge/workflow-transfer/status` identifies bridge version 2.
3. The bridge confirms these workflow-critical classes are loaded:

```text
SineForgeLTXKreaContinuationPlanner
LTXVSulphurAllInOne
Krea2EncodeRebalance
VHS_VideoCombine
easy forLoopStart
easy forLoopEnd
SaveText
ShowText|pysssss
```

The bridge answers the required-node query from ComfyUI's live
`NODE_CLASS_MAPPINGS`. This avoids serializing the approximately 8 MiB
`object_info` response on every status poll.

## Custom-node policy

All custom nodes are disabled first, then only a versioned allowlist is enabled.
ComfyUI Manager, the external duplicate SineForge bridge, loose Python files,
and unknown newly added folders are excluded. Two audited optional packs are
also excluded because they are unused by shipped workflows and emit known
broken optional-node imports:

- `ComfyLiterals`
- `ComfyUI-Addoor`

`comfyui_starnodes` remains pinned because it provides the required
`LTXVSulphurAllInOne` class used by the shipped LTX workflows. ComfyUI's
`--base-directory` points at `storage/runtime/comfyui/base`, so StarNodes'
wildcard bootstrap and other extension state are written there rather than
into the separate BlokeyUI source tree.

The repository bridge is mounted from `ComfyUI/sineforge_workflow_bridge`.
External nodes are mounted through a generated JSON/YAML-compatible path file
under `storage/runtime/comfyui`.

This workstation still references a live external node directory. For a
reproducible installer, copy a tested snapshot into an immutable engine bundle
and redirect each node pack's writable state to the Sineforge user directory.

## Core parity patches

Three proven local LTX fixes were forward-ported into the separate BlokeyUI
tree:

1. Hidden-console logging tolerates invalid Windows stream handles while
   retaining in-memory logs.
2. LTX guide attention entries may describe a tracked suffix of the keyframe
   mask; overflow still fails.
3. `SaveLatent` recognizes nested LTX2 video/audio latents and saves the video
   component rather than crashing on `.contiguous()`.

The third behavior is intentionally video-only and does not preserve the nested
audio latent in the legacy latent file format.

## Queue and lifecycle safety

Normal stop and restart query `/api/queue`. If a render is active or pending,
the API returns HTTP 409 and tells the operator to wait. `force=true` is an
explicit interruption path. Native Runner, Phase 6, Phase 7, and controlled
worker prompt submissions all share one process-wide admission gate with
stop, restart, and shutdown. Restart checks the queue while that gate is held,
so a new managed prompt cannot enter between the idle check and termination.
Malformed queue payloads fail closed. Lifecycle mutation routes require:

- the lifespan-owned manager instance;
- a loopback Host;
- an allowed Sineforge browser Origin when Origin is present;
- a non-cross-site fetch context.

A healthy responder at 8190 is not automatically trusted. If FastAPI does not
own its PID, managed status reports `conflict`, not `running`.

Automatic recovery never force-kills a live but unresponsive engine because
its queue cannot be proven idle. It only relaunches a process confirmed dead.
Manual Stop, Restart, and application shutdown clear the desired-running flag
and cancel any pending recovery delay before lifecycle mutation begins.

## Direct execution paths

The native API Runner and Phase 7 call ComfyUI directly through FastAPI:

```text
validate saved snapshot + SHA
  -> upload/copy managed inputs
  -> POST /api/prompt
  -> persist Comfy prompt ID
  -> poll history/queue
  -> preview managed outputs in Sineforge
```

Compatibility response aliases containing `runner_*` remain temporarily, but
the canonical contract is `engine="comfyui"`, `comfy_prompt_id`, and
`comfyui_url`.

## Verification evidence (2026-07-31)

The integrated manager was started on port 8190 with the existing independent
8889 process left untouched. Live result:

```json
{
  "status": "running",
  "ready": true,
  "checks": {
    "system_stats": true,
    "sineforge_bridge": true,
    "required_nodes": true
  },
  "missing_required_nodes": [],
  "queue": {"running": 0, "pending": 0}
}
```

The live engine reported Python 3.11.9 and ComfyUI 0.29.2. Managed shutdown
returned exit code 0, cleared the PID, released port 8190, and left the older
8889 process running.

A second live check used the final pinned allowlist and runtime base directory.
It queued `EmptyImage -> PreviewImage`, completed successfully, returned one
temporary preview, and then shut down with exit code 0. StarNodes installed 48
wildcard files under `storage/runtime/comfyui/base/wildcards`; the BlokeyUI
source-tree `wildcards` directory remained empty. The final launch segment had
no custom-node import failure or traceback.

An isolated FastAPI instance then exercised the complete Sineforge-native path:
`POST /native-api-runner/run` submitted the same no-model workflow, reported
`external_runner_used=false`, completed with one preview output, and released
both its temporary backend port and engine port. Its exact smoke-test database
row and temporary preview were removed afterward.

Regression results:

- Backend full-suite snapshot: 782 passed, 9 skipped.
- Supervisor and engine recovery focused suite: 41 tests passed, including
  confirmed-dead child recovery, bounded retry backoff, clean shutdown, and
  service replacement.
- Frontend: 17 test files and 81 tests passed, including transport recovery
  without replaying mutations.
- Frontend ESLint and the TypeScript/Vite production build passed.
- Live fault injection killed the owned FastAPI process and then the owned
  ComfyUI engine process independently. The supervisor restored FastAPI while
  leaving Vite running, and the backend restored ComfyUI without a supervisor
  restart. The separate ComfyUI listener on port 8889 remained untouched.

Before changing core/runtime/node versions, repeat:

1. Backend and frontend regression suites.
2. Engine identity/required-node live startup.
3. Empty-queue and busy-queue lifecycle tests.
4. No-model prompt execution.
5. An LTX workflow covering guide-token suffix handling.
6. Nested LTX2 latent saving.
