# SineForge LTX-2.3 Workflows

This package contains repository-managed LTX-2.3 workflows for the main LTX
ComfyUI installation. The general continuation workflow is genre-neutral. The
dynamic podcast workflow remains available as a separate specialized lane.

## WhatDreamsCost LTX Director 2 lane

`WhatDreamsCost-Director-2/LTX_Director_2_Distilled.workflow.json` provides a
shot-by-shot timeline for image, text, video, and audio segments, prompt relay,
keyframe guides, native audio, and long sequence construction. The package
contains the source provenance, required nodes and models, normalized bundled
model paths, API Runner graph, and live-validation evidence. See that folder's
`README.md` for first-run guidance and the members-only Hotfix disclosure.

## Licon MSR V2 multi-scene lane

`Licon-MSR-V2/LTX-2.3_MSR_Single_Image_to_Multiple_Scenes_V2.workflow.json`
uses LiconStudio's Multiple Subject Reference V2 LoRA to preserve referenced
characters, objects, clothing, and environments across an ordered sequence of
pipe-delimited scene prompts. Its full-precision LTX checkpoint, Gemma encoder,
MSR V2 LoRA, demonstration references, required custom nodes, API Runner graph,
and dependency manifest are kept together under `Licon-MSR-V2/`. See that
folder's `README.md` for model paths and first-run instructions.

## General Krea 2 → LTX-2.3 continuation

`SineForge_LTX23_Krea2_Lossless_Continuation_Loop.workflow.json` accepts any
starting image and optional Ingredients/reference sheet. Its visible controls
are:

- `loop_count`: 1+ runs exactly that many cycles; 0 keeps running until
  ComfyUI **Interrupt** (implemented as the Easy-Use maximum of 100000);
- `scene_or_subject`: any person, creature, object, product, environment,
  graphic, or story context;
- `next_event`: the next visual beat;
- `audio_mode`: automatic from scene, no dialogue, dialogue JSON, or advanced
  JSON only; and
- `dialogue_json`: an optional ordered array of exact speaker turns.

The planner dropdown discovers every executable GGUF package physically under
`C:\Users\Blokey\.lmstudio\models`. Qwen 3.6 40B is the default only. Packages
with vision support receive the current frame and reference sheet; text-only
packages remain usable and receive the same JSON scene request without image
attachments. Hosted/API models, embeddings, `mmproj`-only entries, and paths
outside that root are excluded.

Example exact dialogue:

```json
[
  {
    "speaker": "Character A",
    "position": "camera-left",
    "line": "Did you hear the update?"
  },
  {
    "speaker": "Character B",
    "position": "camera-right",
    "line": "Yes, and I want to check the details."
  }
]
```

The workflow does not assume a podcast or dialogue. Leave `dialogue_json` as
`[]` for cats, objects, products, environments, or any scene that does not need
exact speech.

## Dynamic podcast lane

The specialized podcast workflow performs one local staged run:

```text
two-person source image
    → selected local GGUF strict-JSON variation
    → confirmed complete LM Studio unload
    → two-pass LTX-2.3 image-to-video with native audio
    → matching MP4 and JSON prompt artifacts
```

No hosted/API agent is used. LM Studio is contacted only on
`127.0.0.1:1234`. Its planner dropdown discovers executable GGUF packages
under `C:\Users\Blokey\.lmstudio\models`. Qwen 3.6 40B is the default only.

## Files

- `SineForge_LTX23_Dynamic_Podcast_Qwen40B.workflow.json` is the
  editor-format workflow loaded by **Load in ComfyUI**.
- `SineForge_LTX23_Dynamic_Podcast_Qwen40B.api.json` is the executable
  API-format graph used by SineForge's native API Runner.
- `SineForge_LTX23_Dynamic_Podcast.prompt.json` is the only prompt-contract
  source of truth. It contains the system prompt object, default request
  object, category hints, strict response schema, and fixed negative prompt.
