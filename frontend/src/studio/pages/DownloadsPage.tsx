type DownloadStatus = 'Installed' | 'Missing' | 'Downloading'

type DownloadModelRow = {
  id: string
  name: string
  version: string
  modelType: string
  baseModel: string
  sourceUrl: string
  modelId: string
  versionId: string
  trainedWords: string
  localPath: string
  sha256: string
  status: DownloadStatus
  note: string
  movedFromDownloads?: boolean
}

type ReferenceRow = {
  id: string
  kind: string
  label: string
  url: string
  disposition: string
}

type IPAdapterRow = {
  id: string
  filename: string
  family: string
  sourceUrl: string
  destination: string
  sha256: string
  status: DownloadStatus
  note: string
}

const downloadRows: DownloadModelRow[] = [
  {
    id: 'masc-krea2-v2026-1',
    name: 'MASC (Krea 2)',
    version: 'V2026.1',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2740540/masc-krea-2?modelVersionId=3082005',
    modelId: '2740540',
    versionId: '3082005',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\male-focused\\(Krea 2) MASC V2026.1.safetensors',
    sha256: 'F9B1088498CD3659820EEE5876839BAFBFD7E517D6408C8F5BD7628683C4094F',
    status: 'Installed',
    note: 'Repeated pasted links were deduped. One hash-verified copy was installed and the duplicate download was archived.',
    movedFromDownloads: true,
  },
  {
    id: 'krea2-nsfw-prompt-adherence',
    name: 'Krea 2 — Enable NSFW prompt adherence',
    version: 'v1.0',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl:
      'https://civitai.red/models/2727829/krea-2-enable-nsfw-prompt-adherence-krea2-nsfw?modelVersionId=3066310',
    modelId: '2727829',
    versionId: '3066310',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\prompting\\Krea-2-Turbo-Projector-Scale-LoRA-Diffusers.safetensors',
    sha256: '9C3EEB6EF85BF1B569183C4B0337D97152E8B1FA2E32DA5A30095380D5DE6E13',
    status: 'Installed',
    note: 'Hash verified and installed from Downloads. Publisher file is intentionally tiny in the Civitai metadata.',
    movedFromDownloads: true,
  },
  {
    id: 'krea2-filterbypass-3vector',
    name: 'Krea2FilterBypass',
    version: '3vector',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2728234/krea2filterbypass?modelVersionId=3067151',
    modelId: '2728234',
    versionId: '3067151',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\prompting\\krea2filterbypass3.safetensors',
    sha256: 'EC5901A2D0B8F4E4E1E7E62FE4567566F0837799F7A413B03A06F72F47934DDA',
    status: 'Installed',
    note: 'Repeated pasted links were deduped. One hash-verified copy was installed and the duplicate download was archived.',
    movedFromDownloads: true,
  },
  {
    id: 'krea2-dicktator',
    name: 'KREA 2 - DickTator - Male Focused',
    version: 'v1.0',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2732041/krea-2-dicktator-male-focused?modelVersionId=3071591',
    modelId: '2732041',
    versionId: '3071591',
    trainedWords: 'erect penis; flaccid penis and testicles hanging between his legs; pointing down',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\male-focused\\KREA2 - DickTatorV1 - Release.safetensors',
    sha256: '4085A0E64C0122893A410D516792B4C65A417D8A6CFE3B4DE2783228D5B0B474',
    status: 'Installed',
    note: 'Hash verified against the Civitai version API and moved from Downloads.',
    movedFromDownloads: true,
  },
  {
    id: 'realism-engine-krea2-v30',
    name: 'Realism Engine Ideogram 4 + Krea 2',
    version: 'Krea2 v3.0',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2688234/realism-engine-ideogram-4-krea-2?modelVersionId=3109006',
    modelId: '2688234',
    versionId: '3109006',
    trainedWords: 'Not specified by selected version',
    localPath: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\realism\realism_engine_krea2_v3.1.safetensors',
    sha256: 'A6712629445A2E91A616568E82BEFA8C8C7518E891A0F7C9918138634B5B54A5',
    status: 'Installed',
    note: 'Active copy was already verified; the repeated matching download was moved to models\\duplicates\\Downloads.',
  },
  {
    id: 'penis-size-slider-krea2-v2',
    name: 'Penis Size Slider — Krea-2 + ZIT',
    version: 'Krea-2_v2',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2687793/penis-size-slider-krea-2-zit?modelVersionId=3154138',
    modelId: '2687793',
    versionId: '3154138',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\male-focused\\penis_size_krea2_v2_loraholic.safetensors',
    sha256: '6157E05063B89E091B1D2E6BFF3ADE235658BB8231EB5B80047B79E5B05CE949',
    status: 'Installed',
    note: 'Distinct v2 artifact from the repeated paste; v1 remains tracked separately in the model audit.',
    movedFromDownloads: true,
  },
  {
    id: 'pornmaster-krea2-shot-size-slider-v1',
    name: 'PornMaster Krea2 Shot Size Slider',
    version: 'V1',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2785002/pornmaster-krea2-shot-size-slider?modelVersionId=3137731',
    modelId: '2785002',
    versionId: '3137731',
    trainedWords:
      'wide-angle, wide shot, long shot, camera pulled back, large field of view; close-up, extreme close-up, tight framing, camera close, small field of view',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\style\\PornMaster_Krea2_Shot_Size_Slider_V1.safetensors',
    sha256: 'A7E55417514A9985D1424F6E9A9A643CF5457C28F3899104464B60804EC9C983',
    status: 'Installed',
    note: 'Repeated pasted links were deduped and the single local copy was hash-verified before placement.',
    movedFromDownloads: true,
  },
  {
    id: 'ultrareal-krea2-klein9b-kr2-v1',
    name: 'UltraReal — Krea2, Klein9b',
    version: 'KR2_V1',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2462105/ultrareal-krea2-klein9b?modelVersionId=3091374',
    modelId: '2462105',
    versionId: '3091374',
    trainedWords: 'high-quality',
    localPath: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\style\\ultra_real_krea2_v1.safetensors',
    sha256: '083EDC5BF8B333DC1859DFD5FF937EAD86F2977A4167E3BAFD0C761AD3B24108',
    status: 'Installed',
    note: 'Hash verified against the Civitai version API and moved from Downloads.',
    movedFromDownloads: true,
  },
  {
    id: 'detailed-perfection-zib',
    name: 'Detailed Perfection style — Perfection zib',
    version: 'Perfection zib v1.0',
    modelType: 'LoRA',
    baseModel: 'ZImageBase',
    sourceUrl:
      'https://civitai.red/models/411088/detailed-perfection-style-hands-feet-face-body-all-in-one-xl-f1d-sd15-pony-illu-zit-zib?modelVersionId=2709983',
    modelId: '411088',
    versionId: '2709983',
    trainedWords:
      'ultra detailed; cinematic; detailed photorealistic cinematic style; detailed skin pore; realistic style',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\zimage\\Hands + Feet + skin perfection style zib v1.safetensors',
    sha256: 'A8104470E3607F2DA326813BBD04C70134EF521951005BDC9FAE704BD80D8124',
    status: 'Installed',
    note: 'Hash verified against the Civitai version API and moved from Downloads.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx-23-gtanimation',
    name: 'LTX 2.3 GTAnimation — 25 frames in 5s',
    version: 'Kijai-umt5-xxl-enc-Wan',
    modelType: 'Checkpoint',
    baseModel: 'Wan Video / LTX 2.3 workflow asset',
    sourceUrl: 'https://civitai.red/models/1295569/ltx-23-gtanimation-or-25-frames-in-5s-12g-vram?modelVersionId=1464054',
    modelId: '1295569',
    versionId: '1464054',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\diffusion_models\\LTX 2.3\\GTAnimation\\ltx23Gtanimation25Frames_kijaiUmt5XxlEncWan.safetensors',
    sha256:
      'C3355D30191F1F066B26D93FBA017AE9809DCE6C627DDA5F6A66EAA651204F68 or 4FA971FAF306CAD919033D5BBE192E571DC08452F800CBF2EC3C73977C01B2CC',
    status: 'Missing',
    note: 'Not found in Downloads or the shared model tree; the version publishes two files with the same filename, so the intended artifact needs manual selection.',
  },
  {
    id: 'sexgod-pinkcherry-ltx23-v15-int8',
    name: 'SexGod PinkCherry LTX 2.3 Uncensored NSFW Checkpoint',
    version: 'v1.5 convrot int8',
    modelType: 'Checkpoint',
    baseModel: 'LTXV 2.3',
    sourceUrl:
      'https://civitai.red/models/2732210/sexgod-pinkcherry-ltx-23-uncensored-nsfw-checkpoint?modelVersionId=3122529',
    modelId: '2732210',
    versionId: '3122529',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\diffusion_models\\LTX 2.3\\PinkCherry\\sexgodPinkcherryLTX23_v15ConvrotInt8.safetensors',
    sha256: 'BAFA3AC499ED54B2E30481C055250F6633221E3F19FCBD3714F5DFD5267635CA',
    status: 'Installed',
    note: 'Duplicate pasted link was deduped. Hash verified and installed from the follow-up Downloads batch.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-vbvr-sulphur2-v4',
    name: 'LTX 2.3 I2V/T2V Video Reasoning LoRA VBVR',
    version: 'v4.0 motion I2V Sulphur 2',
    modelType: 'LoRA',
    baseModel: 'LTXV 2.3',
    sourceUrl: 'https://civitai.red/models/2497207/ltx-23-i2v-t2v-video-reasoning-lora-vbvr?modelVersionId=3025398',
    modelId: '2497207',
    versionId: '3025398',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\VBVR\\LTX2.3_reasoning_Sulphur-2_I2V_V4.safetensors',
    sha256: '1F7C87052D44087E17630B7075D8DFD8205C17CE5E7D3BCBEAE11AF2102C88DB',
    status: 'Installed',
    note: 'Duplicate pasted link was deduped. Active copy is verified; the matching follow-up download was archived as a duplicate.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-vbvr-multistep-v01',
    name: 'LTX 2.3 Multi Step Video Reasoning LoRA VBVR',
    version: 'v0.1 I2V',
    modelType: 'LoRA',
    baseModel: 'LTXV 2.3',
    sourceUrl: 'https://civitai.red/models/2610321/ltx-23-multi-step-video-reasoning-lora-vbvr?modelVersionId=2930993',
    modelId: '2610321',
    versionId: '2930993',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\VBVR\\LTX2.3_Multi_step_video_reasoning_V0.1.safetensors',
    sha256: '3605F3E49E4E243E3DB729EE4F2211BF281FE1345D81888AA519E65A81EA237D',
    status: 'Installed',
    note: 'Hash verified against the Civitai version API and moved from Downloads.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-licon-msr-v2',
    name: 'Licon MSR V2 for LTX 2.3',
    version: 'V2',
    modelType: 'Multiple-Subject Reference LoRA',
    baseModel: 'LTX 2.3 22B',
    sourceUrl: 'https://huggingface.co/LiconStudio/LTX-2.3-Multiple-Subject-Reference',
    modelId: 'LiconStudio/LTX-2.3-Multiple-Subject-Reference',
    versionId: 'LTX-2.3-Licon-MSR-V2.safetensors',
    trainedWords: 'Not applicable; multiple reference images and background are supplied through LiconMSR',
    localPath:
      'C:\\Users\\Blokey\\Documents\\Sineforge\\BlokeyUI\\ComfyUI\\models\\loras\\LTX\\2.3\\Licon\\MSR\\LTX-2.3-Licon-MSR-V2.safetensors',
    sha256: '6F61D3B5C61B160C409B45EBAA72FD7AB9BB38BF3BF7F09EDADDC87762D5FA98',
    status: 'Installed',
    note:
      'Apache-2.0 MSR V2 LoRA installed in the new bundled model library. It improves multi-reference identity, stability, and scene logic.',
  },
  {
    id: 'ltx23-distilled-11-full-checkpoint',
    name: 'LTX 2.3 22B Distilled 1.1',
    version: 'Distilled 1.1 full checkpoint',
    modelType: 'Checkpoint',
    baseModel: 'LTX 2.3 22B',
    sourceUrl: 'https://huggingface.co/Lightricks/LTX-2.3/blob/main/ltx-2.3-22b-distilled-1.1.safetensors',
    modelId: 'Lightricks/LTX-2.3',
    versionId: 'ltx-2.3-22b-distilled-1.1.safetensors',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\Users\\Blokey\\Documents\\Sineforge\\BlokeyUI\\ComfyUI\\models\\checkpoints\\LTX-Video\\ltx-2.3-22b-distilled-1.1.safetensors',
    sha256: 'B33B7FE4BBFE084F484BE4AAF90B0F1D95DCA20D403AC4C0E037EB8C4F0AF7CC',
    status: 'Installed',
    note: 'Official Lightricks full distilled checkpoint required by the MSR V2 workflow. Exact 46,149,345,334-byte file and publisher SHA-256 verified in the new bundled model library.',
  },
  {
    id: 'gemma-3-12b-it-ltx23-bf16',
    name: 'Gemma 3 12B IT — LTX text encoder',
    version: 'ComfyUI BF16 safetensors',
    modelType: 'Text encoder',
    baseModel: 'LTX 2 / LTX 2.3',
    sourceUrl: 'https://huggingface.co/Comfy-Org/ltx-2/blob/main/split_files/text_encoders/gemma_3_12B_it.safetensors',
    modelId: 'Comfy-Org/ltx-2',
    versionId: 'split_files/text_encoders/gemma_3_12B_it.safetensors',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\Users\\Blokey\\Documents\\Sineforge\\BlokeyUI\\ComfyUI\\models\\text_encoders\\gemma_3_12B_it.safetensors',
    sha256: '56EAA964A0D9325D2DC9ECAF7759BFAF0FAC78AE36C789BED6E03E275A3729EC',
    status: 'Installed',
    note: 'Official Comfy-Org Gemma 3 12B encoder required by the publisher workflow. Exact 24,379,468,890-byte file and publisher SHA-256 verified in the new bundled model library.',
  },
  {
    id: 'ltx23-licon-msr-v2-multiscene-workflow',
    name: 'LTX 2.3 MSR V2 — Single Image to Multiple Scenes',
    version: 'Publisher V2 workflow, path-normalized',
    modelType: 'Workflow',
    baseModel: 'LTX 2.3 22B + Licon MSR V2',
    sourceUrl: 'https://www.youtube.com/watch?v=EFm4z0ZF20M',
    modelId: 'LiconStudio/LTX-2.3-Multiple-Subject-Reference',
    versionId: 'LTX-2.3_MSR_sample_workflow_V2.json',
    trainedWords: 'Global prompt plus pipe-delimited temporal scene prompts',
    localPath:
      'C:\\Users\\Blokey\\Documents\\Sineforge\\Workflows\\LTX23\\Licon-MSR-V2\\LTX-2.3_MSR_Single_Image_to_Multiple_Scenes_V2.workflow.json',
    sha256: 'DCC220FA59E70D1D0E4F1B9114136FB5FB459A6636F338972B9B2A5C5F05FBF4',
    status: 'Installed',
    note:
      'Saved in the SineForge workflow library, bundled ComfyUI user workflows, and native API Runner. Model selectors were normalized to the new bundled library; publisher demo references and all six required custom-node packs are installed. Two disconnected publisher test nodes were disabled so the operational graph opens without validation errors.',
  },
  {
    id: 'ltx23-director-distilled-transformer-fp8',
    name: 'LTX 2.3 22B Distilled 1.1 — Transformer-only FP8',
    version: '1.1 FP8 scaled',
    modelType: 'Diffusion model',
    baseModel: 'LTX 2.3',
    sourceUrl:
      'https://huggingface.co/Kijai/LTX2.3_comfy/blob/main/diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors',
    modelId: 'Kijai/LTX2.3_comfy',
    versionId:
      'diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\Users\\Blokey\\Documents\\Sineforge\\BlokeyUI\\ComfyUI\\models\\diffusion_models\\LTX\\2.3\\Director\\ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors',
    sha256: '0A1D7AAC2B338E8EC7E832149F1DCF11C9323272482B1CCA0673D229702370F0',
    status: 'Installed',
    note:
      'Exact 25,226,571,988-byte publisher file downloaded for the LTX Director 2 Distilled workflow and verified after transfer.',
  },
  {
    id: 'gemma-3-12b-it-fp4-mixed-director',
    name: 'Gemma 3 12B IT — FP4 Mixed Director Encoder',
    version: 'Comfy-Org FP4 mixed safetensors',
    modelType: 'Text encoder',
    baseModel: 'LTX 2 / LTX 2.3',
    sourceUrl:
      'https://huggingface.co/Comfy-Org/ltx-2/blob/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors',
    modelId: 'Comfy-Org/ltx-2',
    versionId: 'split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\Users\\Blokey\\Documents\\Sineforge\\BlokeyUI\\ComfyUI\\models\\text_encoders\\LTX\\2.3\\Director\\gemma_3_12B_it_fp4_mixed.safetensors',
    sha256: 'AACA463D11E6D8D2A4BDB0D6299214C15EF78A3F73E0EF8113D5A9D0219B3F6D',
    status: 'Installed',
    note:
      'Exact 9,447,702,218-byte publisher file downloaded for LTX Director 2 and verified after transfer.',
  },
  {
    id: 'ltx23-director-spatial-upscaler-x2-11',
    name: 'LTX 2.3 Spatial Upscaler x2 — Director Copy',
    version: '1.1',
    modelType: 'Latent upscaler',
    baseModel: 'LTX 2.3',
    sourceUrl:
      'https://huggingface.co/Lightricks/LTX-2.3/blob/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors',
    modelId: 'Lightricks/LTX-2.3',
    versionId: 'ltx-2.3-spatial-upscaler-x2-1.1.safetensors',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\Users\\Blokey\\Documents\\Sineforge\\BlokeyUI\\ComfyUI\\models\\latent_upscale_models\\LTX\\2.3\\Director\\ltx-2.3-spatial-upscaler-x2-1.1.safetensors',
    sha256: '5F416311FA8172B65AF67530758964708D29A317B830D689A51143B7F91913ED',
    status: 'Installed',
    note:
      'Exact 995,743,560-byte official Lightricks file installed in the latent-upscale registry used by the Director graph; live selector visibility verified.',
  },
  {
    id: 'ltx23-whatdreamscost-director-2-distilled',
    name: 'LTX Director 2 — Distilled Timeline Workflow',
    version: 'WhatDreamsCost 2.0.5 public workflow',
    modelType: 'Workflow',
    baseModel: 'LTX 2.3 distilled FP8',
    sourceUrl: 'https://www.youtube.com/watch?v=GpsS9YW2MQk',
    modelId: 'WhatDreamsCost/WhatDreamsCost-ComfyUI',
    versionId: 'LTX_Director_2_Workflow_Distilled.json',
    trainedWords: 'Timeline prompts, prompt relay, keyframes, and audio segments',
    localPath:
      'C:\\Users\\Blokey\\Documents\\Sineforge\\Workflows\\LTX23\\WhatDreamsCost-Director-2\\LTX_Director_2_Distilled.workflow.json',
    sha256: '244D3F82876024BAECB45D97D39CD0223A450FA10C2E87E1C63F4FC4B71D6D1A',
    status: 'Installed',
    note:
      'Official public LTX Director 2 Distilled workflow from the author repository. Installed in the SineForge library, bundled ComfyUI, and native API Runner with all three required model files in organized LTX 2.3 Director subfolders. Live validation found all node classes and model selectors with 0 errors and 0 warnings. The Patreon Hotfix attachment is members-only and was not present locally.',
  },
  {
    id: 'ltx23-ic-lora-ingredients-09',
    name: 'LTX 2.3 Ingredients IC-LoRA',
    version: '0.9',
    modelType: 'IC-LoRA',
    baseModel: 'LTX 2.3 22B',
    sourceUrl: 'https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients',
    modelId: 'Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients',
    versionId: 'ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors',
    trainedWords: 'Reference sheet: … / Generated video: …',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\Official\\IC-LoRA\\Ingredients\\ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors',
    sha256: '515E4E139001AC6282357A5B35372E42E98B3AFFD5FCC886A52242ABEED19559',
    status: 'Installed',
    note: 'Official gated Lightricks IC-LoRA. Exact publisher byte size and local SHA-256 verified; visible in the live LTX IC-LoRA loader.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-ic-lora-dubit-lipdub-09',
    name: 'LTX 2.3 DubIt Lip-Sync IC-LoRA',
    version: '0.9',
    modelType: 'IC-LoRA',
    baseModel: 'LTX 2.3 22B',
    sourceUrl: 'https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-DubIt',
    modelId: 'Lightricks/LTX-2.3-22b-IC-LoRA-DubIt',
    versionId: 'ltx-2.3-22b-ic-lora-lipdub-0.9.safetensors',
    trainedWords: 'Not applicable; audio/reference conditioned',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\Official\\IC-LoRA\\DubIt\\ltx-2.3-22b-ic-lora-lipdub-0.9.safetensors',
    sha256: 'FC415B12CB639E78511BC264F85080C2F7B188E334C1D9FADE76B310E2BC419C',
    status: 'Installed',
    note: 'Official gated Lightricks lip-sync IC-LoRA. Exact publisher byte size and local SHA-256 verified; visible in the live LTX IC-LoRA loader.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-ic-lora-pixel-spatial-x2-09',
    name: 'LTX 2.3 Pixel Spatial Upscaler IC-LoRA — 2×',
    version: '0.9',
    modelType: 'IC-LoRA upscaler',
    baseModel: 'LTX 2.3 22B',
    sourceUrl: 'https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Pixel-Spatial-Upscaler',
    modelId: 'Lightricks/LTX-2.3-22b-IC-LoRA-Pixel-Spatial-Upscaler',
    versionId: 'ltx-2.3-22b-ic-lora-pixel-spatial-upscaler-x2-0.9.safetensors',
    trainedWords: 'Not applicable; low-resolution reference-video conditioned',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\Official\\IC-LoRA\\Pixel-Spatial-Upscaler\\ltx-2.3-22b-ic-lora-pixel-spatial-upscaler-x2-0.9.safetensors',
    sha256: '0667334E23AF9FC0AB3FDFF2E059C805AC0D162B1F96F18A462801478027451E',
    status: 'Installed',
    note: 'Official generative 2× video upscaler. Exact publisher byte size and local SHA-256 verified; visible in the live LTX IC-LoRA loader.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-ic-lora-pixel-spatial-x4-09',
    name: 'LTX 2.3 Pixel Spatial Upscaler IC-LoRA — 4×',
    version: '0.9',
    modelType: 'IC-LoRA upscaler',
    baseModel: 'LTX 2.3 22B',
    sourceUrl: 'https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Pixel-Spatial-Upscaler',
    modelId: 'Lightricks/LTX-2.3-22b-IC-LoRA-Pixel-Spatial-Upscaler',
    versionId: 'ltx-2.3-22b-ic-lora-pixel-spatial-upscaler-x4-0.9.safetensors',
    trainedWords: 'Not applicable; low-resolution reference-video conditioned',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\Official\\IC-LoRA\\Pixel-Spatial-Upscaler\\ltx-2.3-22b-ic-lora-pixel-spatial-upscaler-x4-0.9.safetensors',
    sha256: '5B6370C3CC3A9A773F3655A411FD8EA4B47F4237BD2288A35B3291E2A33840F5',
    status: 'Installed',
    note: 'Official generative 4× video upscaler. Exact publisher byte size and local SHA-256 verified; visible in the live LTX IC-LoRA loader.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-ic-lora-hdr-09',
    name: 'LTX 2.3 HDR IC-LoRA',
    version: '0.9',
    modelType: 'IC-LoRA',
    baseModel: 'LTX 2.3 22B',
    sourceUrl: 'https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-HDR',
    modelId: 'Lightricks/LTX-2.3-22b-IC-LoRA-HDR',
    versionId: 'ltx-2.3-22b-ic-lora-hdr-0.9.safetensors',
    trainedWords: 'Not applicable; HDR generation and SDR-to-HDR conversion',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\Official\\IC-LoRA\\HDR\\ltx-2.3-22b-ic-lora-hdr-0.9.safetensors',
    sha256: 'C56BFA0F2E4461A8B2F318F494C61C5BF97F462F2220E31ECE93EA7851CA871E',
    status: 'Installed',
    note: 'Official 16-bit HDR IC-LoRA. Installed with its companion scene embedding; both are visible in the live LTX IC-LoRA loader.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-hdr-scene-embedding',
    name: 'LTX 2.3 HDR Scene Embedding',
    version: 'Companion to HDR 0.9',
    modelType: 'Scene embedding',
    baseModel: 'LTX 2.3 22B HDR IC-LoRA',
    sourceUrl: 'https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-HDR',
    modelId: 'Lightricks/LTX-2.3-22b-IC-LoRA-HDR',
    versionId: 'ltx-2.3-22b-ic-lora-hdr-scene-emb.safetensors',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\Official\\IC-LoRA\\HDR\\ltx-2.3-22b-ic-lora-hdr-scene-emb.safetensors',
    sha256: '78BFFA6049BAE2649A4365EC8769DB88052C21348D643E8FC1CE6D483D994C5B',
    status: 'Installed',
    note: 'Companion HDR scene embedding from the official gated repository. Exact publisher byte size and local SHA-256 verified.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-ic-lora-in-outpainting-09',
    name: 'LTX 2.3 In/Outpainting IC-LoRA',
    version: '0.9',
    modelType: 'IC-LoRA',
    baseModel: 'LTX 2.3 22B',
    sourceUrl: 'https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-In-Outpainting',
    modelId: 'Lightricks/LTX-2.3-22b-IC-LoRA-In-Outpainting',
    versionId: 'ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors',
    trainedWords: 'Not applicable; reference video plus binary mask',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\LTX\\2.3\\Official\\IC-LoRA\\In-Outpainting\\ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors',
    sha256: '73DD0841C0D4F0EB26FB1F017781B841B2752021944AC5ECEFE57917F6DAE6B5',
    status: 'Installed',
    note: 'Official video inpainting/outpainting IC-LoRA. Exact publisher byte size and local SHA-256 verified; visible in the live LTX IC-LoRA loader.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx-23-gtanimation-int4-convrot',
    name: 'LTX 2.3 GTAnimation — INT4 ConvRot',
    version: 'LTXV 2.3高速版 INT4 ConvRot',
    modelType: 'Checkpoint',
    baseModel: 'LTXV 2.3',
    sourceUrl: 'https://civitai.red/models/1295569/ltx-23-gtanimation-or-25-frames-in-5s-12g-vram?modelVersionId=3143864',
    modelId: '1295569',
    versionId: '3143864',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\diffusion_models\\LTX 2.3\\GTAnimation\\ltx23Gtanimation25Frames_ltxv23INT4Convrot.safetensors',
    sha256: 'FA457F3FB702A24CFEFA1167DB5CE11D8C8994023120B560E34D778CFA071D1D',
    status: 'Missing',
    note: 'Newer GTAnimation INT4 ConvRot version is not present locally yet.',
  },
  {
    id: 'ltx23-10eros-v14',
    name: 'LTX2.3 10Eros',
    version: 'v1.4',
    modelType: 'Checkpoint',
    baseModel: 'LTXV 2.3',
    sourceUrl: 'https://civitai.red/models/2447875/ltx23-10eros?modelVersionId=3109610',
    modelId: '2447875',
    versionId: '3109610',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\diffusion_models\\LTX 2.3\\10Eros\\ltx2310eros_v14.safetensors',
    sha256: '54BCB40427FF1A3E54CFA6087DF765B617BEE238D58AA49947C517A727722AD2',
    status: 'Missing',
    note:
      'Operator deleted the previously verified full checkpoint on 2026-07-29. Its provenance and blur-forensics research remain archived in docs.',
  },
  {
    id: 'sulphur-2-base-quants-dev',
    name: 'Sulphur 2 Base Quants',
    version: 'Dev — official FP8 mixed quant',
    modelType: 'Checkpoint',
    baseModel: 'LTXV 2.3',
    sourceUrl: 'https://civitai.red/models/2630742/sulphur-2-base-quants?modelVersionId=2953675',
    modelId: '2630742',
    versionId: '2953675',
    trainedWords: 'None documented (no trigger word)',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\checkpoints\\LTX 2.3\\Sulphur 2\\sulphur2BaseQuants_dev.safetensors',
    sha256: '41C999575859C528FF108022246A5524960A778C18742696971C9B0AADB4F70F',
    status: 'Installed',
    note: 'Hash verified; an organized hardlink alias was added for existing Sulphur workflows.',
    movedFromDownloads: true,
  },
  {
    id: 'rebels-sulphur-2-gguf-workflow',
    name: 'Rebels Sulphur 2 GGUF (LTX-2.3 NSFW Model)',
    version: 'gguf',
    modelType: 'Workflow',
    baseModel: 'LTXV 2.3',
    sourceUrl: 'https://civitai.red/models/2606616/rebels-sulphur-2-gguf-ltx-23-nsfw-model?modelVersionId=2926883',
    modelId: '2606616',
    versionId: '2926883',
    trainedWords: 'None documented (no trigger word)',
    localPath: 'C:\\Users\\Blokey\\Documents\\Sineforge\\Workflows\\Sulphur2\\Sulphur_2_GGUF_LTX23.workflow.json',
    sha256: '3BA0EAB2017B180AC0C76E37E6C8FB9A82132C0D21AD8908BCBF0981EB54E456',
    status: 'Installed',
    note:
      'Workflow JSON was copied into SineForge and ComfyUI user workflows; the original zip archive was moved into Workflows\\Sulphur2.',
    movedFromDownloads: true,
  },
  {
    id: 'sulphur-distil-q6-k-gguf',
    name: 'Sulphur distil Q6_K GGUF',
    version: 'Q6_K transformer GGUF',
    modelType: 'GGUF transformer',
    baseModel: 'LTXV 2.3 / Sulphur 2',
    sourceUrl: 'https://civitai.red/models/2606616/rebels-sulphur-2-gguf-ltx-23-nsfw-model?modelVersionId=2926883',
    modelId: '2606616',
    versionId: '2926883',
    trainedWords: 'None documented (no trigger word)',
    localPath: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\gguf\\sulphur_distil-Q6_K.gguf',
    sha256: 'B3E19985A4283936B179CC00A8542A49D2BD1FE8A0770E6D2A5027CC526EDF59',
    status: 'Installed',
    note: 'Moved from Downloads into the ComfyUI gguf folder and verified in the LTX2_SM_Model GGUF dropdown.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-distilled-transformer-11-q6-k-gguf',
    name: 'LTX 2.3 22B distilled transformer 1.1 GGUF',
    version: '1.1 Q6_K transformer GGUF',
    modelType: 'GGUF transformer',
    baseModel: 'LTX 2.3',
    sourceUrl: 'https://huggingface.co/smthem/LTX-2.3-test-gguf/tree/main',
    modelId: 'smthem/LTX-2.3-test-gguf',
    versionId: 'ltx-2.3-22b-distilled-transformer-1.1-Q6_K.gguf',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\gguf\\ltx-2.3-22b-distilled-transformer-1.1-Q6_K.gguf',
    sha256: '26B760168FBD5431E05F5C974A8D0614D9EF7D907ACC09254F23223200D55201',
    status: 'Installed',
    note: 'Moved from Downloads into the ComfyUI gguf folder and verified in the LTX2_SM_Model GGUF dropdown.',
    movedFromDownloads: true,
  },
  {
    id: 'gemma-3-12b-it-qat-q4-0-gguf',
    name: 'Gemma 3 12B IT QAT Q4_0 GGUF',
    version: 'Q4_0 text encoder GGUF',
    modelType: 'Text encoder GGUF',
    baseModel: 'LTX 2 / LTX 2.3',
    sourceUrl: 'https://huggingface.co/smthem/LTX-2.3-test-gguf/tree/main',
    modelId: 'smthem/LTX-2.3-test-gguf',
    versionId: 'gemma-3-12b-it-qat-Q4_0.gguf',
    trainedWords: 'Not applicable',
    localPath: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\gguf\\gemma-3-12b-it-qat-Q4_0.gguf',
    sha256: '4703E568CC5A9B15F76FE93FFCDE33C05278A5A8565C5DABDC6DE45230C4430F',
    status: 'Installed',
    note: 'Moved from Downloads into the ComfyUI gguf folder and verified in the LTX2_SM_Clip clip dropdown.',
    movedFromDownloads: true,
  },
  {
    id: 'connector-11-safetensors',
    name: 'LTX 2.3 connector-11',
    version: 'connector-11 text-encoder bridge',
    modelType: 'Connector checkpoint',
    baseModel: 'LTX 2.3',
    sourceUrl: 'https://huggingface.co/smthem/LTX-2.3-test-gguf/tree/main',
    modelId: 'smthem/LTX-2.3-test-gguf',
    versionId: 'connector-11.safetensors',
    trainedWords: 'Not applicable',
    localPath: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\checkpoints\\connector-11.safetensors',
    sha256: '696D5B5759CD69FA941F7DD79014A9B894AB503F22ED671D3456AD985E34A718',
    status: 'Installed',
    note: 'Moved from Downloads into the ComfyUI checkpoints folder and verified in the LTX2_SM_Clip connector dropdown.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-distilled-audio-vae-sm',
    name: 'LTX 2.3 22B distilled audio VAE',
    version: 'BF16 audio VAE',
    modelType: 'Audio VAE',
    baseModel: 'LTX 2.3',
    sourceUrl: 'https://huggingface.co/unsloth/LTX-2.3-GGUF/tree/main/vae',
    modelId: 'unsloth/LTX-2.3-GGUF',
    versionId: 'ltx-2.3-22b-distilled_audio_vae.safetensors',
    trainedWords: 'Not applicable',
    localPath: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\vae\\ltx-2.3-22b-distilled_audio_vae.safetensors',
    sha256: '3CD6A6EB8CB28F5ECC12F1F3126952B2A3D2B0B42AD3270E63CEFAFAFE0D9B57',
    status: 'Installed',
    note: 'Moved from Downloads into the ComfyUI vae folder for SM/Unsloth-name workflow compatibility.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-distilled-video-vae-sm',
    name: 'LTX 2.3 22B distilled video VAE',
    version: 'BF16 video VAE',
    modelType: 'Video VAE',
    baseModel: 'LTX 2.3',
    sourceUrl: 'https://huggingface.co/unsloth/LTX-2.3-GGUF/tree/main/vae',
    modelId: 'unsloth/LTX-2.3-GGUF',
    versionId: 'ltx-2.3-22b-distilled_video_vae.safetensors',
    trainedWords: 'Not applicable',
    localPath: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\vae\\ltx-2.3-22b-distilled_video_vae.safetensors',
    sha256: 'E68D6D8F8A42942AC9B862CC315BEB3BC30805A8876C7AD63BA5BF7A2B8E168A',
    status: 'Installed',
    note: 'Moved from Downloads into the ComfyUI vae folder for SM/Unsloth-name workflow compatibility.',
    movedFromDownloads: true,
  },
  {
    id: 'sulphur-lora-rank-768',
    name: 'Sulphur rank-768 distillation LoRA',
    version: 'rank 768',
    modelType: 'Distillation LoRA',
    baseModel: 'LTXV 2.3 / Sulphur 2',
    sourceUrl: 'https://huggingface.co/a4rtx/Sulphur-2-base/blob/main/sulphur_lora_rank_768.safetensors',
    modelId: 'a4rtx/Sulphur-2-base',
    versionId: 'sulphur_lora_rank_768.safetensors',
    trainedWords: 'None documented (no trigger word)',
    localPath: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\sulphur_lora_rank_768.safetensors',
    sha256: 'B7151FC78066457A38153F3F1C899851C667527AA2108E39A7F4BE3E3B5E4F2D',
    status: 'Installed',
    note:
      'Root-level hardlink alias added so the Rebels workflow can resolve the exact basename expected by its LTX2_SM_Model node.',
    movedFromDownloads: true,
  },
  {
    id: 'ltx23-all-in-one-workflow-v40',
    name: 'LTX2.3 All in one — SFW / NSFW workflow package',
    version: 'v4.0',
    modelType: 'Workflow',
    baseModel: 'LTXV 2.3',
    sourceUrl:
      'https://civitai.red/models/2553704/ltx23-all-in-one-sfw-nsfw-ltx-director-id-lora-controlnet-detailer-upscaler-interpolator?modelVersionId=3057263',
    modelId: '2553704',
    versionId: '3057263',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\ComfyUI\\BlokeyUI\\ComfyAPI-Runner\\static_workflows\\ltx23AllInOneSFWNSFWLTXDirectorID_v40.zip',
    sha256: '7DB95FFCE607C7E073A959D52922DF50436E7A9DAEDC7698EA94D04D82747183',
    status: 'Installed',
    note: 'Hash verified and installed into ComfyAPI-Runner static_workflows from the follow-up Downloads batch.',
    movedFromDownloads: true,
  },
  {
    id: 'videoflow-ltx23-all-in-one-v30',
    name: 'VideoFlow — LTX 2.3 All-in-One workflow',
    version: 'LTX 2.3 All-in-One v3.0',
    modelType: 'Workflow',
    baseModel: 'LTXV 2.3',
    sourceUrl:
      'https://civitai.red/models/1815300/videoflow-ltx-23-all-in-one-t2v-i2v-a2v-stable-character-voice-wan-2221-i2v-workflow?modelVersionId=2940161',
    modelId: '1815300',
    versionId: '2940161',
    trainedWords: 'Not applicable',
    localPath:
      'C:\\ComfyUI\\BlokeyUI\\ComfyAPI-Runner\\static_workflows\\videoflowLTX23AllInOneT2VI2VA2V_ltx23AllInOneV30.json',
    sha256: '382D1442FB396CBC10E6C75E09E9D4F8933C6EA006171CB926410A9F6BF60680',
    status: 'Installed',
    note: 'Hash verified and installed into ComfyAPI-Runner static_workflows from the follow-up Downloads batch.',
    movedFromDownloads: true,
  },
  {
    id: 'krea2-aio-nsfw',
    name: 'Krea2 AIO NSFW LoRA',
    version: 'v1.0',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2732306/krea2-aio-nsfw-lora?modelVersionId=3071904',
    modelId: '2732306',
    versionId: '3071904',
    trainedWords: 'HMNSFW',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\general-purpose\\Krea2_HMNSFW_AIO.safetensors',
    sha256: 'C2E4988A775E41FD50BA1CB3A68F3B38C094A819E786AB97693F05ADD331F922',
    status: 'Installed',
    note: 'Already verified in the local model audit table.',
  },
  {
    id: 'male-genitals-perspectives',
    name: 'Male genitals from different perspectives',
    version: 'v1.1',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2753644/male-genitals-from-different-perspectives?modelVersionId=3104903',
    modelId: '2753644',
    versionId: '3104903',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\male-focused\\yng_male_000006000.safetensors',
    sha256: 'F566B18E3EF261EA9F0A3DE14CF6912D63552EE7F9A13DCD0491374014CD7AEF',
    status: 'Installed',
    note: 'Hash verified against the Civitai version API and moved from Downloads.',
    movedFromDownloads: true,
  },
  {
    id: 'phone-photography-2020',
    name: 'Phone Photography (2000-2025)',
    version: '2020_KR2',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2537408/phone-photography-2000-2025?modelVersionId=3111163',
    modelId: '2537408',
    versionId: '3111163',
    trainedWords: 'Publisher trigger starts: “This is a candid photograph taken with a low-end smartphone of”',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\style\\phone_photography_2020_krea2.safetensors',
    sha256: '0F7CA9975CA60AA644BE3EE6E77C441592BABC20058487CE74B7698ABF38EEF7',
    status: 'Installed',
    note: 'Hash verified against the Civitai version API and moved from Downloads.',
    movedFromDownloads: true,
  },
  {
    id: 'krea2-textfusion-refusal-reduction',
    name: 'Krea2 TextFusion Refusal-Reduction LoRA',
    version: 'v1.0',
    modelType: 'LoRA',
    baseModel: 'Krea 2',
    sourceUrl: 'https://civitai.red/models/2775340/krea2-textfusion-refusal-reduction-lora?modelVersionId=3125118',
    modelId: '2775340',
    versionId: '3125118',
    trainedWords: 'Not specified by selected version',
    localPath:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\krea2\\prompting\\Krea2_TextFusion_Refusal_Reduction.safetensors',
    sha256: '84EC722DDAB93F6489C5315BCA25DE5DD1A7B7EC5045A3C4CE2F97F62E54E8E6',
    status: 'Installed',
    note: 'Active copy already existed; matching duplicate from Downloads was moved to models\\duplicates\\Downloads.',
  },
]

