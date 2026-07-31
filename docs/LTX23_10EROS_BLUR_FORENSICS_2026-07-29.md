# LTX 2.3 10Eros I2V Blur Forensics and Recovery Notes

Date: 2026-07-29

Status: archived research; the local 10Eros checkpoint has been deleted

Evidence video: `C:\Users\Blokey\Downloads\LTX_2.3_10Eros_I2V_00002_.mp4`

## Executive conclusion

The blurry output was not caused by the MP4 encoder. It was created in the
latent-generation path.

The embedded ComfyUI workflow used the development-based 10Eros v1.4
transformer with a distilled `8 + 3`/CFG-1 sampling recipe, but no distillation
adapter was present in the model path. That is the primary configuration
mismatch. It can preserve broad structure in the opening frames, then rapidly
lose high-frequency detail, identity, anatomy, and motion coherence.

The output was made more fragile by:

- generating 201 frames from one starting-image anchor;
- a first pass at only half the final spatial resolution;
- applying several optional LoRAs only to the first stage;
- sending the raw base model to the second stage;
- an unaligned requested height of 720, which LTX silently resolved to 704; and
- a long, highly overloaded prompt asking one eight-second shot to maintain
  several simultaneous interactions and fine anatomical details.

The correct recovery is not “raise the video bitrate.” It is to match the
sampling recipe to the selected model, use aligned dimensions, shorten test
clips, keep a consistent model path through both stages, and establish a
controlled no-LoRA baseline before adding adapters one at a time.

## Evidence captured from the rendered MP4

`ffprobe` reported:

| Property | Value |
|---|---:|
| Codec | H.264 |
| Resolution | 1280 × 704 |
| Frame rate | 25 fps |
| Frames | 201 |
| Duration | 8.04 seconds |
| Video bitrate | approximately 18.49 Mbps |

The file contains both `workflow` and API `prompt` metadata. The embedded
workflow is the authoritative record of what generated this exact video; it is
more reliable than a similarly named JSON file that may have been edited after
rendering.

The bitrate is ample for a 1280 × 704 clip. Encoder starvation does not explain
the progressive softening that was visible in the generated frames.

## Exact generation topology recovered from metadata

The embedded graph used:

- diffusion model:
  `LTX 2.3\10Eros\ltx2310eros_v14.safetensors`;
- Gemma FP8 text encoder and the LTX 2.3 BF16 text projection;
- separate LTX 2.3 BF16 video and audio VAEs;
- spatial upscaler:
  `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`;
- requested canvas: 1280 × 720;
- output canvas: 1280 × 704;
- duration: eight seconds at 25 fps, producing 201 frames;
- first-stage I2V strength: `0.7`;
- second-stage I2V strength: `1.0`;
- first-stage manual sigma schedule:
  `1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0`;
- second-stage manual sigma schedule:
  `0.85, 0.7250, 0.4219, 0.0`;
- CFG: `1.0`;
- first sampler: `euler_ancestral_cfg_pp`;
- second sampler: `euler_cfg_pp`; and
- input preprocessing compression/CRF: `18`.

The first stage generated at one-half of the requested width and height, then
the latent x2 upscaler and a short second pass produced the final resolution.

The embedded graph also applied these optional LoRAs before the first stage:

- LTX 2.3 Crisp Enhance;
- LTX 2.3 multi-step video reasoning;
- DR34ML4Y LTX 2.3; and
- Sulphur-2 I2V reasoning.

The second-stage guider did not receive that same complete adapted model path.
This stage mismatch can change texture, motion behavior, and subject identity
across the upscale boundary.

## Why the model/scheduler mismatch matters

LTX has two materially different inference families:

1. Full/development-model inference uses a normal LTX scheduler, multimodal
   guidance, and typically tens of denoising steps.
2. Distilled inference uses CFG near 1 with a short, predefined sigma sequence.

The recovered workflow used the second family’s short schedule and CFG with a
development-based checkpoint, without a matching distilled adapter. A short
schedule assumes the model or an attached adapter has learned to cover much
larger denoising intervals. Without that training, the sampler can produce
coarse early structure but lacks enough effective refinement to preserve small
features through time and through the second pass.

The official LTX repository distinguishes its normal two-stage pipelines from
its distilled pipeline and lists a distilled LoRA as a requirement for the
normal two-stage implementation. See:

