# SineForge LTX Sequence Sheet and Long-Video Implementation Plan

Date: 2026-07-29

Repository: [tj1784/sineforge](https://github.com/tj1784/sineforge)

Upstream concept reviewed:
[niknah/Spreadsheet2Video-ComfyUI](https://github.com/niknah/Spreadsheet2Video-ComfyUI)

Pinned upstream review revision:
[145e15a6fd7c2f746444869550ee3c7a25e17126](https://github.com/niknah/Spreadsheet2Video-ComfyUI/commit/145e15a6fd7c2f746444869550ee3c7a25e17126)

Document status: approved implementation contract; execution authorized

Production renderer in scope: **LTX only**

WAN status: **`on_hold` — the local dry run did not complete successfully**

## 1. Executive decision

SineForge will implement the useful product pattern demonstrated by
Spreadsheet2Video as a native, durable **LTX Sequence Sheet**:

```text
editable ordered rows
  → strict named-field validation
  → one admitted LTX workflow request per row
  → durable ComfyUI queueing and recovery
  → selected last-frame continuity between rows
  → bounded-memory synchronized A/V assembly
  → final LTX mux with native segment audio preserved
```

This replaces the earlier WAN-first implementation direction for the current
release. The rules are:

- LTX is the only executable long-video family in this implementation.
- Every sequence row represents one LTX render request.
- Every row must request **at least 8 seconds and at most 15 seconds**, inclusive.
- Material longer than 15 seconds must be represented by multiple explicit
  rows. The system must not hide a second or third render request inside one
  row.
- The continuation image for a dependent row is the selected, validated
  handoff frame from its predecessor unless the row explicitly selects a
  canonical asset instead.
- WAN references, profiles, and evidence remain in the repository, but WAN
  execution is placed on hold because the dry run failed. It must not be
  selected, queued, or advertised as execution-ready.
- LTX native audio is generated with each segment, is required for the normal
  LTX path, and remains synchronized to that segment through assembly and the
  final mux.
- Phase 8 audio belongs to the WAN production architecture. It is not an LTX
  dependency, execution phase, or admission gate.
- Spreadsheet2Video is a research and compatibility source, not a required
  production dependency.

The implementation must use versioned contracts. Existing
`ltx_base@1` projects remain readable and reproducible. The new 8–15 second
sequence behavior is introduced as **`ltx_base@2`** instead of silently changing
the meaning of a previously versioned profile.

## 2. Why this shape is correct for SineForge

Spreadsheet2Video proves four useful ideas:

1. A row can select a named workflow branch.
2. Row values can parameterize generation.
3. The last image of one row can become the starting image of the next row.
4. Different operations can be sequenced into a longer result.

The project describes the first-row/previous-row handoff and shows long-video
examples for LTX and mixed workflow chains in its
[README](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/README.md#L15-L55).
Its LTX examples include:

- [an LTX room continuation](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/example_workflows/Spreadsheet2Video_ConcatVideoRoom.json);
- [an LTX example with video and audio output](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/example_workflows/Spreadsheet2Video_LTX_example.json).

SineForge must not copy the parts that are unsuitable for a recoverable
production application:

- positional spreadsheet columns;
- one dynamically expanded ComfyUI graph containing every row;
- a process-global prompt lookup;
- random execution fingerprints;
- temporary PNG/FLAC files without a durable artifact manifest;
- loading every frame of the finished movie into a float tensor;
- raw audio tensor concatenation without authoritative duration and sample-rate
  normalization;
- no per-row status, lease, retry, idempotency, or resume record.

Those behaviors are visible in the upstream
[graph expansion and row loop](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/Spreadsheet2VideoNodes.py#L361-L444)
and
[frame/audio finalizer](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/Spreadsheet2VideoNodes.py#L449-L534).

SineForge already owns the better primitives: versioned workflow manifests,
durable queue records, managed assets, render-segment and EDL contracts,
picture-lock contracts, and frame/sample-accurate native-audio planning. The work is
therefore an integration and productization effort rather than a custom-node
port.

## 3. Scope

### 3.1 Included

- A project-scoped Sequence Sheet.
- Native row creation and editing.
- CSV, XLSX, ODS, and canonical JSON import/export.
- Strict named columns.
- One LTX render request per row.
- 8–15 second duration enforcement.
- Deterministic splitting of longer material into explicit rows.
- Text-to-video and image-to-video LTX modes when supported by the selected,
  admitted workflow.
- Previous-row handoff, arbitrary earlier-row handoff, or canonical managed
  asset anchoring.
- Character, location, wardrobe, prop, and reference-asset IDs in row
  contracts and prompts.
- Static, versioned ComfyUI API workflows with semantic manifests.
- Dry-run compilation and runtime dependency preflight.
- Durable row/attempt/job/artifact state.
- Restart-safe retry and resume.
- Handoff-frame selection and quality checks.
- Bounded-memory FFmpeg visual assembly.
- Exact video edit and synchronized LTX native-audio assembly.
- One final LTX A/V mux with frame/sample parity.
- Studio UI for editing, validating, reviewing, queueing, pausing, resuming,
  and retrying the sequence.
- Explicit provenance for every row, attempt, workflow, model, seed, input,
  handoff, clip, EDL decision, native-audio edit, final mux, and delivery.

### 3.2 Explicitly excluded

- Executing WAN.
- Automatically falling back from LTX to WAN.
- Installing Spreadsheet2Video as a runtime dependency.
- Expanding all rows into one giant ComfyUI prompt.
- A row longer than 15 seconds.
- A row shorter than 8 seconds.
- Hidden sub-renders within a row.
- Raw local paths as persisted production references.
- Unvalidated ComfyUI UI-graph JSON as executable API JSON.
- Cross-model latent transfer.
- Rebuilding completed predecessor rows during an ordinary retry.
- Routing LTX clips through WAN Phase 8.

## 4. Production profile policy

### 4.1 New LTX profile

Add `ltx_base@2`:

| Property | Contract |
|---|---|
| Family | `ltx` |
| Status | `qualified` only after the exact workflow/runtime gate passes |
| Default for new Sequence Sheets | yes |
| Minimum row/request duration | 8.0 seconds |
| Maximum row/request duration | 15.0 seconds |
| Short-row exception | none |
| Long-row exception | none |
| Frame rule | positive `8n+1` |
| Default FPS | project FPS; first release qualification at 24 FPS |
| Continuation | supported through an image handoff |
| Native audio | required synchronized segment output |
| Final audio path | preserve, concatenate/remux, and mux with the LTX video |
| WAN Phase 8 | not used by LTX |

Keep `ltx_base@1` registered and readable so existing snapshots retain their
original 6–10 second meaning. Do not rewrite old project snapshots to
`ltx_base@2` automatically. A project owner can explicitly upgrade after seeing
the compilation difference.

### 4.2 WAN hold

Change the public WAN state from the ambiguous
`qualification_required` label to an explicit, non-executable `on_hold` state.
The reason must be persisted and exposed:

```json
{
  "profile_ref": "wan_base@1",
  "status": "on_hold",
  "execution_qualified": false,
  "hold_reason": "Local WAN dry run did not complete successfully.",
  "selectable_for_execution": false
}
```

Required behavior:

- Existing WAN research files and provenance remain untouched.
- Existing projects that reference WAN remain readable.
- Creating or updating an executable Sequence Sheet with WAN fails validation.
- Queue endpoints fail closed if a WAN profile reaches them.
- Studio selectors show “WAN Base v1 · on hold” but do not offer it as an
  executable choice.
- No automatic substitution to LTX occurs because that would change artistic
  and technical semantics.
- WAN may leave hold only through a separate, explicitly approved
  qualification change with successful dry-run evidence.

## 5. Duration and frame contract

### 5.1 One row equals one request

The invariant is:

```text
one SequenceRow
  = one logical LTX request
  = one selected candidate clip
  = one continuity handoff opportunity
```

Retries and alternate candidates are attempts of the same row. They do not
become new sequence rows unless the operator explicitly promotes them into the
edit.

### 5.2 Accepted duration

For `ltx_base@2`:

```text
8.0 <= requested_duration_sec <= 15.0
```

Both endpoints are valid. There is no “shorter with reason” bypass.

At 24 FPS, the boundary examples are:

| Requested duration | Effective intervals | LTX frame count |
|---:|---:|---:|
| 8.0 s | 192 | 193 |
| 10.0 s | 240 | 241 |
| 12.0 s | 288 | 289 |
| 15.0 s | 360 | 361 |

The exact rule is:

```text
frame_count = effective_intervals + 1
frame_count % 8 == 1
effective_duration = (frame_count - 1) / fps
```

Not every arbitrary decimal duration maps to `8n+1` at every FPS. The compiler
must:

1. calculate the nearest admitted frame count;
2. expose the resulting exact duration and delta in dry-run output;
3. require approval when the delta is material;
4. record the requested and compiled values separately;
5. use the EDL/picture-lock stage for deterministic final timing.

It must never silently truncate a numeric value.

### 5.3 Splitting longer material

When the user requests material longer than 15 seconds, the authoring service
creates explicit rows before execution.

For a target duration `T >= 16`:

```text
row_count = ceil(T / 15)
balanced_row_duration = T / row_count
```

The result is then quantized to valid frame counts while preserving the target
through the final EDL. Each created row receives:

- its own immutable `row_id`;
- `split_group_id`;
- `split_ordinal`;
- `split_count`;
- the originating scene/subscene/shot IDs;
- its own prompt and continuity description;
- an explicit dependency on the preceding row.

A target strictly greater than 15 and strictly less than 16 seconds cannot be
represented by two rows under the hard 8-second minimum. The compiler must
return a reviewable proposal:

- reduce the target to 15 seconds; or
- increase it to at least 16 seconds.

It must not create a hidden sub-8-second row.

## 6. Canonical Sequence Sheet contract

The spreadsheet is an authoring/import format. The source of truth is an
immutable, versioned SineForge `SequencePlanRevision`.

### 6.1 Core columns

| Group | Canonical fields |
|---|---|
| Contract | `schema_version`, `row_id`, `row_revision`, `order`, `enabled` |
| Story | `chapter_id`, `scene_id`, `subscene_id`, `shot_id` |
| Split | `split_group_id`, `split_ordinal`, `split_count` |
| Workflow | `profile_ref`, `template_key`, `workflow_version`, `workflow_sha256`, `mode` |
| Text | `prompt`, `negative_prompt`, `audio_prompt` |
| Timing | `requested_duration_sec`, `fps`, `compiled_frame_count`, `compiled_duration_sec` |
| Geometry | `width`, `height`, `aspect_ratio` |
| Sampling | `seed`, `steps`, `cfg`, `strength` |
| Continuity | `continuity_source`, `character_ids`, `asset_ids`, `location_id`, `reference_asset_ids` |
| Editing | `transition_policy`, `boundary_policy`, `audio_policy` |
| Recovery | `max_attempts`, `on_error` |
| Output | `output_name`, `tags`, `params_json` |

### 6.2 Required fields

Every executable row requires:

- `row_id`;
- `order`;
- `profile_ref=ltx_base@2`;
- an admitted `template_key` and version;
- `mode`;
- `prompt`;
- `requested_duration_sec`;
- `fps`;
- `seed` or the literal `derive`;
- `continuity_source`;
- `output_name`.

Image-to-video rows also require a resolvable image source, directly or through
their dependency.

### 6.3 Continuity-source syntax

Supported values:

```text
none
previous_last_frame
asset:<managed-asset-id>
row:<row-id>:handoff_frame
```

Rules:

- `previous_last_frame` resolves at compile time to the nearest preceding,
  enabled row.
- An explicit row reference must exist in the same plan revision.
- A row cannot depend on itself.
- Dependency cycles fail validation.
- A disabled dependency fails validation unless the row selects a different
  anchor.
- Local file paths and URLs must be ingested into managed project storage
  before execution.
- LTX latent handoff is not part of V1. The accepted interchange is a managed
  image plus its provenance and continuity metadata.

### 6.4 Identity and asset metadata

Every compiled prompt must contain stable machine-readable tags:

```text
[PROJECT_ID:<uuid>]
[STORY_ID:<uuid>]
[SCENE_ID:<uuid>]
[SHOT_ID:<uuid>]
[SEQUENCE_PLAN_REVISION_ID:<uuid>]
[SEQUENCE_ROW_ID:<uuid>]
[CHARACTER_IDS:<comma-separated IDs>]
[ASSET_IDS:<comma-separated IDs>]
[LOCATION_ID:<ID>]
[REFERENCE_ASSET_IDS:<comma-separated IDs>]
[CONTINUITY_SOURCE_ROW_ID:<uuid or none>]
[CONTINUITY_HANDOFF_ASSET_ID:<uuid or none>]
```

The prose prompt must also explicitly describe the relevant approved
characters, wardrobe, location, vehicle, props, and other reference assets.
Metadata tags alone are not expected to condition the model.

### 6.5 Seed behavior

`seed` accepts:

- an explicit signed integer; or
- `derive`.

`derive` is resolved once, before queue submission, from stable row inputs and a
plan-level seed. The concrete seed is persisted. Retrying the same attempt
policy reuses it. “Random on every execution” is not permitted for a resumable
production row.

### 6.6 Example

```csv
schema_version,row_id,order,profile_ref,template_key,mode,prompt,requested_duration_sec,fps,seed,continuity_source,character_ids,asset_ids,output_name
sineforge.sequence-sheet/v1,row-001,1,ltx_base@2,ltx23_i2v_hq,i2v,"The worker leaves the office and walks toward the parked car, preserving his face, clothing, and tired posture.",12,24,derive,asset:start-frame-001,"char:worker","asset:car","office_exit"
sineforge.sequence-sheet/v1,row-002,2,ltx_base@2,ltx23_i2v_hq,i2v,"The same worker reaches the same car, opens the driver door, and sits down. Preserve the worker, wardrobe, car, parking layout, and dusk lighting.",12,24,derive,previous_last_frame,"char:worker","asset:car","enter_car"
```

## 7. Workflow admission contract

Extend the existing workflow manifest instead of addressing arbitrary ComfyUI
nodes from spreadsheet cells.

Each admitted LTX template must declare:

```yaml
identity:
  template_key:
  version:
  workflow_sha256:
  profile_ref: ltx_base@2
  model_family: ltx

capabilities:
  modes: [t2v, i2v]
  native_audio:
  reference_image_count:

semantic_inputs:
  positive_prompt:
  negative_prompt:
  seed:
  input_image:
  frame_count:
  fps:
  width:
  height:
  steps:
  cfg:
  strength:
  output_prefix:

semantic_outputs:
  video:
  image:
  audio:
  last_frame:

frame_policy:
  multiple: 8
  remainder: 1
  min_duration_sec: 8
  max_duration_sec: 15

runtime_requirements:
  checkpoints:
  vaes:
  text_encoders:
  loras:
  custom_nodes:
  object_info_contract:
```

Runtime admission must verify:

- API-format workflow shape;
- immutable workflow SHA-256;
- every semantic node ID, class type, and input name;
- every selected dropdown value against live `/object_info`;
- checkpoints, VAEs, encoders, LoRAs, and custom nodes;
- output node and media type;
- frame-count acceptance;
- image-input support for I2V;
- output collection from the active ComfyUI instance;
- one local dry run at 8 seconds;
- one local dry run at 15 seconds;
- a two-row continuation dry run;
- VRAM and wall-clock evidence on the target workstation.

No template is queueable merely because its JSON file exists.

## 8. Durable data model

Add immutable authoring records:

### `sequence_plans`

- `id`
- `project_id`
- `story_id`
- `name`
- `active_revision_id`
- timestamps

### `sequence_plan_revisions`

- `id`
- `sequence_plan_id`
- `revision`
- `schema_version`
- `profile_ref`
- `source_kind`
- `source_filename`
- `source_sha256`
- `canonical_sha256`
- `status`
- `created_by`
- timestamp

### `sequence_rows`

- `id`
- `sequence_plan_revision_id`
- `row_id`
- `row_revision`
- `order_index`
- story placement IDs
- split metadata
- workflow identity and hash
- mode
- prompt fields
- requested and compiled timing
- geometry and sampling fields
- continuity fields
- behavior fields
- canonical row hash
- enabled

### `sequence_row_dependencies`

- `id`
- `sequence_plan_revision_id`
- `predecessor_row_id`
- `successor_row_id`
- `dependency_kind`
- `required_artifact_kind`

### `sequence_row_executions`

- `id`
- `orchestration_run_id`
- `sequence_row_id`
- `status`
- `current_attempt`
- `idempotency_key`
- `lease_owner`
- `lease_expires_at`
- `next_attempt_at`
- timestamps

### `sequence_row_attempts`

- `id`
- `sequence_row_execution_id`
- `attempt_number`
- concrete seed
- patched-workflow snapshot ID/hash
- Comfy job ID
- input asset hashes
- handoff input hash
- output clip ID/hash
- required synchronized native-audio asset ID/hash
- error class and bounded error detail
- started/finished timestamps

### `continuity_packets`

- predecessor/successor row IDs
- source clip asset ID/hash
- selected handoff image ID/hash
- source frame index and PTS
- character, asset, location, wardrobe, and camera state
- approved reference asset IDs
- workflow/model provenance
- QA metrics and warnings
- re-anchor decision

Reuse existing durable execution and media tables wherever their ownership and
constraints fit:

- `OrchestrationRun`
- `OrchestrationStep`
- `ProviderInvocation`
- `WorkflowRun`
- `ComfyJob`
- `GeneratedAsset`
- `FileOutput`
- `FFmpegJob`
- `AuditLog`
- `ErrorLog`

The migration must be additive. It must not repurpose or delete the existing
WAN evidence, LTX v1 records, generated assets, or workflow snapshots.

## 9. Idempotency and invalidation

The row-execution idempotency key must include:

```text
project_id
sequence_plan_revision_id
row_id
row_revision
profile_ref
workflow_sha256
model/profile snapshot hash
prompt and negative-prompt hash
concrete seed
compiled frame count/FPS/geometry
sampler settings
input asset hashes
reference asset hashes
continuity handoff hash
```

Editing a row creates a new plan revision. It never mutates an approved
revision in place.

Invalidation rules:

- Editing row N invalidates N.
- It invalidates every transitive dependent that consumes N’s handoff.
- It does not invalidate an independent row or a row anchored to an unaffected
  canonical asset.
- It never deletes prior artifacts; they remain attached to the prior revision.
- The UI must show the complete invalidation set before the new revision is
  approved.

## 10. Execution state machine

Per-row states:

```text
draft
invalid
pending
blocked_on_dependency
ready
leased
submitting
queued
running
collecting
validating
awaiting_selection
succeeded
retry_wait
failed
skipped
canceled
stale
```

Execution order:

1. Admit an immutable plan revision.
2. Resolve every dependency into a DAG.
3. Mark root rows `ready`.
4. Acquire a lease for one row.
5. Materialize managed input and reference files into the bounded Comfy input
   namespace.
6. Patch the admitted static workflow through semantic manifest bindings.
7. Persist the exact patched-workflow snapshot before submission.
8. Submit one job to ComfyUI.
9. Poll or consume events with bounded timeouts.
10. Collect output files into managed project storage.
11. Fully decode and probe the clip.
12. Run clip and tail-frame QA.
13. Select a candidate or await operator selection.
14. Extract and persist the continuity handoff.
15. Mark the row successful.
16. Unblock dependent rows.

Queue policy:

- Keep the local video queue shallow; default to one LTX video job in flight.
- Do not prequeue a dependent row before its exact handoff asset exists.
- Independent roots may be scheduled concurrently only after workstation
  benchmarking proves it safe.
- Every lease has a heartbeat and expiration.
- A process restart recovers stale leases and resumes from the earliest
  incomplete row.
- Retrying a row does not rerun successful ancestors.
- Canceling a sequence prevents new submissions and requests cancellation of
  an active job when the runtime supports it.

## 11. Continuity packet and handoff QA

Passing only the literal last frame is too fragile. For each accepted clip:

1. Fully decode the clip.
2. Inspect a bounded tail window.
3. Reject frames that are:
   - corrupt or undecodable;
   - black or nearly blank;
   - exact duplicates beyond policy;
   - frozen;
   - severely blurred;
   - grossly malformed;
   - an obvious identity/geography discontinuity when review metrics exist.
4. Prefer the latest usable frame.
5. Extract it losslessly to managed project storage.
6. Record source frame number, PTS, source hash, image hash, extraction version,
   and QA results.
7. Attach character, asset, wardrobe, location, and camera state.
8. Pass the resulting image asset—not an untracked temporary path—to the
   successor.

The opening of the successor must be checked against the predecessor handoff.
When the successor contains the same anchor as its first frame, the EDL may
remove exactly one duplicate boundary frame. This must be an explicit edit
decision, not an unconditional deletion.

Identity drift is controlled through re-anchoring:

- A row may select a canonical character/location asset instead of the previous
  frame.
- The compiler may warn after a configured number of chained handoffs.
- A QA failure may require operator re-anchoring before successors run.
- Crossfades are not the default continuity repair because they can ghost
  people and deform geometry.

## 12. LTX synchronized audiovisual assembly

### 12.1 File-based video assembly

The final LTX pipeline is file based:

```text
selected managed clips
  → full decode/probe
  → boundary trims
  → optional retime/interpolation/upscale
  → stream-signature comparison
  → FFmpeg concat or one controlled mezzanine encode
  → sample-exact native-audio edits using the same row boundaries
  → one synchronized final A/V mux
```

Rules:

- Never reopen the whole film as a ComfyUI IMAGE tensor.
- Use the concat demuxer and stream copy when stream signatures match.
- Normalize dimensions, FPS, time base, pixel format, color metadata, and codec
  only when necessary.
- Preserve originals and selected candidates.
- Persist EDL decisions, source hashes, FFmpeg/ffprobe versions, command
  templates, output hashes, and full probe evidence.
- Preserve the native audio generated with every LTX row.
- Apply every frame trim, retime, or transition to the corresponding audio
  samples deterministically.
- Verify that final frame duration and final native-audio sample duration are
  exactly equal before delivery.

### 12.2 LTX native audio

An admitted LTX workflow must emit synchronized native audio for every row:

- collect it as a required row-scoped managed asset;
- preserve its sample rate, channels, duration, workflow identity, seed, and
  hash;
- label it `synchronized_native`;
- do not concatenate it as raw tensors;
- require its decoded sample duration to match the row video duration;
- trim the corresponding samples when an exact duplicate boundary frame is
  removed;
- perform an explicit controlled audio remux when video retiming or transition
  overlap prevents stream-copy concatenation;
- mux the assembled native audio with the assembled LTX video.

Missing or mistimed native audio is an LTX assembly failure. It must not be
replaced with implicit silence and it must not be deferred to another
production phase.

### 12.3 WAN Phase 8 boundary

Phase 8 is defined only for the WAN-based production path. No LTX Sequence
Sheet state transition, admission rule, queue worker, assembly worker, or final
delivery may depend on Phase 8.

## 13. API surface

Proposed routes:

```text
POST   /projects/{project_id}/sequence-plans
GET    /projects/{project_id}/sequence-plans
GET    /sequence-plans/{plan_id}
POST   /sequence-plans/{plan_id}/imports
POST   /sequence-plans/{plan_id}/revisions
GET    /sequence-plan-revisions/{revision_id}
POST   /sequence-plan-revisions/{revision_id}/validate
POST   /sequence-plan-revisions/{revision_id}/compile
POST   /sequence-plan-revisions/{revision_id}/approve
POST   /sequence-plan-revisions/{revision_id}/execute
POST   /sequence-plan-revisions/{revision_id}/pause
POST   /sequence-plan-revisions/{revision_id}/resume
POST   /sequence-plan-revisions/{revision_id}/cancel
GET    /sequence-plan-revisions/{revision_id}/runs
GET    /sequence-row-executions/{execution_id}
POST   /sequence-row-executions/{execution_id}/retry
POST   /sequence-row-executions/{execution_id}/select-candidate
POST   /sequence-row-executions/{execution_id}/re-anchor
GET    /sequence-plan-revisions/{revision_id}/export.csv
GET    /sequence-plan-revisions/{revision_id}/export.xlsx
GET    /sequence-plan-revisions/{revision_id}/export.json
```

All mutating execution routes require:

- project authorization;
- approved plan revision;
- explicit `allow_rendering`;
- qualified `ltx_base@2`;
- a caller-provided idempotency key;
- optimistic revision/version checking;
- audit logging.

The dry-run endpoints do not queue work.

## 14. Studio experience

Add a project-scoped **Sequences** page rather than placing the production
sequence inside the global Workflow Registry.

Required interface:

- upload CSV/XLSX/ODS;
- create rows without uploading a file;
- edit in a spreadsheet-like grid;
- reorder and enable/disable rows;
- split material longer than 15 seconds into visible rows;
- choose an admitted LTX static workflow;
- choose T2V/I2V mode;
- edit prompt, negative prompt, duration, seed, settings, references, and
  continuity source;
- show character, location, and reusable-asset chips;
- render the selected ComfyUI workflow in the right panel;
- inspect semantic bindings and patched values;
- display exact compiled frame count and duration delta;
- display dependency-chain and DAG views;
- preflight all workflows, models, custom nodes, and input assets;
- show row state, current attempt, queue status, logs, output previews, and
  handoff image;
- retry, pause, resume, cancel, skip, select candidate, or re-anchor;
- show downstream invalidation before accepting an edit;
- assemble selected clips with their synchronized native audio;
- preview and approve the final LTX A/V mux;
- export canonical sheets and JSON.

The global Workflow/API Caller pages remain responsible for registering and
testing static API workflows. The Sequence Sheet may select admitted
workflows, but it must not silently import or mutate them.

WAN presentation:

- show `WAN Base v1 · on hold`;
- include the dry-run failure reason;
- disable selection and queue actions;
- link to its existing research/evidence;
- never imply that it ran successfully.

## 15. Concrete file map

The implementation is expected to touch or add the following bounded areas.
Exact module splitting may change during implementation, but ownership and
behavior must remain equivalent.

### 15.1 Backend contracts and services

Modify:

- `backend/app/services/production_profiles.py`
  - add `on_hold`;
  - preserve `ltx_base@1`;
  - add `ltx_base@2`;
  - enforce 8–15 seconds;
  - fail closed for WAN.
- `backend/app/services/workflows/template_service.py`
  - manifest v2 semantic capabilities, outputs, frame policy, and runtime
    requirements.
- `backend/app/services/queue/service.py`
  - sequence-row ownership, lease, idempotency, and dependency-ready claims.
- `backend/app/services/video/phase_seven.py`
  - LTX row/frame compilation and exact EDL integration.
- `backend/app/services/phase_seven_videos.py`
  - replace WAN-specific direct batch queueing with the LTX durable sequence
    scheduler.
- `backend/app/services/audio/planning.py`
  - consume persisted picture-lock boundaries and optional LTX guide stems.
- `backend/app/db/base.py`
  - add sequence tables and relationships without removing existing records.
- `backend/app/api/router.py`
  - register the sequence router.

Add:

- `backend/app/schemas/sequence_sheet.py`
- `backend/app/services/sequence_sheets/__init__.py`
- `backend/app/services/sequence_sheets/importers.py`
- `backend/app/services/sequence_sheets/validator.py`
- `backend/app/services/sequence_sheets/compiler.py`
- `backend/app/services/sequence_sheets/scheduler.py`
- `backend/app/services/sequence_sheets/continuity.py`
- `backend/app/services/sequence_sheets/assembly.py`
- `backend/app/api/routes/sequence_sheets.py`
- one additive Alembic migration for sequence records and profile-state data.

### 15.2 Workflow storage

Add one or more admitted, static templates under:

```text
storage/workflow_templates/ltx_sequence_<template-key>/
  workflow_api.json
  workflow_manifest.json
  README.md
  qualification.json
```

The README and qualification record must state:

- original source URL and revision;
- whether the JSON is an untouched source, a local export, or a reconstruction;
- local changes;
- exact required model paths and hashes;
- exact custom-node names and revisions;
- successful 8-second, 15-second, and two-row continuation evidence;
- measured VRAM and wall-clock results;
- known limitations.

Do not delete the existing WAN reference directories.

### 15.3 Frontend

Modify:

- `frontend/src/api/client.ts`
- `frontend/src/studio/StudioRouter.tsx`
- `frontend/src/components/AppShell.tsx`
- `frontend/src/studio/pages/SettingsPage.tsx`
- `frontend/src/studio/components/ProductionPhasePreview.tsx`
- project creation/settings selectors that currently expose WAN as a normal
  choice.

Add:

- `frontend/src/studio/pages/SequencesPage.tsx`
- `frontend/src/studio/components/sequence/SequenceGrid.tsx`
- `frontend/src/studio/components/sequence/SequenceRowEditor.tsx`
- `frontend/src/studio/components/sequence/SequenceWorkflowPanel.tsx`
- `frontend/src/studio/components/sequence/SequenceDependencyView.tsx`
- `frontend/src/studio/components/sequence/SequenceRunMonitor.tsx`
- focused component and API tests.

### 15.4 Tests

Add:

- `backend/tests/test_ltx_sequence_profile.py`
- `backend/tests/test_sequence_sheet_import.py`
- `backend/tests/test_sequence_sheet_validation.py`
- `backend/tests/test_sequence_sheet_compiler.py`
- `backend/tests/test_sequence_sheet_scheduler.py`
- `backend/tests/test_sequence_continuity.py`
- `backend/tests/test_sequence_assembly.py`
- `backend/tests/api/test_sequence_sheet_routes.py`
- frontend Sequence Sheet tests.

Update the existing production-profile, project-settings, queue, workflow
manifest, LTX A/V assembly, and WAN Phase 8 tests for the explicit family
boundary.

## 16. Implementation milestones

Engineering milestones are named “milestones” to avoid confusion with
SineForge’s user-facing production phases.

### Milestone 0 — Preserve evidence and make WAN fail closed

Deliver:

- Record this plan.
- Add `on_hold` profile status.
- Set `wan_base@1` to `on_hold` with the dry-run failure reason.
- Disable WAN execution in backend and Studio selectors.
- Preserve all WAN evidence and existing project readability.
- Add regression tests proving no WAN job can be queued.

Exit gate:

- WAN is visible as historical/research state but impossible to execute.

### Milestone 1 — LTX profile v2 and duration compiler

Deliver:

- Add `ltx_base@2`.
- Set 8–15 second hard bounds.
- Implement `8n+1` frame compilation.
- Implement exact-duration reporting and frame-delta review.
- Implement explicit long-material splitting.
- Preserve `ltx_base@1`.
- Update settings/API/frontend types.

Exit gate:

- 7.999 and 15.001 second rows fail;
- 8.0 and 15.0 second rows pass;
- a longer request is represented by visible valid rows;
- existing v1 snapshots retain their old identity.

### Milestone 2 — Sequence Sheet schema, import, and dry run

Deliver:

- Canonical Pydantic models.
- CSV/XLSX/ODS/JSON import.
- Named header binding.
- Cell-level validation errors.
- Stable row IDs and canonical hashes.
- DAG validation.
- dry-run compilation API.
- safe export.

Exit gate:

- A sheet can be imported, normalized, validated, compiled, and exported
  without touching ComfyUI.

### Milestone 3 — Workflow manifest v2 and LTX admission

Deliver:

- Semantic input/output bindings.
- LTX capabilities and frame policy.
- Runtime artifact requirements.
- live `/object_info` preflight.
- patched-workflow preview.
- static workflow registration.
- local qualification evidence for 8 seconds, 15 seconds, and a two-row
  continuation.

Exit gate:

- The selected LTX workflow is proven queueable on the active runtime with all
  exact dependencies.

### Milestone 4 — Durable persistence and scheduler

Deliver:

- Additive migration.
- Plans, revisions, rows, dependencies, executions, attempts, and continuity
  packets.
- Lease-based row scheduler.
- idempotent submission.
- bounded polling/event collection.
- retry, pause, resume, cancel, and stale recovery.
- transitive invalidation.

Exit gate:

- Killing and restarting the backend during row N resumes safely without
  regenerating successful predecessors.

### Milestone 5 — Continuity extraction and candidate QA

Deliver:

- Managed candidate collection.
- full-decode validation.
- tail-window QA.
- exact handoff extraction and hashing.
- continuity packet.
- duplicate-boundary decision.
- re-anchor path.
- candidate selection.

Exit gate:

- The handoff hash consumed by row N+1 exactly matches the approved output from
  row N.

### Milestone 6 — Bounded-memory LTX A/V assembly

Deliver:

- EDL from selected sequence clips.
- stream compatibility comparison.
- stream-copy concat where possible.
- one controlled encode where necessary.
- exact trims and duplicate handling.
- required synchronized native-audio edits.
- exact video-frame/audio-sample parity.
- final mux and immutable delivery provenance.

Exit gate:

- A multi-minute sequence assembles with bounded memory, fully decodes, and
  retains synchronized native audio.

### Milestone 7 — LTX final mux and delivery

Deliver:

- Required LTX-native audio assets.
- row-boundary-derived sample edits.
- exact sample ranges and any controlled retime/remux decisions.
- one final mux.
- final A/V QA and delivery manifest.

Exit gate:

- Final native-audio and video durations agree exactly and no WAN Phase 8
  service is invoked.

### Milestone 8 — Studio UI and end-to-end qualification

Deliver:

- Sequence Sheet page and grid.
- workflow right panel.
- dependency view.
- dry-run/preflight.
- run monitor and operator controls.
- split, retry, re-anchor, assembly, and picture-lock flows.
- production soak test.

Exit gate:

- An operator can create, inspect, execute, interrupt, resume, assemble, add
  audio, and deliver an LTX sequence without editing JSON by hand.

## 17. Acceptance tests

### 17.1 Duration and frames

- Accept exactly 8.0 seconds.
- Accept exactly 15.0 seconds.
- Reject 7.999 seconds.
- Reject 15.001 seconds.
- Reject NaN, infinity, booleans, and numeric strings where strict numbers are
  required.
- Every compiled frame count satisfies `8n+1`.
- Requested, compiled, and final EDL durations are separately recorded.
- A 30-second request becomes two explicit 15-second rows.
- A 45-second request becomes three explicit 15-second rows.
- A 60-second request becomes four explicit 15-second rows.
- A 15.5-second request produces an explicit timing-choice validation result,
  not a hidden short row.

### 17.2 Import and schema

- Reordered named columns produce the same canonical plan.
- Duplicate or missing headers fail.
- Duplicate row IDs fail.
- Blank and disabled rows behave predictably.
- Quoted commas, multiline text, and UTF-8 BOM work.
- Selected XLSX/ODS sheet behavior is explicit.
- Workbook size, row, column, cell, and decompression limits work.
- Export protects formula-leading cells.
- Paths outside managed roots fail.
- URLs are ingested through bounded, validated asset handling rather than
  dereferenced by the execution worker.

### 17.3 Workflow admission

- UI graph JSON fails as executable workflow input.
- A changed workflow hash fails.
- A missing checkpoint, VAE, text encoder, LoRA, or custom node fails before
  GPU work.
- An invalid dropdown selection fails before submission.
- T2V/I2V capability mismatches fail.
- Missing image input for I2V fails.
- The 8-second and 15-second qualification fixtures complete and fully decode.
- The two-row last-frame continuation fixture completes.

### 17.4 Scheduling and recovery

- A successor cannot queue before its approved handoff exists.
- Fixed-seed retry preserves exact inputs.
- A successful predecessor is not rerun after a successor failure.
- A backend restart recovers stale leases.
- Repeated execute calls with the same idempotency key do not create duplicate
  Comfy jobs.
- Two project runs do not share temporary directories or outputs.
- Pause prevents new submissions.
- Cancel prevents new submissions and records the active-job outcome.
- Editing an upstream row invalidates only its transitive dependents.

### 17.5 Continuity

- Character, asset, location, reference, plan, and row IDs appear in the
  compiled prompt and manifest.
- The prompt prose explicitly mentions relevant approved references.
- Handoff QA rejects black, corrupt, frozen, duplicated, and severely blurred
  tail frames.
- The exact selected frame index, PTS, source hash, and image hash are stored.
- One duplicated opening anchor is removed only through an explicit EDL
  decision.
- An independent canonical anchor does not become invalid merely because a
  preceding row changes.
- Re-anchor intervention blocks successors until resolved.

### 17.6 Assembly and audio

- Compatible clips use stream-copy concat.
- Incompatible clips are normalized through one controlled encode.
- Resolution, FPS, time-base, pixel-format, codec, and color mismatches are
  visible and deterministic.
- Long assembly memory usage remains bounded.
- All source and final files fully decode.
- Native LTX audio is required and preserved as a managed synchronized asset.
- Missing or mistimed native audio fails LTX assembly.
- Sample-rate and channel differences are rejected or normalized explicitly
  through the controlled LTX A/V assembly path.
- The final sample count and A/V duration pass exact validation.
- LTX delivery never invokes WAN Phase 8.

### 17.7 WAN hold

- WAN remains visible in catalog responses with `status=on_hold`.
- WAN is disabled in project and Sequence Sheet execution selectors.
- Direct WAN queue requests fail with a stable, descriptive error.
- No automatic LTX substitution occurs.
- Existing WAN evidence files and project snapshots remain readable.

## 18. Security and resource controls

- Limit upload size, workbook expansion, row count, column count, and cell size.
- Treat spreadsheet formulas as data; never evaluate them.
- Escape formula-leading cells on CSV/XLSX export.
- Resolve every persisted media reference through managed project assets.
- Prevent traversal and junction/symlink escape.
- Restrict output prefixes to sanitized project namespaces.
- Never allow a sheet to supply arbitrary server paths, shell commands, URL
  schemes, node classes, or node IDs.
- Validate external imports against an SSRF-safe allowlist and bounded download
  policy.
- Bound Comfy polling and output collection.
- Bound log/error payloads.
- Keep secrets and bearer tokens out of snapshots, logs, sheets, and
  provenance manifests.
- Maintain a shallow local GPU queue.
- Store large media as files, not database blobs or in-memory frame arrays.
- Use content hashes and ownership checks before reusing an artifact.

## 19. Observability

Every run should expose:

- plan revision and canonical hash;
- row counts by state;
- currently leased/running row;
- attempt number and concrete seed;
- workflow/profile/model identity and hashes;
- dependency wait reason;
- Comfy prompt/job ID;
- queue, generation, collection, QA, and assembly durations;
- input, output, reference, and handoff hashes;
- VRAM evidence when available;
- retry and failure class;
- EDL and picture-lock identity;
- native-audio edit, mux, and delivery identity.

Required metrics:

- row success/failure/retry rate;
- median and percentile wall-clock time by duration/template;
- queue wait;
- stale-lease recoveries;
- continuity QA failures;
- re-anchor rate;
- invalidation fan-out;
- output decode failures;
- assembly throughput and peak memory;
- audio sample/duration corrections.

## 20. Rollout

### Stage 1 — Contract-only

- Land profile states, `ltx_base@2`, schemas, and tests.
- Keep Sequence execution behind `ltx_sequence_sheet_enabled=false`.
- Make WAN fail closed.

### Stage 2 — Dry-run authoring

- Enable import, editing, validation, compilation, workflow preview, and export.
- Do not expose Generate.

### Stage 3 — Single-row LTX

- Enable one admitted 8–15 second row.
- Require successful local runtime preflight.
- Preserve explicit operator submission.

### Stage 4 — Two-row continuity

- Enable a predecessor and one dependent.
- Require handoff hash and full-decode evidence.

### Stage 5 — Multi-row and recovery

- Enable longer sequences.
- Require restart, retry, pause, resume, cancellation, and invalidation tests.

### Stage 6 — Synchronized LTX A/V assembly

- Enable selected-clip and native-audio assembly.
- Require bounded-memory soak, exact EDL validation, and frame/sample parity.

### Stage 7 — LTX final mux and delivery

- Enable native-audio edits, final mux, and delivery QA.

### Stage 8 — General availability

- Remove the feature flag only after all acceptance gates pass on the target
  workstation.
- WAN remains on hold independently.

## 21. Rollback

Rollback must be non-destructive.

Feature rollback:

1. Set `ltx_sequence_sheet_enabled=false`.
2. Stop claiming new sequence-row leases.
3. Allow an already-running Comfy job either to finish and be collected or to
   be canceled explicitly.
4. Keep plans, revisions, attempts, logs, workflow snapshots, and media.
5. Restore the previous Studio navigation/default experience.
6. Continue to serve read-only sequence history and exports.

Profile rollback:

- Stop defaulting new projects to `ltx_base@2`.
- Preserve `ltx_base@2` records and snapshots.
- Return the new-project default to `ltx_base@1`.
- Do not rewrite an existing plan revision from v2 to v1.

Migration rollback:

- The migration is additive.
- Application rollback ignores the new tables after leases are quiesced.
- Do not drop sequence tables as an operational rollback.
- A destructive down migration is reserved for an explicit maintenance window
  after backup and verification, not routine deployment recovery.

Media rollback:

- Never delete accepted source clips, handoff frames, picture locks, native
  audio stems, or final deliveries automatically.
- Mark superseded artifacts through lineage/status records.
- Garbage collection is a separate, reviewable retention operation.

WAN rollback is unnecessary because the plan makes WAN more restrictive:
`on_hold` is the safe state. Re-enabling WAN requires a new qualification
decision, not a rollback shortcut.

## 22. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LTX 15-second request exceeds local VRAM or practical runtime | 15-second qualification is mandatory before `ltx_base@2` becomes executable; fail closed if it does not pass |
| Last-frame drift accumulates | continuity packet, tail QA, canonical references, explicit re-anchor policy |
| A bad tail frame poisons the successor | inspect a bounded tail window and select the latest usable frame |
| Spreadsheet column reorder changes meaning | named schema only; legacy positional import is compatibility-only and visibly warned |
| Retry changes the shot | persist concrete seed, workflow snapshot, model/profile snapshot, and all input hashes |
| One failed row loses completed work | per-row jobs, durable artifacts, dependency state, and resume |
| Large movie exhausts RAM | encoded segment files and bounded-memory FFmpeg assembly |
| Native audio changes picture timing | picture is authoritative; native audio is an optional managed stem |
| Old project behavior changes | preserve `ltx_base@1`; introduce `ltx_base@2` |
| WAN is accidentally reactivated | explicit `on_hold` state, backend execution guard, disabled selectors, regression tests |
| Workflow JSON changes under the same name | immutable hash and version; fail preflight |
| User edit invalidates too much work | dependency-aware transitive invalidation preview |

## 23. Definition of done

The implementation is complete only when:

- WAN is visibly on hold and cannot execute.
- `ltx_base@1` remains reproducible.
- `ltx_base@2` enforces one 8–15 second LTX request per row.
- Longer material is represented by explicit rows.
- A sheet imports through named, strict fields.
- Every admitted row dry-runs before queueing.
- Exact workflows and runtime requirements are pinned and validated.
- The scheduler runs rows through durable, dependency-aware jobs.
- Restart, retry, pause, resume, cancel, and invalidation work.
- The selected handoff frame is a managed, hashed artifact.
- Character and asset IDs and reference descriptions follow every row.
- A multi-row LTX sequence completes without one giant ComfyUI graph.
- Selected clips assemble through bounded-memory file operations.
- The final LTX A/V assembly identity is immutable and fully evidenced.
- Native segment audio remains synchronized through the final mux.
- WAN Phase 8 is never invoked by an LTX sequence.
- The final file fully decodes and has complete reproducible provenance.
- The operator can perform the workflow in Studio without manually editing
  JSON.

## 24. Provenance and implementation references

### External primary sources

- [Spreadsheet2Video-ComfyUI repository](https://github.com/niknah/Spreadsheet2Video-ComfyUI)
- [Pinned README](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/README.md)
- [Pinned node implementation](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/Spreadsheet2VideoNodes.py)
- [Pinned LTX room example](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/example_workflows/Spreadsheet2Video_ConcatVideoRoom.json)
- [Pinned LTX video/audio example](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/example_workflows/Spreadsheet2Video_LTX_example.json)
- [Upstream MIT license](https://github.com/niknah/Spreadsheet2Video-ComfyUI/blob/145e15a6fd7c2f746444869550ee3c7a25e17126/LICENSE)
- [LTX-2 repository](https://github.com/Lightricks/LTX-2)
- [LTX two-stage pipeline documentation](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-pipelines/README.md)
- [Official LTX image-to-video guide](https://docs.ltx.io/open-source-model/usage-guides/image-to-video)
- [ComfyUI LTX 2.3 examples](https://docs.comfy.org/tutorials/video/ltx/ltx-2-3)

### Existing SineForge implementation anchors

- `backend/app/services/production_profiles.py`
- `backend/app/services/workflows/template_service.py`
- `backend/app/services/queue/service.py`
- `backend/app/services/video/phase_seven.py`
- `backend/app/services/phase_seven_videos.py`
- `backend/app/services/audio/contracts.py`
- `backend/app/services/audio/planning.py`
- `backend/app/db/base.py`
- `backend/app/api/routes/video.py`
- `backend/app/api/routes/audio.py`
- `backend/app/api/routes/api_caller.py`
- `frontend/src/studio/pages/ApiCallerPage.tsx`
- `frontend/src/studio/components/ProductionPhasePreview.tsx`
- `docs/SINEFORGE_WAN_BASE_AND_PHASE8_AUDIO_IMPLEMENTATION_PLAN_2026-07-28.md`
- `docs/SULPHUR2_FP8_QUANT_I2V_WORKFLOW_GUIDE_2026-07-29.md`

This document supersedes the WAN-first execution priority in the 2026-07-28
plan. It does not delete that plan or its evidence. Where the documents differ,
this document controls renderer priority, Sequence Sheet behavior, the hard
8–15 second LTX row contract, and WAN’s `on_hold` execution state.
