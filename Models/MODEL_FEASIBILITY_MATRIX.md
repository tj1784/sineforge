# Model Feasibility Matrix

Target: single RTX 5090 Laptop GPU, 24GB VRAM, 192GB RAM. Feasibility below is intentionally conservative. "Feasible" means worth benchmarking locally, not production-approved.

Local model provenance, trigger words, integrity hashes, and `file:///` locations are tracked in [LOCAL_MODEL_RESOURCES.md](LOCAL_MODEL_RESOURCES.md).

## Model Matrix

| Model | Variant | Source | Params | File Size | Text Encoder | VAE | ComfyUI Support | Required Nodes | Quant Options | LoRA Support | 24GB Feasible? | Best Use | Risk |
|---|---|---|---:|---:|---|---|---|---|---|---|---|---|---|
| LTX-Video / LTXV | `ltxv-2b-0.9.8-distilled` | https://huggingface.co/Lightricks/LTX-Video | 2B | ~6.34GB FP16, ~4.46GB FP8 from HF API | T5 XXL family per model card | `AutoencoderKLLTXVideo` | Official `ComfyUI-LTXVideo`; some LTX nodes in ComfyUI core | LTXVideo nodes or official node pack | FP16, FP8, GGUF community variants | LTXV LoRA ecosystem exists; exact LoRA must match base/version | Compatible only at reduced resolution/frame count | Speed prototype, preview | Requires local benchmark for exact 5090 laptop thermal/perf |
| LTX-Video / LTXV | `ltxv-13b-0.9.8-dev` / distilled | https://huggingface.co/Lightricks/LTX-Video | 13B | ~28.58GB FP16, ~15.69GB FP8 | T5 XXL family | `AutoencoderKLLTXVideo` | Official `ComfyUI-LTXVideo` workflows | LTXVideo nodes | FP16, FP8, Q8/GGUF community paths | Official distilled LoRA lineage and community LoRAs | Compatible only with quantization/offload | Balanced/final candidate if benchmarks pass | 24GB borderline; text encoder/VAE can OOM |
| LTX-2 | `ltx-2-19b-dev`, distilled, FP8, FP4 | https://huggingface.co/Lightricks/LTX-2 | 19B | ~43.29GB FP16, ~27.08GB FP8, ~19.99GB FP4, ~7.67GB LoRA | Gemma3 family per official docs | `AutoencoderKLLTX2Video` | Lightricks says built-in LTXVideo nodes plus official repo | Built-in LTXVideo nodes; optional official pack | FP16, FP8, FP4, offload | Official distilled/control/detailer/camera LoRAs referenced | Compatible only with quantization/offload; needs local testing | Experimental high quality | Official 32GB+ signals make 24GB unproven |
| LTX-2.3 | `ltx-2.3-22b-dev`, distilled | https://huggingface.co/Lightricks/LTX-2.3 | 22B | HF tree shows ~46.1GB large weights, ~7.61GB LoRA | Gemma3 family | LTX2 VAE | Same LTXVideo ecosystem | Built-in/official LTX nodes | FP8/FP4 if provided; offload | Official distilled LoRA files | Compatible only with quantization/offload; needs local testing | Research only until benchmarked | 24GB production risk high |
| Wan2.1 | `Wan2.1-T2V-1.3B` | https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B | 1.3B | Comfy repack FP16 ~2.84GB | T5 / UMT5 path in Comfy workflows | `wan_2.1_vae.safetensors` | Native ComfyUI examples | Native Wan nodes | FP16/BF16/FP8 | Wan LoRA ecosystem, exact base match required | Compatible only at reduced resolution/frame count | Fast prototype, motion exploration | Quality below larger variants |
| Wan2.1 | `Wan2.1-T2V-14B` | https://huggingface.co/Wan-AI/Wan2.1-T2V-14B | 14B | Comfy repack ~28.58GB FP16, ~14.29GB FP8 scaled | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` in Comfy path | `wan_2.1_vae.safetensors` | Native ComfyUI examples | Native Wan nodes | FP16/BF16/FP8, GGUF via custom nodes | LoRAs exist; quant compatibility needs test | Compatible only with quantization/offload | Balanced/final candidate | 720p/81 frames may fill VRAM |
| Wan2.1 | `Wan2.1-I2V-14B-480P/720P` | https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-720P | 14B | Comfy repack ~32.79GB FP16, ~16.40GB FP8 scaled | UMT5/T5 | `wan_2.1_vae.safetensors` | Native ComfyUI examples | Native Wan I2V nodes | FP8/GGUF | LoRAs require exact I2V/base validation | Compatible only with quantization/offload | Continuity clips | Image conditioning increases workflow complexity |
| Wan2.2 | `Wan2.2-TI2V-5B` | https://docs.comfy.org/tutorials/video/wan/wan2_2 | 5B | Comfy repack ~10GB FP16 | UMT5 FP8 in Comfy docs | `wan2.2_vae.safetensors` | Native ComfyUI docs/examples | Native Wan2.2 nodes | FP16/FP8, offload | Lightx2v-related acceleration LoRAs listed in docs | Compatible only with quantization/offload | Fast/balanced T2V/I2V experiments | Exact 24GB performance needs local benchmark |
| Wan2.2 | `Wan2.2-T2V-A14B` | https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B | ~14B active, ~27B total experts | Comfy high/low FP8 files ~14.29GB each | UMT5 FP8 | Wan VAE | Native ComfyUI docs/examples | Native Wan2.2 high/low workflow | FP8 scaled; GGUF via custom nodes | Lightx2v 4-step LoRA in Comfy docs; other LoRAs test-required | Compatible only with quantization/offload | Best local final candidate if 24GB benchmark passes | Official CLI high-memory guidance conflicts with 24GB; Comfy FP8 may still work |
| Wan2.2 | `Wan2.2-I2V-A14B` | https://docs.comfy.org/tutorials/video/wan/wan2_2 | ~14B active, ~27B total experts | Comfy high/low FP8 files ~14.29GB each | UMT5 FP8 | Wan VAE | Native ComfyUI docs/examples | Native Wan2.2 I2V workflow | FP8 scaled; GGUF via custom nodes | LoRA compatibility test-required | Compatible only with quantization/offload | I2V continuity/final clips | High VRAM pressure and artifact risk |

