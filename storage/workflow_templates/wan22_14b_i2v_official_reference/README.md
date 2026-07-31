# Official WAN 2.2 14B I2V Reference

`workflow_ui_reference.json` is an exact official Comfy-Org UI workflow
reference. It was present in the supplied recovery archive and independently
matched the official file pinned in `wan22_reference_catalog.json`.

It is not the article author's original workflow, not API format, not runtime
qualified, and not enabled.

## Local model-path derivative

`workflow_ui_local_paths.json` is the operator-facing derivative. It preserves
the official graph and changes only four model-selector widget values:

- WAN 2.2 I2V-A14B high-noise diffusion model;
- WAN 2.2 I2V-A14B low-noise diffusion model;
- installed LightX2V rank-64 FP16 high-noise LoRA; and
- installed LightX2V rank-64 FP16 low-noise LoRA.

The text encoder and VAE already live at the root of their respective ComfyUI
model categories, so their correct selector values remain:

```text
umt5_xxl_fp8_e4m3fn_scaled.safetensors
wan_2.1_vae.safetensors
```

The two LightX2V LoRAs are installed and hash-verified. The two FP8 diffusion
models are not currently installed; their selectors point to the intended
relative destination:

```text
WAN\2.2\I2V-A14B\wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors
WAN\2.2\I2V-A14B\wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors
```

Do not replace the hash-pinned `workflow_ui_reference.json` with the derivative.
