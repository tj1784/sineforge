# Operator Local Context

This file records workstation-specific paths and conventions that are required
for safe local operation.

## ComfyUI runtime policy

ComfyUI is manual-only on this workstation. CineForge must never start,
restart, supervise, or automatically open any ComfyUI installation.

`CINEFORGE_COMFYUI_AUTOSTART=false` is a permanent fail-closed invariant.

The preserved LTX installation is:

`C:\ComfyUI\LTX\ComfyUI`

It is not part of CineForge startup. Port `8888` is normally offline. Only the
operator may deliberately start a runtime and identify its endpoint for a
specific generation session.

Never start, configure, repair, or target BlokeyUI, `BLOKEYEYEYEYEY`, port
`8188`, port `8889`, or the legacy external ComfyAPI Runner. Do not recreate
`run_cineforge_ltx.bat`; its disabled copy is retained only as evidence.

Repository workflow files may be mirrors, backups, or versioned templates; do
not treat them as the live ComfyUI canvas unless the operator asks for that file.