## Frame, Duration, Resolution Rules

| Model | Valid Frame Counts | FPS Assumption | Duration Result | VRAM Effect | Notes |
|---|---|---|---|---|---|
| LTXV 0.9.x | Official docs state frames must be `8n + 1`; examples include 161 frames | Examples use 24fps | 161 frames = ~6.7s at 24fps | Longer frames raise latent memory and VAE pressure | Width/height divisible by 32; official card advises under 720x1280 and below 257 frames |
| LTX-2.x | Official docs state frames must be `8n + 1`; examples include 121 frames | Examples use 24fps | 121 frames = ~5.0s | High due 19B/22B models | 24GB should start with FP8/FP4/offload and short clips |
| Wan2.1 1.3B | Comfy workflows expose latent length; common community values include 81 frames | Often 16fps in Comfy workflows | 81 frames = ~5.1s at 16fps | Moderate | Treat exact valid counts as workflow/node-specific; test 49/81/121 |
| Wan2.1 14B | Comfy workflows expose latent length; common 81 frames | Often 16fps | 81 frames = ~5.1s | High at 720p; FP8 recommended | 480p is safer than 720p for 24GB |
| Wan2.2 5B | Official docs describe 5-second workflows; common 81 frames | Often 16fps or 24fps depending template | 81 frames = 3.4s at 24fps or 5.1s at 16fps | Moderate/high | Verify FPS field in exported workflow, not by model family assumption |
| Wan2.2 A14B | Official Comfy examples use high/low noise model pair; common 81 frames | Workflow-specific | Depends on FPS | Very high | Start at 832x480 or 704x1280 only after benchmark |

## Recommended Frame Counts

| Target | Preview Recommendation | Final Recommendation | Evidence / Caveat |
|---|---|---|---|
| 3 seconds | 49 or 57 frames depending workflow FPS and valid-count rule | 73 or 81 if continuity matters | Needs local testing because Comfy nodes differ |
| 5 seconds | 81 frames for Wan-style 16fps workflows; 121 frames for 24fps LTX-2 | 81-121 frames | Source-backed examples; exact FPS must be stored |
| 8 seconds | Avoid initially on 24GB; split into two continuity-linked clips | Only after smaller tests pass | Needs local benchmark |
| 10 seconds | Prefer two 5-second clips with overlap/crossfade/I2V continuity | 161-257 only for LTX if VRAM permits | Compatible only at reduced resolution/frame count |

## Compatibility Conclusions

1. The safest MVP lane is Wan2.1 1.3B and LTXV 2B for fast tests, then Wan2.2 5B or Wan2.1/2.2 14B FP8 after local benchmarks.
2. 14B+ models should never be queued overnight until cold/warm/soak benchmarks show stable peak VRAM, temperature, and restart recovery.
3. LTX-2.3 22B is research-only on 24GB until FP8/FP4/offload workflow passes local tests with a representative 5-second clip.