const ipAdapterRows: IPAdapterRow[] = [
  {
    id: 'ipadapter-clip-vit-h',
    filename: 'CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors',
    family: 'CLIP vision encoder',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors',
    destination:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\clip_vision\\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors',
    sha256: '64A7EF761BFCCBADBAA3DA77366AAC4185A6C58FA5DE5F589B42A65BCC21F161',
    status: 'Installed',
    note: 'Installed as an exact-name hardlink to the existing clip_vision_h.safetensors file.',
  },
  {
    id: 'ipadapter-clip-vit-bigg',
    filename: 'CLIP-ViT-bigG-14-laion2B-39B-b160k.safetensors',
    family: 'CLIP vision encoder',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors',
    destination:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\clip_vision\\CLIP-ViT-bigG-14-laion2B-39B-b160k.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download started but was canceled after C: reached near-zero free space.',
  },
  {
    id: 'ipadapter-clip-kolors',
    filename: 'clip-vit-large-patch14-336.bin',
    family: 'CLIP vision encoder for Kolors',
    sourceUrl: 'https://huggingface.co/Kwai-Kolors/Kolors-IP-Adapter-Plus/resolve/main/image_encoder/pytorch_model.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\clip_vision\\clip-vit-large-patch14-336.bin',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space; required only for Kolors IPAdapter models.',
  },
  {
    id: 'ipadapter-sd15-basic',
    filename: 'ip-adapter_sd15.safetensors',
    family: 'IPAdapter SD1.5',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter_sd15.safetensors',
    sha256: '289B45F16D043D0BF542E45831F971DCDAABE18B656F11E86D9DFBA7E9EE3369',
    status: 'Installed',
    note: 'Installed in the shared ipadapter folder.',
  },
  {
    id: 'ipadapter-sd15-light-v11',
    filename: 'ip-adapter_sd15_light_v11.bin',
    family: 'IPAdapter SD1.5',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_light_v11.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter_sd15_light_v11.bin',
    sha256: '350B63A57847C163E2E984B01090F85FFE60EAAE20F32B2B2C9E1CCC7DDD972B',
    status: 'Installed',
    note: 'Installed in the shared ipadapter folder.',
  },
  {
    id: 'ipadapter-sd15-plus',
    filename: 'ip-adapter-plus_sd15.safetensors',
    family: 'IPAdapter SD1.5',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sd15.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-plus_sd15.safetensors',
    sha256: 'A1C250BE40455CC61A43DA1201EC3F1EDAEA71214865FB47F57927E06CBE4996',
    status: 'Installed',
    note: 'Installed in the shared ipadapter folder.',
  },
  {
    id: 'ipadapter-sd15-plus-face',
    filename: 'ip-adapter-plus-face_sd15.safetensors',
    family: 'IPAdapter SD1.5 face',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-plus-face_sd15.safetensors',
    sha256: '1C9EDC21AF6F737DC1D6E0E734190E976CFACF802D6B024B77AA3BE922F7569B',
    status: 'Installed',
    note: 'Installed in the shared ipadapter folder.',
  },
  {
    id: 'ipadapter-sd15-full-face',
    filename: 'ip-adapter-full-face_sd15.safetensors',
    family: 'IPAdapter SD1.5 face',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-full-face_sd15.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-full-face_sd15.safetensors',
    sha256: 'F4A17FB643BF876235A45A0E87A49DA2855BE6584B28CA04C62A97AB5FF1C6F3',
    status: 'Installed',
    note: 'Installed in the shared ipadapter folder.',
  },
  {
    id: 'ipadapter-sd15-vit-g',
    filename: 'ip-adapter_sd15_vit-G.safetensors',
    family: 'IPAdapter SD1.5 bigG',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_vit-G.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter_sd15_vit-G.safetensors',
    sha256: 'A26F736AF07BB341A83DFEA23713531D0575760E8ED947C68CB31A4C62D9C90B',
    status: 'Installed',
    note: 'Installed, but runtime use still needs the missing bigG CLIP vision encoder.',
  },
  {
    id: 'ipadapter-sdxl-vit-h',
    filename: 'ip-adapter_sdxl_vit-h.safetensors',
    family: 'IPAdapter SDXL',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl_vit-h.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter_sdxl_vit-h.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download started but was canceled after C: reached near-zero free space.',
  },
  {
    id: 'ipadapter-sdxl-plus-vit-h',
    filename: 'ip-adapter-plus_sdxl_vit-h.safetensors',
    family: 'IPAdapter SDXL',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-plus_sdxl_vit-h.safetensors',
    sha256: '3F5062B8400C94B7159665B21BA5C62ACDCD7682262743D7F2AEFEDEF00E6581',
    status: 'Installed',
    note: 'Installed in the shared ipadapter folder.',
  },
  {
    id: 'ipadapter-sdxl-plus-face-vit-h',
    filename: 'ip-adapter-plus-face_sdxl_vit-h.safetensors',
    family: 'IPAdapter SDXL face',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-plus-face_sdxl_vit-h.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download started but was canceled after C: reached near-zero free space.',
  },
  {
    id: 'ipadapter-sdxl-vit-g',
    filename: 'ip-adapter_sdxl.safetensors',
    family: 'IPAdapter SDXL bigG',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter_sdxl.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space; runtime use also needs the missing bigG CLIP vision encoder.',
  },
  {
    id: 'ipadapter-sd15-light-deprecated',
    filename: 'ip-adapter_sd15_light.safetensors',
    family: 'IPAdapter SD1.5 deprecated',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_light.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter_sd15_light.safetensors',
    sha256: '0747D08DB670535BFA286452A77D93CEBAD5C677B46D038543F9F2DE8690BB26',
    status: 'Installed',
    note: 'Installed for legacy workflows.',
  },
  {
    id: 'ipadapter-faceid-sd15',
    filename: 'ip-adapter-faceid_sd15.bin',
    family: 'FaceID SD1.5',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sd15.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid_sd15.bin',
    sha256: '201344E22E6F55849CF07CA7A6E53D8C3B001327C66CB9710D69FD5DA48A8DA7',
    status: 'Installed',
    note: 'Installed. FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-plusv2-sd15',
    filename: 'ip-adapter-faceid-plusv2_sd15.bin',
    family: 'FaceID SD1.5',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sd15.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid-plusv2_sd15.bin',
    sha256: '26D0D86A1D60D6CC811D3B8862178B461E1EEB651E6FE2B72BA17AA95411E313',
    status: 'Installed',
    note: 'Installed. FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-portrait-v11-sd15',
    filename: 'ip-adapter-faceid-portrait-v11_sd15.bin',
    family: 'FaceID SD1.5',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait-v11_sd15.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid-portrait-v11_sd15.bin',
    sha256: 'A48CB4F89ED18E02C6000F65AA9EFEC452E87EAED4A1BC9FCF4A460C8D0E3BC6',
    status: 'Installed',
    note: 'Installed. FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-sdxl',
    filename: 'ip-adapter-faceid_sdxl.bin',
    family: 'FaceID SDXL',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sdxl.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid_sdxl.bin',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space. FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-plusv2-sdxl',
    filename: 'ip-adapter-faceid-plusv2_sdxl.bin',
    family: 'FaceID SDXL',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid-plusv2_sdxl.bin',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space. FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-portrait-sdxl',
    filename: 'ip-adapter-faceid-portrait_sdxl.bin',
    family: 'FaceID SDXL',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait_sdxl.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid-portrait_sdxl.bin',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space. FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-portrait-sdxl-unnorm',
    filename: 'ip-adapter-faceid-portrait_sdxl_unnorm.bin',
    family: 'FaceID SDXL',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait_sdxl_unnorm.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid-portrait_sdxl_unnorm.bin',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space. FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-plus-sd15-deprecated',
    filename: 'ip-adapter-faceid-plus_sd15.bin',
    family: 'FaceID SD1.5 deprecated',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plus_sd15.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid-plus_sd15.bin',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space. Legacy FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-portrait-sd15-deprecated',
    filename: 'ip-adapter-faceid-portrait_sd15.bin',
    family: 'FaceID SD1.5 deprecated',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait_sd15.bin',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip-adapter-faceid-portrait_sd15.bin',
    sha256: '68570F3C14FE125B00D4ABF416AF33D8B13BB496F4E55AF2EB5D0A6017EE99A4',
    status: 'Installed',
    note: 'Installed for legacy workflows. FaceID workflows also require InsightFace.',
  },
  {
    id: 'ipadapter-faceid-sd15-lora',
    filename: 'ip-adapter-faceid_sd15_lora.safetensors',
    family: 'FaceID LoRA SD1.5',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sd15_lora.safetensors',
    destination:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\IPAdapter-FaceID\\ip-adapter-faceid_sd15_lora.safetensors',
    sha256: '70699F0DBFADD47DE1F81D263CF4C86BD4B7271D841304AF9B340B3A7F38E86A',
    status: 'Installed',
    note: 'Installed in the FaceID LoRA subfolder.',
  },
  {
    id: 'ipadapter-faceid-plusv2-sd15-lora',
    filename: 'ip-adapter-faceid-plusv2_sd15_lora.safetensors',
    family: 'FaceID LoRA SD1.5',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sd15_lora.safetensors',
    destination:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\IPAdapter-FaceID\\ip-adapter-faceid-plusv2_sd15_lora.safetensors',
    sha256: '8ABFF87A15A049F3E0186C2E82C1C8E77783BAF2CFB63F34C412656052EB57B0',
    status: 'Installed',
    note: 'Installed in the FaceID LoRA subfolder.',
  },
  {
    id: 'ipadapter-faceid-sdxl-lora',
    filename: 'ip-adapter-faceid_sdxl_lora.safetensors',
    family: 'FaceID LoRA SDXL',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sdxl_lora.safetensors',
    destination:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\IPAdapter-FaceID\\ip-adapter-faceid_sdxl_lora.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space.',
  },
  {
    id: 'ipadapter-faceid-plusv2-sdxl-lora',
    filename: 'ip-adapter-faceid-plusv2_sdxl_lora.safetensors',
    family: 'FaceID LoRA SDXL',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl_lora.safetensors',
    destination:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\IPAdapter-FaceID\\ip-adapter-faceid-plusv2_sdxl_lora.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space.',
  },
  {
    id: 'ipadapter-faceid-plus-sd15-lora-deprecated',
    filename: 'ip-adapter-faceid-plus_sd15_lora.safetensors',
    family: 'FaceID LoRA SD1.5 deprecated',
    sourceUrl: 'https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plus_sd15_lora.safetensors',
    destination:
      'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\loras\\IPAdapter-FaceID\\ip-adapter-faceid-plus_sd15_lora.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space.',
  },
  {
    id: 'ipadapter-composition-sd15',
    filename: 'ip_plus_composition_sd15.safetensors',
    family: 'Community IPAdapter composition',
    sourceUrl: 'https://huggingface.co/ostris/ip-composition-adapter/resolve/main/ip_plus_composition_sd15.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip_plus_composition_sd15.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space.',
  },
  {
    id: 'ipadapter-composition-sdxl',
    filename: 'ip_plus_composition_sdxl.safetensors',
    family: 'Community IPAdapter composition',
    sourceUrl: 'https://huggingface.co/ostris/ip-composition-adapter/resolve/main/ip_plus_composition_sdxl.safetensors',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\ip_plus_composition_sdxl.safetensors',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space.',
  },
  {
    id: 'ipadapter-kolors-plus',
    filename: 'Kolors-IP-Adapter-Plus.bin',
    family: 'Community IPAdapter Kolors',
    sourceUrl:
      'https://huggingface.co/Kwai-Kolors/Kolors-IP-Adapter-Plus/resolve/main/ip_adapter_plus_general.bin?download=true',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\Kolors-IP-Adapter-Plus.bin',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space; requires the Kolors CLIP vision encoder.',
  },
  {
    id: 'ipadapter-kolors-faceid-plus',
    filename: 'Kolors-IP-Adapter-FaceID-Plus.bin',
    family: 'Community IPAdapter Kolors FaceID',
    sourceUrl:
      'https://huggingface.co/Kwai-Kolors/Kolors-IP-Adapter-FaceID-Plus/resolve/main/ipa-faceid-plus.bin?download=true',
    destination: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\ipadapter\\Kolors-IP-Adapter-FaceID-Plus.bin',
    sha256: 'Pending',
    status: 'Missing',
    note: 'Download blocked by disk space; also requires Kolors CLIP vision and InsightFace antelopev2.',
  },
]

