"""Build the repository-managed Krea 2 character Ingredients-sheet workflow.

The workflow is deliberately local and deterministic:

* the SineForge planner exposes every installed local LM Studio GGUF package,
  with the approved Qwen 3.6 40B package selected by default;
* one uploaded identity image is reused for every Krea 2 conditioning branch;
* four independently sampled views are generated from strict JSON planning;
* the views are composed with the installed LTX Ingredients grid node; and
* both the 16-bit PNG sheet and the complete prompt/provenance JSON are saved.

This script registers the generated package in SineForge's repository workflow
library.  It does not download, copy, or mutate any model.
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
    / "krea2_character_ingredients_prompt_contract.json"
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

SOURCE_ID = "sineforge:krea2-character-ingredients-v1"
WORKFLOW_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, SOURCE_ID))
EDITOR_FILENAME = "SineForge_Krea2_Character_Ingredients.workflow.json"
API_FILENAME = "SineForge_Krea2_Character_Ingredients.api.json"
MANIFEST_FILENAME = "SineForge_Krea2_Character_Ingredients.manifest.json"
PROMPT_FILENAME = "SineForge_Krea2_Character_Ingredients.prompt.json"
TIMESTAMP = "2026-07-31T03:00:00-07:00"

MODEL_ID = (
    "qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-"
    "neo-code-di-imatrix-max"
)
KREA_MODEL = "krea2TurboOfficialComfy_krea2RawInt8Convrot.safetensors"
KREA_CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
KREA_VAE = "qwen_image_vae.safetensors"
SHARED_MODEL_ROOT = r"C:\ComfyUI\ComfyUI_Shared_Folders\models"
CUSTOM_NODE_ROOT = r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes"
TRUSTED_MODEL_ROOT = r"C:\Users\Blokey\.lmstudio\models"
REFERENCE_DEFAULT = "SineForge/CharacterIngredients/jesus_white_robe_highres_ingredients.png"
TOKEN_STRENGTHS = ("max", "high", "high", "normal")

FALLBACK_PROFILE = {
    "schema_version": "sineforge.character-profile/v1",
    "character_id": "character_001",
    "character_name": "Alex Rowan",
    "character_kind": "fictional adult human",
    "identity_brief": (
        "A composed adult presenter with a distinctive oval face and calm, "
        "approachable presence."
    ),
    "age_presentation": "approximately 35 years old",
    "face_identity": (
        "oval face, balanced cheekbones, straight nose, softly defined jaw, "
        "medium brown eyes, natural brows"
    ),
    "hair": "short dark brown textured hair with a neat side part",
    "complexion": (
        "medium warm complexion with realistic pores and subtle natural variation"
    ),
    "body_build": "average-height balanced build with natural adult proportions",
    "wardrobe": [
        "charcoal tailored jacket",
        "soft blue open-collar shirt",
        "dark neutral trousers",
        "plain dark shoes",
    ],
    "accessories": ["small matte silver wristwatch"],
    "identity_locks": [
        "same face shape and facial proportions in every view",
        "same age, hairline, hairstyle, complexion, wardrobe, and accessories",
        "natural anatomy and realistic skin texture",
    ],
    "visual_style": (
        "high-resolution photorealistic studio character reference photography"
    ),
    "background": (
        "clean seamless warm-gray studio background with no visible horizon"
    ),
    "avoid": [
        "identity drift",
        "beautification that changes facial proportions",
        "text, labels, logos, watermarks, borders, or extra people",
    ],
}


def _fallback_contract() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "sineforge.krea2-character-ingredients-prompt-contract/v1",
        "planner_model": MODEL_ID,
        "trusted_lm_studio_model_root": TRUSTED_MODEL_ROOT,
        "trusted_planner_models": {
            MODEL_ID: {
                "publisher": "DavidAU",
                "package": (
                    "Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-"
                    "Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-GGUF"
                ),
                "required_relative_files": [
                    (
                        "DavidAU/Qwen3.6-40B-Claude-4.6-Opus-Deckard-"
                        "Heretic-Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-"
                        "GGUF/Qwen3.6-40B-Deck-Opus-NEO-CODE-HERE-2T-OT-"
                        "Q4_K_S.gguf"
                    ),
                    (
                        "DavidAU/Qwen3.6-40B-Claude-4.6-Opus-Deckard-"
                        "Heretic-Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-"
                        "GGUF/mmproj-F32.gguf"
                    ),
                ],
            }
        },
        "variation_modes": ["new variation every run", "replay visible seed"],
        "default_character_profile": FALLBACK_PROFILE,
        "planner_defaults": {
            "seed": 20260731,
            "temperature": 0.55,
            "top_p": 0.9,
            "max_tokens": 2600,
            "timeout_seconds": 900,
        },
        "output_contract": {
            "format": "application/json",
            "views": [
                "face_front_prompt",
                "face_three_quarter_prompt",
                "profile_prompt",
                "body_turnaround_prompt",
            ],
            "rule": (
                "Every view prompt must preserve one canonical identity and "
                "locked wardrobe while changing only the requested viewpoint."
            ),
        },
    }


def _load_contract() -> dict[str, Any]:
    if CONTRACT_SOURCE.is_file():
        return json.loads(CONTRACT_SOURCE.read_text(encoding="utf-8"))
    return _fallback_contract()


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


def _first_mapping(
    contract: dict[str, Any],
    *keys: str,
) -> dict[str, Any] | None:
    for key in keys:
        value = contract.get(key)
        if isinstance(value, dict):
            return value
    return None


def _planner_values(contract: dict[str, Any]) -> dict[str, Any]:
    profile = _first_mapping(
        contract,
        "default_character_profile",
        "default_profile",
        "default_request",
    )
    if profile is None:
        profile = dict(FALLBACK_PROFILE)
    else:
        profile = dict(profile)

    defaults = _first_mapping(
        contract,
        "planner_defaults",
        "generation_defaults",
        "defaults",
    ) or {}
    variation_modes = contract.get("variation_modes")
    if not isinstance(variation_modes, list) or not variation_modes:
        variation_modes = ["new variation every run", "replay visible seed"]
    return {
        "model": str(contract.get("planner_model") or MODEL_ID),
        "variation_mode": str(variation_modes[0]),
        "seed": int(defaults.get("seed", 20260731)),
        "character_profile_json": json.dumps(
            profile,
            ensure_ascii=False,
            indent=2,
        ),
        "temperature": float(defaults.get("temperature", 0.55)),
        "top_p": float(defaults.get("top_p", 0.9)),
        "max_tokens": int(defaults.get("max_tokens", 2600)),
        "timeout_seconds": int(defaults.get("timeout_seconds", 900)),
    }


def _discover_local_llm_packages(root_value: str) -> dict[str, Any]:
    """Mirror the planner's package-level GGUF inventory for library metadata."""

    root = Path(root_value).resolve(strict=True)
    if not root.is_dir():
        raise RuntimeError(f"LM Studio model root is not a directory: {root}")
    packages: dict[str, dict[str, Any]] = {}
    package_directories = sorted(
        {
            path.resolve(strict=True).parent
            for path in root.rglob("*.gguf")
            if path.is_file()
            and not path.name.casefold().startswith("mmproj")
        },
        key=lambda path: path.as_posix().casefold(),
    )
    for directory in package_directories:
        relative_directory = directory.relative_to(root)
        package_name = relative_directory.name
        model_key = package_name
        if model_key.casefold().endswith("-gguf"):
            model_key = model_key[:-5]
        model_key = model_key.casefold()
        if model_key in packages:
            raise RuntimeError(
                f"Ambiguous local LM Studio model key: {model_key}"
            )
        files = []
        for file_path in sorted(
            directory.glob("*.gguf"),
            key=lambda item: item.name.casefold(),
        ):
            stat = file_path.stat()
            files.append(
                {
                    "relative_path": file_path.relative_to(root).as_posix(),
                    "role": (
                        "vision_projector"
                        if file_path.name.casefold().startswith("mmproj")
                        else "model"
                    ),
                    "size_bytes": stat.st_size,
                }
            )
        packages[model_key] = {
            "model": model_key,
            "publisher": (
                relative_directory.parts[0]
                if len(relative_directory.parts) > 1
                else ""
            ),
            "package": package_name,
            "relative_directory": relative_directory.as_posix(),
            "files": files,
            "supports_local_vision_files": any(
                item["role"] == "vision_projector" for item in files
            ),
        }
    if not packages:
        raise RuntimeError(
            f"No selectable local GGUF model package was found beneath {root}."
        )
    return packages


