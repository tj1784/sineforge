# Operator Context for ChatGPT/Codex

## ComfyUI runtime policy

CineForge must never automatically start, restart, supervise, repair, or open
ComfyUI. Keep:

`CINEFORGE_COMFYUI_AUTOSTART=false`

The LTX installation at `C:\ComfyUI\LTX\ComfyUI` is preserved but manual-only.
Port `8888` is normally offline. The operator alone may deliberately start a
runtime for a specific generation session.

Never start or target BlokeyUI, `BLOKEYEYEYEYEY`, port `8188`, port `8889`, or
the legacy external ComfyAPI Runner. Never recreate `run_cineforge_ltx.bat`.
Repository workflow files are mirrors, backups, or versioned templates unless
the operator identifies one as the live source.
