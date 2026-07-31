#!/usr/bin/env python3
"""Create the local Sulphur 2 FP8 I2V workflow from the creator's base graph.

The source graph is SulphurAI's published ``ltx23_i2v base.json`` workflow.
This transformation deliberately preserves its two-stage structure while:

* selecting the full Sulphur 2 FP8 development checkpoint everywhere it is
  independently referenced;
* removing the obsolete ``sulphur_final`` LoRA applications so Sulphur is not
  applied twice;
* applying the creator-provided cond-safe distillation adapter at 0.25/0.50;
* replacing unavailable resize nodes with ComfyUI core nodes installed on this
  machine; and
* using a reproducible, sharper five-second I2V baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any


SOURCE_SHA256 = "571c572d7d377a4c4c102331731ac93862e60cb4b53fd121d554e75adeeafb08"
SULPHUR_CHECKPOINT = (
    r"LTX 2.3\Sulphur 2\sulphur2BaseQuants_dev.safetensors"
)
CONDSAFE_LORA = (
    r"LTX\2.3\Sulphur\distill_loras"
    r"\ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors"
)
GEMMA_ENCODER = "gemma_3_12B_it_fp8_e4m3fn.safetensors"
SPATIAL_UPSCALER = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Creator base workflow JSON")
    parser.add_argument("output", type=Path, help="Tuned workflow destination")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def node_map(workflow: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {node["id"]: node for node in workflow["nodes"]}


def set_title(node: dict[str, Any], title: str) -> None:
    node["title"] = title


def transform(workflow: dict[str, Any], source: Path) -> dict[str, Any]:
    if workflow.get("version") != 0.4:
        raise ValueError(f"Expected ComfyUI workflow version 0.4, got {workflow.get('version')!r}")

    actual_hash = sha256(source)
    if actual_hash != SOURCE_SHA256:
        raise ValueError(
            "Source does not match SulphurAI's audited base workflow: "
            f"expected {SOURCE_SHA256}, got {actual_hash}"
        )

    nodes = node_map(workflow)

    # The downloaded FP8 file is a complete checkpoint. These three selectors
    # independently load its model, audio VAE, and text-projection components.
    nodes[44]["widgets_values"] = [SULPHUR_CHECKPOINT]
    set_title(nodes[44], "Sulphur 2 FP8 Dev · Full Checkpoint")
    nodes[44]["properties"]["models"] = [
        {
            "name": "sulphur2BaseQuants_dev.safetensors",
            "url": "https://civitai.red/api/download/models/2953675",
            "directory": "checkpoints",
        }
    ]
    nodes[4]["widgets_values"] = [SULPHUR_CHECKPOINT]
    set_title(nodes[4], "Sulphur 2 · Audio VAE")
    nodes[4]["properties"]["models"] = [
        {
            "name": "sulphur2BaseQuants_dev.safetensors",
            "url": "https://civitai.red/api/download/models/2953675",
            "directory": "checkpoints",
        }
    ]
    nodes[5]["widgets_values"] = [GEMMA_ENCODER, SULPHUR_CHECKPOINT, "default"]
    set_title(nodes[5], "Installed Gemma FP8 + Sulphur Projection")
    nodes[5]["properties"]["models"] = [
        {
            "name": "sulphur2BaseQuants_dev.safetensors",
            "url": "https://civitai.red/api/download/models/2953675",
            "directory": "checkpoints",
        },
        {
            "name": GEMMA_ENCODER,
            "url": (
                "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/"
                "split_files/text_encoders/"
                "gemma_3_12B_it_fp8_e4m3fn.safetensors"
            ),
            "directory": "text_encoders",
        },
    ]

    # Use the installed current LTX 2.3 spatial upscaler.
    nodes[39]["widgets_values"] = [SPATIAL_UPSCALER]
    set_title(nodes[39], "LTX 2.3 Spatial Upscaler x2 · v1.1")
    nodes[39]["properties"]["models"] = [
        {
            "name": SPATIAL_UPSCALER,
            "url": (
                "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/"
                "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
            ),
            "directory": "latent_upscale_models",
        }
    ]

    # Repurpose the creator graph's bypassed first-pass adapter node and retain
    # its active high-resolution adapter. This follows the current LTX HQ
    # 0.25/0.50 two-stage strengths and avoids stacking distillation adapters.
    for node_id, strength, stage in ((59, 0.25, "Stage 1"), (49, 0.50, "Stage 2")):
        node = nodes[node_id]
        node["mode"] = 0
        node["widgets_values"] = [CONDSAFE_LORA, strength]
        set_title(node, f"{stage} Condsafe Distill · {strength:.2f}")
        node["properties"]["models"] = [
            {
                "name": (
                    "ltx-2.3-22b-distilled-lora-1.1_"
                    "fro90_ceil72_condsafe.safetensors"
                ),
                "url": (
                    "https://huggingface.co/SulphurAI/Sulphur-2-base/"
                    "resolve/main/distill_loras/"
                    "ltx-2.3-22b-distilled-lora-1.1_"
                    "fro90_ceil72_condsafe.safetensors"
                ),
                "directory": "loras",
            }
        ]

    # Remove both active legacy sulphur_final nodes. The creator explicitly says
    # to use the full Sulphur checkpoint or the Sulphur LoRA, never both.
    # Remove three disconnected leftovers as well so no missing model selections
    # survive in the visual graph.
    removed_node_ids = {7, 11, 46, 60, 65}
    workflow["nodes"] = [
        node for node in workflow["nodes"] if node["id"] not in removed_node_ids
    ]

    rewired_links: list[list[Any]] = []
    for link in workflow["links"]:
        link_id = link[0]
        if link_id == 90:
            # Preview-overridden full checkpoint -> stage-2 cond-safe adapter.
            link = [90, 64, 0, 49, 0, "MODEL"]
        elif link_id == 91:
            # Stage-1 cond-safe adapter -> guided first-pass sampler.
            link = [91, 59, 0, 42, 0, "MODEL"]
        elif link_id in {92, 101}:
            continue

        if link[1] in removed_node_ids or link[3] in removed_node_ids:
            continue
        rewired_links.append(link)
    workflow["links"] = rewired_links

    nodes = node_map(workflow)
    nodes[64]["outputs"][0]["links"] = [90, 102]
    nodes[59]["outputs"][0]["links"] = [91]
    nodes[42]["inputs"][0]["link"] = 91
    nodes[49]["inputs"][0]["link"] = 90

    # Replace unavailable third-party resize nodes with installed ComfyUI core
    # nodes. One megapixel plus a 64-pixel resolution step gives aligned
    # dimensions (approximately 1344x768 for a 16:9 source); stage one receives
    # a Lanczos 0.5x version.
    resize = nodes[68]
    resize["type"] = "ImageScaleToTotalPixels"
    resize["size"] = [315, 82]
    resize["widgets_values"] = ["lanczos", 1.0, 64]
    resize["properties"] = {
        "cnr_id": "comfy-core",
        "ver": "0.19.3",
        "Node name for S&R": "ImageScaleToTotalPixels",
        "ue_properties": {
            "widget_ue_connectable": {},
            "input_ue_unconnectable": {},
            "version": "7.4.1",
        },
    }
    set_title(resize, "1.0 MP Lanczos · 64-pixel aligned")

    half_scale = nodes[70]
    half_scale["type"] = "ImageScaleBy"
    half_scale["size"] = [315, 82]
    half_scale["inputs"][0]["name"] = "image"
    half_scale["widgets_values"] = ["lanczos", 0.5]
    half_scale["properties"] = {
        "cnr_id": "comfy-core",
        "ver": "0.19.3",
        "Node name for S&R": "ImageScaleBy",
        "ue_properties": {
            "widget_ue_connectable": {},
            "input_ue_unconnectable": {},
            "version": "7.4.1",
        },
    }
    set_title(half_scale, "Stage 1 Reference · Lanczos 0.5x")

    # Sharper, shorter, reproducible I2V baseline. LTX temporal lengths follow
    # 8n+1: 121 frames at 24 fps is five seconds.
    nodes[15]["widgets_values"] = [18]
    set_title(nodes[15], "LTX I2V Preprocess · CRF 18")
    nodes[27]["widgets_values"] = [121, "fixed"]
    set_title(nodes[27], "Frames · 121 = 5 seconds at 24 fps")
    nodes[26]["widgets_values"] = [24, "fixed"]
    set_title(nodes[26], "FPS · 24")
    nodes[2]["widgets_values"][1] = "fixed"
    set_title(nodes[2], "Stage 1 Seed · fixed for A/B tests")
    nodes[47]["widgets_values"] = [30, 2.72, 0.8, True, 0]
    set_title(nodes[47], "Stage 1 LTX Scheduler · 30 steps")
    nodes[42]["widgets_values"] = [3.0]
    set_title(nodes[42], "Stage 1 CFG · 3.0")
    set_title(nodes[22], "Stage 1 I2V Strength · 0.80")
    set_title(nodes[14], "Stage 2 I2V Strength · 1.00")
    set_title(nodes[58], "Stage 2 Distilled Sigmas · 5 intervals")

    # The original bundled image is not installed here. Select a known local
    # placeholder so the workflow opens cleanly; the node title makes the
    # required user action explicit.
    nodes[67]["widgets_values"] = ["example.png", "image"]
    set_title(nodes[67], "Replace With Your I2V Start Image")

    nodes[29]["widgets_values"] = [
        "REPLACE WITH ONE CONCISE, CHRONOLOGICAL 5-SECOND SHOT DESCRIPTION. "
        "Include subject identity, setting, camera framing and movement, action "
        "over time, lighting, and intended synchronized audio. Photorealistic "
        "live-action cinematography, natural skin texture, coherent anatomy, "
        "stable identity, physically plausible motion, crisp focal-plane "
        "detail, realistic depth of field."
    ]
    set_title(nodes[29], "Positive Prompt · Sulphur 2 has no trigger word")
    nodes[41]["widgets_values"] = [
        "low resolution, blurry, soft focus, motion smear, compression artifacts, "
        "waxy skin, plastic skin, oversmoothed skin, deformed anatomy, bad hands, "
        "extra digits, duplicated limbs, flicker, frame jitter, inconsistent "
        "identity, inconsistent lighting, cartoon, illustration, CGI, 3D render, "
        "video game, childish, text, subtitles, watermark, logo, silent or muted "
        "audio, distorted voice, robotic voice, echo, off-sync audio, incorrect "
        "dialogue"
    ]
    set_title(nodes[41], "Negative Prompt · photoreal clarity")
    nodes[45]["widgets_values"][0] = "video/Sulphur2_I2V_HQ"
    set_title(nodes[45], "Sulphur 2 I2V Output")

    group_titles = {
        "Model": "Sulphur 2 FP8 · Full Checkpoint",
        "Generate Low Resolution": "Stage 1 · 30-step Low Resolution",
        "Generate High Resolution": "Stage 2 · Condsafe Refinement",
        "Lantent Upscale": "Latent x2 Upscale",
        "Video Settings": "Video Settings · 121f / 24fps / 5s",
        "Image Preprocess": "Image Preprocess · 1MP Lanczos + CRF18",
    }
    for group in workflow.get("groups", []):
        if group.get("title") in group_titles:
            group["title"] = group_titles[group["title"]]

    workflow["id"] = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "sineforge://workflows/sulphur2-fp8-dev-i2v-hq-5s/2026-07-29",
        )
    )
    workflow["revision"] = 0
    workflow.setdefault("extra", {})["sineforge"] = {
        "profile": "Sulphur 2 FP8 I2V HQ baseline",
        "generated_at": "2026-07-29",
        "derived_from": source.name,
        "derived_from_sha256": actual_hash,
        "checkpoint": SULPHUR_CHECKPOINT,
        "checkpoint_expected_bytes": 29161842846,
        "checkpoint_sha256": (
            "41c999575859c528ff108022246a5524960a778c18742696971c9b0aadb4f70f"
        ),
        "distill_lora": CONDSAFE_LORA,
        "trigger_word": None,
        "settings": {
            "frames": 121,
            "fps": 24,
            "stage_1_steps": 30,
            "stage_1_cfg": 3.0,
            "stage_1_distill_strength": 0.25,
            "stage_2_distill_strength": 0.5,
            "stage_1_i2v_strength": 0.8,
            "stage_2_i2v_strength": 1.0,
            "preprocess_crf": 18,
            "target_megapixels": 1.0,
            "resolution_step": 64,
        },
        "notes": [
            "Full Sulphur checkpoint: legacy sulphur_final LoRA nodes removed.",
            "No Sulphur 2 trigger word is documented.",
            "Replace the Load Image and positive prompt before queueing.",
        ],
    }
    return workflow


def validate(workflow: dict[str, Any]) -> None:
    nodes = node_map(workflow)
    if len(nodes) != len(workflow["nodes"]):
        raise ValueError("Duplicate node IDs")

    link_ids: set[int] = set()
    links_by_id: dict[int, list[Any]] = {}
    for link in workflow["links"]:
        link_id, source, _source_slot, target, _target_slot, _kind = link
        if link_id in link_ids:
            raise ValueError(f"Duplicate link ID {link_id}")
        link_ids.add(link_id)
        links_by_id[link_id] = link
        if source not in nodes or target not in nodes:
            raise ValueError(f"Dangling link {link_id}: {source} -> {target}")

    for node in workflow["nodes"]:
        for slot, input_spec in enumerate(node.get("inputs", [])):
            link_id = input_spec.get("link")
            if link_id is None:
                continue
            link = links_by_id.get(link_id)
            if link is None or link[3] != node["id"] or link[4] != slot:
                raise ValueError(
                    f"Node {node['id']} input {slot} has inconsistent link {link_id}"
                )
        for slot, output_spec in enumerate(node.get("outputs", [])):
            for link_id in output_spec.get("links") or []:
                link = links_by_id.get(link_id)
                if link is None or link[1] != node["id"] or link[2] != slot:
                    raise ValueError(
                        f"Node {node['id']} output {slot} has inconsistent link {link_id}"
                    )

    required_nodes = {
        "CheckpointLoaderSimple",
        "ImageScaleToTotalPixels",
        "ImageScaleBy",
        "LTXVScheduler",
        "LTXVImgToVideoInplace",
        "LatentUpscaleModelLoader",
        "SaveVideo",
    }
    present_types = {node["type"] for node in workflow["nodes"]}
    missing_types = required_nodes - present_types
    if missing_types:
        raise ValueError(f"Required node types missing: {sorted(missing_types)}")

    serialized = json.dumps(workflow)
    forbidden = {
        "sulphur_final.safetensors",
        "ltx-2.3-22b-dev-fp8.safetensors",
        "ltx-2.3-spatial-upscaler-x2-1.0.safetensors",
        "gemma_3_12B_it_fp4_mixed.safetensors",
        '"ResizeImageResolution"',
        '"ImageScaleDownBy"',
    }
    found = {value for value in forbidden if value in serialized}
    if found:
        raise ValueError(f"Obsolete references remain: {sorted(found)}")


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    workflow = json.loads(source.read_text(encoding="utf-8"))
    workflow = transform(workflow, source)
    validate(workflow)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)
    print(f"nodes={len(workflow['nodes'])} links={len(workflow['links'])}")
    print(f"sha256={sha256(output)}")


if __name__ == "__main__":
    main()
