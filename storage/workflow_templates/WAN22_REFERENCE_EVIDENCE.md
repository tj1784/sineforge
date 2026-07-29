# WAN 2.2 Reference Evidence

These files are disabled workflow-admission evidence. They are not registered
ComfyAPI Runner payloads and must not be submitted to ComfyUI.

## Provenance boundary

- The two `workflow_ui_reference.json` files are exact byte copies of official
  Comfy-Org UI workflow templates recovered in
  `SineForge_Article_Workflow_Recovery_2026-07-28.zip`.
- Their archive bytes also match the official Comfy-Org files at commit
  `8e53edd8a810694c35c92accda40c4dccfb965ae`.
- They are **official references**, not workflows recovered from the article
  author and not proof of the author's original generation graph.
- `reconstruction_manifest.json` is recovery evidence. It explicitly separates
  recovered Flux metadata, official WAN references, article-derived process
  claims, and forensic inferences.

The files deliberately use `workflow_ui_reference.json`, not
`workflow_api.json`. No `workflow_manifest.json` is present because the current
template service validates executable API-format graphs. Renaming these UI
graphs would falsely imply runtime admission.

## Included

- WAN 2.2 14B image-to-video official reference.
- WAN 2.2 14B first/last-frame official reference.
- Article reconstruction/provenance manifest.

## Deliberately excluded

`official_video_wan2_2_5B_ti2v.json` remains in the external recovery archive.
It is a different 5B TI2V model family and is not needed to establish the
requested 14B final-quality I2V and continuity path. Its archived SHA-256 is
`50390798a133757075d750ab78b26274e3bf3e4a09f46aaa2f08d9559e62750b`.

## Required before execution

An operator must load the reviewed reference in the exact active ComfyUI
installation, validate nodes and models, export a separate API-format graph,
create semantic bindings, record hashes and licenses, and pass runtime,
resource, quality, and boundary tests. None of those qualifications are claimed
by this evidence package.
