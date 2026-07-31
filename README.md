# CineForge

CineForge is a local AI video-generation orchestration platform. It is designed to be the deterministic execution layer around an isolated ComfyUI runtime, durable backend-owned queues, manifest-validated workflow templates, reproducible provenance, GPU telemetry, and FFmpeg validation/assembly primitives.

## Current Status

This repository includes **Storyboard Phase A**, a planning-only foundation that ends with an approved, editable production plan.

What works now:

- FastAPI backend scaffold.
- Configuration loading from `.env`.
- Health endpoints for app, ComfyUI reachability, GPU telemetry, and FFmpeg availability.
- SQLAlchemy schema foundation aligned to the research packet.
- Queue state machine primitives.
- Workflow manifest validation and immutable snapshot writing.
- Path safety helpers.
- Offline-safe ComfyUI client wrapper.
- `nvidia-smi` parser for benchmark telemetry.
- FFmpeg/ffprobe validation primitives.
- Non-executing AI/autonomy schemas and validators.
- Pytest coverage for the Sprint 1A primitives.
- Persisted `Project -> Story -> Chapter -> Scene -> Shot` planning hierarchy.
- Storyboard readiness checks, duration rollups, immutable approval versions, JSON and CSV planning exports.
- Storyboard Studio frontend views for planning, assets, routing, workflows, exports, and settings.

What does not work yet:

- No real video generation.
- No model downloads.
- No ComfyUI installation or mutation.
- No autonomous production execution.
- No GPU queue worker yet.
- No image/video generation is triggered by Storyboard Phase A approval.
- Project, campaign, and job APIs are validation stubs, not fully DB-backed.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
Copy-Item .env.example .env
.\.venv\Scripts\python scripts\create_db.py
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
```

### One-command supervised startup

Start the complete local stack from the repository root:

```powershell
.\start-cineforge.cmd
```

The trusted launcher starts or reuses the local Sulphur model API, the FastAPI
backend, and the Vite frontend in that order. It never starts ComfyUI. It
opens Sineforge in the default browser after all readiness checks pass, writes
logs and owned process metadata under `storage/runtime/supervisor/`, and stops
only persistent child processes it started when you press Ctrl+C. Run
`.\start-cineforge.cmd --check` for a read-only configuration and readiness
check, or add `--no-browser` to suppress the browser tab. The default startup
destination is the Sulphur-backed Projects home at `/projects`.

ComfyUI auto-start is disabled through `CINEFORGE_COMFYUI_AUTOSTART=false`.
Administrator overrides are supported through `CINEFORGE_COMFYUI_WORKING_DIR`,
`CINEFORGE_COMFYUI_LAUNCHER`, `CINEFORGE_COMFY_API_RUNNER_WORKING_DIR`,
`CINEFORGE_COMFY_API_RUNNER_LAUNCHER`, `CINEFORGE_LMS_EXECUTABLE`,
`CINEFORGE_PYTHON_EXECUTABLE`, and `CINEFORGE_NPM_EXECUTABLE`. These values are
local configuration only; no API request, story text, AI proposal, or prompt can
supply an executable path or shell command.
Readiness URLs are restricted to loopback HTTP origins, shell metacharacters are rejected
from command paths, ports and timeouts are range-checked, and a singleton lock prevents
competing supervisors. Logs rotate at 10 MiB per stream.

### Manual ComfyUI contract

Starting CineForge must not start ComfyUI. ComfyUI remains an isolated,
operator-started process; CineForge must not import it in-process, launch it
implicitly, or treat a listening port alone as generation readiness.

The runtime integration must:

1. Keep `CINEFORGE_COMFYUI_AUTOSTART=false` on the primary workstation.
2. Never launch `C:\ComfyUI\LTX\ComfyUI`, BlokeyUI, or any other ComfyUI installation as part of CineForge startup.
3. Treat `http://127.0.0.1:8888` as normally offline. The operator alone decides when to start a ComfyUI runtime.
4. When the operator has deliberately started a runtime, require both the ComfyUI root endpoint and `/object_info` before reporting it ready.
5. Fail honestly when ComfyUI is offline: keep planning available, block image/video generation, and show the runtime-readiness blocker.
6. Never install, update, download models, mutate custom nodes, or weaken host security as part of startup.

