type DownloadStatus = 'Installed' | 'Missing'

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
    status: 'Installed',
    note: 'Already verified locally. This row pins the full checkpoint artifact, not the smaller same-name auxiliary file.',
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
  const movedCount = downloadRows.filter((row) => row.movedFromDownloads).length

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