- `SineForge_LTX23_Podcast_Geopolitics_To_Everyday.prompt.json` is a
  ready-to-paste request preset for a fictional-opinion Iran/Russia tension
  discussion followed by a newly selected unrelated everyday topic.
- `SineForge_LTX23_Dynamic_Podcast.manifest.json` maps semantic fields to
  exact node classes, inputs, and outputs.

## What changes on every run

With `variation_mode` set to `new variation every run`, the planner creates:

- a fresh cryptographic variation seed;
- a primary topic category;
- a different pivot category;
- new short dialogue for MAN_A, MAN_B, and MAN_A's pivot;
- image-aware actions and camera direction;
- a complete LTX positive prompt;
- a hardened negative prompt;
- a derived LTX render seed;
- a shared output prefix; and
- a complete retained prompt `.json` record containing the canonical request,
  approved source notes, recent topics, source-image tensor hash, seeds, prompts,
  hashes, and complete LM Studio unload confirmation.

This changes both the semantics and the LTX noise. Semantic uniqueness is
strongly encouraged but cannot be proved from a seed alone. Paste recent topic
names into `recent_topics_json` when duplicate avoidance matters.

## First run

1. Run `scripts/Install-SineForgeWorkflowBridge.ps1` if the bridge is not
   already installed, then restart the main LTX ComfyUI once.
2. Start LM Studio's local server on `http://127.0.0.1:1234`.
3. Confirm the preferred default local planner model is installed:

   ```text
   qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-neo-code-di-imatrix-max
   ```

   The dropdown is populated from executable `.gguf` packages physically
   under:

   ```text
   C:\Users\Blokey\.lmstudio\models
   ├── DavidAU\Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-GGUF
   │   ├── Qwen3.6-40B-Deck-Opus-NEO-CODE-HERE-2T-OT-Q4_K_S.gguf
   │   └── mmproj-F32.gguf
   └── ... other local GGUF packages
   ```

   Qwen 3.6 40B appears first and is selected by default, but it is not locked.
   Each package containing a non-`mmproj` GGUF becomes an option. The node
   excludes embeddings, `mmproj`-only entries, aliases, instance IDs, paths
   outside the root, and hosted/API models. A text-only model stays selectable;
   it receives JSON without the source image, and that omission is saved in the
   prompt record.

4. Keep the preferred ComfyUI model root at:

   ```text
   C:\ComfyUI\ComfyUI_Shared_Folders\models
   ```

   This workflow currently resolves these verified shared files:

   ```text
   checkpoints\sulphur2Base_distilled.safetensors
   text_encoders\gemma_3_12B_it_fp8_e4m3fn.safetensors
   text_encoders\ltx-2.3_text_projection_bf16.safetensors
   vae\LTX23_video_vae_bf16.safetensors
   vae\LTX23_audio_vae_bf16.safetensors
   latent_upscale_models\ltx-2.3-spatial-upscaler-x2-1.1.safetensors
   ```

   The workflow stores registry-facing filenames, so ComfyUI's configured
   shared model path—not an absolute path inside the graph—performs resolution.

5. In SineForge's API Runner, open the read-only workflow and choose
   **Load in ComfyUI**, or upload the API JSON directly to the Runner.
6. Load a source image that clearly shows both podcast participants.
7. In `topic_request_json`, confirm:

   ```json
   {
     "speaker_assignment": {
       "MAN_A": "camera-left",
       "MAN_B": "camera-right"
     }
   }
   ```

   Swap those positions when the source image requires it. Do not assign
   identities from demographic appearance.

8. Validate without queueing. Resolve every missing node or model choice.
9. Queue one job only.

## VRAM handoff

The workstation has a 24GB GPU. A large local planner package and the LTX-2.3
model cannot safely remain in VRAM together.