const referenceRows: ReferenceRow[] = [
  {
    id: 'ciaatm-profile',
    kind: 'Creator profile',
    label: 'ciaatm Creator Profile',
    url: 'https://civitai.red/user/ciaatm/images?sort=Newest',
    disposition: 'Research source only; not a model file.',
  },
  {
    id: 'image-136621150',
    kind: 'Image reference',
    label: 'Image 136621150',
    url: 'https://civitai.red/images/136621150',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-136129525',
    kind: 'Image reference',
    label: 'Image 136129525',
    url: 'https://civitai.red/images/136129525',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-129057096',
    kind: 'Image reference',
    label: 'Image 129057096',
    url: 'https://civitai.red/images/129057096',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-126942742',
    kind: 'Image reference',
    label: 'Image 126942742',
    url: 'https://civitai.red/images/126942742',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-125573627',
    kind: 'Image reference',
    label: 'Image 125573627',
    url: 'https://civitai.red/images/125573627',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-120169859',
    kind: 'Image reference',
    label: 'Image 120169859',
    url: 'https://civitai.red/images/120169859',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'chrome-extensions',
    kind: 'Browser helper',
    label: 'Chrome extensions page',
    url: 'chrome://extensions/',
    disposition: 'Local browser page; not a project download.',
  },
  {
    id: 'copytab-urls',
    kind: 'Browser helper',
    label: 'CopyTab URLs — Chrome Web Store',
    url: 'https://chromewebstore.google.com/detail/copytab-urls/lolhdpcjpflggojkdoamneplianpomnl?pli=1',
    disposition: 'Utility reference only; not a model file.',
  },
  {
    id: 'krea2-search',
    kind: 'Search reference',
    label: 'Civitai Krea 2 ComfyUI image search',
    url: 'https://civitai.red/search/images?tools=ComfyUI&sortBy=images_v6&query=gay&baseModel=Krea%202',
    disposition: 'Research source only; individual model rows are pinned above.',
  },
  {
    id: 'ltxv23-search',
    kind: 'Search reference',
    label: 'Civitai LTXV 2.3 collected models search',
    url: 'https://civitai.red/search/models?baseModel=LTXV%202.3&sortBy=models_v9%3Ametrics.collectedCount%3Adesc',
    disposition: 'Research source only; selected model-version rows are pinned above.',
  },
  {
    id: 'video-137771709',
    kind: 'Video reference',
    label: 'Video 137771709 by aferventu807',
    url: 'https://civitai.red/images/137771709',
    disposition: 'Reference only; duplicate appearances were collapsed to this single row.',
  },
  {
    id: 'image-137505602',
    kind: 'Image reference',
    label: 'Image 137505602 by aferventu807',
    url: 'https://civitai.red/images/137505602',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'video-137676271',
    kind: 'Video reference',
    label: 'Video 137676271 by aferventu807',
    url: 'https://civitai.red/images/137676271',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-137580326',
    kind: 'Image reference',
    label: 'Image 137580326 by aferventu807',
    url: 'https://civitai.red/images/137580326',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'video-137462650',
    kind: 'Video reference',
    label: 'Video 137462650 by aferventu807',
    url: 'https://civitai.red/images/137462650',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'video-136465327',
    kind: 'Video reference',
    label: 'Video 136465327 by aferventu807',
    url: 'https://civitai.red/images/136465327',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-136020786',
    kind: 'Image reference',
    label: 'Image 136020786 by aferventu807',
    url: 'https://civitai.red/images/136020786',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-135976432',
    kind: 'Image reference',
    label: 'Image 135976432 by aferventu807',
    url: 'https://civitai.red/images/135976432',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-136078193',
    kind: 'Image reference',
    label: 'Image 136078193 by aferventu807',
    url: 'https://civitai.red/images/136078193',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'video-137599503',
    kind: 'Video reference',
    label: 'Video 137599503 by simonishere',
    url: 'https://civitai.red/images/137599503',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'local-comfyui-temp-pvrpd-00047',
    kind: 'Local image reference',
    label: 'ComfyUI_temp_pvrpd_00047_.png',
    url: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\references\\Downloads\\incoming-20260728-202536\\ComfyUI_temp_pvrpd_00047_.png',
    disposition: 'Moved from Downloads into shared references; not a model weight.',
  },
  {
    id: 'local-wan22-01090',
    kind: 'Local video reference',
    label: 'wan22_01090.mp4',
    url: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\references\\Downloads\\incoming-20260728-202536\\wan22_01090.mp4',
    disposition: 'Moved from Downloads into shared references; not a model weight.',
  },
  {
    id: 'local-wan22-01120',
    kind: 'Local video reference',
    label: 'wan22_01120.mp4',
    url: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\references\\Downloads\\incoming-20260728-202536\\wan22_01120.mp4',
    disposition: 'Moved from Downloads into shared references; not a model weight.',
  },
  {
    id: 'local-wan22-01179',
    kind: 'Local video reference',
    label: 'wan22_01179.mp4',
    url: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\references\\Downloads\\incoming-20260728-202536\\wan22_01179.mp4',
    disposition: 'Moved from Downloads into shared references; not a model weight.',
  },
  {
    id: 'local-krea2-turbo-01243',
    kind: 'Local image reference',
    label: 'Krea2_turbo_01243_.png',
    url: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\references\\Downloads\\incoming-20260728-202536\\Krea2_turbo_01243_.png',
    disposition: 'Moved from Downloads into shared references; not a model weight.',
  },
  {
    id: 'local-mmaudio-00002-audio',
    kind: 'Local audio-video reference',
    label: 'mmaudio_00002-audio.mp4',
    url: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\references\\Downloads\\incoming-20260728-202536\\mmaudio_00002-audio.mp4',
    disposition: 'Moved from Downloads into shared references; not a model weight.',
  },
  {
    id: 'local-construction-cocksuking-k2',
    kind: 'Local image reference',
    label: 'construction cocksuking (03)k2.png',
    url: 'C:\\ComfyUI\\ComfyUI_Shared_Folders\\models\\references\\Downloads\\incoming-20260728-202536\\construction cocksuking (03)k2.png',
    disposition: 'Moved from Downloads into shared references; not a model weight.',
  },
  {
    id: 'video-137374106',
    kind: 'Video reference',
    label: 'Video 137374106 by rogertimes90834',
    url: 'https://civitai.red/images/137374106',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'video-136628924',
    kind: 'Video reference',
    label: 'Video 136628924 by rogertimes90834',
    url: 'https://civitai.red/images/136628924',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-136180377',
    kind: 'Image reference',
    label: 'Image 136180377',
    url: 'https://civitai.red/images/136180377',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-137919815',
    kind: 'Image reference',
    label: 'Image 137919815',
    url: 'https://civitai.red/images/137919815',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-137727501',
    kind: 'Image reference',
    label: 'Image 137727501',
    url: 'https://civitai.red/images/137727501',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-137767225',
    kind: 'Image reference',
    label: 'Image 137767225',
    url: 'https://civitai.red/images/137767225',
    disposition: 'Reference only; no download candidate recorded.',
  },
  {
    id: 'image-137103586',
    kind: 'Image reference',
    label: 'Image 137103586',
    url: 'https://civitai.red/images/137103586',
    disposition: 'Reference only; no download candidate recorded.',
  },
]