Manual runtime availability does not by itself enable generation. Image
generation additionally requires an enabled backend worker/submission path, a
validated workflow manifest compatible with live `/object_info`, registered
model evidence, output collection, and provenance persistence. Video generation
remains a separately gated phase.

### Local planning models and ComfyAPI Runner

The primary workstation launcher recognizes the local
`sulphur_prompt_enhancer_model-q8_0.gguf` and Qwen 3.6 40B Q4_K_S GGUF, starts
LM Studio's loopback API on `127.0.0.1:1234`, and loads the saved SineForge
planning-model selection with full GPU offload. The Studio top bar and Local AI
panel expose the same model toggle. A switch unloads only the prior SineForge
planning model from memory before loading its replacement; it never downloads,
moves, or deletes either GGUF. The choice is stored under the ignored local
`storage/runtime/` directory and is restored on the next supervised startup.

The selected local model has the highest automatic planning priority, so script
structure, story planning, shot planning, and prompt-package tasks use it unless
a story has an explicit manual provider assignment. Phase 1 also requests a
structured local script enhancement and retains the deterministic source-faithful
package if the model response does not pass the existing QA contract.

The Projects homepage composer sends one complete creative message to the local
Sulphur model. Sulphur extracts a validated title, runtime, audience, genre,
tone, point of view, visual style, language, format, and production constraints;
the original message is also preserved verbatim as the story source. Only after
that intake passes validation does Sineforge call its existing atomic workspace
creator and run Phase 1. The Phase 1 package records
`ceil(target_duration_sec / 8)` planned scenes, equalizes their durations to the
requested total, and requires every generated clip to remain between 6 and 10
seconds.

ComfyAPI Runner is supervised at `http://127.0.0.1:8022`. Sineforge exposes its
health in `/health/comfy-api-runner` and `/runtime/status`, provides quick-open
buttons on the Projects home and Runtime page, and includes a bounded backend
client for workflow analysis, controlled submission, job status, and an
explicit user-triggered ComfyUI restart. Restart progress is proxied through
`/runtime/comfyui/restart`; the runner does not bypass Sineforge's workflow
validation or public-submission gates.

Run tests:

```powershell
.\.venv\Scripts\python -m pytest
```

## Key Architecture Docs

- `Architecture/ARCHITECTURE_BLUEPRINT.md`
- `MVP/MVP_ARCHITECTURE.md`
- `API/BACKEND_API_FLOW.md`
- `Runtime/RUNTIME_ISOLATION_AND_QUEUEING.md`
- `Workflows/WORKFLOW_JSON_MUTATION_STRATEGY.md`
- `ComfyUI/HEADLESS_COMFYUI_API.md`
- `Database/POSTGRES_SCHEMA.sql`
- `Benchmarks/BENCHMARK_PROTOCOL.md`
- `FFmpeg/FFMPEG_STRATEGY_COMMAND_LIBRARY.md`
- `Orchestration/OPTIONAL_AI_ORCHESTRATION_LAYER.md`
- `Orchestration/AUTONOMOUS_PRODUCTION_ARCHITECTURE.md`
- `docs/SPRINT_1A_STATUS.md`

## Safety Boundary

CineForge is intended to remain the deterministic execution engine. AI modules are advisory only in Sprint 1A and cannot directly mutate workflow JSON, queue state, database records, model registries, ComfyUI submissions, asset paths, or FFmpeg commands.

See `docs/STORYBOARD_PHASE_A_SPEC.md` for the planning boundary and `docs/PRODUCT_VISION.md` for current product direction. Older sprint documents are historical implementation records, not product direction.

