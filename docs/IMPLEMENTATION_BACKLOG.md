# SineForge Implementation Backlog

Last audited: 2026-07-29
Scope of this audit: LTX Sequence Sheet with native synchronized audio, WAN
Base hold, and WAN Phase 8 Foley/audio runtime admission
Authoritative design: [WAN Base and Phase 8 Audio Implementation Plan](SINEFORGE_WAN_BASE_AND_PHASE8_AUDIO_IMPLEMENTATION_PLAN_2026-07-28.md)

LTX Sequence Sheet design:
[LTX Sequence Sheet and Long-Video Implementation Plan](SINEFORGE_LTX_SEQUENCE_SHEET_IMPLEMENTATION_PLAN_2026-07-29.md)

## WAN Phase 8 runtime status

**Runtime admission is closed.**

The repository currently proves only non-rendering WAN Phase 8 capabilities:

- immutable picture-lock hash validation;
- exact frame, rational PTS, and 48 kHz sample-range planning;
- 1–15-second Foley windows around an eight-second target;
- a 450-frame analysis ceiling;
- hard-cut, continuous-ambience, and visual-crossfade boundary policies;
- deterministic attempt identifiers and seeds;
- named loudness-policy data;
- bounded numeric PCM silence, length, finite-value, and full-scale QA;
- API responses that explicitly state that they did not generate audio, read
  media, or start a model invocation.

These capabilities do **not** prove that HunyuanVideo-Foley is installed,
licensed for the intended deployment, compatible with the active ComfyUI
runtime, runnable on the target GPU, or able to produce an admitted audio
artifact. They also do not provide a durable audio execution ledger, stem
assembly, mastering, mux execution, or final delivery validation.

No production route, worker, or UI may reinterpret a successful planning or
numeric-QA response as evidence that audio exists.

## Admission rule

WAN Phase 8 media execution remains disabled until every P8-G01 through P8-G09 gate
below has:

1. an implemented owner and fail-closed service boundary;
2. automated acceptance coverage;
3. durable, hash-addressed evidence from the exact target runtime;
4. an explicit promotion decision;
5. rollback and invalidation behavior.

Planning endpoints may remain enabled while runtime admission is closed.

---

## WAN Base and Phase 7 runtime admission

`wan_base@1` is intentionally visible as **`on_hold`** and is not selectable
for execution. The local WAN dry run did not complete successfully. Existing
research, project snapshots, and evidence remain readable, but no route or UI
may queue WAN or silently substitute LTX. Leaving hold requires a separately
approved qualification change backed by a successful dry run.

The following gates remain fail-closed:

### WAN-G01 — Exact workflow, model, and node admission

State: blocked on local runtime evidence.

- Version and hash each WAN API workflow and semantic manifest.
- Record exact base model, high/low-noise pair, text encoder, VAE, LoRAs, and
  every required custom-node commit.
- Validate required classes, inputs, and outputs against a hash-pinned
  `/object_info` response from the active ComfyUI runtime.
- Distinguish official ComfyUI reference graphs, recovery evidence, and locally
  authored SineForge adaptations. Never label a reference graph as the missing
  article author's original workflow.
- Reject missing, differently hashed, partially downloaded, or unlicensed
  artifacts before queue or GPU reservation.

Exit evidence: workflow/manifest/model/node/object-info hashes, license records,
an offline compatibility report, and one online preflight from the exact
runtime.

### WAN-G02 — GPU and render-segment qualification

State: blocked on target-workstation benchmarks.

- Benchmark the admitted preview and quality configurations at provider-valid
  frame counts and resolutions.
- Measure cold/warm latency, peak VRAM/RAM/temperature, failure rate, output
  frame count/FPS, and memory release over repeated attempts.
- Exercise I2V, continuation, first/last-frame bridging when admitted, and a
  multi-segment 15-second subscene.
- Keep WAN in the same exclusive GPU workload group as Phase 8 Foley and other
  GPU generation.

Exit evidence: exact hardware/runtime hashes, telemetry, decoded outputs,
promotion decision, and rollback thresholds.

