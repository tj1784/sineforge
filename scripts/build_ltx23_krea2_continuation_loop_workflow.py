"""Build the read-only Krea 2 -> LTX-2.3 continuation-loop workflow.

The image-generation settings are taken from the repository library's existing
Krea 2 text-to-image workflow.  The continuation workflow adds only:

* SineForge's strict selectable local-GGUF continuation planner;
* 16-bit PNG save/pass-through boundaries;
* an FFV1 + FLAC lossless master;
* final-frame extraction before any delivery encoding; and
* a visible loop count where 1+ is exact and 0 runs until interrupted;
* the installed Easy Use for-loop.

No model is downloaded or copied by this script.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPOSITORY_ROOT / "Workflows" / "LTX23"
CONTRACT_SOURCE = (
    REPOSITORY_ROOT
    / "ComfyUI"
    / "sineforge_workflow_bridge"
    / "ltx23_krea_continuation_prompt_contract.json"
)
RECORDS_DIR = (
    REPOSITORY_ROOT
    / "backend"
    / "app"
    / "resources"
    / "native_workflow_library"
    / "records"
)
CATALOG_PATH = RECORDS_DIR.parent / "catalog.json"

SOURCE_ID = "sineforge:ltx23-krea2-lossless-continuation-loop-v1"
WORKFLOW_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, SOURCE_ID))
EDITOR_FILENAME = "SineForge_LTX23_Krea2_Lossless_Continuation_Loop.workflow.json"
API_FILENAME = "SineForge_LTX23_Krea2_Lossless_Continuation_Loop.api.json"
PROMPT_FILENAME = "SineForge_LTX23_Krea2_Continuation.prompt.json"
MANIFEST_FILENAME = "SineForge_LTX23_Krea2_Lossless_Continuation_Loop.manifest.json"
TIMESTAMP = "2026-07-31T01:00:00-07:00"

MODEL_ID = (
    "qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-"
    "neo-code-di-imatrix-max"
)
KREA_MODEL = "krea2TurboOfficialComfy_krea2RawInt8Convrot.safetensors"
KREA_CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
KREA_VAE = "qwen_image_vae.safetensors"
LTX_MODEL = "sulphur2Base_distilled.safetensors"
LTX_CLIP_1 = "gemma_3_12B_it_fp8_e4m3fn.safetensors"
LTX_CLIP_2 = "ltx-2.3_text_projection_bf16.safetensors"
LTX_VIDEO_VAE = "LTX23_video_vae_bf16.safetensors"
LTX_AUDIO_VAE = "LTX23_audio_vae_bf16.safetensors"
LTX_UPSCALER = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
LTX_INGREDIENTS_ICLORA = (
    "LTX\\2.3\\Official\\IC-LoRA\\Ingredients\\"
    "ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"
)
SHARED_MODEL_ROOT = r"C:\ComfyUI\ComfyUI_Shared_Folders\models"
CUSTOM_NODE_ROOT = r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes"
PASS_1_SIGMAS = (
    "1.0, 0.995833, 0.991667, 0.9875, 0.983333, 0.979167, "
    "0.975, 0.93125, 0.847917, 0.725, 0.522917, 0.28125, 0.0"
)
PASS_2_SIGMAS = "0.85, 0.725, 0.6, 0.4219, 0.0"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _input(
    name: str,
    type_name: str,
    link: int,
    *,
    shape: int | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"name": name, "type": type_name, "link": link}
    if shape is not None:
        value["shape"] = shape
    return value


def _widget_input(name: str, type_name: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_name,
        "widget": {"name": name},
        "link": None,
    }


def _output(name: str, type_name: str, links: list[int] | None) -> dict[str, Any]:
    return {"name": name, "type": type_name, "links": links}


def _properties(cnr_id: str, node_name: str, version: str = "local") -> dict[str, Any]:
    return {
        "cnr_id": cnr_id,
        "ver": version,
        "Node name for S&R": node_name,
    }


def _api_workflow(contract: dict[str, Any]) -> dict[str, Any]:
    request_json = json.dumps(
        contract["default_request"],
        ensure_ascii=False,
        indent=2,
    )
    default_constraints = "\n".join(contract["default_request"]["visual_constraints"])
    png16 = {
        "format": "png",
        "bit_depth": "16-bit",
        "input_color_space": "sRGB",
    }
    return {
        "1": {
            "inputs": {"image": "example.png"},
            "class_type": "LoadImage",
            "_meta": {"title": "1 · Initial or canonical image"},
        },
        "26": {
            "inputs": {"image": "Krea2_00006_.png"},
            "class_type": "LoadImage",
            "_meta": {"title": "1B · Ingredients / identity reference sheet"},
        },
        "32": {
            "inputs": {"loop_count": 4},
            "class_type": "SineForgeContinuationLoopCount",
            "_meta": {"title": "2 · Loop count · 0 = until interrupted"},
        },
        "2": {
            "inputs": {"total": ["32", 0], "initial_value1": ["1", 0]},
            "class_type": "easy forLoopStart",
            "_meta": {"title": "2B · Automated continuation loop engine"},
        },
        "3": {
            "inputs": {
                "model": MODEL_ID,
                "variation_mode": "new variation every run",
                "seed": 20260731,
                "scene_or_subject": (
                    "The subject and environment shown in the starting image, "
                    "preserved as the visual source of truth."
                ),
                "next_event": (
                    "Advance the scene by one clear, visually coherent event "
                    "while preserving everything not explicitly changed."
                ),
                "audio_mode": "automatic from scene",
                "dialogue_json": "[]",
                "continuity_mode": "lossless_loop",
                "duration_seconds": 8,
                "visual_constraints_text": default_constraints,
                "continuation_request_json": request_json,
                "recent_cycles_json": "[]",
                "temperature": 0.85,
                "top_p": 0.95,
                "max_tokens": 1800,
                "timeout_seconds": 900,
                "image": ["2", 2],
                "reference_image": ["26", 0],
            },
            "class_type": "SineForgeLTXGeneralContinuationPlanner",
            "_meta": {"title": "3 · General scene/story continuation JSON"},
        },
        "4": {
            "inputs": {
                "unet_name": KREA_MODEL,
                "weight_dtype": "default",
            },
            "class_type": "UNETLoader",
            "_meta": {"title": "4 · Existing-library Krea 2 model"},
        },
        "5": {
            "inputs": {
                "clip_name": KREA_CLIP,
                "type": "krea2",
                "device": "default",
            },
            "class_type": "CLIPLoader",
            "_meta": {"title": "5 · Krea 2 Qwen3-VL encoder"},
        },
        "6": {
            "inputs": {"vae_name": KREA_VAE},
            "class_type": "VAELoader",
            "_meta": {"title": "6 · Krea 2 VAE"},
        },
        "8": {
            "inputs": {
                "text": ["3", 1],
                "clip": ["5", 0],
                "image1": ["2", 2],
                "image1_tokens": "normal",
                "image2": ["26", 0],
                "image2_tokens": "high",
            },
            "class_type": "Krea2EncodeRebalance",
            "_meta": {
                "title": "8 · Krea prompt + current-frame/reference conditioning"
            },
        },
        "9": {
            "inputs": {"conditioning": ["8", 0]},
            "class_type": "ConditioningZeroOut",
            "_meta": {"title": "9 · Krea negative conditioning"},
        },
        "10": {
            "inputs": {"width": 768, "height": 448, "batch_size": 1},
            "class_type": "EmptySD3LatentImage",
            "_meta": {"title": "10 · Krea anchor latent · 768×448"},
        },
        "11": {
            "inputs": {
                "seed": ["3", 5],
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "er_sde",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["8", 0],
                "negative": ["9", 0],
                "latent_image": ["10", 0],
            },
            "class_type": "KSampler",
            "_meta": {"title": "11 · Existing-library Krea 2 sampler"},
        },
        "12": {
            "inputs": {"samples": ["11", 0], "vae": ["6", 0]},
            "class_type": "VAEDecode",
            "_meta": {"title": "12 · Decode fresh Krea 2 anchor"},
        },
        "13": {
            "inputs": {
                "string_a": ["3", 8],
                "string_b": "_KREA2_ANCHOR",
                "delimiter": "",
            },
            "class_type": "StringConcatenate",
            "_meta": {"title": "13 · Anchor filename"},
        },
        "14": {
            "inputs": {
                "images": ["12", 0],
                "filename_prefix": ["13", 0],
                "format": png16,
            },
            "class_type": "SaveImageAdvanced",
            "_meta": {
                "title": "14 · Save 16-bit PNG · passthrough triggers LTX"
            },
        },
        "24": {
            "inputs": {
                "empty_cache": True,
                "gc_collect": True,
                "unload_all_models": True,
                "image_pass": ["14", 0],
            },
            "class_type": "VRAM_Debug",
            "_meta": {"title": "14B · Unload Krea before LTX · image passthrough"},
        },
        "27": {
            "inputs": {"ckpt_name": LTX_MODEL},
            "class_type": "CheckpointLoaderSimple",
            "_meta": {"title": "14C · Load LTX model for reference override"},
        },
        "28": {
            "inputs": {
                "model": ["27", 0],
                "lora_name": LTX_INGREDIENTS_ICLORA,
                "strength_model": 1.0,
            },
            "class_type": "LTXICLoRALoaderModelOnly",
            "_meta": {"title": "14D · Apply official Ingredients IC-LoRA"},
        },
        "29": {
            "inputs": {
                "model": ["28", 0],
                "zero_ref_timesteps": False,
                "verbose": False,
            },
            "class_type": "LTXReferenceEnable",
            "_meta": {"title": "14E · Enable LTX reference-token injection"},
        },
        "30": {
            "inputs": {"vae_name": LTX_VIDEO_VAE},
            "class_type": "VAELoader",
            "_meta": {"title": "14F · LTX reference-conditioning VAE"},
        },
        "31": {
            "inputs": {
                "model": ["29", 0],
                "vae": ["30", 0],
                "image": ["26", 0],
                "strength": 0.75,
                "position_mode": "reference",
                "verbose": False,
            },
            "class_type": "LTXReferenceConditioning",
            "_meta": {"title": "14G · Attach reference sheet to patched LTX model"},
        },
        "15": {
            "inputs": {
                "mode": "▶️ image_to_video",
                "positive_prompt": ["3", 2],
                "negative_prompt": ["3", 3],
                "base_model": LTX_MODEL,
                "clip_1": LTX_CLIP_1,
                "clip_2": LTX_CLIP_2,
                "vae": LTX_VIDEO_VAE,
                "audio_vae": LTX_AUDIO_VAE,
                "upscale_model": LTX_UPSCALER,
                "video_size": "Custom",
                "ratio": "16:9",
                "ratio_from_image": False,
                "custom_width": 768,
                "custom_height": 448,
                "frame_rate": 24,
                "seconds": ["3", 7],
                "seed": ["3", 6],
                "sigma_preset": "12 steps",
                "image": ["24", 1],
                "override_audio": False,
                "lora_1": "None",
                "lora_1_strength": 0.0,
                "lora_2": "None",
                "lora_2_strength": 0.0,
                "lora_3": "None",
                "lora_3_strength": 0.0,
                "custom_sigmas_pass1": PASS_1_SIGMAS,
                "sigmas_pass2": PASS_2_SIGMAS,
                "cfg": 1.0,
                "sampler_pass1": "euler_ancestral_cfg_pp",
                "sampler_pass2": "euler_cfg_pp",
                "weight_dtype": "default",
                "model_override": ["31", 0],
            },
            "class_type": "LTXVSulphurAllInOne",
            "_meta": {
                "title": "15 · LTX-2.3 from saved Krea anchor + reference override"
            },
        },
        "16": {
            "inputs": {
                "images": ["15", 0],
                "frame_rate": ["15", 2],
                "loop_count": 0,
                "filename_prefix": ["3", 8],
                "format": "video/ffv1-mkv",
                "level": "3",
                "coder": "1",
                "context": "1",
                "gop_size": 1,
                "slices": "16",
                "slicecrc": "1",
                "pix_fmt": "rgba64le",
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
                "audio": ["15", 1],
            },
            "class_type": "VHS_VideoCombine",
            "_meta": {"title": "16 · Lossless FFV1 + FLAC master"},
        },
        "17": {
            "inputs": {
                "text": ["3", 0],
                "filename_prefix": ["3", 8],
                "format": "json",
            },
            "class_type": "SaveText",
            "_meta": {"title": "17 · Save complete prompt JSON"},
        },
        "18": {
            "inputs": {
                "image": ["15", 0],
                "batch_index": -1,
                "length": 1,
            },
            "class_type": "ImageFromBatch",
            "_meta": {"title": "18 · True final tensor frame"},
        },
        "19": {
            "inputs": {
                "string_a": ["3", 8],
                "string_b": "_FINAL_FRAME",
                "delimiter": "",
            },
            "class_type": "StringConcatenate",
            "_meta": {"title": "19 · Final-frame filename"},
        },
        "20": {
            "inputs": {
                "images": ["18", 0],
                "filename_prefix": ["19", 0],
                "format": png16,
            },
            "class_type": "SaveImageAdvanced",
            "_meta": {"title": "20 · Save 16-bit final frame · loop state"},
        },
        "21": {
            "inputs": {"text": ["3", 9]},
            "class_type": "ShowText|pysssss",
            "_meta": {"title": "21 · Planner status · seeds · hashes"},
        },
        "22": {
            "inputs": {
                "flow": ["2", 0],
                "initial_value1": ["20", 0],
            },
            "class_type": "easy forLoopEnd",
            "_meta": {"title": "22 · Continue from saved final-frame tensor"},
        },
        "23": {
            "inputs": {"images": ["22", 0]},
            "class_type": "PreviewImage",
            "_meta": {"title": "23 · Final continuation frame"},
        },
    }


def _editor_workflow(contract: dict[str, Any]) -> dict[str, Any]:
    request_json = json.dumps(
        contract["default_request"],
        ensure_ascii=False,
        indent=2,
    )
    default_constraints = "\n".join(contract["default_request"]["visual_constraints"])
    png16 = {
        "format": "png",
        "bit_depth": "16-bit",
        "input_color_space": "sRGB",
    }

    nodes: list[dict[str, Any]] = [
        {
            "id": 1,
            "type": "LoadImage",
            "pos": [80, 460],
            "size": [320, 420],
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": [
                _widget_input("image", "COMBO"),
                _widget_input("upload", "IMAGEUPLOAD"),
            ],
            "outputs": [
                _output("IMAGE", "IMAGE", [1]),
                _output("MASK", "MASK", None),
            ],
            "title": "1 · Initial or canonical image",
            "properties": _properties("comfy-core", "LoadImage", "0.5.1"),
            "widgets_values": ["example.png", "image"],
            "color": "#17304a",
            "bgcolor": "#102238",
        },
        {
            "id": 26,
            "type": "LoadImage",
            "pos": [80, 920],
            "size": [320, 420],
            "flags": {},
            "order": 1,
            "mode": 0,
            "inputs": [
                _widget_input("image", "COMBO"),
                _widget_input("upload", "IMAGEUPLOAD"),
            ],
            "outputs": [
                _output("IMAGE", "IMAGE", [37, 39, 44]),
                _output("MASK", "MASK", None),
            ],
            "title": "1B · Ingredients / identity reference sheet",
            "properties": _properties("comfy-core", "LoadImage", "0.5.1"),
            "widgets_values": ["Krea2_00006_.png", "image"],
            "color": "#17304a",
            "bgcolor": "#102238",
        },
        {
            "id": 32,
            "type": "SineForgeContinuationLoopCount",
            "pos": [470, 350],
            "size": [360, 150],
            "flags": {},
            "order": 2,
            "mode": 0,
            "inputs": [],
            "outputs": [_output("total", "INT", [46])],
            "title": "2 · Loop count · 0 = until interrupted",
            # Local bundled node: do not advertise a Comfy Registry package.
            "properties": {
                "Node name for S&R": "SineForgeContinuationLoopCount"
            },
            "widgets_values": [4],
            "color": "#513a18",
            "bgcolor": "#38280f",
        },
        {
            "id": 2,
            "type": "easy forLoopStart",
            "pos": [470, 540],
            "size": [360, 210],
            "flags": {},
            "order": 3,
            "mode": 0,
            "inputs": [
                _input("total", "INT", 46),
                _input("initial_value1", "*", 1),
            ],
            "outputs": [
                _output("flow", "FLOW_CONTROL", [2]),
                _output("index", "INT", None),
                _output("value1", "*", [3, 38]),
            ],
            "title": "2B · Automated continuation loop engine",
            "properties": _properties("ComfyUI-Easy-Use", "easy forLoopStart"),
            "widgets_values": [],
            "color": "#513a18",
            "bgcolor": "#38280f",
        },
        {
            "id": 3,
            "type": "SineForgeLTXGeneralContinuationPlanner",
            "pos": [900, 360],
            "size": [680, 920],
            "flags": {},
            "order": 4,
            "mode": 0,
            "inputs": [
                _input("image", "IMAGE", 3, shape=7),
                _input("reference_image", "IMAGE", 37, shape=7),
            ],
            "outputs": [
                _output("prompt_json", "STRING", [19]),
                _output("krea_prompt", "STRING", [6]),
                _output("positive_prompt", "STRING", [34]),
                _output("negative_prompt", "STRING", [14]),
                _output("variation_seed", "INT", None),
                _output("image_seed", "INT", [9]),
                _output("video_seed", "INT", [15]),
                _output("duration_seconds", "INT", [16]),
                _output("output_prefix", "STRING", [17, 18, 21, 35]),
                _output("status_json", "STRING", [24]),
            ],
            "title": "3 · General scene/story continuation JSON",
            # Local bundled node: do not advertise a Comfy Registry package.
            "properties": {
                "Node name for S&R": "SineForgeLTXGeneralContinuationPlanner"
            },
            "widgets_values": [
                MODEL_ID,
                "new variation every run",
                20260731,
                "fixed",
                (
                    "The subject and environment shown in the starting image, "
                    "preserved as the visual source of truth."
                ),
                (
                    "Advance the scene by one clear, visually coherent event "
                    "while preserving everything not explicitly changed."
                ),
                "automatic from scene",
                "[]",
                "lossless_loop",
                8,
                default_constraints,
                request_json,
                "[]",
                0.85,
                0.95,
                1800,
                900,
            ],
            "color": "#2b1d52",
            "bgcolor": "#1d163c",
        },
        {
            "id": 4,
            "type": "UNETLoader",
            "pos": [1660, 330],
            "size": [390, 120],
            "flags": {},
            "order": 3,
            "mode": 0,
            "inputs": [],
            "outputs": [_output("MODEL", "MODEL", [8])],
            "title": "4 · Existing-library Krea 2 model",
            "properties": _properties("comfy-core", "UNETLoader", "0.21.1"),
            "widgets_values": [KREA_MODEL, "default"],
            "color": "#4d2721",
            "bgcolor": "#351b17",
        },
        {
            "id": 5,
            "type": "CLIPLoader",
            "pos": [1660, 490],
            "size": [390, 140],
            "flags": {},
            "order": 4,
            "mode": 0,
            "inputs": [],
            "outputs": [_output("CLIP", "CLIP", [5])],
            "title": "5 · Krea 2 Qwen3-VL encoder",
            "properties": _properties("comfy-core", "CLIPLoader", "0.21.1"),
            "widgets_values": [KREA_CLIP, "krea2", "default"],
            "color": "#4d2721",
            "bgcolor": "#351b17",
        },
        {
            "id": 6,
            "type": "VAELoader",
            "pos": [1660, 670],
            "size": [390, 100],
            "flags": {},
            "order": 5,
            "mode": 0,
            "inputs": [],
            "outputs": [_output("VAE", "VAE", [12])],
            "title": "6 · Krea 2 VAE",
            "properties": _properties("comfy-core", "VAELoader", "0.21.1"),
            "widgets_values": [KREA_VAE],
            "color": "#4d2721",
            "bgcolor": "#351b17",
        },
        {
            "id": 8,
            "type": "Krea2EncodeRebalance",
            "pos": [2120, 540],
            "size": [470, 330],
            "flags": {},
            "order": 6,
            "mode": 0,
            "inputs": [
                _input("text", "STRING", 6),
                _input("clip", "CLIP", 5),
                _input("image1", "IMAGE", 38, shape=7),
                _widget_input("image1_tokens", "COMBO"),
                _input("image2", "IMAGE", 39, shape=7),
                _widget_input("image2_tokens", "COMBO"),
            ],
            "outputs": [_output("CONDITIONING", "CONDITIONING", [7, 11])],
            "title": "8 · Krea prompt + current-frame/reference conditioning",
            "properties": _properties(
                "Rebalance-Pack",
                "Krea2EncodeRebalance",
                "local",
            ),
            "widgets_values": ["", "normal", "high"],
            "color": "#4d2721",
            "bgcolor": "#351b17",
        },
        {
            "id": 9,
            "type": "ConditioningZeroOut",
            "pos": [2620, 650],
            "size": [300, 90],
            "flags": {},
            "order": 7,
            "mode": 0,
            "inputs": [_input("conditioning", "CONDITIONING", 7)],
            "outputs": [_output("CONDITIONING", "CONDITIONING", [10])],
            "title": "9 · Krea negative conditioning",
            "properties": _properties(
                "comfy-core",
                "ConditioningZeroOut",
                "0.5.1",
            ),
            "widgets_values": [],
        },
        {
            "id": 10,
            "type": "EmptySD3LatentImage",
            "pos": [2120, 800],
            "size": [360, 150],
            "flags": {},
            "order": 8,
            "mode": 0,
            "inputs": [],
            "outputs": [_output("LATENT", "LATENT", [11])],
            "title": "10 · Krea anchor latent · 768×448",
            "properties": _properties(
                "comfy-core",
                "EmptySD3LatentImage",
                "0.5.1",
            ),
            "widgets_values": [768, 448, 1],
        },
        {
            "id": 11,
            "type": "KSampler",
            "pos": [3000, 420],
            "size": [390, 430],
            "flags": {},
            "order": 9,
            "mode": 0,
            "inputs": [
                _input("model", "MODEL", 8),
                _input("positive", "CONDITIONING", 11),
                _input("negative", "CONDITIONING", 10),
                _input("latent_image", "LATENT", 11),
                _input("seed", "INT", 9),
            ],
            "outputs": [_output("LATENT", "LATENT", [12])],
            "title": "11 · Existing-library Krea 2 sampler",
            "properties": _properties("comfy-core", "KSampler", "0.5.1"),
            "widgets_values": [
                20260731,
                "fixed",
                8,
                1.0,
                "er_sde",
                "simple",
                1.0,
            ],
            "color": "#4d2721",
            "bgcolor": "#351b17",
        },
        {
            "id": 12,
            "type": "VAEDecode",
            "pos": [3470, 500],
            "size": [270, 100],
            "flags": {},
            "order": 10,
            "mode": 0,
            "inputs": [
                _input("samples", "LATENT", 12),
                _input("vae", "VAE", 12),
            ],
            "outputs": [_output("IMAGE", "IMAGE", [20])],
            "title": "12 · Decode fresh Krea 2 anchor",
            "properties": _properties("comfy-core", "VAEDecode", "0.5.1"),
            "widgets_values": [],
        },
        {
            "id": 13,
            "type": "StringConcatenate",
            "pos": [3470, 670],
            "size": [320, 190],
            "flags": {},
            "order": 11,
            "mode": 0,
            "inputs": [_input("string_a", "STRING", 35)],
            "outputs": [_output("STRING", "STRING", [20])],
            "title": "13 · Anchor filename",
            "properties": _properties("comfy-core", "StringConcatenate", "0.21.1"),
            "widgets_values": ["", "_KREA2_ANCHOR", ""],
        },
        {
            "id": 14,
            "type": "SaveImageAdvanced",
            "pos": [3860, 430],
            "size": [410, 330],
            "flags": {},
            "order": 12,
            "mode": 0,
            "inputs": [
                _input("images", "IMAGE", 20),
                _input("filename_prefix", "STRING", 20),
            ],
            "outputs": [_output("images", "IMAGE", [13])],
            "title": "14 · Save 16-bit PNG · passthrough triggers LTX",
            "properties": _properties(
                "comfy-core",
                "SaveImageAdvanced",
                "0.21.1",
            ),
            "widgets_values": [None, "png", "16-bit", "sRGB"],
            "color": "#52311f",
            "bgcolor": "#3b2114",
        },
        {
            "id": 24,
            "type": "VRAM_Debug",
            "pos": [4310, 1450],
            "size": [360, 210],
            "flags": {},
            "order": 13,
            "mode": 0,
            "inputs": [_input("image_pass", "IMAGE", 13, shape=7)],
            "outputs": [
                _output("any_output", "*", None),
                _output("image_pass", "IMAGE", [36]),
                _output("model_pass", "MODEL", None),
                _output("freemem_before", "INT", None),
                _output("freemem_after", "INT", None),
            ],
            "title": "14B · Unload Krea before LTX · image passthrough",
            "properties": _properties("comfyui-kjnodes", "VRAM_Debug"),
            "widgets_values": [True, True, True],
            "color": "#513a18",
            "bgcolor": "#38280f",
        },
        {
            "id": 27,
            "type": "CheckpointLoaderSimple",
            "pos": [3860, 850],
            "size": [420, 120],
            "flags": {},
            "order": 14,
            "mode": 0,
            "inputs": [],
            "outputs": [
                _output("MODEL", "MODEL", [40]),
                _output("CLIP", "CLIP", None),
                _output("VAE", "VAE", None),
            ],
            "title": "14C · Load LTX model for reference override",
            "properties": _properties("comfy-core", "CheckpointLoaderSimple", "0.5.1"),
            "widgets_values": [LTX_MODEL],
            "color": "#123a30",
            "bgcolor": "#0d2b24",
        },
        {
            "id": 28,
            "type": "LTXICLoRALoaderModelOnly",
            "pos": [4310, 850],
            "size": [500, 140],
            "flags": {},
            "order": 15,
            "mode": 0,
            "inputs": [_input("model", "MODEL", 40)],
            "outputs": [
                _output("model", "MODEL", [41]),
                _output("latent_downscale_factor", "FLOAT", None),
            ],
            "title": "14D · Apply official Ingredients IC-LoRA",
            "properties": _properties(
                "ComfyUI-LTXVideo",
                "LTXICLoRALoaderModelOnly",
                "local",
            ),
            "widgets_values": [LTX_INGREDIENTS_ICLORA, 1.0],
            "color": "#123a30",
            "bgcolor": "#0d2b24",
        },
        {
            "id": 29,
            "type": "LTXReferenceEnable",
            "pos": [4860, 850],
            "size": [360, 130],
            "flags": {},
            "order": 16,
            "mode": 0,
            "inputs": [_input("model", "MODEL", 41)],
            "outputs": [_output("model", "MODEL", [42])],
            "title": "14E · Enable LTX reference-token injection",
            "properties": _properties("10s-comfy-nodes", "LTXReferenceEnable"),
            "widgets_values": [False, False],
            "color": "#123a30",
            "bgcolor": "#0d2b24",
        },
        {
            "id": 30,
            "type": "VAELoader",
            "pos": [3860, 1010],
            "size": [420, 100],
            "flags": {},
            "order": 17,
            "mode": 0,
            "inputs": [],
            "outputs": [_output("VAE", "VAE", [43])],
            "title": "14F · LTX reference-conditioning VAE",
            "properties": _properties("comfy-core", "VAELoader", "0.21.1"),
            "widgets_values": [LTX_VIDEO_VAE],
            "color": "#123a30",
            "bgcolor": "#0d2b24",
        },
        {
            "id": 31,
            "type": "LTXReferenceConditioning",
            "pos": [4860, 1010],
            "size": [440, 260],
            "flags": {},
            "order": 18,
            "mode": 0,
            "inputs": [
                _input("model", "MODEL", 42),
                _input("vae", "VAE", 43),
                _input("image", "IMAGE", 44),
                _widget_input("strength", "FLOAT"),
                _widget_input("position_mode", "COMBO"),
                _widget_input("verbose", "BOOLEAN"),
            ],
            "outputs": [_output("model", "MODEL", [45])],
            "title": "14G · Attach reference sheet to patched LTX model",
            "properties": _properties("10s-comfy-nodes", "LTXReferenceConditioning"),
            "widgets_values": [0.75, "reference", False],
            "color": "#123a30",
            "bgcolor": "#0d2b24",
        },
        {
            "id": 15,
            "type": "LTXVSulphurAllInOne",
            "pos": [4380, 330],
            "size": [520, 1040],
            "flags": {},
            "order": 14,
            "mode": 0,
            "inputs": [
                _input("image", "IMAGE", 36, shape=7),
                _input("positive_prompt", "STRING", 13),
                _input("negative_prompt", "STRING", 14),
                _input("seconds", "INT", 16),
                _input("seed", "INT", 15),
                _input("model_override", "MODEL", 45, shape=7),
            ],
            "outputs": [
                _output("images", "IMAGE", [22, 25]),
                _output("audio", "AUDIO", [23]),
                _output("frame_rate", "FLOAT", [26]),
            ],
            "title": "15 · LTX-2.3 from saved Krea anchor + reference override",
            "properties": _properties(
                "comfyui_starnodes",
                "LTXVSulphurAllInOne",
            ),
            "widgets_values": [
                "▶️ image_to_video",
                "",
                "",
                LTX_MODEL,
                LTX_CLIP_1,
                LTX_CLIP_2,
                LTX_VIDEO_VAE,
                LTX_AUDIO_VAE,
                LTX_UPSCALER,
                "Custom",
                "16:9",
                False,
                768,
                448,
                24,
                8,
                20260731,
                "fixed",
                "12 steps",
                False,
                "None",
                0.0,
                "None",
                0.0,
                "None",
                0.0,
                PASS_1_SIGMAS,
                PASS_2_SIGMAS,
                1.0,
                "euler_ancestral_cfg_pp",
                "euler_cfg_pp",
                "default",
                "",
            ],
            "color": "#123a30",
            "bgcolor": "#0d2b24",
        },
        {
            "id": 16,
            "type": "VHS_VideoCombine",
            "pos": [5000, 350],
            "size": [420, 470],
            "flags": {},
            "order": 15,
            "mode": 0,
            "inputs": [
                _input("images", "IMAGE", 22),
                _input("frame_rate", "FLOAT", 26),
                _input("filename_prefix", "STRING", 17),
                _input("audio", "AUDIO", 23, shape=7),
            ],
            "outputs": [_output("Filenames", "VHS_FILENAMES", None)],
            "title": "16 · Lossless FFV1 + FLAC master",
            "properties": _properties(
                "comfyui-videohelpersuite",
                "VHS_VideoCombine",
            ),
            "widgets_values": {
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "SineForge/Continuation/cycle",
                "format": "video/ffv1-mkv",
                "level": "3",
                "coder": "1",
                "context": "1",
                "gop_size": 1,
                "slices": "16",
                "slicecrc": "1",
                "pix_fmt": "rgba64le",
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            },
            "color": "#52311f",
            "bgcolor": "#3b2114",
        },
        {
            "id": 17,
            "type": "SaveText",
            "pos": [5000, 870],
            "size": [420, 250],
            "flags": {},
            "order": 16,
            "mode": 0,
            "inputs": [
                _input("text", "STRING", 19),
                _input("filename_prefix", "STRING", 18),
            ],
            "outputs": [_output("text", "STRING", None)],
            "title": "17 · Save complete prompt JSON",
            "properties": _properties("comfy-core", "SaveText", "0.5.1"),
            "widgets_values": ["SineForge/Continuation/cycle", "json"],
            "color": "#52311f",
            "bgcolor": "#3b2114",
        },
        {
            "id": 18,
            "type": "ImageFromBatch",
            "pos": [5000, 1190],
            "size": [320, 120],
            "flags": {},
            "order": 17,
            "mode": 0,
            "inputs": [_input("image", "IMAGE", 25)],
            "outputs": [_output("IMAGE", "IMAGE", [27])],
            "title": "18 · True final tensor frame",
            "properties": _properties("comfy-core", "ImageFromBatch", "0.5.1"),
            "widgets_values": [-1, 1],
            "color": "#17304a",
            "bgcolor": "#102238",
        },
        {
            "id": 19,
            "type": "StringConcatenate",
            "pos": [5390, 1200],
            "size": [320, 190],
            "flags": {},
            "order": 18,
            "mode": 0,
            "inputs": [_input("string_a", "STRING", 21)],
            "outputs": [_output("STRING", "STRING", [28])],
            "title": "19 · Final-frame filename",
            "properties": _properties("comfy-core", "StringConcatenate", "0.21.1"),
            "widgets_values": ["", "_FINAL_FRAME", ""],
        },
        {
            "id": 20,
            "type": "SaveImageAdvanced",
            "pos": [5790, 1110],
            "size": [410, 330],
            "flags": {},
            "order": 19,
            "mode": 0,
            "inputs": [
                _input("images", "IMAGE", 27),
                _input("filename_prefix", "STRING", 28),
            ],
            "outputs": [_output("images", "IMAGE", [29])],
            "title": "20 · Save 16-bit final frame · loop state",
            "properties": _properties(
                "comfy-core",
                "SaveImageAdvanced",
                "0.21.1",
            ),
            "widgets_values": [None, "png", "16-bit", "sRGB"],
            "color": "#52311f",
            "bgcolor": "#3b2114",
        },
        {
            "id": 21,
            "type": "ShowText|pysssss",
            "pos": [5000, 1450],
            "size": [420, 280],
            "flags": {},
            "order": 20,
            "mode": 0,
            "inputs": [_input("text", "STRING", 24)],
            "outputs": [_output("STRING", "STRING", None)],
            "title": "21 · Planner status · seeds · hashes",
            "properties": _properties(
                "pysssss/ComfyUI-Custom-Scripts",
                "ShowText|pysssss",
            ),
            "widgets_values": [""],
            "color": "#283140",
            "bgcolor": "#1c2430",
        },
        {
            "id": 22,
            "type": "easy forLoopEnd",
            "pos": [6200, 1120],
            "size": [360, 220],
            "flags": {},
            "order": 21,
            "mode": 0,
            "inputs": [
                _input("flow", "FLOW_CONTROL", 2),
                _input("initial_value1", "*", 29),
            ],
            "outputs": [_output("value1", "*", [30])],
            "title": "22 · Continue from saved final-frame tensor",
            "properties": _properties("ComfyUI-Easy-Use", "easy forLoopEnd"),
            "widgets_values": [],
            "color": "#513a18",
            "bgcolor": "#38280f",
        },
        {
            "id": 23,
            "type": "PreviewImage",
            "pos": [6660, 1110],
            "size": [360, 360],
            "flags": {},
            "order": 22,
            "mode": 0,
            "inputs": [_input("images", "IMAGE", 30)],
            "outputs": [],
            "title": "23 · Final continuation frame",
            "properties": _properties("comfy-core", "PreviewImage", "0.5.1"),
            "widgets_values": [],
        },
        {
            "id": 25,
            "type": "MarkdownNote",
            "pos": [80, 30],
            "size": [6940, 230],
            "flags": {},
            "order": 23,
            "mode": 0,
            "inputs": [],
            "outputs": [],
            "title": "READ ME · existing Krea 2 → 16-bit anchor → LTX → final-frame loop",
            "properties": {},
            "widgets_values": [
                "# SineForge · Krea 2 + LTX-2.3 Lossless Continuation Loop\n\n"
                "1. Load any starting image.\n"
                "2. Load an Ingredients/reference sheet in node 1B. Use a clean panel sheet for recurring characters, wardrobe, props, style, or studio/set identity.\n"
                "3. Set `loop_count` on node 2. Values 1+ run exactly that many cycles. Set 0 to keep going until you press ComfyUI Interrupt.\n"
                "4. On node 3, describe any `scene_or_subject` and the `next_event`. The defaults make no assumption about people, podcasts, or dialogue.\n"
                "5. Choose `audio_mode`: automatic from scene, no dialogue, dialogue JSON, or advanced JSON only. `dialogue_json` is optional and defaults to `[]`.\n"
                "6. For exact speech, choose dialogue JSON and use entries such as `[{\"speaker\":\"Character A\",\"position\":\"camera-left\",\"line\":\"Exact words\"}]`.\n"
                "7. Keep `recent_cycles_json` as `[]` unless you paste valid JSON history. The advanced `continuation_request_json` remains available for full-contract control.\n"
                "8. Node 3 lists every local executable GGUF package. Qwen 3.6 40B is the default only. Vision models see both images; text-only models receive the JSON scene request without image attachments. Krea still uses both images through `Krea2EncodeRebalance`.\n"
                "9. The LTX model path uses the official Ingredients IC-LoRA plus LTX reference-token conditioning, then feeds the patched model into the Sulphur all-in-one node via `model_override`.\n"
                "10. The Krea sampler creates a fresh 768×448 anchor. Node 14 saves it as 16-bit PNG and passes the same unmodified tensor into LTX.\n"
                "11. LTX produces native audio/video. Node 16 saves a lossless FFV1 + FLAC master.\n"
                "12. Node 18 extracts the true final tensor frame before encoding. Node 20 saves it as 16-bit PNG and passes the same tensor into the next cycle.\n"
                "13. Every planner artifact and all editable dialogue are JSON. No hosted/API agent is used.\n\n"
                "**Lossless scope:** PNG/FFV1/FLAC storage and in-memory handoffs avoid additional codec loss. Krea and LTX generation themselves are generative and cannot be mathematically lossless."
            ],
            "color": "#26354f",
            "bgcolor": "#172237",
        },
    ]

    links = [
        [1, 1, 0, 2, 1, "IMAGE"],
        [2, 2, 0, 22, 0, "FLOW_CONTROL"],
        [3, 2, 2, 3, 0, "*"],
        [5, 5, 0, 8, 1, "CLIP"],
        [6, 3, 1, 8, 0, "STRING"],
        [7, 8, 0, 9, 0, "CONDITIONING"],
        [8, 4, 0, 11, 0, "MODEL"],
        [9, 3, 5, 11, 4, "INT"],
        [10, 9, 0, 11, 2, "CONDITIONING"],
        [11, 8, 0, 11, 1, "CONDITIONING"],
        [12, 6, 0, 12, 1, "VAE"],
        [13, 14, 0, 24, 0, "IMAGE"],
        [14, 3, 3, 15, 2, "STRING"],
        [15, 3, 6, 15, 4, "INT"],
        [16, 3, 7, 15, 3, "INT"],
        [17, 3, 8, 16, 2, "STRING"],
        [18, 3, 8, 17, 1, "STRING"],
        [19, 3, 0, 17, 0, "STRING"],
        [20, 12, 0, 14, 0, "IMAGE"],
        [21, 3, 8, 19, 0, "STRING"],
        [22, 15, 0, 16, 0, "IMAGE"],
        [23, 15, 1, 16, 3, "AUDIO"],
        [24, 3, 9, 21, 0, "STRING"],
        [25, 15, 0, 18, 0, "IMAGE"],
        [26, 15, 2, 16, 1, "FLOAT"],
        [27, 18, 0, 20, 0, "IMAGE"],
        [28, 19, 0, 20, 1, "STRING"],
        [29, 20, 0, 22, 1, "*"],
        [30, 22, 0, 23, 0, "*"],
    ]
    # KSampler latent and decoded-sample links share source slots but still
    # require distinct link records in the editor graph.
    links.extend(
        [
            [31, 10, 0, 11, 3, "LATENT"],
            [32, 11, 0, 12, 0, "LATENT"],
            [33, 13, 0, 14, 1, "STRING"],
            [34, 3, 2, 15, 1, "STRING"],
            [35, 3, 8, 13, 0, "STRING"],
            [36, 24, 1, 15, 0, "IMAGE"],
            [37, 26, 0, 3, 1, "IMAGE"],
            [38, 2, 2, 8, 2, "*"],
            [39, 26, 0, 8, 4, "IMAGE"],
            [40, 27, 0, 28, 0, "MODEL"],
            [41, 28, 0, 29, 0, "MODEL"],
            [42, 29, 0, 31, 0, "MODEL"],
            [43, 30, 0, 31, 1, "VAE"],
            [44, 26, 0, 31, 2, "IMAGE"],
            [45, 31, 0, 15, 5, "MODEL"],
            [46, 32, 0, 2, 0, "INT"],
        ]
    )

    # Add the late link ids to the matching node slots.
    for node in nodes:
        if node["id"] == 10:
            node["outputs"][0]["links"] = [31]
        elif node["id"] == 11:
            node["inputs"][3]["link"] = 31
            node["outputs"][0]["links"] = [32]
        elif node["id"] == 12:
            node["inputs"][0]["link"] = 32
        elif node["id"] == 13:
            node["outputs"][0]["links"] = [33]
        elif node["id"] == 14:
            node["inputs"][1]["link"] = 33
        elif node["id"] == 15:
            node["inputs"][1]["link"] = 34
            node["inputs"][5]["link"] = 45

    return {
        "id": WORKFLOW_ID,
        "revision": 0,
        "last_node_id": 32,
        "last_link_id": 46,
        "nodes": nodes,
        "links": sorted(links, key=lambda item: item[0]),
        "groups": [
            {
                "id": 1,
                "title": "GENERAL JSON CONTINUATION",
                "bounding": [50, 300, 1540, 1110],
                "color": "#6c4eb6",
                "font_size": 24,
                "flags": {},
            },
            {
                "id": 2,
                "title": "EXISTING LIBRARY KREA 2 IMAGE GENERATION",
                "bounding": [1620, 280, 2670, 760],
                "color": "#b45a43",
                "font_size": 24,
                "flags": {},
            },
            {
                "id": 3,
                "title": "LTX-2.3 + INGREDIENTS REFERENCE + LOSSLESS MASTER",
                "bounding": [3820, 280, 3250, 1500],
                "color": "#397f69",
                "font_size": 24,
                "flags": {},
            },
        ],
        "config": {},
        "extra": {
            "ds": {"scale": 0.55, "offset": [20, 90]},
            "frontendVersion": "1.47.10",
            "sineforge": {
                "schema_version": "sineforge.ltx23-krea2-continuation-loop/v1",
                "read_only_library_source": True,
                "prompt_contract": PROMPT_FILENAME,
                "krea_library_source": (
                    "Krea 2 Text to Image + Prompt from Image"
                ),
                "reference_conditioning": {
                    "planner": "current frame + reference sheet",
                    "krea": "Krea2EncodeRebalance image1=current frame image2=reference sheet",
                    "ltx": "Ingredients IC-LoRA model_override + LTXReferenceConditioning",
                    "ingredients_lora": LTX_INGREDIENTS_ICLORA,
                },
            },
        },
        "version": 0.4,
    }


def _manifest(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "sineforge.semantic-workflow-manifest/v1",
        "template_id": "ltx23-krea2-lossless-continuation-loop-v1",
        "workflow_name": (
            "LTX-2.3 + Krea 2 General Continuation Loop — Local GGUF JSON"
        ),
        "editor_workflow": EDITOR_FILENAME,
        "api_workflow": API_FILENAME,
        "prompt_contract": PROMPT_FILENAME,
        "execution_policy": {
            "cloud_agents_allowed": False,
            "local_planner": "LM Studio",
            "planner_model_default": MODEL_ID,
            "planner_model_selection": (
                "all local executable GGUF packages beneath the trusted "
                "LM Studio model root"
            ),
            "shared_model_root": SHARED_MODEL_ROOT,
            "loop_count_default": 4,
            "loop_count_zero_mode": {
                "meaning": "continuous_until_interrupted",
                "internal_total": 100000,
                "stop_control": "ComfyUI Interrupt",
            },
            "queue_depth": 1,
            "batch_size": 1,
            "anchor_format": "16-bit PNG",
            "master_video": "FFV1 MKV",
            "master_audio": "FLAC",
            "handoff": "unmodified in-memory IMAGE tensor",
            "reference_conditioning": {
                "planner": "Node 3 receives the current loop frame and node 1B reference sheet.",
                "krea": "Node 8 uses Krea2EncodeRebalance with image1=current frame and image2=reference sheet.",
                "ltx": "Nodes 27-31 patch the all-in-one LTX model_override with Ingredients IC-LoRA and reference-token conditioning.",
                "ingredients_lora": LTX_INGREDIENTS_ICLORA,
            },
        },
        "bindings": {
            "initial_image": {
                "node_id": "1",
                "class_type": "LoadImage",
                "input": "image",
            },
            "ingredients_reference_image": {
                "node_id": "26",
                "class_type": "LoadImage",
                "input": "image",
            },
            "loop_count": {
                "node_id": "32",
                "class_type": "SineForgeContinuationLoopCount",
                "input": "loop_count",
            },
            "loop_engine_total": {
                "source": {"node_id": "32", "output_index": 0},
                "target": {
                    "node_id": "2",
                    "class_type": "easy forLoopStart",
                    "input": "total",
                },
            },
            "continuation_request_json": {
                "node_id": "3",
                "class_type": "SineForgeLTXGeneralContinuationPlanner",
                "input": "continuation_request_json",
                "media_type": "application/json",
            },
            "scene_or_subject": {
                "node_id": "3",
                "class_type": "SineForgeLTXGeneralContinuationPlanner",
                "input": "scene_or_subject",
            },
            "next_event": {
                "node_id": "3",
                "class_type": "SineForgeLTXGeneralContinuationPlanner",
                "input": "next_event",
            },
            "audio_mode": {
                "node_id": "3",
                "class_type": "SineForgeLTXGeneralContinuationPlanner",
                "input": "audio_mode",
            },
            "dialogue_json": {
                "node_id": "3",
                "class_type": "SineForgeLTXGeneralContinuationPlanner",
                "input": "dialogue_json",
                "media_type": "application/json",
            },
            "krea_prompt": {
                "source": {"node_id": "3", "output_index": 1},
                "target": {
                    "node_id": "8",
                    "class_type": "Krea2EncodeRebalance",
                    "input": "text",
                },
            },
            "krea_current_frame_reference": {
                "source": {"node_id": "2", "output_index": 2},
                "target": {
                    "node_id": "8",
                    "class_type": "Krea2EncodeRebalance",
                    "input": "image1",
                },
            },
            "krea_ingredients_reference": {
                "source": {"node_id": "26", "output_index": 0},
                "target": {
                    "node_id": "8",
                    "class_type": "Krea2EncodeRebalance",
                    "input": "image2",
                },
            },
            "ltx_ingredients_iclora": {
                "node_id": "28",
                "class_type": "LTXICLoRALoaderModelOnly",
                "input": "lora_name",
                "value": LTX_INGREDIENTS_ICLORA,
            },
            "ltx_reference_model_override": {
                "source": {"node_id": "31", "output_index": 0},
                "target": {
                    "node_id": "15",
                    "class_type": "LTXVSulphurAllInOne",
                    "input": "model_override",
                },
            },
            "krea_anchor": {
                "source": {"node_id": "14", "output_index": 0},
                "target": {
                    "node_id": "15",
                    "class_type": "LTXVSulphurAllInOne",
                    "input": "image",
                },
            },
            "final_frame": {
                "source": {"node_id": "18", "output_index": 0},
                "save": {
                    "node_id": "20",
                    "class_type": "SaveImageAdvanced",
                    "input": "images",
                },
                "next_cycle": {
                    "node_id": "22",
                    "class_type": "easy forLoopEnd",
                    "input": "initial_value1",
                },
            },
        },
        "lossless_scope": {
            "true": [
                "16-bit PNG compression",
                "FFV1 video",
                "FLAC audio",
                "JSON prompts",
                "in-memory tensor handoff",
            ],
            "not_claimed": [
                "Krea image synthesis",
                "LTX video synthesis",
                "mathematically identical generated pixels",
            ],
        },
    }


def _instructions() -> str:
    return """1. Load any starting image in node 1.
