# Spreadsheet2Video Krea2 Eight-Image Workflow Validation

Date: 2026-07-29

Validation target:
`C:\ComfyUI\BlokeyUI\ComfyUI\user\default\workflows\Spreadsheet2Video_ConcatVideoRoom_kra2_8_image_sequence.workflow.json`

## Decision

The supplied file is a structurally valid ComfyUI **visual workflow** for
rendering eight independent LTX image-to-video rows and concatenating their
decoded frames. It is suitable for interactive inspection in ComfyUI.

It is **not admitted as a SineForge static API workflow** and must not be sent
through the current visual-to-API converter. Before headless execution it must
be exported from the active ComfyUI installation in API format, assigned a
workflow manifest with semantic bindings, and pass the local LTX qualification
gate.

It is also not a last-frame continuation workflow. Every row loads its own
Krea2 image, and the final concatenated output does not receive an audio input.

## Structural inspection

| Check | Result |
|---|---|
| JSON parsing | pass |
| Workflow representation | ComfyUI visual graph |
| File size | 153,274 bytes |
| SHA-256 | `6A9967B40733FEF9F5D5EEDC3BEA5C52A71CF8ABD5309D7A4C9AB8EF4317C713` |
| Node count | 125 |
| Link count | 102 |
| Duplicate node IDs | none |
| Duplicate link IDs | none |
| Dangling links | none found |
| Executable class availability | pass against live ComfyUI `/object_info` |
| API-format admission | fail closed; no API-format export or manifest |

The three class names absent from `/object_info` were:

- `Fast Groups Bypasser (rgthree)`
- `GetNode`
- `SetNode`

They are frontend or virtual graph helpers rather than executable ComfyUI
classes. Their absence from `/object_info` is therefore not evidence of a
missing runtime custom node.

Initial automated link inspection reported these apparent mismatches:

```text
IMAGE -> IMAGE,MASK
FLOAT -> INT,FLOAT,BOOLEAN
INT -> FLOAT,INT
```

Those target strings are accepted type unions. They are not broken links.

## Active model and loader selections

The active graph resolves the following selectors in the live ComfyUI
installation:

| Node | Loader | Selection | Live selector result |
|---|---|---|---|
| 329 | `UNETLoader` | `sulphur2BaseQuants_dev.safetensors` | found |
| 184 | `VAELoader` | `LTX23_video_vae_bf16.safetensors` | found |
| 189 | `LatentUpscaleModelLoader` | `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | found |
| 190 | `DualCLIPLoader` | `gemma_3_12B_it_fp8_e4m3fn.safetensors` and `ltx-2.3_text_projection_bf16.safetensors` | found |
| 196 | `VAELoaderKJ` | `LTX23_audio_vae_bf16.safetensors` | found |
| 330 | `VAELoader` | `taeltx2_3.safetensors` | found |

The missing distillation LoRA at node 134, GGUF loaders at nodes 345 and 346,
and Power LoRA Loader at node 301 are bypassed (`mode=4`). They are not active
runtime requirements for this graph state.

Selector availability proves only that ComfyUI can resolve the names. It does
not replace full model hashing, decoding, or a successful 8-second,
15-second, and two-row continuation qualification run.

## Duration calculation

The workflow uses:

- 24 FPS from node 285;
- an eight-second constant from node 291; and
- the frame expression `1 + 8 * (round(a * b) / 8)` from node 287.

At 8 seconds and 24 FPS, the expression produces 193 frames. This satisfies
the LTX `8n+1` frame rule.

```text
8 seconds × 24 fps = 192 frame intervals
192 + the inclusive first frame = 193 encoded frames
```

The runtime-linked frame input overrides the stale `121` value visible in the
`EmptyLTXVLatentVideo` widget snapshot.

Eight rows at 193 frames each produce 1,544 encoded frames:

```text
1,544 / 24 = approximately 64.33 seconds
```

The editorial intent is eight nominal eight-second clips, approximately
64 seconds total—not an exact one-minute delivery.

## Row continuity

The spreadsheet contains eight rows, using:

```text
kra2_00022_.png
kra2_00023_.png
kra2_00024_.png
kra2_00025_.png
kra2_00026_.png
kra2_00027_.png
kra2_00028_.png
kra2_00029_.png
```

All eight images exist in the active ComfyUI input directory, are 2880×1632,
and have distinct SHA-256 values.

The spreadsheet's previous-image output is not connected to the next row.
Instead, each row's image column is connected to `LoadImage`. Consequently:

```text
row 1 -> its own Krea2 image
row 2 -> its own Krea2 image
...
row 8 -> its own Krea2 image
```

This design can work when the eight source images already encode matching
character, wardrobe, location, vehicle, lighting, and camera continuity. It
does not create continuity from the selected last usable frame of the prior
video.

For SineForge `ltx_base@2`, each row must instead declare one of:

- a managed starting asset;
- `previous_last_frame`; or
- an explicit prior-row handoff.

The resolved handoff must be persisted and dependency-gated before the
successor is submitted.

## Audio and final concatenation

In the original eight-image reference workflow, the per-row preview combine
node receives decoded LTX video and audio, but the final long-video combine
node receives the concatenated images without audio.

Expected behavior:

- individual row previews may contain audio; and
- the original eight-image final concatenation is silent.

That original wiring is not the LTX production contract. LTX must use:

```text
row video plus synchronized native LTX audio
  -> frame/sample-exact row aggregation
  -> synchronized LTX A/V assembly
  -> one final mux
