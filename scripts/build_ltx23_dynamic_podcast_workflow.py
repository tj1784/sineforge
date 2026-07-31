"""Build the repository-managed LTX-2.3 dynamic podcast workflow package.

The source of truth for the planner prompt is the JSON contract bundled with
the SineForge ComfyUI bridge. This script writes deterministic editor/API
workflow JSON, a semantic manifest, a copied prompt contract, and the native
Runner library record.
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
    / "ltx23_podcast_prompt_contract.json"
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

SOURCE_ID = "sineforge:ltx23-dynamic-podcast-qwen40b-v1"
WORKFLOW_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, SOURCE_ID))
EDITOR_FILENAME = "SineForge_LTX23_Dynamic_Podcast_Qwen40B.workflow.json"
API_FILENAME = "SineForge_LTX23_Dynamic_Podcast_Qwen40B.api.json"
PROMPT_FILENAME = "SineForge_LTX23_Dynamic_Podcast.prompt.json"
MANIFEST_FILENAME = "SineForge_LTX23_Dynamic_Podcast.manifest.json"
TIMESTAMP = "2026-07-30T12:00:00-07:00"

MODEL_ID = (
    "qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-"
    "neo-code-di-imatrix-max"
)
BASE_MODEL = "sulphur2Base_distilled.safetensors"
CLIP_1 = "gemma_3_12B_it_fp8_e4m3fn.safetensors"
CLIP_2 = "ltx-2.3_text_projection_bf16.safetensors"
VIDEO_VAE = "LTX23_video_vae_bf16.safetensors"
AUDIO_VAE = "LTX23_audio_vae_bf16.safetensors"
UPSCALER = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
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


def _input(name: str, type_name: str, link: int, *, shape: int | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"name": name, "type": type_name, "link": link}
    if shape is not None:
        item["shape"] = shape
    return item


def _output(name: str, type_name: str, links: list[int] | None) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_name,
        "links": links,
    }


def _properties(cnr_id: str, node_name: str, version: str) -> dict[str, Any]:
    return {
        "cnr_id": cnr_id,
        "ver": version,
        "Node name for S&R": node_name,
    }


def _editor_workflow(contract: dict[str, Any]) -> dict[str, Any]:
    default_request = json.dumps(
        contract["default_request"],
        ensure_ascii=False,
        indent=2,
    )
    readme = """# SineForge · LTX-2.3 Dynamic Podcast

1. Load a two-person podcast image. The original image goes directly to LTX as the first frame.
2. Edit `topic_request_json` only as valid JSON. MAN_A defaults to camera-left; MAN_B defaults to camera-right.
3. `new variation every run` creates a fresh topic, reply, unrelated pivot, JSON artifact, and video seed.
4. Local Qwen 3.6 40B is called through LM Studio on loopback. Comfy models are released first, and every LM Studio model must be confirmed unloaded before LTX can start.
5. LTX-2.3 renders one 8-second, two-pass, native-audio I2V clip. The accepted prompt is saved beside the video as `.json`.

