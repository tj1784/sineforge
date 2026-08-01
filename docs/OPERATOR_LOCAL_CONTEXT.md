# Operator Local Context

This file records workstation-specific runtime paths for the unified local app.

## Owned engine policy

Sineforge is the only supported frontend and FastAPI is the sole process owner
of the integrated ComfyUI engine. `start-cineforge.cmd` sets the process-scoped
ownership flag and starts the engine automatically on:

```text
http://127.0.0.1:8190
```

The engine uses:

```text
BlokeyUI core:       C:\Users\Blokey\Documents\Sineforge\BlokeyUI\ComfyUI
Python/dependencies: C:\ComfyUI\LTX\ComfyUI\python_embeded\python.exe
Custom nodes:        C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes
Shared models:       C:\ComfyUI\ComfyUI_Shared_Folders
Input:               C:\Users\Blokey\Documents\Sineforge\storage\inputs
Output:              C:\Users\Blokey\Documents\Sineforge\storage\outputs
User/database/temp:  C:\Users\Blokey\Documents\Sineforge\storage\runtime\comfyui
```

The Python 3.11 runtime supplies dependencies only. The source bootstrap puts
BlokeyUI first on `sys.path`, preventing the runtime's older ComfyUI source from
being imported.

BlokeyUI and Sineforge remain separate Git trees. Do not flatten their histories
or treat one repository's status as the other's.

## Preserved external processes

The older LTX ComfyUI service on port 8889 is not part of the unified app.
Sineforge must not stop, restart, or reuse it. The legacy external ComfyAPI
Runner on port 8022 is also outside the active architecture.

## Reproducibility constraints

- Keep ComfyUI Manager excluded.
- Keep Hugging Face, Transformers, and pip offline during engine startup.
- Do not add arbitrary folders to the custom-node allowlist.
- Normal restart/stop must refuse while the queue is busy.
- Keep data directories under Sineforge `storage`.
- Do not expose 8190 beyond loopback.
- Before updating the Python runtime, nodes, or core, rerun both a no-model
  smoke workflow and an LTX workflow exercising guide tokens and nested latents.

The current external dependency paths are a workstation bridge. A packaged
release should freeze/copy the proven Python 3.11 runtime and curated node set
beside the BlokeyUI engine source.
