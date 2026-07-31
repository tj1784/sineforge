# Operator Context for ChatGPT/Codex

## Sole ComfyUI runtime

Use exactly one ComfyUI installation for all CineForge work:

`C:\ComfyUI\LTX\ComfyUI`

The executable runtime contains the live ComfyUI source at:

`C:\ComfyUI\LTX\ComfyUI\ComfyUI`

The active operator workflow folder is:

`C:\ComfyUI\LTX\ComfyUI\ComfyUI\user\default\workflows`

The sole endpoint is `http://127.0.0.1:8888`. CineForge's native API Runner
submits directly to it. Never start or target BlokeyUI, port `8188`, port
`8889`, or the legacy external ComfyAPI Runner unless the operator explicitly
changes this invariant. Repository workflow files are mirrors, backups, or
versioned templates unless the operator identifies one as the live source.