### P7-G01 — Durable video attempt and picture-lock ledger

State: not implemented; current Phase 7 APIs are plan-only.

- Persist append-only `VideoRun`, `RenderSegment`, `VideoAttempt`,
  `ContinuityPacket`, `SelectedClip`, `PictureEdit`, and `PictureLock` records.
- Bind every attempt to immutable workflow/model/runtime/input hashes, exact
  frame rules, seed, prompt, queue ownership, prompt ID, managed outputs, and QA
  evidence.
- Make retry/resume idempotent and prevent a changed EDL or source hash from
  reusing stale picture-lock evidence.
- Preserve existing LTX attempts when a user promotes selected work to WAN.

Exit evidence: additive migration, transaction/state-machine tests, crash
recovery tests, and a reproducible picture-lock manifest.

### P7-G02 — Controlled video worker and output validation

State: not implemented.

- Execute only a persisted approved attempt through the worker-owned queue and
  exclusive GPU lease.
- Accept managed asset IDs, not arbitrary local paths or caller-supplied raw
  workflows.
- Revalidate admission hashes immediately before submission.
- Fully decode every returned clip; verify container, codec, dimensions, FPS,
  frame count, duration, non-black/non-frozen policy, expected output node,
  SHA-256, and prompt provenance.
- Quarantine partial or mismatched outputs and reconcile timeout, cancellation,
  ComfyUI restart, and unknown prompt IDs without duplicate submission.

Exit evidence: worker tests, decoded managed output, attempt lineage, fault
injection, and bounded retry results.

### P7-G03 — Typed FFmpeg assembly and picture-lock materialization

State: blocked; only EDL validation and contract construction exist.

- Run only typed, allowlisted FFmpeg/ffprobe templates.
- Fully decode uploaded video before it may enter a picture lock; an
  `ffprobe`-only ingest result is never sufficient.
- Validate all source clips against the canonical EDL and normalize only when
  stream-copy compatibility or transitions require it.
- Perform at most one required visual mezzanine encode, resolve visual
  transitions before Foley analysis, and emit the analysis proxy plus immutable
  picture-lock manifest.
- Support both persisted stitch choices while producing the same canonical
  frame/PTS timeline before the first Foley request.

Exit evidence: typed-template tests, stream-copy and normalized cases, full
decode/probe/hash reports, equivalent-timeline tests for both stitch stages,
and an immutable picture-lock approval.

---

## LTX Sequence Sheet runtime admission

The LTX Sequence Sheet authoring and dry-run layer is implemented around
`ltx_base@2`, with one visible row per 8–15-second LTX request, strict named
fields, deterministic seeds, dependency validation, `8n+1` frame compilation,
durable database records, and a project-scoped Studio editor.

`ltx_base@2` intentionally remains `qualification_required`. Authoring,
validation, and dry-run compilation are available; runtime submission remains
fail-closed.

The additive durable-record migration was applied to the local CineForge
database on 2026-07-29 at revision `d0e1f2a3b4c5`. The pre-migration database
was preserved at:

```text
storage/backups/cineforge_local.pre-sequence-sheet.20260729-062221.db
```

The backup and migrated database both passed SQLite integrity checks. A live
dry-run against the restarted project API compiled an eight-second row to 193
frames and created zero sequence records, while correctly reporting the
profile and workflow qualification blockers.

### LTX-G01 — Static API workflow and semantic manifest

Priority: P0
State: blocked on an exact API-format export.

- Export the chosen LTX graph from the active ComfyUI installation using
  **Save (API Format)**.
- Do not pass the current visual graph through the generic converter: local
  validation showed that converter can corrupt reroutes, math-expression
  inputs, batch sizes, and output bit depth.
- Store the API JSON immutably with its SHA-256.
- Add manifest bindings for positive and negative prompts, seed, frame count,
  FPS, starting image, output prefix, video output, and required synchronized
  native-audio output.
- Record exact model paths/hashes, custom-node revisions, ComfyUI commit, and
  `/object_info` hash.