- [Lightricks LTX-2 repository](https://github.com/Lightricks/LTX-2)
- [LTX pipelines documentation](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-pipelines/README.md)
- [ComfyUI LTX 2.3 workflow guide](https://docs.comfy.org/tutorials/video/ltx/ltx-2-3)

## Progressive detail-loss measurements

The forensic review measured a strong decline in frame detail over the clip.
The exact metric is useful as a relative trend rather than a universal
perceptual-quality score:

| Time | Relative detail metric |
|---:|---:|
| 0 s | 100 |
| 1 s | 71 |
| 2 s | 54 |
| 3 s | 28 |
| 4 s | 12 |
| 5 s | 4.4 |
| 6 s | 3.7 |
| 8 s | 3.8 |

That temporal collapse is consistent with a generation/sampling failure. A
codec problem would more typically create blocking, ringing, banding, or
roughly uniform texture loss across the clip rather than this steep
frame-by-frame decline from the reference anchor.

## Secondary contributors

### One anchor across eight seconds

The first image constrains frame zero most strongly. With 201 output frames and
no later keyframe, identity and spatial relationships have a long interval in
which to drift. For troubleshooting, four or five seconds is a better unit.
Long scenes should be built as continuations or multiple subscenes.

### First-stage spatial budget

The graph requested 1280 × 720 but generated the initial latent at approximately
640 × 352 before the x2 pass. Fine facial, hand, skin, hair, and interaction
details that never become coherent in that first latent cannot be reliably
reconstructed by the upscaler.

### Unaligned height

The requested 720 height did not survive the model’s spatial alignment rules;
the encoded result is 704 pixels high. Use explicit aligned dimensions such as
1280 × 704, 1600 × 896, or 1920 × 1088 instead of relying on silent flooring.
The official two-stage LTX path validates its target dimensions rather than
leaving this implicit.

### Too many variables in the first test

Four LoRAs, a complex prompt, a random first-stage seed, a long duration, and a
model/scheduler mismatch were changed or active simultaneously. That makes a
useful A/B diagnosis impossible. The no-LoRA baseline should establish that the
checkpoint, sampler, resolution, and conditioning are sound before optional
adapters are introduced.

### Prompt density

LTX benefits from chronological shot descriptions. A single shot that requests
many independently moving subjects, simultaneous fine contact actions, complex
fluid behavior, exact anatomy, identity preservation, and cinematic camera
behavior consumes a large portion of the model’s temporal and spatial
attention. Split independent actions into separate shots or describe one clear
sequence of events.

## Recovery recipes

### Full-quality development-model recipe

Use this when the selected checkpoint is a full/development model:

- normal LTX scheduler;
- approximately 20–30 steps as a first controlled baseline;
- video CFG around `3.0`;
- a compatible distilled LoRA only where the official two-stage path expects
  it;
- first-stage I2V strength `0.8`, then test `0.85` or `0.9` for identity;
- second-stage I2V strength `1.0`;
- 97 or 121 frames at 24 fps;
- dimensions aligned to the pipeline’s required multiple;
- x2 spatial upscaler v1.1;
- CRF `18`;
- fixed seed; and
- no optional content/style LoRAs for the first test.

### Fast distilled recipe

Use this only when the selected distilled model or attached distillation adapter
matches the short schedule:

- CFG `1.0`;
- official short sigma schedules;
- approximately eight first-stage denoising intervals and three or four
  second-stage intervals;
- adapter/model present on every branch that relies on distilled behavior; and
- the same short-duration, aligned-resolution, fixed-seed test discipline.

Do not use the `8 + 3` recipe merely because it is faster. It is a model
compatibility decision.

## Controlled validation sequence

1. Use one source image with sharp eyes, hair, skin texture, and clear hands.
2. Use 97 frames at 24 fps and an aligned final resolution.
3. Fix both seeds.
4. Disable every optional content/style LoRA.
5. Run the full-model recipe with a concise, chronological prompt.
6. Inspect frame 0, 25%, 50%, 75%, and the final frame at 100% zoom.
7. If the baseline is stable, add one LoRA at a conservative strength.
8. Re-run with the identical seed and settings.
9. Repeat one variable at a time.
10. Extend to 121 frames only after the shorter baseline remains coherent.

## Archival disposition

The 10Eros checkpoint is no longer present under
`C:\ComfyUI\ComfyUI_Shared_Folders\models`. This document preserves the
diagnosis so the failure does not need to be rediscovered and so its most
important lesson carries into Sulphur 2:

> The scheduler, CFG, sigma sequence, model type, and distillation adapter must
> be treated as one inference configuration. Mixing pieces from different
> configurations can produce valid-looking early frames and still collapse
> later in the clip.
