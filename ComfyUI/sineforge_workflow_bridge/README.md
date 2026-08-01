# SineForge workflow bridge

This loopback-only ComfyUI extension supplies Sineforge identity/readiness and
local planning nodes. It retains a compatibility-only editor transfer route,
but the supported unified application keeps operators in the Sineforge Engine
workspace and never queues an editor-format graph.

The bridge accepts editor-format workflow JSON only from loopback clients,
stores at most 32 one-time transfers in memory, expires them after five
minutes, and consumes each token the first time the ComfyUI browser requests
it.

It also registers local planning and flow nodes:

```text
SineForge · Local Podcast JSON Planner
SineForge · Local Model Krea 2 Continuation JSON
SineForge · Local Model General Continuation JSON
SineForge · Continuation Loop Count · 0 = Continuous
```

The general continuation node puts `scene_or_subject` and `next_event` first,
makes dialogue optional and JSON-only, and maps those controls into the same
strict continuation request contract used by the compatibility node. Its
`audio_mode` can infer audio from the scene, force no dialogue, consume an
ordered `dialogue_json` array, or use the advanced request JSON without
overrides.

The loop-count node sends values 1 through 100000 through unchanged. A visible
value of 0 resolves to 100000 cycles so the workflow keeps going until the user
presses ComfyUI **Interrupt**.

Every planner presents a real model dropdown discovered from executable GGUF
packages physically beneath `C:\Users\Blokey\.lmstudio\models`. Qwen 3.6 40B
is first and selected by default only; all other installed local LLM packages
remain selectable. Embedding entries, `mmproj`-only entries, aliases, hosted
models, and paths outside that root are excluded. Vision-capable models receive
local image references; text-only models receive the same strict JSON request
without image attachments, and that omission is recorded in JSON provenance.

Each run resolves the selected value to one exact LM Studio LLM/GGUF catalog
key, requires a strict JSON-Schema response, releases cached ComfyUI models
before planning, and uses an outer cleanup guard to unload every LM Studio
model instance before returning anything to an LTX render node. If the
complete loaded-instance set cannot be verified empty, the node fails closed.
No planner accepts a cloud URL or API key.

The owned engine mounts this directory through
`ComfyUI/sineforge_engine_paths.yaml`; no external install step is required.