Exit evidence: admitted `workflow_api.json`, manifest, immutable hashes,
patched-prompt preview, and live preflight with no unresolved selector.

### LTX-G02 — Workstation qualification

Priority: P0
State: blocked on completed Sulphur artifact and local render evidence.

- Let the Sulphur 2 Base Quants browser download finalize; never move or hash a
  `.crdownload` as though it were complete.
- Verify the final file size and SHA-256 before installation/admission.
- Unload Qwen 3.6 40B from LM Studio before LTX rendering. The last validation
  found only about 452 MiB of VRAM free while `llama-server.exe` held nearly
  the full 24 GiB GPU.
- Complete and fully decode:
  - one eight-second row;
  - one fifteen-second row; and
  - a two-row last-usable-frame continuation.
- Record wall time, peak VRAM/RAM, frame count, FPS, duration, output hash,
  decode/QA evidence, and model/runtime provenance.

Exit evidence: three successful qualification records and an explicit
promotion of `ltx_base@2` to `qualified`.

### LTX-G03 — Dependency worker and continuity materialization

Priority: P1
State: persistence and pure continuity-QA contracts implemented; controlled
renderer, frame extraction, and scheduler ownership remain pending workflow
admission.

- Claim only rows whose dependencies are satisfied.
- Keep the local LTX queue at one video job in flight until benchmark evidence
  permits otherwise.
- Persist the exact patched API prompt before submission.
- Collect the selected managed clip and its synchronized native-audio asset.
- Fully decode and QA a bounded tail window, select the latest usable frame,
  extract it losslessly, and persist a continuity packet.
- Unblock a successor only after its exact managed handoff exists.
- Recover expired leases without regenerating successful ancestors.

Exit evidence: restart and fault-injection tests plus a reproducible two-row
continuation ledger.

### LTX-G04 — Spreadsheet workbook import

Priority: P2
State: CSV and JSON implemented; XLSX and ODS deferred.

The repository currently declares no workbook parser. Add a reviewed,
version-pinned XLSX/ODS parser or a bounded standard-library reader before
enabling those extensions in the Studio file picker. Workbook import must use
the same named-column, type, row-limit, and cell-diagnostic contract as CSV;
formulas, external links, macros, and embedded content must not execute.

Exit evidence: XLSX/ODS fixtures, repeated-cell and shared-string cases, file
size/row bounds, malicious workbook tests, and canonical parity with CSV.

### LTX-G05 — Synchronized native-audio assembly and final mux

Priority: P1
State: deterministic EDL, stream-signature, native-audio sample-edit, and final
mux contracts implemented; media probing/encoding and the materializing worker
remain pending admitted clips.

- Assemble managed selected clips file-by-file.
- Remove a duplicated boundary frame only through an explicit EDL decision.
- Prefer concat-demuxer stream copy when signatures match; use one controlled
  mezzanine encode only when required.
- Require synchronized native audio from every LTX row.
- Apply the same boundary trims, retimes, and transition overlaps to exact
  native-audio sample ranges.
- Mux assembled native audio with the assembled LTX video.
- Never invoke WAN Phase 8 from an LTX sequence.

Exit evidence: full A/V decode, exact frame/PTS/sample manifest, stream-copy and
normalization cases, immutable mux identity, and exact final duration parity.

---

## P8-G01 — Model artifact and license admission

Priority: P0  
State: blocked; no admitted Hunyuan runtime artifact is represented by the
current Phase 8 services.

### Dependencies

- [Tencent HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley)
- Exact selected model variant: XL or XXL
- Exact upstream weight release and configuration
- Legal/product review of the applicable Tencent Hunyuan license
- Managed model registry and approved storage root

### Required implementation

- Register the model source URL, upstream release/revision, variant, byte size,
  SHA-256, expected file layout, and license document/version.
- Record deployment scope, distribution/hosted-service decision, required
  notices, geographic conditions, acceptable-use conditions, and the identity
  and timestamp of the approval.
- Verify every model file against the admitted hashes before worker startup and
  before a first invocation after replacement.
- Treat an absent, partial, differently hashed, or unapproved model as
  `unavailable`, never as `installed` or `ready`.