def _api_workflow(contract: dict[str, Any]) -> dict[str, Any]:
    planner = _planner_values(contract)
    png16 = {
        "format": "png",
        "bit_depth": "16-bit",
        "input_color_space": "sRGB",
    }
    workflow: dict[str, Any] = {
        "1": {
            "inputs": {
                **planner,
                "reference_image": ["2", 0],
            },
            "class_type": "SineForgeKrea2CharacterIngredientsPlanner",
            "_meta": {
                "title": "1 · Selectable local-model JSON character-sheet planner"
            },
        },
        "2": {
            "inputs": {"image": REFERENCE_DEFAULT},
            "class_type": "LoadImage",
            "_meta": {"title": "2 · Primary face / identity reference"},
        },
        "6": {
            "inputs": {"unet_name": KREA_MODEL, "weight_dtype": "default"},
            "class_type": "UNETLoader",
            "_meta": {"title": "6 · Local Krea 2 model"},
        },
        "7": {
            "inputs": {
                "clip_name": KREA_CLIP,
                "type": "krea2",
                "device": "default",
            },
            "class_type": "CLIPLoader",
            "_meta": {"title": "7 · Local Krea 2 Qwen3-VL encoder"},
        },
        "8": {
            "inputs": {"vae_name": KREA_VAE},
            "class_type": "VAELoader",
            "_meta": {"title": "8 · Local Krea 2 VAE"},
        },
    }

    branches = [
        ("10", "11", "12", "13", "14", 1, 5, 1024, 1024, "Front face"),
        ("20", "21", "22", "23", "24", 2, 6, 1024, 1024, "Three-quarter face"),
        ("30", "31", "32", "33", "34", 3, 7, 1024, 1024, "Side profile"),
        ("40", "41", "42", "43", "44", 4, 8, 1024, 1536, "Body turnaround"),
    ]
    for (
        encode_id,
        negative_id,
        latent_id,
        sampler_id,
        decode_id,
        prompt_index,
        seed_index,
        width,
        height,
        label,
    ) in branches:
        workflow[encode_id] = {
            "inputs": {
                "text": ["1", prompt_index],
                "clip": ["7", 0],
                "image1": ["2", 0],
                "image1_tokens": TOKEN_STRENGTHS[0],
                "image2": ["2", 0],
                "image2_tokens": TOKEN_STRENGTHS[1],
                "image3": ["2", 0],
                "image3_tokens": TOKEN_STRENGTHS[2],
                "image4": ["2", 0],
                "image4_tokens": TOKEN_STRENGTHS[3],
            },
            "class_type": "Krea2EncodeRebalance",
            "_meta": {
                "title": (
                    f"{encode_id} · {label} · four-reference conditioning"
                )
            },
        }
        workflow[negative_id] = {
            "inputs": {"conditioning": [encode_id, 0]},
            "class_type": "ConditioningZeroOut",
            "_meta": {"title": f"{negative_id} · {label} negative"},
        }
        workflow[latent_id] = {
            "inputs": {"width": width, "height": height, "batch_size": 1},
            "class_type": "EmptySD3LatentImage",
            "_meta": {
                "title": f"{latent_id} · {label} latent · {width}×{height}"
            },
        }
        workflow[sampler_id] = {
            "inputs": {
                "seed": ["1", seed_index],
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "er_sde",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["6", 0],
                "positive": [encode_id, 0],
                "negative": [negative_id, 0],
                "latent_image": [latent_id, 0],
            },
            "class_type": "KSampler",
            "_meta": {
                "title": f"{sampler_id} · Independent {label} sampler"
            },
        }
        workflow[decode_id] = {
            "inputs": {"samples": [sampler_id, 0], "vae": ["8", 0]},
            "class_type": "VAEDecode",
            "_meta": {"title": f"{decode_id} · Decode {label}"},
        }

    workflow.update(
        {
            "50": {
                "inputs": {
                    "image_count": 4,
                    "layout": "wide_bottom",
                    "output_width": 1536,
                    "output_height": 1920,
                    "columns": 0,
                    "gutter": 4,
                    "outer_padding": 4,
                    "corner_radius": 0,
                    "fit_mode": "contain_pad",
                    "batch_mode": "first_image_only",
                    "background_color": "#000000",
                    "cell_background_color": "#000000",
                    "image1": ["14", 0],
                    "image2": ["24", 0],
                    "image3": ["34", 0],
                    "image4": ["44", 0],
                },
                "class_type": "VRGDG_LTXICIngredientsGrid",
                "_meta": {
                    "title": "50 · LTX Ingredients sheet · wide bottom · no labels"
                },
            },
            "51": {
                "inputs": {
                    "images": ["50", 0],
                    "filename_prefix": ["1", 9],
                    "format": png16,
                },
                "class_type": "SaveImageAdvanced",
                "_meta": {
                    "title": "51 · Save 16-bit PNG Ingredients sheet"
                },
            },
            "52": {
                "inputs": {
                    "text": ["1", 0],
                    "filename_prefix": ["1", 9],
                    "format": "json",
                },
                "class_type": "SaveText",
                "_meta": {
                    "title": "52 · Save complete planner prompt JSON"
                },
            },
            "53": {
                "inputs": {"images": ["51", 0]},
                "class_type": "PreviewImage",
                "_meta": {"title": "53 · Preview final Ingredients sheet"},
            },
        }
    )
    return workflow