```

Phase 8 belongs to the WAN architecture and is not part of the LTX path.

## Required changes before SineForge admission

1. Export the active graph using ComfyUI's **Save (API Format)** path. Do not
   treat the current visual JSON as an API prompt.
2. Store the API JSON as an immutable static template and record its SHA-256.
3. Add a semantic workflow manifest for prompt, negative prompt, seed, frame
   count, FPS, starting image, output prefix, video output, and synchronized
   native-audio output.
4. Decide whether this template is:
   - an independent eight-image montage; or
   - a true dependency-driven continuation workflow.
5. If independent, label it honestly and keep all eight managed image inputs.
6. If continuous, remove spreadsheet-level prequeueing and let SineForge
   submit one row only after the prior row's selected handoff image exists.
7. Require native LTX audio for every row, retain exact sample metadata, and
   keep it connected through the final A/V mux.
8. Run and fully decode:
   - one 8-second row;
   - one 15-second row; and
   - a two-row last-frame continuation.
9. Record model hashes, custom-node revisions, VRAM, wall time, output hashes,
   and probe evidence in the qualification record.

## Final result

The file is correct as an interactive eight-image LTX montage graph with a
nominal eight-second row length. It is not correct as a SineForge
dependency-aware continuation workflow, not yet safe as a static API workflow,
and not configured to carry audio into the final concatenated video.

## 2026-07-29 appended 16-image prompt workflow

The operator later supplied
`C:\Users\Blokey\Downloads\I2V_Prompts_for_Images.xlsx` together with 16 Krea
output images. A separate visual-workflow copy was created at:

```text
C:\ComfyUI\BlokeyUI\ComfyUI\user\default\workflows\Spreadsheet2Video_ConcatVideoRoom_kra2_16_image_prompts.workflow.json
```

This append operation did not modify the validated eight-image source
workflow.

| Evidence | Result |
|---|---|
| Derived workflow SHA-256 | `B5B472F49051B0F00022717F57724A8DA522CB33E8BBA658C85B9517EE762926` |
| Derived workflow size | 179,620 bytes |
| Original workflow SHA-256 after append | `6A9967B40733FEF9F5D5EEDC3BEA5C52A71CF8ABD5309D7A4C9AB8EF4317C713` |
| Graph topology | 125 nodes, 104 links, no duplicate or dangling identifiers |
| Spreadsheet schema | `subworkflow,image,prompt,image_id` |
| Timing | 8 requested seconds, 24 FPS, 193 frames per row |
| Native audio wiring | row decoder → row output → spreadsheet aggregation → final combine |
| ComfyUI submission | not submitted |

The workbook order differs from the order in which the paths were supplied.
Rows were therefore joined by exact `Filename`, not by position:

| Order | Image ID | Filename |
|---:|---|---|
| 1 | `ayeC4` | `kra2_00024_.png` |
| 2 | `aGFvR` | `kra2_00025_.png` |
| 3 | `Q6dpq` | `kra2_00026_.png` |
| 4 | `K9u41` | `kra2_00027_.png` |
| 5 | `lLoZP` | `kra2_00028_.png` |
| 6 | `Ikgci` | `kra2_00029_.png` |
| 7 | `nGDlY` | `kra2_00034_.png` |
| 8 | `KpT4j` | `Krea2_00003_.png` |
| 9 | `O5YDx` | `Krea2_00004_.png` |
| 10 | `RITGi` | `Krea2_00005_.png` |
| 11 | `kbX1D` | `Krea2_00006_.png` |
| 12 | `DUYo4` | `Krea2_Turbo_Group_Portrait_00004_.png` |
| 13 | `AHf7C` | `kra2_00005_.png` |
| 14 | `9MpO9` | `kra2_00021_.png` |
| 15 | `gAmBi` | `kra2_00022_.png` |
| 16 | `ewp7o` | `kra2_00023_.png` |

All 16 output images decode as 24-bit RGB PNGs and are unique within the
selected set. Nine already had byte-identical ComfyUI input copies. The seven
missing input files were copied, never moved, into the ComfyUI input root and
then verified against their output sources by SHA-256:

```text
kra2_00034_.png
Krea2_00003_.png
Krea2_00004_.png
Krea2_00005_.png
Krea2_Turbo_Group_Portrait_00004_.png
kra2_00005_.png
kra2_00021_.png
```

The derived file remains an interactive visual-workflow JSON rather than an
API-format prompt and does not perform dependency-driven last-frame
continuity. Unlike the eight-image source, it now preserves the decoded native
LTX audio through the Spreadsheet2Video row output and connects the aggregated
audio to the final video combine. It must not be admitted to SineForge
execution until an exact API-format export and runtime qualification record
exist.
