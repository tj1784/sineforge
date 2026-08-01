# CineForge / Sineforge

CineForge is a local AI-video production application with one user-facing
Sineforge interface and one privately owned ComfyUI engine. The engine source is
the separate `BlokeyUI` tree; Sineforge owns its lifecycle, validation, queue,
inputs, outputs, and operator controls.

## Unified application status

The active runtime is now a single supervised application:

```text
Sineforge React UI (:5174)
        |
        v
Sineforge FastAPI (:8010)
        |
        +-- native workflow validation/submission/output tracking
        |
        +-- owned BlokeyUI ComfyUI 0.29.2 subprocess (:8190)
```

What works:

- The Projects and Studio UI are the only supported frontend.
- FastAPI starts, probes, restarts, stops, and reaps the BlokeyUI engine.
- The engine is bound to `127.0.0.1:8190`; the UI does not send the operator to
  the ComfyUI canvas.
- The native API Runner loads, edits, validates, saves, queues, monitors,
  interrupts, and previews API-format ComfyUI workflows inside Sineforge.
- Phase 7 submits image-to-video prompts directly to ComfyUI; no service on
  port 8022 is involved.
- Engine readiness proves the ComfyUI system endpoint, the Sineforge bridge
  identity, and the required LTX/Krea/VHS/easy-use text nodes.
- Normal stop and restart operations refuse to interrupt active or pending
  renders. Explicit force is a separate control.
- Engine data is isolated under `storage/inputs`, `storage/outputs`, and
  `storage/runtime/comfyui`.
- The engine process tree is attached to a kill-on-close Windows Job Object and
  a cross-process owner lock.
- Existing project planning, storyboard, workflow-manifest, local-model,
  provenance, GPU telemetry, and FFmpeg features remain available.

Current workstation dependency boundary:

- Core source: `BlokeyUI/ComfyUI` (ComfyUI 0.29.2).
- Dependency runtime: `C:\ComfyUI\LTX\ComfyUI\python_embeded\python.exe`
  (Python 3.11.9, Torch/CUDA stack proven with the installed LTX nodes).
- Curated custom-node source:
  `C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes`.
- Integrated Sineforge model library:
  `BlokeyUI/ComfyUI/models`. The managed engine loads this checkout-local
  inventory as its default model root; the older shared model library is not
  part of the core managed-engine registry.

BlokeyUI's bundled Python 3.13 environment cannot load a material part of the
current LTX node stack. The launcher therefore uses the proven Python 3.11
dependency environment while the source bootstrap guarantees that all ComfyUI
core imports resolve from BlokeyUI 0.29.2. This is one engine process, not two
ComfyUI services. A future distributable should copy/freeze that dependency
runtime beside BlokeyUI instead of referencing the existing LTX installation.

The BlokeyUI repository remains a separate nested Git tree. Runtime integration
does not combine or rewrite the two repositories' histories.

## Start the complete app

From the Sineforge repository root:

```powershell
.\start-cineforge.cmd
```

The trusted launcher:

1. Starts or verifies the local LM Studio/Sulphur planning service.
2. Starts FastAPI; FastAPI is the sole owner of the BlokeyUI engine child.
3. Waits for engine identity and required-node readiness.
4. Starts or reuses the Vite frontend.
5. Opens `/projects` after the unified application is ready.
6. Continuously probes FastAPI and Vite, replacing an exited or repeatedly
   unresponsive owned process with capped backoff while the other service stays up.
7. Lets FastAPI automatically recover a confirmed-dead BlokeyUI child; explicit
   Stop and shutdown cancel recovery so the engine cannot resurrect itself.
8. Stops only the process trees it owns on Ctrl+C.

Useful options:

```powershell
.\start-cineforge.cmd --check
.\start-cineforge.cmd --no-browser
```

`--check` validates the Sineforge services plus the configured BlokeyUI source,
Python compatibility runtime, bootstrap, path configuration, and curated
custom-node root. Logs are written under:

```text
storage/runtime/supervisor/logs/
storage/runtime/comfyui/logs/
```

Manual `uvicorn` startup is intentionally diagnostic-only unless the launcher
sets the process-scoped `CINEFORGE_COMFYUI_BACKEND_MANAGED=true` flag. This
prevents tests or an incidental backend process from claiming the GPU engine.
Keep the launcher running for the session: it is the watchdog and records live
PIDs, restart counts, liveness failures, and backoff state in
`storage/runtime/supervisor/cineforge-services.json`.

## Engine configuration

The relevant local settings are:

```text
CINEFORGE_COMFYUI_AUTOSTART=true
CINEFORGE_COMFYUI_BASE_URL=http://127.0.0.1:8190
CINEFORGE_COMFYUI_WORKING_DIR=./BlokeyUI
CINEFORGE_COMFYUI_PYTHON_EXECUTABLE=C:\ComfyUI\LTX\ComfyUI\python_embeded\python.exe
CINEFORGE_COMFYUI_MAIN_PATH=./BlokeyUI/ComfyUI/main.py
CINEFORGE_COMFYUI_BOOTSTRAP_PATH=./scripts/run_blokeyui_engine.py
CINEFORGE_COMFYUI_CUSTOM_NODES_DIR=C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes
CINEFORGE_COMFYUI_SINEFORGE_PATHS_CONFIG=./ComfyUI/sineforge_engine_paths.yaml
```

Executable and path settings are local administrator configuration. API input,
project text, AI output, and workflow JSON cannot supply a command or executable
path. The engine origin must be an explicit non-privileged loopback HTTP port.
Lifecycle POSTs reject cross-site browser requests.

The old external ComfyAPI Runner on `127.0.0.1:8022` is not required or started.
An older independently running ComfyUI on port 8889 is outside this app and is
neither stopped nor reused.

## Workflow boundary

Sineforge is the frontend for curated production workflows and API-format JSON.
It does not expose arbitrary visual graph authoring as part of the unified UI.
Repository workflows are validated against their saved snapshot and the live
engine before queueing. The submitted SHA-256 is carried through the native
runner contract. UI-graph JSON and executable API JSON remain distinct formats.

The engine starts offline with Manager excluded and a versioned custom-node
allowlist. It never performs package or model installation during startup.
Known optional packs that mutate the source tree or expose broken optional
nodes are not loaded unless they are deliberately repaired and admitted.

## Development setup and verification

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
Copy-Item .env.example .env
.\.venv\Scripts\python scripts\create_db.py
.\.venv\Scripts\python -m pytest

Set-Location frontend
npm install
npm test -- --run
npm run build
```

Detailed runtime and compatibility evidence is in
`docs/UNIFIED_BLOKEYUI_ENGINE.md`.

## Key architecture documents

- `docs/UNIFIED_BLOKEYUI_ENGINE.md`
- `Architecture/ARCHITECTURE_BLUEPRINT.md`
- `MVP/MVP_ARCHITECTURE.md`
- `API/BACKEND_API_FLOW.md`
- `Runtime/RUNTIME_ISOLATION_AND_QUEUEING.md`
- `Workflows/WORKFLOW_JSON_MUTATION_STRATEGY.md`
- `ComfyUI/HEADLESS_COMFYUI_API.md`
- `Database/POSTGRES_SCHEMA.sql`
- `FFmpeg/FFMPEG_STRATEGY_COMMAND_LIBRARY.md`

## Safety boundary

Sineforge remains the deterministic control plane. AI-generated content cannot
select executables, bypass workflow validation, mutate the engine installation,
or directly invoke lifecycle commands. Public prompt submission remains
disabled. Destructive engine lifecycle actions are explicit, loopback-only,
queue-aware, and process-owner checked.