def _widget_input(name: str, type_name: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_name,
        "widget": {"name": name},
        "link": None,
    }


def _socket_input(
    name: str,
    type_name: str,
    *,
    shape: int | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"name": name, "type": type_name, "link": None}
    if shape is not None:
        value["shape"] = shape
    return value


def _output(name: str, type_name: str) -> dict[str, Any]:
    return {"name": name, "type": type_name, "links": None}


def _properties(
    cnr_id: str,
    node_name: str,
    version: str = "local",
) -> dict[str, Any]:
    return {
        "cnr_id": cnr_id,
        "ver": version,
        "Node name for S&R": node_name,
    }


class _EditorGraph:
    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.by_id: dict[int, dict[str, Any]] = {}
        self.links: list[list[Any]] = []
        self.next_link_id = 1

    def add(self, node: dict[str, Any]) -> None:
        self.nodes.append(node)
        self.by_id[int(node["id"])] = node

    def connect(
        self,
        source_id: int,
        source_slot: int,
        target_id: int,
        target_name: str,
        type_name: str,
    ) -> None:
        source = self.by_id[source_id]
        target = self.by_id[target_id]
        target_slot = next(
            index
            for index, item in enumerate(target.get("inputs") or [])
            if item["name"] == target_name
        )
        link_id = self.next_link_id
        self.next_link_id += 1
        target["inputs"][target_slot]["link"] = link_id
        source_output = source["outputs"][source_slot]
        if source_output.get("links") is None:
            source_output["links"] = []
        source_output["links"].append(link_id)
        self.links.append(
            [
                link_id,
                source_id,
                source_slot,
                target_id,
                target_slot,
                type_name,
            ]
        )


def _node(
    *,
    node_id: int,
    type_name: str,
    title: str,
    pos: list[int],
    size: list[int],
    order: int,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    widgets_values: Any,
    properties: dict[str, Any],
    color: str | None = None,
    bgcolor: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": node_id,
        "type": type_name,
        "pos": pos,
        "size": size,
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "title": title,
        "properties": properties,
        "widgets_values": widgets_values,
    }
    if color:
        value["color"] = color
    if bgcolor:
        value["bgcolor"] = bgcolor
    return value