SineForge therefore persists Qwen 3.6 40B as the default planning model while
allowing any discovered local GGUF to be selected, and starts LM Studio in
on-demand mode (`CINEFORGE_PLANNING_MODEL_PRELOAD=false`).
The supervisor empties LM Studio before starting ComfyUI; the workflow node
then owns the complete planner-load → planner-unload → LTX handoff.

The bundled `SineForgeLTXPodcastPlanner` node therefore:

1. verifies the selection is an executable GGUF package inside the configured
   local root and resolves it to exactly one LM Studio LLM/GGUF catalog key;
2. releases cached ComfyUI models;
3. unloads other LM Studio model instances;
4. sends image-aware grammar-constrained JSON when the selected model
   advertises vision, or text-only JSON when it does not;
5. validates topic separation, factuality mode, speaker assignment, duration,
   and dialogue word limits;
6. retries one malformed result;
7. enters one outer `finally` path even when preflight or inference fails;
8. unloads every LM Studio model instance;
9. polls LM Studio until the complete loaded-instance set is empty; and
10. returns its prompt outputs only after cleanup succeeds.

Aliases and loaded-instance IDs are rejected because they cannot support an
exact unload proof. If complete cleanup cannot be confirmed, the node raises an
error and deliberately prevents LTX from starting.

## Default LTX profile

```json
{
  "mode": "image_to_video",
  "native_audio": true,
  "two_pass": true,
  "width": 768,
  "height": 448,
  "fps": 24,
  "duration_seconds": 8,
  "sigma_preset": "12 steps",
  "cfg": 1.0,
  "batch_size": 1,
  "optional_loras": []
}
```

The graph uses the installed distilled Sulphur checkpoint, Gemma encoder, LTX
text projection, video/audio VAEs, and spatial latent upscaler. Optional LoRAs
are intentionally disabled until the base workflow is benchmarked.

## Fresh variation versus replay

- **new variation every run** ignores the visible seed as an entropy source
  and creates a new cryptographic variation seed even through an API-format
  submission. This also avoids a cached local-planner result.
- **replay visible seed** uses the visible seed and a stable cache identity.
  It is suitable for retrying a known plan. Exact local-model replay is
  best-effort; the retained JSON is the authoritative prompt record. Full render
  reproduction also requires the API Runner's submitted workflow hash and
  collected output metadata.

Every prompt is retained as JSON. The LTX positive and negative strings are
runtime values nested inside that JSON record; no loose `.txt` prompt file is
created.

## Current-affairs dialogue

If the conversation mentions Iran, Russia, war, elections, medicine, finance,
or any other changing real-world matter, choose one of these policies:

For the example requested here, paste the complete contents of
`SineForge_LTX23_Podcast_Geopolitics_To_Everyday.prompt.json` into
`topic_request_json`. Fresh mode changes the exact opening topic angle,
dialogue, actions, unrelated pivot subject, and video seed on every run. With
no approved source notes, the geopolitical exchange remains explicitly
fictional opinion rather than a claim of verified current events.

```json
{
  "source_notes": [],
  "factuality_policy": "Treat this as fictional opinion dialogue and avoid precise unsupported claims."
}
```

or add approved notes and ask the planner to remain source-bound:

```json
{
  "source_notes": [
    "Approved source note one.",
    "Approved source note two."
  ],
  "factuality_policy": "Use only the approved source notes."
}
```

The video model and local planner must not be presented as verified news
sources.

## Two-speaker limitations

LTX-2.3 native audio can generate quoted dialogue with synchronized motion, but
one continuous two-person shot does not guarantee:

- verbatim words;
- stable distinct voices;
- the correct face speaking each line;
- perfect lip sync; or
- zero identity drift.

Treat those as QA checks. The stronger production lane is four independent
five-second jobs—A speaks, B replies, A pivots, B replies—each starting from
the original lossless image or an approved lossless speaker crop, then
assembled after review.

The workflow is intentionally labeled static-validated, not render-qualified.
Its first live job should remain at the default profile and queue depth one.
