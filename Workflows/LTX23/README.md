# SineForge LTX-2.3 Dynamic Podcast

This package contains a repository-managed, image-driven podcast workflow for
the main LTX ComfyUI installation.

It performs one local staged run:

```text
two-person source image
    → local Qwen 3.6 40B strict-JSON variation
    → confirmed Qwen unload
    → two-pass LTX-2.3 image-to-video with native audio
    → matching MP4 and JSON prompt artifacts
```

No hosted/API agent is used. LM Studio is contacted only on
`127.0.0.1:1234`.

## Files

- `SineForge_LTX23_Dynamic_Podcast_Qwen40B.workflow.json` is the
  editor-format workflow loaded by **Load in ComfyUI**.
- `SineForge_LTX23_Dynamic_Podcast_Qwen40B.api.json` is the executable
  API-format graph used by SineForge's native API Runner.
- `SineForge_LTX23_Dynamic_Podcast.prompt.json` is the only prompt-contract
  source of truth. It contains the system prompt object, default request
  object, category hints, strict response schema, and fixed negative prompt.
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
- a complete retained `.json` record with hashes and unload confirmation.

This changes both the semantics and the LTX noise. Semantic uniqueness is
strongly encouraged but cannot be proved from a seed alone. Paste recent topic
names into `recent_topics_json` when duplicate avoidance matters.

## First run

1. Run `scripts/Install-SineForgeWorkflowBridge.ps1` if the bridge is not
   already installed, then restart the main LTX ComfyUI once.
2. Start LM Studio's local server on `http://127.0.0.1:1234`.
3. Confirm this exact model is installed:

   ```text
   qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-neo-code-di-imatrix-max
   ```

4. In SineForge's API Runner, open the read-only workflow and choose
   **Load in ComfyUI**, or upload the API JSON directly to the Runner.
5. Load a source image that clearly shows both podcast participants.
6. In `topic_request_json`, confirm:

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

7. Validate without queueing. Resolve every missing node or model choice.
8. Queue one job only.

## VRAM handoff

The workstation has a 24GB GPU. The Qwen 40B package and the LTX-2.3 model
cannot safely remain in VRAM together.

The bundled `SineForgeLTXPodcastPlanner` node therefore:

1. releases cached ComfyUI models;
2. unloads other LM Studio model instances;
3. requests grammar-constrained JSON from the exact Qwen model;
4. validates topic separation, factuality mode, speaker assignment, duration,
   and dialogue word limits;
5. retries one malformed result;
6. unloads the Qwen instance in a `finally` path;
7. polls LM Studio until the model is absent; and
8. returns its prompt outputs only after unload succeeds.

If unload cannot be confirmed, the node raises an error and deliberately
prevents LTX from starting.

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
  best-effort; the retained prompt JSON and explicit video seed remain the
  authoritative production record.

Every prompt is retained as JSON. The LTX positive and negative strings are
runtime values nested inside that JSON record; no loose `.txt` prompt file is
created.

## Current-affairs dialogue

If the conversation mentions Iran, Russia, war, elections, medicine, finance,
or any other changing real-world matter, choose one of these policies:

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
