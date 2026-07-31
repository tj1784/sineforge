# Agentless Workflow

Agentless Workflow is CineForge’s deterministic, non-cumulative scene-reset
lane. It is selected when the project is created and stored as immutable project
identity:

```text
cineforge_studio  → provider-assisted planning and the existing Studio lane
agentless         → local LM Studio agent planning and deterministic Python
                    scene-reset production
```

“Agentless” means **no hosted/API agents**. It does not mean that local models
are disabled. Every nonblank Agentless project uses one explicitly selected
local LM Studio planning agent:

- Qwen 3.6 40B by default.
- Sulphur 2 Base as the selectable alternative.

The selected local agent produces structured JSON planning artifacts. It does
not own rendering, workflow mutation, queue state, retries, media validation, or
assembly; deterministic Python services retain those production controls.

The canonical project intake artifact is retained as
`project-planning-prompt.json` and can be retrieved without converting it to
plain text:

```http
GET /projects/{project_id}/planning-prompt.json
Accept: application/json
```

The response is `application/json`, carries a `.json` attachment filename, and
includes `X-Content-SHA256` for the canonical response bytes. User-entered
prose is nested under `source.user_text`; the prompt envelope itself remains
versioned JSON.

The database default remains `cineforge_studio` only so legacy rows can be
migrated safely. New API creation requests and both creation interfaces require
an explicit selection.

## Production contract

An Agentless plan compiles each logical scene into one or two isolated segments:

```text
fresh FLUX.2 multi-reference anchor
    → anchor identity/composition QA
    → LTX-2.3 Ingredients + accepted-anchor first-frame I2V
    → video identity/motion QA
    → ProRes 422 HQ or FFV1 master
    → one H.264 or H.265 delivery encode
```

The compiler enforces:

- One through 50 logical scenes.
- Three through 20 seconds per logical scene.
- One segment for scenes up to 10 seconds.
- Two independently anchored segments for scenes longer than 10 seconds.
- 24 fps and the nearest valid LTX `8n+1` frame count.
- Exactly 241 frames for a requested 10-second segment; playback duration is
  `241 / 24`, or approximately 10.0417 seconds.
- Separate image and video seed channels.
- A fresh PNG anchor for every segment.
- Ingredients reference-sheet conditioning and first-frame I2V.
- `bypass_i2v=false`.
- No previous clip, previous final frame, or cross-segment stage dependency.
- At most three anchor attempts and three video attempts.
- `batch_size=1` and one active GPU generation job.
- Project settings remain pinned to `ltx_base@2`, 24 fps, local-only
  agent planning with deterministic production orchestration, hosted/API
  planning disabled, model downloads disabled, and rendering disabled until
  the execution boundary exists.
- A backend-owned outer queue; the plan never creates a 50-branch ComfyUI
  graph.

## API

Read the immutable lane policy and current blockers:

```http
GET /projects/{project_id}/agentless-workflow
```

Compile a read-only plan:

```http
POST /projects/{project_id}/agentless-workflow/dry-run
Content-Type: application/json
```

Example request:

```json
{
  "schema_version": "sineforge.agentless-scene-reset-request/v1",
  "project_id": "11111111-1111-4111-8111-111111111111",
  "workflow_templates": {
    "anchor": {
      "template_id": "flux2-multi-reference-anchor",
      "version": "1.0",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    "video": {
      "template_id": "ltx23-ingredients-i2v-scene-reset",
      "version": "1.0",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    }
  },
  "master_policy": {
    "intermediate_codec": "prores_422_hq",
    "delivery_codec": "h264",
    "delivery_encode_count": 1,
    "intermediate_reencoding_allowed": false,
    "anchor_format": "png"
  },
  "scenes": [
    {
      "scene_id": "S012",
      "duration_sec": 20,
      "visible_character_ids": ["SARAH", "MARK"],
      "character_reference_asset_ids": {
        "SARAH": ["sarah-front-v3", "sarah-seated-v3"],
        "MARK": ["mark-front-v2", "mark-seated-v2"]
      },
      "flux_reference_assets": {
        "set_studio_asset_ids": ["studio-main-v1"],
        "composition_asset_ids": ["podcast-twoshot-v1"],
        "pose_asset_ids": ["two-seated-facing-v1"],
        "prop_asset_ids": ["desk-microphones-v1"]
      },
      "ingredients_reference_asset_id": "sarah-mark-twoshot-v1",
      "character_description_block": "Preserve Sarah and Mark’s exact facial identity, age, hair, complexion, wardrobe, and accessories from the supplied canonical references.",
      "anchor_prompt": "Sarah and Mark in a premium broadcast podcast two-shot.",
      "video_prompt": "Sarah turns toward Mark and asks the question calmly while Mark listens.",
      "negative_prompt": "identity drift, merged faces, wardrobe change",
      "image_seed": 318700421,
      "video_seed": 791420508,
      "width": 768,
      "height": 448,
      "ingredients_lora_strength": 1.0,
      "distilled_lora_strength": 0.5,
      "bypass_i2v": false,
      "output_prefix": "earth-debate-001-S012",
      "audio_asset_id": "audio-S012-master",
      "anchor_max_attempts": 3,
      "video_max_attempts": 3
    }
  ]
}
```