function shortHash(value: string): string {
  if (!/^[A-Fa-f0-9]{24,}( or [A-Fa-f0-9]{24,})?$/.test(value)) return value
  if (value.includes(' or ')) {
    return value
      .split(' or ')
      .map((part) => `${part.slice(0, 12)}…`)
      .join(' or ')
  }
  return `${value.slice(0, 12)}…`
}

function referenceLink(row: ReferenceRow) {
  if (!row.url.startsWith('http')) return <code className="mono">{row.url}</code>
  return (
    <a href={row.url} target="_blank" rel="noreferrer">
      Open
    </a>
  )
}

export function DownloadsPage() {
  const installedCount = downloadRows.filter((row) => row.status === 'Installed').length
  const missingCount = downloadRows.filter((row) => row.status === 'Missing').length
  const downloadingCount = downloadRows.filter((row) => row.status === 'Downloading').length
  const movedCount = downloadRows.filter((row) => row.movedFromDownloads).length
  const ipAdapterInstalledCount = ipAdapterRows.filter((row) => row.status === 'Installed').length
  const ipAdapterMissingCount = ipAdapterRows.filter((row) => row.status === 'Missing').length

  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">MODEL DOWNLOAD QUEUE</span>
          <h1>Downloads</h1>
          <p>
            Operator-pinned model links, verified local placement, and source references. This page records download state;
            it does not auto-download, install, or queue ComfyUI jobs.
          </p>
        </div>
      </div>

      <div className="workflow-summary">
        <div>
          <span>Download rows</span>
          <b>{downloadRows.length}</b>
        </div>
        <div>
          <span>Installed / verified</span>
          <b>{installedCount}</b>
        </div>
        <div>
          <span>Moved from Downloads</span>
          <b>{movedCount}</b>
        </div>
        <div>
          <span>Missing</span>
          <b>{missingCount}</b>
        </div>
        <div>
          <span>Downloading</span>
          <b>{downloadingCount}</b>
        </div>
        <p>
          <i /> Exact filenames and SHA-256 values came from the selected Civitai model-version records.
        </p>
      </div>

      <p className="notice warning">
        Sensitive/adult LoRAs are cataloged here as explicit operator-managed assets. Sineforge still requires deliberate
        workflow selection and does not infer prompts, safety settings, or queue behavior from these rows.
      </p>

      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>Model and workflow downloads</h2>
            <p>Rows from the latest Civitai paste, normalized into source, version, hash, and local placement.</p>
          </div>
        </header>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Type / base</th>
                <th>Version IDs</th>
                <th>Trigger words</th>
                <th>Local placement</th>
                <th>SHA-256</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {downloadRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <a href={row.sourceUrl} target="_blank" rel="noreferrer">
                      {row.name}
                    </a>
                    <br />
                    <small>{row.note}</small>
                  </td>
                  <td>
                    <b>{row.modelType}</b>
                    <br />
                    <small>{row.baseModel}</small>
                  </td>
                  <td>
                    <span className="mono">model {row.modelId}</span>
                    <br />
                    <span className="mono">version {row.versionId}</span>
                    <br />
                    <small>{row.version}</small>
                  </td>
                  <td>{row.trainedWords}</td>
                  <td>
                    <code className="mono">{row.localPath}</code>
                  </td>
                  <td>
                    <code className="mono" title={row.sha256}>
                      {shortHash(row.sha256)}
                    </code>
                  </td>
                  <td>
                    <span className="status-pill" data-status={row.status.toLowerCase()}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <header className="panel-head">
          <div>
            <h2>IPAdapter runtime models</h2>
            <p>
              Exact filenames required by ComfyUI IPAdapter Plus unified loaders. Installed {ipAdapterInstalledCount} of{' '}
              {ipAdapterRows.length}; {ipAdapterMissingCount} remain pending because C: ran out of free space during the
              transfer.
            </p>
          </div>
        </header>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Family</th>
                <th>Source</th>
                <th>Local placement</th>
                <th>SHA-256</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {ipAdapterRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <span className="mono">{row.filename}</span>
                    <br />
                    <small>{row.note}</small>
                  </td>
                  <td>{row.family}</td>
                  <td>
                    <a href={row.sourceUrl} target="_blank" rel="noreferrer">
                      Hugging Face
                    </a>
                  </td>
                  <td>
                    <code className="mono">{row.destination}</code>
                  </td>
                  <td>
                    <code className="mono" title={row.sha256}>
                      {shortHash(row.sha256)}
                    </code>
                  </td>
                  <td>
                    <span className="status-pill" data-status={row.status.toLowerCase()}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <header className="panel-head">
          <div>
            <h2>Research references from the same paste</h2>
            <p>Image, creator, search, and browser-helper links are retained without treating them as model weights.</p>
          </div>
        </header>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Reference</th>
                <th>Kind</th>
                <th>Link</th>
                <th>Disposition</th>
              </tr>
            </thead>
            <tbody>
              {referenceRows.map((row) => (
                <tr key={row.id}>
                  <td>{row.label}</td>
                  <td>{row.kind}</td>
                  <td>{referenceLink(row)}</td>
                  <td>{row.disposition}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
