# Sulphur 2 FP8 Quant: Local ComfyUI I2V Workflow Guide

Date: 2026-07-29

Workflow:
`Workflows/Sulphur2/Sulphur2_FP8_Dev_I2V_HQ_5s.json`

Source workflow:
`C:\Users\Blokey\Downloads\ltx23_i2v%20base.json`

## Result

The supplied JSON is not an arbitrary third-party graph. Its SHA-256 is
`571C572D7D377A4C4C102331731AC93862E60CB4B53FD121D554E75ADEEAFB08`,
and it is byte-for-byte identical to SulphurAI’s published
[`ltx23_i2v base.json`](https://huggingface.co/SulphurAI/Sulphur-2-base/blob/main/workflows/ltx23_i2v%20base.json).

The tuned workflow preserves the creator’s two-stage visual graph while fixing
the full-checkpoint wiring, local model selections, missing node types, and
quality-sensitive defaults.

## Exact quant identity

The user’s active Civitai download and the creator’s Hugging Face FP8-mixed file
are the same checkpoint under different filenames.

| Property | Value |
|---|---|
| Civitai filename | `sulphur2BaseQuants_dev.safetensors` |
| Hugging Face filename | `sulphur_dev_fp8mixed.safetensors` |
| Civitai model/version | `2630742` / `2953675` |
| Expected size | `29,161,842,846` bytes |
| Expected SHA-256 | `41C999575859C528FF108022246A5524960A778C18742696971C9B0AADB4F70F` |
| Format | full SafeTensor checkpoint |
| Precision | FP8 mixed / Comfy FP8 E4M3 |

Primary sources:

- [SulphurAI/Sulphur-2-base model card](https://huggingface.co/SulphurAI/Sulphur-2-base)
- [Official Sulphur 2 FP8 quant](https://civitai.red/models/2630742/sulphur-2-base-quants?modelVersionId=2953675)
- [Sulphur 2 repository files](https://huggingface.co/SulphurAI/Sulphur-2-base/tree/main)

The partial SafeTensor header was inspected locally. It contains the LTX 2.3
diffusion model, video VAE, audio VAE, vocoder, bandwidth-extension components,
and text-projection tensors. It is a full checkpoint, not a transformer-only
UNET, GGUF, or prompt-enhancer model.

Consequently, the same completed filename belongs in all three creator-workflow
selectors:

1. `CheckpointLoaderSimple`;
2. `LTXVAudioVAELoader`; and
3. the checkpoint field of `LTXAVTextEncoderLoader`.

## Correct local placement

After Chrome completes the download and removes the `.crdownload` suffix, the
verified file belongs at:

```text
C:\ComfyUI\ComfyUI_Shared_Folders\models\checkpoints\
  LTX 2.3\Sulphur 2\sulphur2BaseQuants_dev.safetensors
```

The workflow’s relative selection is:

```text
LTX 2.3\Sulphur 2\sulphur2BaseQuants_dev.safetensors
```

Do not rename or move the active `.crdownload`. Wait for Chrome to finalize it,
verify the byte count and SHA-256, then move the completed SafeTensor.

## Creator-required distillation adapter

SulphurAI recommends a development checkpoint—BF16 or FP8 mixed—plus the
provided distillation adapter. The exact adapter is:

```text
ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors
```

It is installed locally at:

```text
C:\ComfyUI\ComfyUI_Shared_Folders\models\loras\LTX\2.3\
  Sulphur\distill_loras\
  ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors
```

Local SHA-256:

```text
E970F64A2CE5469491FB1714A3FA72C8B606FA82AFFFF0531E836DBC91D31F34
```

Source:
[creator-provided cond-safe distillation adapter](https://huggingface.co/SulphurAI/Sulphur-2-base/tree/main/distill_loras).

The tuned graph applies it at:

- `0.25` on the 30-step first stage; and
- `0.50` on the short high-resolution refinement stage.

Those strengths follow the current LTX two-stage HQ pattern. SulphurAI does not
publish a controlled comparison proving one unique optimum, so they should be
treated as a strong baseline and adjusted through fixed-seed A/B tests.

## Do not double-apply Sulphur

SulphurAI explicitly warns that the published workflows still contain the old
`sulphur_final.safetensors` LoRA. Use either:

- a stock LTX checkpoint plus the Sulphur LoRA; or
- the full Sulphur checkpoint.

Never use both in the same path.

Because this workflow selects the full Sulphur FP8 checkpoint, the tuned copy
removes both active `sulphur_final` nodes. It also removes disconnected legacy
distillation/sigma leftovers so ComfyUI does not report missing files that have
no role in generation.

## Prompt enhancer is a different model

The repository’s Qwen/GGUF files:

```text
prompt_enhancer/sulphur_prompt_enhancer_model-q8_0.gguf
prompt_enhancer/mmproj-BF16.gguf
```

are a separate prompt enhancer intended for a local language-model runtime such
as LM Studio. They are not the Sulphur video diffusion checkpoint and should
not be selected in the ComfyUI checkpoint loader.

The creator documents no system prompt for the enhancer: send the scene text,
and optionally an image, directly.

## Trigger word

No Sulphur 2 trigger word is documented on the creator’s model card or official
quant version. The workflow therefore does not invent or inject one.

## Local support models selected by the tuned graph

| Purpose | Local workflow selection |
|---|---|
| Gemma text encoder | `gemma_3_12B_it_fp8_e4m3fn.safetensors` |
| Preview VAE | `taeltx2_3.safetensors` |
| Spatial latent upscaler | `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` |
| Cond-safe adapter | `LTX\2.3\Sulphur\distill_loras\ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors` |

All four selections were verified against the live ComfyUI model registry at
`127.0.0.1:8888`.

## Why the creator graph was changed

The creator’s base graph shipped with provisional or unavailable selections:

| Original | Tuned |
|---|---|
| stock `ltx-2.3-22b-dev-fp8.safetensors` in three loaders | full Sulphur FP8 quant in all three |
| two active `sulphur_final` LoRAs at `1.0` | removed |
| missing FP4 Gemma | installed FP8 Gemma |
| old x2 upscaler v1.0 | installed x2 upscaler v1.1 |
| missing `ResizeImageResolution` custom node | core `ImageScaleToTotalPixels` |
| missing `ImageScaleDownBy` custom node | core `ImageScaleBy` |
| nearest-neighbor input resize | Lanczos |
| unbounded/custom target alignment | 1.0 MP with 64-pixel steps |
| preprocessing CRF `38` | CRF `18` |
| 241 frames at 24 fps | 121 frames at 24 fps |
| 50 first-stage steps, CFG `3.6` | 30 steps, CFG `3.0` |
| random first-stage seed | fixed seed |
| missing bundled start image | installed `example.png` placeholder |
| output prefix says T2V | `video/Sulphur2_I2V_HQ` |

The current LTX repository describes two-stage generation as its recommended
production-quality path, requires a spatial upscaler and distillation adapter,
and distinguishes it from a fully distilled `8 + 3` pipeline. See:

- [LTX-2 repository and required models](https://github.com/Lightricks/LTX-2)
- [LTX two-stage pipeline documentation](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-pipelines/README.md)
- [Official LTX image-to-video guide](https://docs.ltx.io/open-source-model/usage-guides/image-to-video)
- [ComfyUI LTX 2.3 examples](https://docs.comfy.org/tutorials/video/ltx/ltx-2-3)

## Tuned baseline

| Setting | Value |
|---|---:|
| Final target | approximately 1.0 MP, aligned in 64-pixel steps |
| 16:9 example | approximately 1344 × 768 |
| Stage-one reference scale | 0.5× Lanczos |
| Frames | 121 |
| FPS | 24 |
| Duration | 5 seconds |
| Stage-one steps | 30 |
| Stage-one CFG | 3.0 |
| Stage-one distill strength | 0.25 |
| Stage-two distill strength | 0.50 |
| Stage-one I2V strength | 0.80 |
| Stage-two I2V strength | 1.00 |
| Preprocess compression/CRF | 18 |
| Stage-one seed behavior | fixed |

Five seconds is a diagnostic and production subscene baseline, not a hard
maximum. Once identity and motion are stable, longer shots can be tested or
assembled as continuations.

## Live graph validation

The tuned file is a regular ComfyUI visual workflow. An independent validation
against the live ComfyUI instance confirmed:

- 49 nodes and 68 links;
- no duplicate IDs, dangling links, endpoint mismatches, or datatype
  mismatches;
- every executable node class is installed;
- Gemma FP8, the cond-safe adapter, the x2 v1.1 upscaler, the preview VAE, and
  the placeholder image are all selectable; and
- a compiled prompt reached ComfyUI's `/prompt` validator with exactly three
  errors, all for the same not-yet-installed Sulphur checkpoint in the model,
  audio-VAE, and text-projection loaders. No other workflow error was returned.

The generator script recreates the checked-in graph exactly. The tuned workflow
SHA-256 is:

```text
D11C0A394E61609320A6174506C5F3A3D9F44A2E8706AA47FDB20DFFB1892130
```

Load this JSON directly in ComfyUI. The older visual-to-API converter at
`C:\ComfyUI\BlokeyUI\Cinematic-Physique-Video\FluxAPI\comfy_api.py` does not
currently preserve this graph correctly: it drops reroute/math values and
misreads several integer widgets as batch size or video bit depth. For headless
execution, export a proper API-format prompt from ComfyUI or repair and
revalidate that converter first.

## VRAM requirement on this machine

During validation, LM Studio's Qwen 3.6 40B server occupied approximately
24,011 of 24,463 MiB of VRAM. The approximately 29.16 GB Sulphur FP8 checkpoint
must use ComfyUI smart CPU offload on this 24 GB GPU; the machine's system RAM is
ample, but roughly 452 MiB of free VRAM is not enough to begin loading it.

Unload Qwen 40B in LM Studio before queuing Sulphur. Confirm that its
`llama-server.exe` process has released VRAM; closing only the LM Studio window
may leave the model server running.

## Before the first queue

1. Wait for the Sulphur checkpoint download to finish.
2. Verify its exact byte count and SHA-256.
3. Move it to the checkpoint path documented above.
4. Refresh the ComfyUI model list or restart ComfyUI.
5. Unload Qwen 40B from LM Studio and confirm GPU memory was released.
6. Open `Sulphur2_FP8_Dev_I2V_HQ_5s.json` directly in ComfyUI.
7. Replace the `example.png` placeholder with the intended start image.
8. Replace the positive-prompt template with one concise, chronological shot.
9. Keep the seed and optional-LoRA set fixed for the first comparison.

## Reproducible workflow generation

The derived workflow can be recreated from the audited creator JSON with:

```powershell
python .\scripts\tune_sulphur2_i2v_workflow.py `
  'C:\Users\Blokey\Downloads\ltx23_i2v%20base.json' `
  '.\Workflows\Sulphur2\Sulphur2_FP8_Dev_I2V_HQ_5s.json'
```

The script refuses to transform an unaudited source hash and validates node
IDs, link endpoints, input/output link metadata, required node types, and the
absence of obsolete model/node references.