def _editor_workflow(contract: dict[str, Any]) -> dict[str, Any]:
    planner = _planner_values(contract)
    png16 = {
        "format": "png",
        "bit_depth": "16-bit",
        "input_color_space": "sRGB",
    }
    graph = _EditorGraph()
    graph.add(
        _node(
            node_id=1,
            type_name="SineForgeKrea2CharacterIngredientsPlanner",
            title="1 · Selectable local-model JSON character-sheet planner",
            pos=[80, 440],
            size=[680, 780],
            order=4,
            inputs=[
                _socket_input("reference_image", "IMAGE", shape=7),
            ],
            outputs=[
                _output("prompt_json", "STRING"),
                _output("face_front_prompt", "STRING"),
                _output("face_three_quarter_prompt", "STRING"),
                _output("profile_prompt", "STRING"),
                _output("body_turnaround_prompt", "STRING"),
                _output("image_seed_1", "INT"),
                _output("image_seed_2", "INT"),
                _output("image_seed_3", "INT"),
                _output("image_seed_4", "INT"),
                _output("output_prefix", "STRING"),
                _output("status_json", "STRING"),
            ],
            widgets_values=[
                planner["model"],
                planner["variation_mode"],
                planner["seed"],
                "fixed",
                planner["character_profile_json"],
                planner["temperature"],
                planner["top_p"],
                planner["max_tokens"],
                planner["timeout_seconds"],
            ],
            # This is a local bundled custom node, not a Comfy Registry pack.
            # Adding a cnr_id makes ComfyUI's dependency checker incorrectly
            # block the workflow behind a nonexistent "missing node pack".
            properties={
                "Node name for S&R": "SineForgeKrea2CharacterIngredientsPlanner"
            },
            color="#2b1d52",
            bgcolor="#1d163c",
        )
    )

    graph.add(
        _node(
            node_id=2,
            type_name="LoadImage",
            title="2 · Upload one identity / character image · REQUIRED",
            pos=[80, 1290],
            size=[500, 520],
            order=0,
            inputs=[
                _widget_input("image", "COMBO"),
                _widget_input("upload", "IMAGEUPLOAD"),
            ],
            outputs=[
                _output("IMAGE", "IMAGE"),
                _output("MASK", "MASK"),
            ],
            widgets_values=[REFERENCE_DEFAULT, "image"],
            properties=_properties("comfy-core", "LoadImage", "0.5.1"),
            color="#17304a",
            bgcolor="#102238",
        )
    )

    graph.add(
        _node(
            node_id=6,
            type_name="UNETLoader",
            title="6 · Local Krea 2 model",
            pos=[840, 440],
            size=[420, 120],
            order=5,
            inputs=[],
            outputs=[_output("MODEL", "MODEL")],
            widgets_values=[KREA_MODEL, "default"],
            properties=_properties("comfy-core", "UNETLoader", "0.21.1"),
            color="#4d2721",
            bgcolor="#351b17",
        )
    )
    graph.add(
        _node(
            node_id=7,
            type_name="CLIPLoader",
            title="7 · Local Krea 2 Qwen3-VL encoder",
            pos=[840, 600],
            size=[420, 140],
            order=6,
            inputs=[],
            outputs=[_output("CLIP", "CLIP")],
            widgets_values=[KREA_CLIP, "krea2", "default"],
            properties=_properties("comfy-core", "CLIPLoader", "0.21.1"),
            color="#4d2721",
            bgcolor="#351b17",
        )
    )
    graph.add(
        _node(
            node_id=8,
            type_name="VAELoader",
            title="8 · Local Krea 2 VAE",
            pos=[840, 780],
            size=[420, 100],
            order=7,
            inputs=[],
            outputs=[_output("VAE", "VAE")],
            widgets_values=[KREA_VAE],
            properties=_properties("comfy-core", "VAELoader", "0.21.1"),
            color="#4d2721",
            bgcolor="#351b17",
        )
    )

    branch_specs = [
        (10, 11, 12, 13, 14, 1, 5, 1024, 1024, "Front face", 60),
        (
            20,
            21,
            22,
            23,
            24,
            2,
            6,
            1024,
            1024,
            "Three-quarter face",
            1030,
        ),
        (30, 31, 32, 33, 34, 3, 7, 1024, 1024, "Side profile", 2000),
        (
            40,
            41,
            42,
            43,
            44,
            4,
            8,
            1024,
            1536,
            "Body turnaround",
            2970,
        ),
    ]
    for order_offset, spec in enumerate(branch_specs):
        (
            encode_id,
            negative_id,
            latent_id,
            sampler_id,
            decode_id,
            _prompt_index,
            _seed_index,
            width,
            height,
            label,
            x,
        ) = spec
        graph.add(
            _node(
                node_id=encode_id,
                type_name="Krea2EncodeRebalance",
                title=f"{encode_id} · {label} · four-reference conditioning",
                pos=[x, 1880],
                size=[560, 470],
                order=8 + order_offset * 5,
                inputs=[
                    _socket_input("text", "STRING"),
                    _socket_input("clip", "CLIP"),
                    _socket_input("image1", "IMAGE", shape=7),
                    _widget_input("image1_tokens", "COMBO"),
                    _socket_input("image2", "IMAGE", shape=7),
                    _widget_input("image2_tokens", "COMBO"),
                    _socket_input("image3", "IMAGE", shape=7),
                    _widget_input("image3_tokens", "COMBO"),
                    _socket_input("image4", "IMAGE", shape=7),
                    _widget_input("image4_tokens", "COMBO"),
                ],
                outputs=[_output("conditioning", "CONDITIONING")],
                widgets_values=[
                    "",
                    TOKEN_STRENGTHS[0],
                    TOKEN_STRENGTHS[1],
                    TOKEN_STRENGTHS[2],
                    TOKEN_STRENGTHS[3],
                ],
                properties=_properties(
                    "Rebalance-Pack",
                    "Krea2EncodeRebalance",
                ),
                color="#4d2721",
                bgcolor="#351b17",
            )
        )
        graph.add(
            _node(
                node_id=negative_id,
                type_name="ConditioningZeroOut",
                title=f"{negative_id} · {label} negative",
                pos=[x + 610, 1880],
                size=[300, 90],
                order=9 + order_offset * 5,
                inputs=[_socket_input("conditioning", "CONDITIONING")],
                outputs=[_output("CONDITIONING", "CONDITIONING")],
                widgets_values=[],
                properties=_properties(
                    "comfy-core",
                    "ConditioningZeroOut",
                    "0.5.1",
                ),
            )
        )
        graph.add(
            _node(
                node_id=latent_id,
                type_name="EmptySD3LatentImage",
                title=f"{latent_id} · {label} latent · {width}×{height}",
                pos=[x + 610, 2020],
                size=[300, 150],
                order=10 + order_offset * 5,
                inputs=[],
                outputs=[_output("LATENT", "LATENT")],
                widgets_values=[width, height, 1],
                properties=_properties(
                    "comfy-core",
                    "EmptySD3LatentImage",
                    "0.5.1",
                ),
            )
        )
        graph.add(
            _node(
                node_id=sampler_id,
                type_name="KSampler",
                title=f"{sampler_id} · Independent {label} sampler",
                pos=[x + 960, 1810],
                size=[390, 430],
                order=11 + order_offset * 5,
                inputs=[
                    _socket_input("model", "MODEL"),
                    _socket_input("positive", "CONDITIONING"),
                    _socket_input("negative", "CONDITIONING"),
                    _socket_input("latent_image", "LATENT"),
                    _socket_input("seed", "INT"),
                ],
                outputs=[_output("LATENT", "LATENT")],
                widgets_values=[
                    20260731,
                    "fixed",
                    8,
                    1.0,
                    "er_sde",
                    "simple",
                    1.0,
                ],
                properties=_properties("comfy-core", "KSampler", "0.5.1"),
                color="#4d2721",
                bgcolor="#351b17",
            )
        )
        graph.add(
            _node(
                node_id=decode_id,
                type_name="VAEDecode",
                title=f"{decode_id} · Decode {label}",
                pos=[x + 1410, 1930],
                size=[270, 100],
                order=12 + order_offset * 5,
                inputs=[
                    _socket_input("samples", "LATENT"),
                    _socket_input("vae", "VAE"),
                ],
                outputs=[_output("IMAGE", "IMAGE")],
                widgets_values=[],
                properties=_properties("comfy-core", "VAEDecode", "0.5.1"),
            )
        )

    graph.add(
        _node(
            node_id=50,
            type_name="VRGDG_LTXICIngredientsGrid",
            title="50 · LTX Ingredients sheet · wide bottom · no labels",
            pos=[4860, 1770],
            size=[520, 620],
            order=28,
            inputs=[
                _widget_input("image_count", "INT"),
                _widget_input("layout", "COMBO"),
                _widget_input("output_width", "INT"),
                _widget_input("output_height", "INT"),
                _widget_input("columns", "INT"),
                _widget_input("gutter", "INT"),
                _widget_input("outer_padding", "INT"),
                _widget_input("corner_radius", "INT"),
                _widget_input("fit_mode", "COMBO"),
                _widget_input("batch_mode", "COMBO"),
                _widget_input("background_color", "STRING"),
                _widget_input("cell_background_color", "STRING"),
                _socket_input("image1", "IMAGE", shape=7),
                _socket_input("image2", "IMAGE", shape=7),
                _socket_input("image3", "IMAGE", shape=7),
                _socket_input("image4", "IMAGE", shape=7),
            ],
            outputs=[_output("reference_sheet", "IMAGE")],
            widgets_values=[
                4,
                "wide_bottom",
                1536,
                1920,
                0,
                4,
                4,
                0,
                "contain_pad",
                "first_image_only",
                "#000000",
                "#000000",
            ],
            properties=_properties(
                "VRGDG",
                "VRGDG_LTXICIngredientsGrid",
            ),
            color="#123a30",
            bgcolor="#0d2b24",
        )
    )
    graph.add(
        _node(
            node_id=51,
            type_name="SaveImageAdvanced",
            title="51 · Save 16-bit PNG Ingredients sheet",
            pos=[5460, 1770],
            size=[420, 330],
            order=29,
            inputs=[
                _socket_input("images", "IMAGE"),
                _socket_input("filename_prefix", "STRING"),
            ],
            outputs=[_output("images", "IMAGE")],
            widgets_values=[None, "png", "16-bit", "sRGB"],
            properties=_properties(
                "comfy-core",
                "SaveImageAdvanced",
                "0.21.1",
            ),
            color="#52311f",
            bgcolor="#3b2114",
        )
    )
    graph.add(
        _node(
            node_id=52,
            type_name="SaveText",
            title="52 · Save complete planner prompt JSON",
            pos=[5460, 2160],
            size=[420, 250],
            order=30,
            inputs=[
                _socket_input("text", "STRING"),
                _socket_input("filename_prefix", "STRING"),
            ],
            outputs=[_output("text", "STRING")],
            widgets_values=["SineForge/Ingredients/Character_One", "json"],
            properties=_properties("comfy-core", "SaveText", "0.5.1"),
            color="#52311f",
            bgcolor="#3b2114",
        )
    )
    graph.add(
        _node(
            node_id=53,
            type_name="PreviewImage",
            title="53 · Preview final Ingredients sheet",
            pos=[5950, 1770],
            size=[430, 430],
            order=31,
            inputs=[_socket_input("images", "IMAGE")],
            outputs=[],
            widgets_values=[],
            properties=_properties("comfy-core", "PreviewImage", "0.5.1"),
        )
    )
    graph.add(
        _node(
            node_id=54,
            type_name="MarkdownNote",
            title="READ ME · Krea 2 character Ingredients-sheet generator",
            pos=[60, 30],
            size=[6320, 300],
            order=32,
            inputs=[],
            outputs=[],
            widgets_values=[
                "# SineForge · Krea 2 Character Ingredients Sheet\n\n"
                "1. Choose one high-resolution local sheet in node 2, or upload one clean identity image. Use a clear "
                "front or three-quarter view of the single character whose "
                "identity and wardrobe should remain consistent.\n"
                "2. Edit only `character_profile_json` in node 1. Keep it valid "
                "JSON and preserve every declared schema key. Describe one "
                "character through `identity_brief`, `age_presentation`, "
                "`face_identity`, `hair`, `complexion`, `body_build`, locked "
                "`wardrobe`, `accessories`, `identity_locks`, `visual_style`, "
                "`background`, and `avoid`.\n"
                "3. The planner model is a visible dropdown populated from every "
                "installed GGUF package under the local LM Studio model root. "
                "Qwen 3.6 40B is selected by default, but any listed local model "
                "may be chosen. The planner emits one strict JSON record plus "
                "four view-specific Krea prompts and four independent seeds. No "
                "hosted/API model is used.\n"
                "4. Every Krea branch receives the same single uploaded identity "
                "image through the available conditioning slots. The branches generate a "
                "front face, three-quarter face, profile, and body turnaround.\n"
                "5. Face views use 1024×1024 latents. The body turnaround uses "
                "1024×1536. All samplers use 8 steps, CFG 1, ER-SDE, simple "
                "schedule, batch size one.\n"
                "6. Node 50 creates a clean 1536×1920 `wide_bottom` Ingredients "
                "sheet with a black background and no labels. The compositor "
                "internally produces an 8-bit-equivalent tensor; node 51 saves "
                "that result in a lossless 16-bit PNG container without claiming "
                "new source precision. Node 52 saves the full JSON "
                "prompt/provenance record.\n"
                "7. For Ingredients conditioning, clear image panels are more "
                "valuable than text labels or decorative layouts. Regenerate "
                "individual views by changing the planner seed/profile, then "
                "keep the best accepted PNG as the canonical identity sheet."
            ],
            properties={},
            color="#26354f",
            bgcolor="#172237",
        )
    )

    graph.connect(2, 0, 1, "reference_image", "IMAGE")

    branch_link_specs = [
        (10, 11, 12, 13, 14, 1, 5, "image1"),
        (20, 21, 22, 23, 24, 2, 6, "image2"),
        (30, 31, 32, 33, 34, 3, 7, "image3"),
        (40, 41, 42, 43, 44, 4, 8, "image4"),
    ]
    for (
        encode_id,
        negative_id,
        latent_id,
        sampler_id,
        decode_id,
        prompt_index,
        seed_index,
        grid_input,
    ) in branch_link_specs:
        graph.connect(1, prompt_index, encode_id, "text", "STRING")
        graph.connect(7, 0, encode_id, "clip", "CLIP")
        for reference_name in ("image1", "image2", "image3", "image4"):
            graph.connect(
                2,
                0,
                encode_id,
                reference_name,
                "IMAGE",
            )
        graph.connect(
            encode_id,
            0,
            negative_id,
            "conditioning",
            "CONDITIONING",
        )
        graph.connect(6, 0, sampler_id, "model", "MODEL")
        graph.connect(
            encode_id,
            0,
            sampler_id,
            "positive",
            "CONDITIONING",
        )
        graph.connect(
            negative_id,
            0,
            sampler_id,
            "negative",
            "CONDITIONING",
        )
        graph.connect(
            latent_id,
            0,
            sampler_id,
            "latent_image",
            "LATENT",
        )
        graph.connect(1, seed_index, sampler_id, "seed", "INT")
        graph.connect(sampler_id, 0, decode_id, "samples", "LATENT")
        graph.connect(8, 0, decode_id, "vae", "VAE")
        graph.connect(decode_id, 0, 50, grid_input, "IMAGE")

    graph.connect(50, 0, 51, "images", "IMAGE")
    graph.connect(1, 9, 51, "filename_prefix", "STRING")
    graph.connect(1, 0, 52, "text", "STRING")
    graph.connect(1, 9, 52, "filename_prefix", "STRING")
    graph.connect(51, 0, 53, "images", "IMAGE")

    return {
        "id": WORKFLOW_ID,
        "revision": 0,
        "last_node_id": 54,
        "last_link_id": graph.next_link_id - 1,
        "nodes": graph.nodes,
        "links": graph.links,
        "groups": [
            {
                "id": 1,
                "title": "LOCAL JSON PLANNING + ONE UPLOADED IDENTITY IMAGE",
                "bounding": [40, 380, 1420, 1370],
                "color": "#6c4eb6",
                "font_size": 24,
                "flags": {},
            },
            {
                "id": 2,
                "title": "FOUR INDEPENDENT KREA 2 REFERENCE VIEWS",
                "bounding": [40, 1740, 4670, 720],
                "color": "#b45a43",
                "font_size": 24,
                "flags": {},
            },
            {
                "id": 3,
                "title": "LTX INGREDIENTS GRID + 16-BIT PNG + JSON",
                "bounding": [4800, 1720, 1620, 760],
                "color": "#397f69",
                "font_size": 24,
                "flags": {},
            },
        ],
        "config": {},
        "extra": {
            "ds": {"scale": 0.58, "offset": [30, 80]},
            "frontendVersion": "1.47.10",
            "sineforge": {
                "schema_version": (
                    "sineforge.krea2-character-ingredients-workflow/v1"
                ),
                "read_only_library_source": True,
                "repository_managed": True,
                "prompt_contract": PROMPT_FILENAME,
                "prompt_media_type": "application/json",
                "planner_model_policy": (
                    "all installed GGUF packages under the configured local "
                    "LM Studio model root; Qwen 3.6 40B is only the default"
                ),
                "reference_token_strengths": list(TOKEN_STRENGTHS),
                "grid": {
                    "node": "VRGDG_LTXICIngredientsGrid",
                    "layout": "wide_bottom",
                    "size": [1536, 1920],
                    "background": "#000000",
                    "labels": False,
                },
            },
        },
        "version": 0.4,
    }