**Reality check:** native two-person speech is experimental. Exact words, voice separation, and which face speaks are QA conditions, not guarantees. For verified current affairs, add approved source notes or treat the dialogue as fictional commentary."""

    nodes: list[dict[str, Any]] = [
        {
            "id": 1,
            "type": "LoadImage",
            "pos": [80, 420],
            "size": [320, 420],
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": [
                {
                    "name": "image",
                    "type": "COMBO",
                    "widget": {"name": "image"},
                    "link": None,
                },
                {
                    "name": "upload",
                    "type": "IMAGEUPLOAD",
                    "widget": {"name": "upload"},
                    "link": None,
                },
            ],
            "outputs": [
                _output("IMAGE", "IMAGE", [1, 2]),
                _output("MASK", "MASK", None),
            ],
            "title": "1 · Podcast reference image",
            "properties": _properties("comfy-core", "LoadImage", "0.5.1"),
            "widgets_values": ["example.png", "image"],
            "color": "#17304a",
            "bgcolor": "#102238",
        },
        {
            "id": 2,
            "type": "SineForgeLTXPodcastPlanner",
            "pos": [470, 350],
            "size": [650, 920],
            "flags": {},
            "order": 1,
            "mode": 0,
            "inputs": [
                _input("image", "IMAGE", 1, shape=7),
            ],
            "outputs": [
                _output("prompt_json", "STRING", [7]),
                _output("positive_prompt", "STRING", [3]),
                _output("negative_prompt", "STRING", [4]),
                _output("variation_seed", "INT", None),
                _output("video_seed", "INT", [5]),
                _output("duration_seconds", "INT", [6]),
                _output("output_prefix", "STRING", [13, 14]),
                _output("status_json", "STRING", [8]),
            ],
            "title": "2 · Local Qwen 3.6 40B · strict JSON + unload",
            "properties": _properties(
                "SineForge-Workflow-Bridge",
                "SineForgeLTXPodcastPlanner",
                "2",
            ),
            "widgets_values": [
                MODEL_ID,
                "new variation every run",
                20260730,
                "fixed",
                default_request,
                "[]",
                0.9,
                0.95,
                1600,
                900,
            ],
            "color": "#2b1d52",
            "bgcolor": "#1d163c",
        },
        {
            "id": 3,
            "type": "LTXVSulphurAllInOne",
            "pos": [1190, 350],
            "size": [520, 1040],
            "flags": {},
            "order": 2,
            "mode": 0,
            "inputs": [
                _input("image", "IMAGE", 2, shape=7),
                _input("positive_prompt", "STRING", 3),
                _input("negative_prompt", "STRING", 4),
                _input("seconds", "INT", 6),
                _input("seed", "INT", 5),
            ],
            "outputs": [
                _output("images", "IMAGE", [9]),
                _output("audio", "AUDIO", [10]),
                _output("frame_rate", "FLOAT", [11]),
            ],
            "title": "3 · LTX-2.3 · two-pass native-audio I2V",
            "properties": _properties(
                "comfyui_starnodes",
                "LTXVSulphurAllInOne",
                "local",
            ),
            "widgets_values": [
                "▶️ image_to_video",
                "",
                "",
                BASE_MODEL,
                CLIP_1,
                CLIP_2,
                VIDEO_VAE,
                AUDIO_VAE,
                UPSCALER,
                "Custom",
                "16:9",
                False,
                768,
                448,
                24,
                8,
                20260730,
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
            "id": 4,
            "type": "CreateVideo",
            "pos": [1800, 440],
            "size": [350, 260],
            "flags": {},
            "order": 3,
            "mode": 0,
            "inputs": [
                _input("images", "IMAGE", 9),
                _input("fps", "FLOAT", 11),
                _input("audio", "AUDIO", 10, shape=7),
                {
                    "name": "bit_depth",
                    "type": "INT",
                    "widget": {"name": "bit_depth"},
                    "link": None,
                },
            ],
            "outputs": [_output("VIDEO", "VIDEO", [12])],
            "title": "4 · Mux native video + audio",
            "properties": _properties("comfy-core", "CreateVideo", "0.5.1"),
            "widgets_values": [8],
            "color": "#4a3218",
            "bgcolor": "#35240f",
        },
        {
            "id": 5,
            "type": "SaveVideo",
            "pos": [2220, 390],
            "size": [430, 310],
            "flags": {},
            "order": 4,
            "mode": 0,
            "inputs": [
                _input("video", "VIDEO", 12),
                _input("filename_prefix", "STRING", 13),
                {
                    "name": "format",
                    "type": "COMBO",
                    "widget": {"name": "format"},
                    "link": None,
                },
                {
                    "name": "codec",
                    "type": "COMBO",
                    "widget": {"name": "codec"},
                    "link": None,
                },
            ],
            "outputs": [_output("video", "VIDEO", None)],
            "title": "5 · Save MP4",
            "properties": _properties("comfy-core", "SaveVideo", "0.5.1"),
            "widgets_values": [
                "SineForge/LTX23_Podcast/podcast",
                "mp4",
                "h264",
            ],
            "color": "#52311f",
            "bgcolor": "#3b2114",
        },
        {
            "id": 6,
            "type": "SaveText",
            "pos": [2220, 760],
            "size": [430, 250],
            "flags": {},
            "order": 5,
            "mode": 0,
            "inputs": [
                _input("text", "STRING", 7),
                _input("filename_prefix", "STRING", 14),
                {
                    "name": "format",
                    "type": "COMBO",
                    "widget": {"name": "format"},
                    "link": None,
                },
            ],
            "outputs": [_output("text", "STRING", None)],
            "title": "6 · Save exact prompt artifact · JSON",
            "properties": _properties("comfy-core", "SaveText", "0.5.1"),
            "widgets_values": [
                "SineForge/LTX23_Podcast/podcast",
                "json",
            ],
            "color": "#52311f",
            "bgcolor": "#3b2114",
        },
        {
            "id": 7,
            "type": "ShowText|pysssss",
            "pos": [1800, 760],
            "size": [350, 330],
            "flags": {},
            "order": 6,
            "mode": 0,
            "inputs": [_input("text", "STRING", 8)],
            "outputs": [_output("STRING", "STRING", None)],
            "title": "Planner status · seeds · hashes",
            "properties": _properties(
                "pysssss/ComfyUI-Custom-Scripts",
                "ShowText|pysssss",
                "local",
            ),
            "widgets_values": [""],
            "color": "#283140",
            "bgcolor": "#1c2430",
        },
        {
            "id": 8,
            "type": "MarkdownNote",
            "pos": [80, 30],
            "size": [2570, 230],
            "flags": {},
            "order": 7,
            "mode": 0,
            "inputs": [],
            "outputs": [],
            "title": "READ ME · one-click local planner → safe VRAM handoff → LTX-2.3",
            "properties": {},
            "widgets_values": [readme],
            "color": "#26354f",
            "bgcolor": "#172237",
        },
    ]

    links = [
        [1, 1, 0, 2, 0, "IMAGE"],
        [2, 1, 0, 3, 0, "IMAGE"],
        [3, 2, 1, 3, 1, "STRING"],
        [4, 2, 2, 3, 2, "STRING"],
        [5, 2, 4, 3, 4, "INT"],
        [6, 2, 5, 3, 3, "INT"],
        [7, 2, 0, 6, 0, "STRING"],
        [8, 2, 7, 7, 0, "STRING"],
        [9, 3, 0, 4, 0, "IMAGE"],
        [10, 3, 1, 4, 2, "AUDIO"],
        [11, 3, 2, 4, 1, "FLOAT"],
        [12, 4, 0, 5, 0, "VIDEO"],
        [13, 2, 6, 5, 1, "STRING"],
        [14, 2, 6, 6, 1, "STRING"],
    ]
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, SOURCE_ID + ":editor")),
        "revision": 0,
        "last_node_id": 8,
        "last_link_id": 14,
        "nodes": nodes,
        "links": links,
        "groups": [
            {
                "id": 1,
                "title": "INPUT · original image remains the first-frame anchor",
                "bounding": [50, 300, 380, 650],
                "color": "#3977a8",
                "flags": {},
            },
            {
                "id": 2,
                "title": "PLAN · local Qwen 3.6 40B · strict JSON · unload gate",
                "bounding": [440, 300, 710, 1120],
                "color": "#7357c8",
                "flags": {},
            },
            {
                "id": 3,
                "title": "RENDER · LTX-2.3 · one two-pass GPU job",
                "bounding": [1160, 300, 580, 1120],
                "color": "#3a9a76",
                "flags": {},
            },
            {
                "id": 4,
                "title": "OUTPUT · MP4 + immutable JSON prompt record",
                "bounding": [1760, 300, 920, 820],
                "color": "#b47a35",
                "flags": {},
            },
        ],
        "config": {},
        "extra": {
            "ds": {
                "scale": 0.82,
                "offset": [20, 80],
            },
            "frontendVersion": "1.47.10",
            "sineforge": {
                "schema_version": "sineforge.ltx23-dynamic-podcast-workflow/v1",
                "read_only_library_source": True,
                "prompt_contract": PROMPT_FILENAME,
            },
        },
        "version": 0.4,
    }


def _api_workflow(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "1": {
            "inputs": {"image": "example.png"},
            "class_type": "LoadImage",
            "_meta": {"title": "1 · Podcast reference image"},
        },
        "2": {
            "inputs": {
                "model": MODEL_ID,
                "variation_mode": "new variation every run",
                "seed": 20260730,
                "topic_request_json": json.dumps(
                    contract["default_request"],
                    ensure_ascii=False,
                    indent=2,
                ),
                "recent_topics_json": "[]",
                "temperature": 0.9,
                "top_p": 0.95,
                "max_tokens": 1600,
                "timeout_seconds": 900,
                "image": ["1", 0],
            },
            "class_type": "SineForgeLTXPodcastPlanner",
            "_meta": {
                "title": "2 · Local Qwen 3.6 40B · strict JSON + unload"
            },
        },
        "3": {
            "inputs": {
                "mode": "▶️ image_to_video",
                "positive_prompt": ["2", 1],
                "negative_prompt": ["2", 2],
                "base_model": BASE_MODEL,
                "clip_1": CLIP_1,
                "clip_2": CLIP_2,
                "vae": VIDEO_VAE,
                "audio_vae": AUDIO_VAE,
                "upscale_model": UPSCALER,
                "video_size": "Custom",
                "ratio": "16:9",
                "ratio_from_image": False,
                "custom_width": 768,
                "custom_height": 448,
                "frame_rate": 24,
                "seconds": ["2", 5],
                "seed": ["2", 4],
                "sigma_preset": "12 steps",
                "image": ["1", 0],
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
            },
            "class_type": "LTXVSulphurAllInOne",
            "_meta": {"title": "3 · LTX-2.3 · two-pass native-audio I2V"},
        },
        "4": {
            "inputs": {
                "images": ["3", 0],
                "fps": ["3", 2],
                "audio": ["3", 1],
                "bit_depth": 8,
            },
            "class_type": "CreateVideo",
            "_meta": {"title": "4 · Mux native video + audio"},
        },
        "5": {
            "inputs": {
                "video": ["4", 0],
                "filename_prefix": ["2", 6],
                "format": "mp4",
                "codec": "h264",
            },
            "class_type": "SaveVideo",
            "_meta": {"title": "5 · Save MP4"},
        },
        "6": {
            "inputs": {
                "text": ["2", 0],
                "filename_prefix": ["2", 6],
                "format": "json",
            },
            "class_type": "SaveText",
            "_meta": {"title": "6 · Save exact prompt artifact · JSON"},
        },
        "7": {
            "inputs": {"text": ["2", 7]},
            "class_type": "ShowText|pysssss",
            "_meta": {"title": "Planner status · seeds · hashes"},
        },
    }


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": "sineforge.semantic-workflow-manifest/v1",
        "template_id": "ltx23-dynamic-podcast-qwen40b-native-audio-v1",
        "workflow_name": "LTX-2.3 Dynamic Podcast — Local Qwen JSON + Native Audio",
        "editor_workflow": EDITOR_FILENAME,
        "api_workflow": API_FILENAME,
        "prompt_contract": PROMPT_FILENAME,
        "execution_policy": {
            "cloud_agents_allowed": False,
            "local_planner": "LM Studio",
            "planner_model": MODEL_ID,
            "planner_must_unload_before_render": True,
            "all_lm_studio_models_must_unload_before_render": True,
            "gpu_queue_depth": 1,
            "batch_size": 1,
            "native_audio": True,
            "default_mode": "new variation every run",
        },
        "bindings": {
            "scene_anchor_image": {
                "node_id": "1",
                "class_type": "LoadImage",
                "input": "image",
            },
            "planner_model": {
                "node_id": "2",
                "class_type": "SineForgeLTXPodcastPlanner",
                "input": "model",
            },
            "variation_mode": {
                "node_id": "2",
                "class_type": "SineForgeLTXPodcastPlanner",
                "input": "variation_mode",
            },
            "prompt_seed": {
                "node_id": "2",
                "class_type": "SineForgeLTXPodcastPlanner",
                "input": "seed",
            },
            "topic_request_json": {
                "node_id": "2",
                "class_type": "SineForgeLTXPodcastPlanner",
                "input": "topic_request_json",
                "media_type": "application/json",
            },
            "recent_topics_json": {
                "node_id": "2",
                "class_type": "SineForgeLTXPodcastPlanner",
                "input": "recent_topics_json",
                "media_type": "application/json",
            },
            "positive_prompt": {
                "source": {"node_id": "2", "output_index": 1},
                "target": {
                    "node_id": "3",
                    "class_type": "LTXVSulphurAllInOne",
                    "input": "positive_prompt",
                },
            },
            "negative_prompt": {
                "source": {"node_id": "2", "output_index": 2},
                "target": {
                    "node_id": "3",
                    "class_type": "LTXVSulphurAllInOne",
                    "input": "negative_prompt",
                },
            },
            "video_seed": {
                "source": {"node_id": "2", "output_index": 4},
                "target": {
                    "node_id": "3",
                    "class_type": "LTXVSulphurAllInOne",
                    "input": "seed",
                },
            },
            "duration_seconds": {
                "source": {"node_id": "2", "output_index": 5},
                "target": {
                    "node_id": "3",
                    "class_type": "LTXVSulphurAllInOne",
                    "input": "seconds",
                },
            },
            "output_prefix": {
                "source": {"node_id": "2", "output_index": 6},
                "targets": [
                    {
                        "node_id": "5",
                        "class_type": "SaveVideo",
                        "input": "filename_prefix",
                    },
                    {
                        "node_id": "6",
                        "class_type": "SaveText",
                        "input": "filename_prefix",
                    },
                ],
            },
            "width": {
                "node_id": "3",
                "class_type": "LTXVSulphurAllInOne",
                "input": "custom_width",
            },
            "height": {
                "node_id": "3",
                "class_type": "LTXVSulphurAllInOne",
                "input": "custom_height",
            },
            "fps": {
                "node_id": "3",
                "class_type": "LTXVSulphurAllInOne",
                "input": "frame_rate",
            },
            "quality_schedule": {
                "node_id": "3",
                "class_type": "LTXVSulphurAllInOne",
                "input": "sigma_preset",
            },
        },
        "limitations": [
            "Native LTX audio does not guarantee verbatim dialogue.",
            "Two-speaker voice separation and face-to-speaker assignment require QA.",
            "A continuous two-shot is experimental; production dialogue is stronger as one independently anchored speaker turn per job.",
            "Semantic novelty is encouraged with a fresh seed and category pair but cannot be mathematically guaranteed without recent-topic comparison.",
        ],
    }


def _instructions() -> str:
    return """1. Install or update the bundled `SineForge-Workflow-Bridge` with `scripts/Install-SineForgeWorkflowBridge.ps1`, then restart the main LTX ComfyUI once. The workflow requires the `SineForge · Local Qwen Podcast JSON` node.