- Do not auto-download weights from an API read, application startup, health
  check, or job retry.

### Acceptance criteria

- A fixture with one missing or mismatched file fails admission before a GPU
  lease or ComfyUI prompt is acquired.
- A license record without an approval decision fails admission.
- The admitted model evidence names one exact variant and cannot silently
  resolve to another.
- Runtime status distinguishes `registered`, `files_verified`,
  `license_approved`, `runtime_qualified`, and `unavailable`.
- Required notices can be reproduced from stored evidence.

### Evidence required for promotion

- Model manifest and aggregate SHA-256
- Per-file hashes and sizes
- License document hash/version and approval record
- Verification timestamp and verifier version
- Selected variant and configuration hash

---

## P8-G02 — Custom-node and dependency admission

Priority: P0  
State: blocked; the pure Phase 8 package imports no Foley custom node and
therefore proves no node availability.

### Dependencies

- A selected, audited ComfyUI integration; the architecture currently points to
  [if-ai/ComfyUI_HunyuanVideoFoley](https://github.com/if-ai/ComfyUI_HunyuanVideoFoley)
- Exact active ComfyUI commit
- Exact Python, PyTorch, CUDA, and platform environment
- Dependency-lock and custom-node snapshot support

### Required implementation

- Pin the custom-node repository and commit; never admit a floating branch.
- Capture source hash, dependency lock, imported module versions, and a custom
  node snapshot.
- Review installation scripts and dependencies before execution. Application
  startup and job submission must not run installers.
- Qualify the pinned node on the actual Windows/ComfyUI runtime used by
  SineForge.
- Record whether FP8, CPU offload, Torch Compile, model caching, negative
  prompt, silent fallback, and audio-only outputs are supported by the pinned
  revision. Do not infer these capabilities from a different revision.
- Fail closed if imported node code or dependencies differ from the admitted
  snapshot.

### Acceptance criteria

- Changing the custom-node commit or one dependency invalidates runtime
  qualification.
- A missing import, startup exception, or changed node registration reports
  `unavailable` without attempting generation.
- No health/readiness endpoint mutates `custom_nodes`, invokes `pip`, or
  downloads a model.
- The admitted snapshot can be recreated and compared byte-for-byte.

### Evidence required for promotion

- Repository URL and commit
- Source-tree hash
- Dependency lock/SBOM
- ComfyUI, Python, PyTorch, CUDA, driver, and OS versions
- Startup/import log with sanitized paths and no credentials

---

## P8-G03 — Static workflow and `/object_info` compatibility

Priority: P0  
State: blocked; no admitted Hunyuan API-format workflow/manifest is proven by
the Phase 8 planner.

### Dependencies

- P8-G01 and P8-G02
- Static API-format workflow storage
- Semantic workflow manifest validation
- Existing `ObjectInfoCacheService`
- Active ComfyUI `/object_info` snapshot

### Required implementation

- Create a static, hash-pinned Foley-window API workflow and semantic manifest.
- The manifest must identify, at minimum:
  - video input;
  - positive and negative Foley prompts;
  - model/variant selection;
  - seed;
  - guidance and inference steps;
  - feature-extraction batch size;
  - precision/offload controls;
  - enable/silent-fallback controls;
  - lossless audio-only output;
  - status/error output where the node exposes one.
- Capture and hash `/object_info` from the exact active runtime.
- Validate every required class, required/optional input name, input type, and
  output relied on by the manifest.
- Revalidate the fully patched workflow immediately before reservation or
  execution.
- Expire compatibility when the ComfyUI commit, custom-node snapshot, workflow,
  manifest, or `/object_info` hash changes.
- Ensure a silent fallback can keep a graph structurally alive but can never
  mark an attempt successful.

### Acceptance criteria

- Missing class, renamed input, wrong class type, wrong output, or stale
  `/object_info` fails before queue submission.
- Unknown extra workflow nodes or an altered workflow hash fail admission.
- The API workflow contains no arbitrary filesystem path, raw command, or
  downloader.
- Patching only changes manifest-declared runtime parameters.
- Object-info compatibility is tested offline from a captured fixture and
  online against the admitted runtime.

### Evidence required for promotion

- Workflow JSON and SHA-256
- Semantic manifest and SHA-256
- `/object_info` snapshot and SHA-256
- ComfyUI/custom-node snapshot identifiers
- Compatibility result listing every validated class/input/output

---

## P8-G04 — GPU, VRAM, memory-release, and thermal qualification

Priority: P0  
State: blocked; published upstream requirements are planning inputs, not local
benchmark evidence.

### Dependencies

- P8-G01 through P8-G03
- Existing GPU telemetry and benchmark primitives
- Existing exclusive GPU lease service
- Foley workload classification in the same exclusive group as WAN/video and
  voice-preview GPU work
- Fixed target hardware profile

### Required implementation

- Prevent Foley work from overlapping WAN/video generation or voice preview on
  the same GPU.
- Benchmark the admitted XL/XXL configuration using the exact model, workflow,
  node, driver, CUDA, and ComfyUI snapshots.
- Exercise 1-, 8-, and 15-second inputs, including 450 frames at the qualified
  frame rate.
- Measure cold and warm load time, inference time, peak VRAM, peak RAM,
  utilization, temperature, model-release behavior, and failures.
- Qualify baseline precision first. Qualify FP8, offload, Torch Compile, and
  feature-extraction batch sizes as independent configurations rather than
  assuming wrapper claims apply locally.
- Perform repeated load/generate/release cycles and a WAN-to-Foley handoff test.
- Keep the existing promotion ceiling of peak VRAM below 23,000 MiB unless a
  separately reviewed hardware policy changes it.

### Acceptance criteria

- Incomplete telemetry yields `retry`, never `promote`.
- Peak VRAM at or above the configured limit rejects the configuration.
- Any OOM, ComfyUI crash, lease conflict, or unbounded memory growth rejects the
  configuration.
- Repeated jobs release enough VRAM for the next admitted workload.
- A deterministic lower-batch/offload retry policy is recorded; fallback to a
  different model requires a separate user/policy decision.
- Benchmark evidence cannot be reused after any model, workflow, node, runtime,
  driver, or hardware hash changes.

### Evidence required for promotion

- Hardware profile and driver/runtime versions
- Per-case telemetry time series and summary
- Cold/warm and repeated-cycle results
- Peak VRAM/RAM/temperature
- Failure rate and sanitized failure classes
- Promotion-gate result and qualified settings hash

---

## P8-G05 — Controlled Foley execution boundary

Priority: P0  
State: not implemented. Current endpoints only plan windows and derive attempt
metadata.

### Dependencies

- P8-G01 through P8-G04
- Worker-owned queue reservation
- Exclusive GPU lease
- Managed asset identifiers and approved storage
- Controlled ComfyUI submission, progress, history, output, timeout, cancel,
  and recovery adapters

### Required implementation

- Add an internal worker operation that consumes a persisted, approved audio
  attempt. Do not turn the planning endpoints into render endpoints.
- Recheck picture-lock, workflow, model, node, and runtime hashes after lease
  acquisition and immediately before submission.
- Accept managed asset IDs only. Resolve paths inside the worker against
  approved roots; never accept raw local paths or raw prompt graphs.
- Persist the ComfyUI prompt ID, queue ownership, state transitions, heartbeat,
  progress evidence, history response, output metadata, and terminal error.
- Copy/ingest outputs into managed storage, compute hashes, and verify the
  selected output came from the expected prompt and output node.
- Make submission idempotent and define timeout, cancellation, worker-crash,
  ComfyUI-restart, and unknown-prompt reconciliation.

### Acceptance criteria

- No public planning request submits a prompt.
- A stale picture lock, missing approval, failed admission gate, or unavailable
  GPU lease prevents submission.
- Duplicate idempotency keys resolve to one attempt rather than two prompts.
- Losing worker ownership prevents further mutation.
- A prompt ID alone is not success; success requires admitted output evidence
  and per-window QA.
- Retrying one failed audio window never rerenders or invalidates the locked
  picture.

---

## P8-G06 — Generated-audio artifact validation

Priority: P0  
State: partially specified. Numeric PCM QA exists; managed media decode and
provenance QA do not.

### Dependencies

- P8-G05
- Managed audio-asset reader
- Approved probe/decode service
- Exact output-node contract

### Required implementation

- Fully decode the produced audio stem.
- Verify codec/container policy, 48 kHz sample rate, channel layout, finite
  samples, exact or bounded duration, non-silence unless explicitly intended,
  full-scale/clipping policy, and readable metadata.
- Compare decoded sample count with the planned half-open sample range.
- Reject the wrapper's silent fallback as a successful generated stem.
- Record synchronization review evidence for visible actions; automated metrics
  may assist but must not fabricate a human approval.
- Detect and warn on unintended speech-like audio or music where the project
  policy prohibits it.

### Acceptance criteria

- Corrupt, truncated, silent-fallback, wrong-rate, wrong-channel, non-finite,
  clipped, wrong-duration, or wrong-output-node artifacts fail.
- Failure retains the immutable attempt record and never overwrites a previous
  valid candidate.
- Accepted stems retain both source/output hashes and exact frame/PTS/sample
  lineage.

---

## P8-G07 — Durable audio and assembly execution ledger

Priority: P0  
State: not implemented. Deterministic metadata is currently returned to the
caller but is not a durable execution ledger.

### Dependencies

- Approved additive database design and migration
- Managed asset registry
- Audit/event conventions
- Picture-lock identity from Phase 7

### Required records

| Record | Required purpose |
|---|---|
| `AudioRun` | One Phase 8 run bound to one immutable picture-lock hash |
| `AudioWindow` | Exact core/analysis frame, PTS, and sample ranges plus boundary policy |
| `AudioAttempt` | Append-only model invocation, hashes, prompt version, seed, state, metrics, and error |
| `AudioStem` | Managed Foley/dialogue/ambience/music/SFX/master asset and lineage |
| `AudioLock` | Approved stem selection and immutable assembled audio-master hash |
| `AssemblyRun` | Approved mix/master/mux transform manifest and final delivery evidence |

### Required implementation

- Keep planning snapshots separate from the execution ledger.
- Persist append-only attempt history; selecting a candidate must not delete
  rejected attempts.
- Use explicit state machines and transactional ownership.
- Store idempotency keys, model/workflow/runtime hashes, picture-lock hash,
  prompt hashes, seed, input/output asset IDs and hashes, frame/PTS/sample
  ranges, telemetry summary, QA result, timestamps, and sanitized errors.
- Invalidate downstream audio windows, masters, and assembly only when their
  picture/timeline dependency changes.
- Write external artifacts to temporary managed locations and publish them
  atomically only after validation.

### Acceptance criteria

- Every generated byte is attributable to one immutable attempt.
- Every final delivery is reproducible from an immutable assembly manifest.
- A picture-lock hash change prevents reuse of stale windows and masters.
- An audio failure does not modify the Phase 7 picture lock.
- Resume after process or machine restart starts at the first incomplete or
  invalid record, not at the beginning.
- Downgrade/rollback behavior preserves or explicitly archives Phase 8 data.

---

## P8-G08 — Stem assembly, loudness, exact length, and final mux

Priority: P0  
State: not implemented. Named delivery profiles are policy data only.

### Dependencies

- P8-G06 and P8-G07
- Approved, typed FFmpeg templates
- 48 kHz PCM intermediate storage
- Locked Phase 7 video and optional captions

### Required implementation

- Assemble lossless stems on the exact sample timeline.
- Apply boundary behavior from the plan:
  - continuous ambience: reviewed equal-power overlap/crossfade;
  - hard cut: butt join or non-overlapping click guard;
  - visual crossfade: audio transition aligned to picture timing.
- Preserve dialogue, Foley, ambience, music, designed-SFX, and master stems
  separately when those lanes exist.
- Do not independently normalize every Foley window to the final integrated
  target.
- Measure the complete mix, perform approved two-pass loudness processing,
  enforce true peak, and then enforce the exact expected 48 kHz sample count.
- Mux once against the unchanged locked picture; prefer video stream copy when
  admitted compatibility permits it.
- Do not use `-shortest` as a substitute for exact duration enforcement.
- Fully decode the result and verify that video duration/content hash remained
  unchanged apart from the container/mux representation allowed by policy.
- Execute only typed, allowlisted templates. Never store or accept arbitrary
  shell commands.

### Acceptance criteria

- The assembled master has exactly the expected sample count and start offset.
- Boundary tests cover continuous ambience, hard cuts, and visual crossfades.
- The selected delivery profile's loudness and true-peak limits pass from
  measured evidence.
- Final mux has the expected video/audio/caption streams and fully decodes.
- Video is not silently truncated, retimed, or re-rendered by an audio retry.
- Lossless master, delivery file, and assembly manifest each have stored hashes.

---

## P8-G09 — Recovery, soak, promotion, and rollback

Priority: P0  
State: not implemented for Phase 8 runtime.

### Dependencies

- P8-G01 through P8-G08
- Operations runbook
- Feature flags for WAN Phase 8 execution, independent from all LTX runtime
  flags

### Required implementation

- Test crash/restart before submission, during queue wait, during generation,
  during output ingest, during QA, during mastering, and during final mux.
- Reconcile orphaned prompts and expired leases without duplicating an
  invocation.
- Quarantine partial or hash-mismatched outputs.
- Run at least:
  - 1-, 8-, and 15-second Foley cases;
  - a 15-second subscene;
  - a 90-second subscene with multiple windows;
  - 10 or more consecutive windows;
  - WAN-to-Foley GPU handoffs;
  - an uploaded silent-video direct-Phase-8 case;
  - a repeated retry/load/unload soak.
- Exercise disable, rollback, and re-enable with existing audio records.

### Acceptance criteria

- Resume does not repeat completed valid windows.
- No retry rerenders the picture.
- No orphaned active lease or indefinitely running ledger state remains after
  recovery.
- A changed dependency hash automatically closes runtime admission.
- `ltx_base@1` and `ltx_base@2` never invoke Phase 8.
- WAN Phase 8 can be disabled while preserving silent picture locks, attempts,
  stems, and audit history.
- Operations can distinguish planning-ready, runtime-blocked,
  runtime-qualified, running, failed, and delivery-approved states.

---

## Recommended implementation order

1. P8-G01 model/license evidence.
2. P8-G02 pinned custom node and dependency snapshot.
3. P8-G03 static workflow/manifest and exact `/object_info` validation.
4. P8-G04 local GPU qualification and Foley lease classification.
5. P8-G07 durable execution ledger and migration.
6. P8-G05 controlled worker execution against that ledger.
7. P8-G06 managed generated-audio validation.
8. P8-G08 typed assembly/master/mux.
9. P8-G09 soak, recovery, promotion, and rollout.

P8-G07 is listed before the rendering worker deliberately: production
generation must not begin until its durable evidence model exists.

## Minimum evidence bundle for one admitted delivery

An admitted WAN Phase 8 delivery must be able to export a manifest containing:

- picture-lock and EDL hashes;
- exact video frame rate, time base, frame count, and duration;
- every Foley core/analysis frame and PTS range;
- every expected and decoded 48 kHz sample range;
- model files, variant, license, custom-node, workflow, manifest,
  `/object_info`, ComfyUI, and environment hashes;
- hardware profile and benchmark/promotion decision;
- attempt IDs, seeds, prompt hashes, prompt IDs, state transitions, telemetry,
  and QA findings;
- selected audio candidates and all stem hashes;
- mix/master profile, measurements, approved transform-template versions, and
  exact sample-length enforcement result;
- locked video, lossless audio master, caption, final container, and assembly
  manifest hashes;
- approval actor/time and rollback/invalidation lineage.

If any required evidence is missing, the result may be retained as a diagnostic
artifact but must not be labeled runtime-qualified or delivery-approved.