def _manifest(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "sineforge.semantic-workflow-manifest/v1",
        "template_id": "krea2-character-ingredients-v1",
        "workflow_name": (
            "Krea 2 Character Ingredients Sheet — High-Resolution Local Models"
        ),
        "editor_workflow": EDITOR_FILENAME,
        "api_workflow": API_FILENAME,
        "prompt_contract": PROMPT_FILENAME,
        "execution_policy": {
            "hosted_or_api_models_allowed": False,
            "local_planner": "LM Studio",
            "default_planner_model": str(
                contract.get("planner_model") or MODEL_ID
            ),
            "planner_model_selection": (
                "all installed GGUF packages under "
                f"{contract.get('trusted_lm_studio_model_root') or TRUSTED_MODEL_ROOT}"
            ),
            "shared_model_root": SHARED_MODEL_ROOT,
            "queue_depth": 1,
            "batch_size": 1,
            "independent_generation_branches": 4,
            "output_image": "16-bit PNG",
            "prompt_and_provenance": "JSON",
            "repository_managed_read_only": True,
        },
        "bindings": {
            "character_profile_json": {
                "node_id": "1",
                "class_type": "SineForgeKrea2CharacterIngredientsPlanner",
                "input": "character_profile_json",
                "media_type": "application/json",
            },
            "references": [
                {
                    "node_id": str(node_id),
                    "class_type": "LoadImage",
                    "input": "image",
                    "planner_input": f"reference_image_{index}",
                    "krea_input": f"image{index}",
                    "token_strength": TOKEN_STRENGTHS[index - 1],
                }
                for index, node_id in enumerate((2, 3, 4, 5), start=1)
            ],
            "generated_views": {
                "front_face": {
                    "prompt_output_index": 1,
                    "seed_output_index": 5,
                    "encode_node": "10",
                    "sampler_node": "13",
                    "latent": [1024, 1024],
                },
                "three_quarter_face": {
                    "prompt_output_index": 2,
                    "seed_output_index": 6,
                    "encode_node": "20",
                    "sampler_node": "23",
                    "latent": [1024, 1024],
                },
                "profile": {
                    "prompt_output_index": 3,
                    "seed_output_index": 7,
                    "encode_node": "30",
                    "sampler_node": "33",
                    "latent": [1024, 1024],
                },
                "body_turnaround": {
                    "prompt_output_index": 4,
                    "seed_output_index": 8,
                    "encode_node": "40",
                    "sampler_node": "43",
                    "latent": [1024, 1536],
                },
            },
            "ingredients_grid": {
                "node_id": "50",
                "class_type": "VRGDG_LTXICIngredientsGrid",
                "layout": "wide_bottom",
                "output_size": [1536, 1920],
                "background": "#000000",
                "labels": False,
            },
            "save_image": {
                "node_id": "51",
                "class_type": "SaveImageAdvanced",
                "format": "16-bit PNG",
            },
            "save_prompt_json": {
                "node_id": "52",
                "class_type": "SaveText",
                "format": "json",
            },
        },
        "sampler_profile": {
            "sampler": "er_sde",
            "scheduler": "simple",
            "steps": 8,
            "cfg": 1.0,
            "denoise": 1.0,
            "seed_policy": "four planner-derived independent seeds",
        },
    }