2. Keep LM Studio's local server running at `http://127.0.0.1:1234`. The planner explicitly selects the installed Qwen 3.6 40B model; it does not use the currently selected global LM Studio model and never calls a hosted API.
3. Upload a two-person podcast image and patch `1.image`. The same original image is sent losslessly to LTX as its first-frame guide. A resized JPEG copy is used only for local Qwen visual analysis.
4. In `2.topic_request_json`, edit valid JSON only. Set `speaker_assignment.MAN_A` and `MAN_B` to match the people in the image. Default is camera-left and camera-right. Keep source notes in `source_notes` when dialogue must remain grounded.
5. Leave `variation_mode` at `new variation every run` for a fresh cryptographic variation seed, two topic categories, three short dialogue turns, prompt JSON, and LTX seed each run. Change it to `replay visible seed` to reproduce the visible seed as closely as local-model sampling allows.
6. Use `recent_topics_json` as a JSON array of recent topic names when you want stronger duplicate avoidance. The default `[]` is valid. The planner retries malformed or overlong output once under the same strict response schema.
7. Validate against the active ComfyUI registry before queueing. Confirm the exact Sulphur distilled checkpoint, Gemma encoder, LTX projection, video/audio VAEs, and spatial upscaler remain selectable.
8. Queue one job only. Before Qwen runs, the planner resolves the exact LM Studio catalog key, releases cached ComfyUI models, and unloads other local models. Its outer cleanup guard then unloads every LM Studio instance and refuses to hand the prompt to LTX unless the complete loaded-instance set is empty. This is required on the 24GB GPU.
9. The default render is one 8-second, 24fps, 768×448 custom-profile, two-pass LTX-2.3 I2V job with native audio and all optional LoRAs disabled. Start here; benchmark before increasing duration or resolution.
10. Each run saves an H.264 MP4 and its exact `.json` prompt record under the same variation prefix. The JSON includes the canonical request and approved source notes, recent topics, source-image tensor hash, planner and video seeds, topics, dialogue, positive/negative prompts, model ID, hashes, and complete LM Studio unload confirmation. The API Runner separately retains the submitted graph hash and output metadata needed for full render provenance.
11. Treat two-person native dialogue as experimental. Exact words, distinct voices, lip sync, and the correct face speaking are QA conditions rather than guarantees. For production, render one independently anchored five-second speaker turn per job and assemble the accepted turns.
12. LTX and the local planner are not news sources. Without approved source notes, dialogue about war, politics, elections, medicine, finance, or other changing facts is generated as fictional opinion or broad discussion, not verified reporting."""


def _library_record(
    *,
    editor: dict[str, Any],
    api: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "sineforge.api-caller-workflow.v1",
        "id": WORKFLOW_ID,
        "name": "LTX-2.3 Dynamic Podcast — Local Qwen JSON + Native Audio",
        "version": "1.0",
        "description": (
            "A one-click, image-driven LTX-2.3 podcast experiment that creates "
            "a fresh structured conversation locally before every render. The "
            "SineForge planner calls the installed Qwen 3.6 40B model through "
            "loopback LM Studio with a strict JSON Schema, saves the complete "
            "prompt as `.json`, derives a new render seed, and confirms every "
            "LM Studio model is unloaded before the two-pass Sulphur LTX-2.3 "
            "native-audio I2V node can claim VRAM. The default eight-second shot "
            "has MAN_A open a "
            "topic, MAN_B reply, and MAN_A pivot to an unrelated topic while "
            "the supplied image remains the first-frame identity and set "
            "anchor. Fresh mode varies both meaning and pixels; replay mode "
            "locks the visible seed. Two-face lip assignment and verbatim "
            "native dialogue remain experimental and require review."
        ),
        "category": "Video & Animation",
        "subcategory": "LTX-2.3 · Dynamic podcasts",
        "episode": None,
        "instructions": _instructions(),
        "tags": [
            "LTX-2.3",
            "image to video",
            "podcast",
            "talking characters",
            "native audio",
            "local Qwen 3.6 40B",
            "strict JSON",
            "dynamic prompt",
            "two pass",
            "read only",
        ],
        "requirements": {
            "custom_node_root": (
                "C:\\ComfyUI\\LTX\\ComfyUI\\ComfyUI\\custom_nodes"
            ),
            "custom_node_packs": [
                "SineForge-Workflow-Bridge",
                "comfyui_starnodes",
                "ComfyUI-Custom-Scripts",
            ],
            "unresolved_node_classes": [],
            "node_classes": sorted(
                {
                    node["class_type"]
                    for node in api.values()
                    if isinstance(node, dict)
                }
            ),
            "model_files": [
                {
                    "node_id": "3",
                    "node_type": "LTXVSulphurAllInOne",
                    "input": "base_model",
                    "value": BASE_MODEL,
                },
                {
                    "node_id": "3",
                    "node_type": "LTXVSulphurAllInOne",
                    "input": "clip_1",
                    "value": CLIP_1,
                },
                {
                    "node_id": "3",
                    "node_type": "LTXVSulphurAllInOne",
                    "input": "clip_2",
                    "value": CLIP_2,
                },
                {
                    "node_id": "3",
                    "node_type": "LTXVSulphurAllInOne",
                    "input": "vae",
                    "value": VIDEO_VAE,
                },
                {
                    "node_id": "3",
                    "node_type": "LTXVSulphurAllInOne",
                    "input": "audio_vae",
                    "value": AUDIO_VAE,
                },
                {
                    "node_id": "3",
                    "node_type": "LTXVSulphurAllInOne",
                    "input": "upscale_model",
                    "value": UPSCALER,
                },
            ],
            "local_services": [
                {
                    "service": "LM Studio",
                    "url": "http://127.0.0.1:1234",
                "model": MODEL_ID,
                "cloud": False,
                "unload_required_before_render": True,
                "all_models_unloaded_before_render": True,
                }
            ],
            "media_inputs": [
                {
                    "node_id": "1",
                    "node_type": "LoadImage",
                    "input": "image",
                    "default": "example.png",
                    "purpose": "Two-person podcast first-frame anchor",
                }
            ],
            "prompt_field_count": 2,
            "output_node_count": 3,
            "prompt_contract": (
                f"Workflows/LTX23/{PROMPT_FILENAME}"
            ),
            "semantic_manifest": (
                f"Workflows/LTX23/{MANIFEST_FILENAME}"
            ),
            "qualification": {
                "status": "static_validated_not_rendered",
                "reason": (
                    "No expensive generation was queued while building the "
                    "read-only library entry."
                ),
                "recommended_first_run": {
                    "seconds": 8,
                    "fps": 24,
                    "width": 768,
                    "height": 448,
                    "sigma_preset": "12 steps",
                    "queue_depth": 1,
                },
            },
            "documentation_notes": (
                "The local planner's system prompt, user request, and generated "
                "record are JSON. `SaveText` is fixed to format=json. The record "
                "retains the canonical request, recent-topic list, approved source "
                "notes, source-image tensor hash, planner and video seeds, and the "
                "LTX positive/negative strings. A resized JPEG is sent only to "
                "local Qwen for visual analysis; LTX receives the original image "
                "tensor. The API Runner's submitted graph hash and output metadata "
                "remain the render-provenance record. Native two-speaker speech is "
                "probabilistic."
            ),
        },
        "workflow_status": "converted",
        "repository_managed": True,
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
        sorted(Counter(item.get("category") or "Uncategorized" for item in records).items())
    )
    catalog["episode_counts"] = dict(
        sorted(
            Counter(
                item["episode"]
                for item in records
                if item.get("episode")
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
    manifest = _manifest()
    record = _library_record(editor=editor, api=api)

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
