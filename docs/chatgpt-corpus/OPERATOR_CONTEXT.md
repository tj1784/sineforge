# Operator Context for ChatGPT/Codex

## Unified ComfyUI runtime policy

The operator explicitly merged Sineforge and the separate BlokeyUI tree into a
single runtime application. Sineforge is the frontend and FastAPI is the sole
lifecycle owner of BlokeyUI's ComfyUI 0.29.2 engine.

The trusted launcher sets:

```text
CINEFORGE_COMFYUI_AUTOSTART=true
CINEFORGE_COMFYUI_BACKEND_MANAGED=true   # child-process environment only
CINEFORGE_COMFYUI_BASE_URL=http://127.0.0.1:8190
```

The dependency runtime and curated node source currently come from the
preserved LTX installation, but the source bootstrap must resolve ComfyUI core
imports from `Sineforge\BlokeyUI\ComfyUI`.

Do not start, stop, or repurpose the independent service on port 8889. Do not
restore the external ComfyAPI Runner on port 8022. Do not flatten the separate
BlokeyUI and Sineforge Git histories.

Normal engine stop/restart is queue-safe. Keep the engine loopback-only,
Manager-disabled, offline during startup, and limited to the pinned node
allowlist. See `docs/UNIFIED_BLOKEYUI_ENGINE.md` for the authoritative contract.
