# LTX 2.3 MSR V2 — Single Image to Multiple Scenes

This package contains LiconStudio's V2 multiple-subject-reference workflow for
LTX 2.3. The operational editor graph preserves the publisher's node layout
while normalizing model selectors to SineForge's bundled BlokeyUI model tree.

## Library files

- `LTX-2.3_MSR_Single_Image_to_Multiple_Scenes_V2.workflow.json` — ComfyUI
  editor workflow.
- `LTX-2.3_MSR_Single_Image_to_Multiple_Scenes_V2.api.json` — queueable graph
  used by SineForge's native API Runner.
- `LTX-2.3_MSR_Single_Image_to_Multiple_Scenes_V2.manifest.json` — provenance,
  dependency, and semantic-binding manifest.
- `UPSTREAM_README.md` — publisher model card retained for reference.
- `assets/01.jfif`, `assets/02.jfif`, and `assets/03.jfif` — publisher V2
  demonstration references. Replace these with approved production references.

The unmodified publisher workflow is retained under
`storage/downloads/LiconStudio-LTX23-MSR-V2/`.

## Installed models

```text
BlokeyUI\ComfyUI\models\
├── checkpoints\LTX-Video\ltx-2.3-22b-distilled-1.1.safetensors
├── loras\LTX\2.3\Licon\MSR\LTX-2.3-Licon-MSR-V2.safetensors
└── text_encoders\gemma_3_12B_it.safetensors
```

## Installed node packs

- `ComfyUI-Licon-MSR`
- `ComfyUI-LTXVideo`
- `ComfyUI-KJNodes`
- `ComfyUI_essentials`
- `ComfyUI_Comfyroll_CustomNodes`
- `ComfyUI-PromptRelay`

The bundled LTXVideo pack is pinned locally to `kornia>=0.7.1,<0.8` because
its pyramid-blending module imports the pre-0.8 `pad` helper. This workflow
does not use KJNodes' optional Triton VAE node, so the Windows Triton warning
does not affect execution.

## Operation

1. Replace the three active Load Image references with approved character,
   object, or environment references. Two additional reference loaders are
   bypassed by default.
2. Use `global_prompt` to define persistent identities and scene context.
3. Separate temporal scene prompts in `local_prompts` with `|`.
4. Validate in the API Runner before queueing. Start with one short sequence to
   confirm identity preservation, motion, audio, and VRAM behavior.
5. Queue at depth one on the 24 GB GPU.

The native API Runner library record is
`4c088eaa-926a-4aad-875f-f714e30299a6`. Its normalized workflow digest is
`39ff54869b62ff3efb4b64563288b7b8eed8ae24912b213d12414fcd478f4bdf`.
Two disconnected publisher test nodes (`104` and `105`) are disabled in the
operational editor graph; they had no consumers and produced five missing-input
warnings. The corrected graph reopens in bundled ComfyUI without a validation
error banner. No video render was submitted during installation validation.

Source video: <https://www.youtube.com/watch?v=EFm4z0ZF20M>

Publisher repository:
<https://huggingface.co/LiconStudio/LTX-2.3-Multiple-Subject-Reference>

Custom node repository: <https://github.com/liconstudio/ComfyUI-Licon-MSR>
