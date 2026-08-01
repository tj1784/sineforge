# LTX Director 2 — distilled workflow

This package installs the official public `LTX_Director_2_Workflow_Distilled.json`
from WhatDreamsCost's ComfyUI node repository for the MDMZ tutorial
“LTX2.3 Director: Control EVERYTHING”. The operational copy is renamed
`LTX_Director_2_Distilled.workflow.json` and its three model selectors are
normalized to the organized bundled model library.

## Installed copies

- SineForge library: `Workflows/LTX23/WhatDreamsCost-Director-2/`
- ComfyUI editor library:
  `BlokeyUI/ComfyUI/user/default/workflows/LTX_Director_2_Distilled.workflow.json`
- SineForge native API Runner: registered after live ComfyUI conversion and
  validation; its record ID is recorded in the package manifest.

## Model layout

```text
BlokeyUI/ComfyUI/models/
├── diffusion_models/LTX/2.3/Director/
│   └── ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors
├── text_encoders/LTX/2.3/Director/
│   └── gemma_3_12B_it_fp4_mixed.safetensors
└── latent_upscale_models/LTX/2.3/Director/
    └── ltx-2.3-spatial-upscaler-x2-1.1.safetensors
```

The workflow also uses the already-installed LTX 2.3 text projection, video
VAE, audio VAE, and TAELTX preview VAE.

## Required custom nodes

- `WhatDreamsCost-ComfyUI` (LTX Director)
- `ComfyUI-LTXVideo`
- `ComfyUI-KJNodes`

The installed WhatDreamsCost repository and its two upstream companions were
checked against their remote default branches before admission.

## How to use it

1. Open `LTX_Director_2_Distilled.workflow.json` in the bundled ComfyUI.
2. Use the large **LTX Director** timeline node to add image, text, video, and
   audio segments. Prompt relay controls the action across shot boundaries.
3. Keep the first validation/run at queue depth one. This graph loads a roughly
   25 GB FP8 transformer plus Gemma, so close games and other GPU-heavy apps.
4. Validate the workflow before queueing. A validation does not render.

## Source note

The tutorial's Patreon guide advertises an attachment named
`LTX_Director_2_Workflow_Hotfix.json`, but that attachment is members-only and
was not present locally. This package therefore uses the current public
Distilled Director 2 workflow published by the same author in the official
GitHub repository. No paywall was bypassed.

Sources:

- Video: <https://www.youtube.com/watch?v=GpsS9YW2MQk>
- Node repository: <https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI>
- Members-only guide: <https://www.patreon.com/posts/ltx2-3-director-160709967>
