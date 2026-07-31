# Operator Local Context

This file records workstation-specific paths and conventions that are required
for safe local operation.

## Sole ComfyUI runtime

The only approved ComfyUI installation for CineForge on this workstation is:

`C:\ComfyUI\LTX\ComfyUI`

Its ComfyUI source and live workflow folder are:

`C:\ComfyUI\LTX\ComfyUI\ComfyUI`

`C:\ComfyUI\LTX\ComfyUI\ComfyUI\user\default\workflows`

It listens only on `http://127.0.0.1:8888`. CineForge submits API workflows
directly to this runtime. Do not start, configure, repair, or target BlokeyUI,
port `8188`, port `8889`, or the legacy external ComfyAPI Runner unless the
operator explicitly replaces this invariant.

Repository workflow files may be mirrors, backups, or versioned templates; do
not treat them as the live ComfyUI canvas unless the operator asks for that file.