def _instructions() -> str:
    return """1. Choose one high-resolution local sheet from `SineForge/CharacterIngredients/` in node 2, or upload one clean image of one character. A clear front or three-quarter identity view works best. The same image conditions every Krea branch.
2. Edit node 1 `character_profile_json`. It must remain valid JSON and conform to the embedded profile schema. Preserve all keys: `schema_version`, `character_id`, `character_name`, `character_kind`, `identity_brief`, `age_presentation`, `face_identity`, `hair`, `complexion`, `body_build`, `wardrobe`, `accessories`, `identity_locks`, `visual_style`, `background`, and `avoid`.
3. Keep the profile limited to one canonical character. Specify stable face geometry, age, complexion, eyes, hairstyle, distinctive features, wardrobe colors/materials, footwear, and accessories. Do not request labels or decorative frames.
4. Node 1 exposes every installed GGUF package beneath the local LM Studio model root as a visible model dropdown. Qwen 3.6 40B is selected by default, but it is not locked. The chosen local model returns one complete JSON record, four standalone Krea prompts, four independent image seeds, an output prefix, and status JSON. No hosted/API Krea or prompt agent is present.
5. Every Krea2EncodeRebalance branch receives the same uploaded identity image. The prompt changes the view; the identity and wardrobe instructions remain locked.
6. The three face branches use independent 1024×1024 latents. The body-turnaround branch uses a 1024×1536 latent. Every KSampler is independent and uses 8 steps, CFG 1, ER-SDE, the simple scheduler, denoise 1, and batch size one.
7. Node 50 composes the decoded views with the installed `VRGDG_LTXICIngredientsGrid` at 1536×1920 using `wide_bottom`, black background/cells, contain-pad fitting, and no text labels.
8. The installed Ingredients compositor converts panels to an 8-bit-equivalent tensor internally. Node 51 saves that compositor result in a lossless 16-bit PNG container; this prevents further PNG compression loss but does not recreate source precision discarded by the grid. Node 52 saves the exact planner prompt/provenance record with `format=json`. Node 53 previews the same image returned by the save node.
9. Use the accepted PNG as an LTX-2.3 Ingredients reference sheet. If one view is weak, change the planner seed or improve the uploaded identity image/profile and regenerate; do not add labels or clutter to compensate.
10. The workflow is repository-managed and read-only in the SineForge library. Load it into ComfyUI to make an editable working copy."""