`output_prefix` is deliberately a safe basename, not a filesystem path. The
eventual executor must derive project and scene directories itself. The
20-second example compiles to `S012-A` and `S012-B`, with independent anchors,
independent derived B seeds, and audio source offsets of zero and 10 seconds.

The request uses opaque asset identifiers. The planning-only endpoint validates
their shape and bounds but does not access media or assert ownership. A future
executor must resolve every asset against the route project and reject missing,
cross-project, archived, unapproved, or media-incompatible assets before any
submission.

The compiler prepends `character_description_block` unchanged to both the
shot-specific FLUX anchor prompt and LTX video prompt. This makes the canonical
identity description an enforced input rather than relying on every scene
author to copy it into two different prompts.

## Exact workflow admission

Both workflow references must resolve to one `WorkflowTemplate` row with the
same template name, version, and canonical SHA-256. The stored manifest must
declare:

```json
{
  "api_format": true,
  "runtime_qualified": true,
  "agentless_role": "flux_anchor",
  "nodes": {
    "positive_prompt": {
      "node_id": "74",
      "class_type": "CLIPTextEncode",
      "input": "text"
    }
  }
}
```

The video template uses `agentless_role: "ltx_ingredients_i2v"`.

Admission checks that the node exists, its `class_type` matches, and the named
input exists. The required FLUX mappings are:

```text
positive_prompt
image_seed
character_reference_assets
set_studio_reference_assets
composition_reference_assets
pose_reference_assets
prop_reference_assets
width
height
output_prefix
```

The required LTX mappings are:

```text
positive_prompt
negative_prompt
video_seed
ingredients_reference_image
scene_anchor_image
width
height
frame_count
fps
ingredients_lora_strength
distilled_lora_strength
bypass_i2v
output_prefix
audio_input
```

A role label by itself is not admission evidence.

## Execution boundary

This implementation intentionally stops at deterministic compilation and static
workflow admission. Every response reports:

```text
submission_enabled=false
ready_to_execute=false
submission_supported=false
```

It does not submit ComfyUI, write scene outputs, persist an execution ledger, or
run FFmpeg. Those steps remain blocked until the exact exported FLUX and
LTX-2.3 API workflows are supplied and a project-scoped asset resolver,
serialized worker, collector, QA engine, retry controller, and master writer are
implemented against their verified semantic mappings.

Agentless projects are also rejected from legacy paths that would violate this
boundary:

- Hosted/API planning providers and fallback to the deterministic mock agent.
- Any planning route that differs from the project-selected local Qwen or
  Sulphur agent.
- Generic Phase 5/6 FLUX generation.
- Generic Phase 7 WAN/16-fps queue submission.
- The older LTX Sequence Sheet, including `previous_last_frame` continuity.

The Studio keeps Story & Chapters planning available, but locks it to the
project-selected local LM Studio agent and structured JSON prompts. Hosted,
mixed, and mock fallback controls are unavailable. Generic execution surfaces
that could bypass the scene-reset contract remain hidden and are replaced by
the Agentless profile/readiness response. Manual storyboard,
character-reference, voice-metadata, workflow catalog, export, and policy views
remain available under their existing consent and approval gates.

The global API Caller and one-off operator scripts are intentionally outside
project scope and therefore cannot infer a project lane. They are not an
Agentless execution mechanism and must not be used to submit an Agentless plan.
The eventual executor must be project-scoped so the backend can enforce asset
ownership, exact workflow admission, queue serialization, and the persisted
lane before every submission.