2. Load a clean Ingredients/reference sheet in node 1B. This can be a character sheet, product sheet, studio/set sheet, or style sheet. Do not include labels or clutter if you want identity/reference conditioning to work well.
3. Set node 2 `loop_count`. Values 1 through 100000 run exactly that many cycles. Set 0 for continuous mode; internally it resolves to 100000 cycles, so stop it at any time with ComfyUI Interrupt. Start with 1 while tuning.
4. In node 3, describe any `scene_or_subject` and the `next_event`. These are the primary controls. The workflow does not assume a podcast, conversation, people, or any particular genre.
5. Choose node 3 `audio_mode`: `automatic from scene`, `no dialogue`, `dialogue JSON`, or `advanced JSON only`.
6. Dialogue is optional and JSON-only. Leave `dialogue_json` as `[]` unless `audio_mode` is `dialogue JSON`. For exact speech, use an ordered array such as `[{"speaker":"Character A","position":"camera-left","line":"Exact words"},{"speaker":"Character B","position":"camera-right","line":"Exact reply"}]`. Optional per-turn keys are `delivery` and `action`.
7. Keep node 3 `recent_cycles_json` as `[]` unless you paste valid JSON history. The advanced `continuation_request_json` remains available for full-contract edits.
8. Node 3 offers every local executable GGUF package beneath the LM Studio model root; Qwen 3.6 40B is only the default. Vision-capable models receive the current frame and node 1B reference image. Text-only models remain usable and receive the JSON scene request without image attachments. Every selected model is fully unloaded before Krea/LTX generation.
9. Node 8 uses `Krea2EncodeRebalance`; `image1` is the current loop frame and `image2` is the Ingredients/reference sheet. This makes Krea anchor generation reference-aware instead of text-only.
10. Nodes 27–31 load the LTX model, apply the official Ingredients IC-LoRA, enable LTX reference-token injection, attach node 1B as the reference image, and feed the patched model into node 15 through `model_override`.
11. Node 14 saves the new Krea image as a 16-bit PNG and returns the same unmodified tensor. LTX is connected to that Save node's output, making successful anchor creation the hard dependency for video generation.
12. Node 16 saves the generated frame batch and native audio as FFV1 + FLAC in MKV. No H.264 intermediate is used.
13. Node 18 selects the final generated tensor frame with `batch_index=-1`. Node 20 saves a 16-bit PNG and returns the same tensor to node 22 for the next cycle.
14. Node 17 saves the full request, generated prompts, seeds, source-image hash, reference-image hash, and planner result as `.json`.
15. If a cycle fails, earlier PNG, FFV1, and JSON outputs remain recoverable. Set node 2 to 1 while tuning.
16. “Lossless” applies to handoff and storage. Krea and LTX are generative models, so newly synthesized content cannot be mathematically pixel-identical or lossless."""


def _library_record(
    *,
    editor: dict[str, Any],
    api: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    trusted_root = contract["trusted_lm_studio_model_root"]
    preferred_package = contract["preferred_planner_model_package"]
    model_files = [
        {
            "node_id": "4",
            "node_type": "UNETLoader",
            "input": "unet_name",
            "value": KREA_MODEL,
            "preferred_relative_path": f"diffusion_models/{KREA_MODEL}",
        },
        {
            "node_id": "5",
            "node_type": "CLIPLoader",
            "input": "clip_name",
            "value": KREA_CLIP,
            "preferred_relative_path": f"text_encoders/{KREA_CLIP}",
        },
        {
            "node_id": "6",
            "node_type": "VAELoader",
            "input": "vae_name",
            "value": KREA_VAE,
            "preferred_relative_path": f"vae/{KREA_VAE}",
        },
        {
            "node_id": "15",
            "node_type": "LTXVSulphurAllInOne",
            "input": "base_model",
            "value": LTX_MODEL,
            "preferred_relative_path": f"checkpoints/{LTX_MODEL}",
        },
        {
            "node_id": "15",
            "node_type": "LTXVSulphurAllInOne",
            "input": "clip_1",
            "value": LTX_CLIP_1,
            "preferred_relative_path": f"text_encoders/{LTX_CLIP_1}",
        },
        {
            "node_id": "15",
            "node_type": "LTXVSulphurAllInOne",
            "input": "clip_2",
            "value": LTX_CLIP_2,
            "preferred_relative_path": f"text_encoders/{LTX_CLIP_2}",
        },
        {
            "node_id": "15",
            "node_type": "LTXVSulphurAllInOne",
            "input": "vae",
            "value": LTX_VIDEO_VAE,
            "preferred_relative_path": f"vae/{LTX_VIDEO_VAE}",
        },
        {
            "node_id": "15",
            "node_type": "LTXVSulphurAllInOne",
            "input": "audio_vae",
            "value": LTX_AUDIO_VAE,
            "preferred_relative_path": f"vae/{LTX_AUDIO_VAE}",
        },
        {
            "node_id": "15",
            "node_type": "LTXVSulphurAllInOne",
            "input": "upscale_model",
            "value": LTX_UPSCALER,
            "preferred_relative_path": f"latent_upscale_models/{LTX_UPSCALER}",
        },
        {
            "node_id": "27",
            "node_type": "CheckpointLoaderSimple",
            "input": "ckpt_name",
            "value": LTX_MODEL,
            "preferred_relative_path": f"checkpoints/{LTX_MODEL}",
        },
        {
            "node_id": "28",
            "node_type": "LTXICLoRALoaderModelOnly",
            "input": "lora_name",
            "value": LTX_INGREDIENTS_ICLORA,
            "preferred_relative_path": (
                "loras/" + LTX_INGREDIENTS_ICLORA.replace("\\", "/")
            ),
        },
        {
            "node_id": "30",
            "node_type": "VAELoader",
            "input": "vae_name",
            "value": LTX_VIDEO_VAE,
            "preferred_relative_path": f"vae/{LTX_VIDEO_VAE}",
        },
    ]
    return {
        "schema": "sineforge.api-caller-workflow.v1",
        "id": WORKFLOW_ID,
        "name": (
            "LTX-2.3 + Krea 2 General Continuation Loop — Local GGUF JSON"
        ),
        "version": "1.0",
        "description": (
            "A reusable general-purpose continuation loop built from SineForge's LTX "
            "workflow and the library's existing Krea 2 image-generation "
            "settings. Scene or subject and next event are the primary controls; "
            "dialogue is optional JSON rather than a podcast-shaped form. Each "
            "cycle uses selectable local-GGUF JSON planning, creates and "
            "saves a fresh 16-bit Krea anchor, and uses a separate "
            "Ingredients/reference image as planner context, Krea image "
            "conditioning, and an LTX reference-conditioned Ingredients "
            "IC-LoRA model override. It animates the saved anchor with LTX-2.3, "
            "stores an FFV1 + FLAC master, extracts the true final tensor frame, "
            "saves it as 16-bit PNG, and passes the unchanged tensor into the "
            "next cycle. Loop counts 1+ are exact; 0 keeps running until "
            "ComfyUI Interrupt."
        ),
        "category": "Video & Animation",
        "subcategory": "LTX-2.3 · Automated continuation",
        "episode": None,
        "instructions": _instructions(),
        "tags": [
            "LTX-2.3",
            "Krea 2",
            "continuation",
            "loop",
            "16-bit PNG",
            "FFV1",
            "FLAC",
            "lossless handoff",
            "local GGUF planner",
            "Qwen 3.6 40B default",
            "strict JSON",
            "Ingredients IC-LoRA",
            "reference sheet",
            "Krea reference conditioning",
            "LTX reference conditioning",
            "read only",
            "general purpose",
        ],
        "requirements": {
            "custom_node_root": CUSTOM_NODE_ROOT,
            "shared_model_root": SHARED_MODEL_ROOT,
            "model_root_policy": "prefer_shared_comfy_root",
            "trusted_prompt_model_root": trusted_root,
            "preferred_prompt_model": MODEL_ID,
            "preferred_prompt_model_package": preferred_package,
            "prompt_model_selection": {
                "source": "recursive_local_gguf_package_discovery",
                "root": trusted_root,
                "default": MODEL_ID,
                "includes": "executable model GGUF files in named packages",
                "excludes": [
                    "mmproj-only files",
                    "embeddings",
                    "hosted models",
                    "API models",
                    "paths outside the local model root",
                ],
                "non_vision_behavior": (
                    "omit image attachments and continue with JSON text context"
                ),
            },
            "custom_node_packs": [
                "SineForge-Workflow-Bridge",
                "comfyui_starnodes",
                "ComfyUI-Easy-Use",
                "ComfyUI-VideoHelperSuite",
                "ComfyUI-Custom-Scripts",
                "comfyui-kjnodes",
                "ComfyUI-Conditioning-Rebalance",
                "ComfyUI-LTXVideo",
                "10S_Nodes",
            ],
            "unresolved_node_classes": [],
            "node_classes": sorted(
                {
                    node["class_type"]
                    for node in api.values()
                    if isinstance(node, dict)
                }
            ),
            "model_files": model_files,
            "media_inputs": [
                {
                    "node_id": "1",
                    "node_type": "LoadImage",
                    "input": "image",
                    "default": "example.png",
                    "purpose": "Initial or canonical continuation image",
                },
                {
                    "node_id": "26",
                    "node_type": "LoadImage",
                    "input": "image",
                    "default": "Krea2_00006_.png",
                    "purpose": (
                        "Ingredients/reference sheet used by local-model planning, "
                        "Krea image conditioning, and LTX reference conditioning"
                    ),
                }
            ],
            "prompt_field_count": 3,
            "output_node_count": 6,
            "prompt_contract": f"Workflows/LTX23/{PROMPT_FILENAME}",
            "semantic_manifest": f"Workflows/LTX23/{MANIFEST_FILENAME}",
            "qualification": {
                "status": "static_validated_not_rendered",
                "reason": (
                    "No expensive Krea or LTX generation was queued while "
                    "building the read-only workflow."
                ),
                "recommended_first_run": {
                    "loop_count": 1,
                    "seconds_per_cycle": 8,
                    "fps": 24,
                    "width": 768,
                    "height": 448,
                    "queue_depth": 1,
                },
            },
            "documentation_notes": (
                "The Krea model, Krea text encoder, Krea VAE, LTX checkpoint, "
                "LTX encoders, LTX VAEs, LTX upscaler, and official Ingredients "
                "IC-LoRA are exact physical files under "
                f"`{SHARED_MODEL_ROOT}`. Node 8 uses Krea2EncodeRebalance with "
                "the current frame and reference sheet. Nodes 27-31 produce the "
                "reference-conditioned LTX model_override. SaveImageAdvanced "
                "uses 16-bit PNG and returns the original tensor. VHS saves "
                "FFV1 video with FLAC audio. ImageFromBatch selects the true "
                "last frame before encoding. All prompt artifacts are JSON."
            ),
        },
        "workflow_status": "converted",
        "repository_managed": True,
        "read_only": True,
        "is_overridden": False,
        "source_kind": "repository_native_workflow",
        "source_id": SOURCE_ID,
        "source_filename": EDITOR_FILENAME,
        "source_archive": None,
        "source_entry": f"Workflows/LTX23/{EDITOR_FILENAME}",
        "source_workflow": editor,
        "source_workflow_sha256": _sha256(editor),
        "workflow": api,
        "sha256": _sha256(api),
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }


def _update_catalog(record: dict[str, Any]) -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    records = [
        item
        for item in catalog.get("records") or []
        if item.get("id") != WORKFLOW_ID
    ]
    records.append(
        {
            "id": record["id"],
            "name": record["name"],
            "category": record["category"],
            "subcategory": record["subcategory"],
            "episode": record["episode"],
            "workflow_status": record["workflow_status"],
            "source_archive": record["source_archive"],
            "source_entry": record["source_entry"],
            "sha256": record["sha256"],
            "source_workflow_sha256": record["source_workflow_sha256"],
        }
    )
    catalog["generated_at"] = TIMESTAMP
    catalog["workflow_count"] = len(records)
    catalog["category_counts"] = dict(
        sorted(
            Counter(
                item.get("category") or "Uncategorized" for item in records
            ).items()
        )
    )
    catalog["episode_counts"] = dict(
        sorted(
            Counter(
                item["episode"] for item in records if item.get("episode")
            ).items()
        )
    )
    catalog["status_counts"] = dict(
        sorted(
            Counter(
                item.get("workflow_status") or "converted"
                for item in records
            ).items()
        )
    )
    catalog["records"] = records
    _write_json(CATALOG_PATH, catalog)


def main() -> None:
    contract = json.loads(CONTRACT_SOURCE.read_text(encoding="utf-8"))
    editor = _editor_workflow(contract)
    api = _api_workflow(contract)
    manifest = _manifest(contract)
    record = _library_record(editor=editor, api=api, contract=contract)

    _write_json(WORKFLOW_DIR / EDITOR_FILENAME, editor)
    _write_json(WORKFLOW_DIR / API_FILENAME, api)
    _write_json(WORKFLOW_DIR / PROMPT_FILENAME, contract)
    _write_json(WORKFLOW_DIR / MANIFEST_FILENAME, manifest)
    _write_json(RECORDS_DIR / f"{WORKFLOW_ID}.json", record)
    _update_catalog(record)

    print(f"workflow_id={WORKFLOW_ID}")
    print(f"editor={WORKFLOW_DIR / EDITOR_FILENAME}")
    print(f"api={WORKFLOW_DIR / API_FILENAME}")
    print(f"record={RECORDS_DIR / f'{WORKFLOW_ID}.json'}")


if __name__ == "__main__":
    main()