def _library_record(
    *,
    editor: dict[str, Any],
    api: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    planner_model = str(contract.get("planner_model") or MODEL_ID)
    trusted_root = str(
        contract.get("trusted_lm_studio_model_root") or TRUSTED_MODEL_ROOT
    )
    available_local_models = _discover_local_llm_packages(trusted_root)
    selectable_model_keys = sorted(
        available_local_models,
        key=lambda value: (
            value != planner_model,
            value.casefold(),
        ),
    )
    node_classes = sorted(
        {
            node["class_type"]
            for node in api.values()
            if isinstance(node, dict) and node.get("class_type")
        }
    )
    return {
        "schema": "sineforge.api-caller-workflow.v1",
        "id": WORKFLOW_ID,
        "name": "Krea 2 Character Ingredients Sheet — High-Resolution Local Models",
        "version": "1.0",
        "description": (
            "Creates one clean high-resolution LTX-2.3 Ingredients reference sheet for a "
            "recurring character. The visible planner dropdown discovers every "
            "installed GGUF package beneath the local LM Studio model root, with "
            "Qwen 3.6 40B selected only as the default. The chosen local planner "
            "reads a structured JSON character profile and one local identity "
            "image, then produces four Krea 2 prompts and independent "
            "seeds for a front face, three-quarter face, profile, and full-body "
            "turnaround. Every local Krea branch reuses the one uploaded identity "
            "image for consistent conditioning. The installed LTX Ingredients grid "
            "composes a label-free 1536×1920 high-resolution sheet on black; the workflow saves a "
            "16-bit PNG container plus complete JSON prompt and provenance."
        ),
        "category": "Image Editing & Composition",
        "subcategory": "Character reference sheets",
        "episode": None,
        "instructions": _instructions(),
        "tags": [
            "Krea 2",
            "LTX-2.3",
            "Ingredients",
            "character reference sheet",
            "identity consistency",
            "wardrobe consistency",
            "front face",
            "three-quarter face",
            "profile",
            "body turnaround",
            "one identity image",
            "selectable local LM Studio models",
            "Qwen 3.6 40B default",
            "strict JSON",
            "16-bit PNG",
            "read only",
            "repository managed",
        ],
        "requirements": {
            "custom_node_root": CUSTOM_NODE_ROOT,
            "shared_model_root": SHARED_MODEL_ROOT,
            "model_root_policy": "prefer_shared_comfy_root",
            "local_prompt_model_root": trusted_root,
            "prompt_model_policy": (
                "select every installed executable GGUF package beneath the "
                "local model root; do not expose paths outside that root"
            ),
            "default_prompt_model": planner_model,
            "selectable_prompt_model_keys": selectable_model_keys,
            "available_local_prompt_models": available_local_models,
            "custom_node_packs": [
                "SineForge-Workflow-Bridge",
                "ComfyUI-Conditioning-Rebalance",
                "ComfyUI-VideoHelperSuite",
                "VRGDG",
            ],
            "unresolved_node_classes": [],
            "node_classes": node_classes,
            "model_files": [
                {
                    "node_id": "6",
                    "node_type": "UNETLoader",
                    "input": "unet_name",
                    "value": KREA_MODEL,
                    "preferred_relative_path": f"diffusion_models/{KREA_MODEL}",
                },
                {
                    "node_id": "7",
                    "node_type": "CLIPLoader",
                    "input": "clip_name",
                    "value": KREA_CLIP,
                    "preferred_relative_path": f"text_encoders/{KREA_CLIP}",
                },
                {
                    "node_id": "8",
                    "node_type": "VAELoader",
                    "input": "vae_name",
                    "value": KREA_VAE,
                    "preferred_relative_path": f"vae/{KREA_VAE}",
                },
            ],
            "media_inputs": [
                {
                    "node_id": str(node_id),
                    "node_type": "LoadImage",
                    "input": "image",
                    "default": REFERENCE_DEFAULT,
                    "purpose": purpose,
                    "krea_token_strength": strength,
                }
                for node_id, purpose, strength in [
                    (2, "Primary face and canonical identity", "max"),
                    (3, "Alternate face angle", "high"),
                    (4, "Body and locked wardrobe", "high"),
                    (5, "Optional detail, accessory, or style", "normal"),
                ]
            ],
            "prompt_field_count": 5,
            "output_node_count": 3,
            "prompt_contract": f"Workflows/LTX23/{PROMPT_FILENAME}",
            "semantic_manifest": f"Workflows/LTX23/{MANIFEST_FILENAME}",
            "qualification": {
                "status": "static_validated_not_rendered",
                "reason": (
                    "The graph and installed node/model inventory were validated "
                    "without queueing an expensive four-image Krea generation."
                ),
                "recommended_first_run": {
                    "references": 4,
                    "sampler_steps": 8,
                    "batch_size": 1,
                    "face_latent": [1024, 1024],
                    "body_latent": [1024, 1536],
                    "sheet_size": [1536, 1920],
                    "queue_depth": 1,
                },
            },
            "documentation_notes": (
                f"The Krea model, Krea text encoder, and Krea VAE nodes remain "
                f"visible editable ComfyUI dropdowns backed by "
                f"`{SHARED_MODEL_ROOT}`; their repository defaults point to the "
                "exact locally installed files listed above. The planner dropdown "
                f"discovers every executable GGUF package beneath `{trusted_root}` "
                f"and defaults to `{planner_model}` without locking selection. "
                "All planner inputs and outputs are represented in JSON. No hosted "
                "Krea node or remote agent node is used. The final image "
                "is stored in a lossless 16-bit PNG container. The installed grid "
                "internally composes an 8-bit-equivalent tensor, so the 16-bit "
                "container does not imply retained 16-bit source precision. Krea "
                "synthesis itself is generative and is not mathematically lossless."
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
    contract = _load_contract()
    editor = _editor_workflow(contract)
    api = _api_workflow(contract)
    manifest = _manifest(contract)
    record = _library_record(
        editor=editor,
        api=api,
        contract=contract,
    )

    _write_json(WORKFLOW_DIR / EDITOR_FILENAME, editor)
    _write_json(WORKFLOW_DIR / API_FILENAME, api)
    _write_json(WORKFLOW_DIR / MANIFEST_FILENAME, manifest)
    _write_json(WORKFLOW_DIR / PROMPT_FILENAME, contract)
    _write_json(RECORDS_DIR / f"{WORKFLOW_ID}.json", record)
    _update_catalog(record)

    print(f"workflow_id={WORKFLOW_ID}")
    print(f"editor={WORKFLOW_DIR / EDITOR_FILENAME}")
    print(f"api={WORKFLOW_DIR / API_FILENAME}")
    print(f"manifest={WORKFLOW_DIR / MANIFEST_FILENAME}")
    print(f"prompt={WORKFLOW_DIR / PROMPT_FILENAME}")
    print(f"record={RECORDS_DIR / f'{WORKFLOW_ID}.json'}")


if __name__ == "__main__":
    main()
