"""Build the repository-backed native Runner workflow catalog.

The source packs contain ComfyUI editor-format graphs. Their corresponding
API-format exports are produced by ComfyUI itself and named with the stable
``SFCatalog20260730A_<index>_<source-hash>.json`` convention. This importer
repairs only unresolved class names from the original editor graph, derives
operator-facing metadata, and writes deterministic repository records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


CATALOG_PREFIX = "SFCatalog20260730A"
CATALOG_TIMESTAMP = "2026-07-30T00:00:00+00:00"
RECORD_SCHEMA = "sineforge.api-caller-workflow.v1"
CATALOG_SCHEMA = "sineforge.repository-workflow-catalog/v1"
CATALOG_NAMESPACE = uuid.UUID("3f6b0f33-9a13-5c94-9ef3-26dc84a6b41a")

MODEL_INPUT_MARKERS = (
    "checkpoint",
    "ckpt",
    "clip_name",
    "control_net",
    "diffusion_model",
    "gguf",
    "lora",
    "model",
    "unet",
    "vae",
)
MEDIA_INPUT_MARKERS = ("audio", "image", "mask", "video")
PROMPT_INPUT_MARKERS = ("caption", "instruction", "negative", "positive", "prompt", "text")
OUTPUT_CLASS_MARKERS = ("combine", "export", "preview", "save")


def stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: object) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def source_workflows(source_root: Path) -> list[Path]:
    workflows: list[Path] = []
    for path in source_root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
            workflows.append(path)
    return sorted(workflows, key=lambda path: str(path).casefold())


def source_hash(source_root: Path, source_path: Path) -> str:
    relative = source_path.relative_to(source_root).as_posix()
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:8]


def api_export_path(
    converted_root: Path,
    source_root: Path,
    source_path: Path,
    index: int,
) -> Path:
    digest = source_hash(source_root, source_path)
    expected = converted_root / f"{CATALOG_PREFIX}_{index:03d}_{digest}.json"
    if expected.is_file():
        return expected
    # Browser/JavaScript locale ordering can differ from Python ordering for
    # punctuation. The source-path digest is authoritative and unique.
    matches = list(converted_root.glob(f"{CATALOG_PREFIX}_*_{digest}.json"))
    if len(matches) == 1:
        return matches[0]
    return expected


def episode_from_path(path: Path) -> str | None:
    match = re.search(r"\bep(\d{2})\b", path.as_posix(), re.IGNORECASE)
    return f"EP{match.group(1)}" if match else None


def model_families(text: str) -> list[str]:
    patterns = (
        ("FLUX.2 Klein 9B", r"flux(?:\s*2)?\s*klein\s*9b"),
        ("FLUX.2 Klein 4B", r"flux(?:\s*2)?\s*klein\s*4b"),
        ("FLUX.1 Dev", r"flux\s*1(?:\.0)?\s*dev|flux1\s*dev"),
        ("Qwen Image", r"qwen\s*image"),
        ("Qwen3-TTS", r"qwen3[-\s]*tts"),
        ("Qwen 3.5", r"qwen\s*3\.5"),
        ("QwenVL 3", r"qwenvl\s*3"),
        ("Z-Image Turbo", r"z[-\s]*image\s*turbo"),
        ("LTX-2", r"\bltx[-\s]*2\b"),
        ("Wan 2.2", r"\bwan\s*2\.2\b"),
        ("Wan InfiniteTalk", r"wan\s*infinitetalk"),
        ("Wan Scail", r"wan\s*scail"),
        ("Scail 2", r"\bscail\s*2\b"),
        ("SeedVR2", r"seedvr2"),
        ("Fish S2", r"fish\s*s2"),
        ("Gemma 4", r"gemma\s*4"),
        ("Stable Audio 3", r"stable\s*audio\s*3"),
        ("Krea 2", r"krea\s*2"),
        ("Anima Base 1.0", r"anima\s*base\s*v?1\.0"),
        ("Boogu", r"\bboogu\b"),
        ("ACE-Step 1.5", r"acestep\s*v?1\.5|ace[-\s]*step\s*v?1\.5"),
        ("Ernie Image Turbo", r"ernie\s*image\s*turbo"),
        ("Lens", r"\blens\b"),
    )
    lowered = text.casefold()
    return [label for label, pattern in patterns if re.search(pattern, lowered)]


def classify(name: str, relative: str) -> tuple[str, str]:
    text = f"{name} {relative}".casefold()
    if any(token in text for token in ("video", "wan 2.2", "infinite", "scail", "ltx-2", "animate")):
        if "upscale" in text:
            return "Video & Animation", "Video upscaling"
        if any(token in text for token in ("infinitetalk", "custom audio", "with audio")):
            return "Video & Animation", "Talking characters"
        if any(token in text for token in ("replace character", "animate")):
            return "Video & Animation", "Character animation"
        return "Video & Animation", "Image to video"
    if any(token in text for token in ("tts", "voice", "audio", "music", "sound", "audioreact", "acestep")):
        if any(token in text for token in ("tts", "voice")):
            return "Speech, Audio & Music", "Speech & voice"
        if "react" in text:
            return "Speech, Audio & Music", "Audio reactive"
        return "Speech, Audio & Music", "Music & sound"
    if any(token in text for token in ("upscale", "seedvr2", "image scale")):
        if "paid" in text:
            return "Upscaling & Restoration", "Hosted upscalers"
        return "Upscaling & Restoration", "Local upscaling"
    if any(
        token in text
        for token in (
            "inpaint",
            "outpaint",
            "image edit",
            "boogu edit",
            "remove background",
            "remove image",
            "image blend",
            "image combiner",
            "image compare",
            "image composer",
            "image stitch",
            "image transformation",
            "paint",
            "3d builder",
            "crop",
            "join two images",
            "text overlay",
        )
    ):
        if any(token in text for token in ("inpaint", "outpaint")):
            return "Image Editing & Composition", "Inpaint & outpaint"
        if any(token in text for token in ("2 images", "3 images", "4 images", "blend", "combiner", "composer", "join")):
            return "Image Editing & Composition", "Multi-image composition"
        if "background" in text or "lama" in text:
            return "Image Editing & Composition", "Cleanup & background"
        if any(token in text for token in ("paint", "3d builder")):
            return "Image Editing & Composition", "Paint & spatial tools"
        return "Image Editing & Composition", "Image utilities"
    if any(
        token in text
        for token in (
            "txt2img",
            "text to image",
            "image generation",
            "image turbo",
            "anima base",
            "krea 2",
            "boogu image",
            "fluxmania",
        )
    ):
        if any(token in text for token in ("prompt enhancer", "prompt from image", "prompt2img")):
            return "Image Generation", "Prompt-assisted generation"
        return "Image Generation", "Text to image"
    if any(
        token in text
        for token in (
            "prompt",
            "gemma",
            "qwenvl",
            "qwen 3.5",
            "audio to text",
            "video to description",
            "switch node",
            "read prompt",
            "note",
        )
    ):
        if any(token in text for token in ("image to prompt", "video to", "audio to text", "prompt from image", "qwenvl")):
            return "Prompting & Language", "Captioning & transcription"
        if any(token in text for token in ("stack", "pack", "multi", "queue", "list")):
            return "Prompting & Language", "Prompt batching"
        if any(token in text for token in ("switch", "note", "node color")):
            return "Prompting & Language", "Workflow controls"
        return "Prompting & Language", "Prompt enhancement"
    if any(token in text for token in ("loop", "group compare", "build a list", "carry two values")):
        return "Utilities & Workflow Tools", "Lists & iteration"
    if any(token in text for token in ("filter", "labels", "compare")):
        return "Utilities & Workflow Tools", "Image utilities"
    return "Utilities & Workflow Tools", "General utilities"


def strings_from_value(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(strings_from_value(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(strings_from_value(item))
        return result
    return []


def documentation_from_ui(ui_workflow: dict[str, Any]) -> str | None:
    sections: list[str] = []
    for raw_node in ui_workflow.get("nodes", []):
        if not isinstance(raw_node, dict):
            continue
        node_type = str(raw_node.get("type") or "")
        title = str(raw_node.get("title") or "")
        strings = strings_from_value(raw_node.get("widgets_values"))
        note_like = any(
            marker in f"{node_type} {title}".casefold()
            for marker in ("markdown", "note", "text")
        )
        for value in strings:
            cleaned = value.strip()
            if len(cleaned) < 80:
                continue
            if note_like or any(
                marker in cleaned.casefold()
                for marker in (
                    "models and nodes",
                    "download",
                    "place in",
                    "installed from manager",
                    "how to",
                )
            ):
                sections.append(cleaned)
    deduplicated = list(dict.fromkeys(sections))
    if not deduplicated:
        return None
    return "\n\n".join(deduplicated)[:16_000]


def infer_custom_node_packs(documentation: str | None, node_types: list[str]) -> list[str]:
    combined = f"{documentation or ''}\n{' '.join(node_types)}"
    matches = re.findall(
        r"\b(?:ComfyUI|comfyui)[-_][A-Za-z0-9_.-]+|"
        r"\brgthree-comfy\b|\bVideoHelperSuite\b|\bKJNodes\b|"
        r"\bPixaroma(?:\s+[A-Za-z0-9_.-]+){0,3}",
        combined,
        re.IGNORECASE,
    )
    return sorted({match.strip(" .,:;") for match in matches}, key=str.casefold)[:30]


def repair_api_graph(
    ui_workflow: dict[str, Any],
    api_workflow: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    ui_nodes = {
        str(node.get("id")): node
        for node in ui_workflow.get("nodes", [])
        if isinstance(node, dict) and node.get("id") is not None
    }
    repaired: dict[str, Any] = {}
    unresolved: list[str] = []
    for raw_id, raw_node in api_workflow.items():
        node_id = str(raw_id)
        node = dict(raw_node) if isinstance(raw_node, dict) else {"inputs": {}}
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            node["inputs"] = {}
        class_type = node.get("class_type")
        if not isinstance(class_type, str) or not class_type.strip():
            original_type = str(ui_nodes.get(node_id, {}).get("type") or "UnknownNode")
            node["class_type"] = f"UNRESOLVED::{original_type}"
            unresolved.append(original_type)
        repaired[node_id] = node
    if not repaired:
        raise ValueError("API export contains no nodes")
    return repaired, sorted(set(unresolved), key=str.casefold)


def analyze_requirements(
    workflow: dict[str, Any],
    unresolved: list[str],
    documentation: str | None,
    custom_node_root: str,
) -> dict[str, Any]:
    model_files: list[dict[str, str]] = []
    media_inputs: list[dict[str, str]] = []
    node_types: set[str] = set()
    prompt_fields = 0
    output_nodes = 0
    for node_id, node in workflow.items():
        class_type = str(node.get("class_type") or "")
        actual_type = class_type.removeprefix("UNRESOLVED::")
        node_types.add(actual_type)
        if any(marker in class_type.casefold() for marker in OUTPUT_CLASS_MARKERS):
            output_nodes += 1
        for input_name, value in dict(node.get("inputs") or {}).items():
            lowered = input_name.casefold()
            if (
                isinstance(value, str)
                and value.strip()
                and any(marker in lowered for marker in MODEL_INPUT_MARKERS)
            ):
                model_files.append(
                    {
                        "node_id": node_id,
                        "node_type": actual_type,
                        "input": input_name,
                        "value": value,
                    }
                )
            if (
                isinstance(value, str)
                and any(marker in lowered for marker in MEDIA_INPUT_MARKERS)
            ):
                media_inputs.append(
                    {
                        "node_id": node_id,
                        "node_type": actual_type,
                        "input": input_name,
                        "default": value if isinstance(value, str) else "",
                    }
                )
            if (
                isinstance(value, (str, int, float, bool))
                and any(marker in lowered for marker in PROMPT_INPUT_MARKERS)
            ):
                prompt_fields += 1
    model_files = list(
        {
            (item["input"], item["value"]): item
            for item in model_files
        }.values()
    )
    media_inputs = list(
        {
            (item["node_id"], item["input"]): item
            for item in media_inputs
        }.values()
    )
    types = sorted(node_types, key=str.casefold)
    return {
        "custom_node_root": custom_node_root,
        "custom_node_packs": infer_custom_node_packs(documentation, types),
        "unresolved_node_classes": unresolved,
        "node_classes": types,
        "model_files": model_files[:60],
        "media_inputs": media_inputs[:60],
        "prompt_field_count": prompt_fields,
        "output_node_count": output_nodes,
        "documentation_notes": documentation,
    }


def task_sentence(category: str, subcategory: str) -> str:
    tasks = {
        "Text to image": "turn a text prompt into a finished still image",
        "Prompt-assisted generation": "develop or extract a prompt and render the resulting still image",
        "Inpaint & outpaint": "repair, replace, or extend selected regions of an existing image",
        "Multi-image composition": "combine or condition on multiple images in one controlled edit",
        "Cleanup & background": "isolate the subject or remove unwanted image content",
        "Paint & spatial tools": "prepare image guidance with interactive paint or spatial controls",
        "Image utilities": "inspect, transform, compare, or compose image assets",
        "Local upscaling": "increase image or video resolution with a locally loaded model",
        "Hosted upscalers": "send an asset through the workflow's hosted upscale provider",
        "Image to video": "animate a still image into a generated video clip",
        "Talking characters": "generate a speaking character clip from visual and audio guidance",
        "Character animation": "transfer or generate character motion in a video shot",
        "Video upscaling": "restore and enlarge a generated video",
        "Speech & voice": "synthesize, design, clone, save, or reuse a speaking voice",
        "Audio reactive": "drive visual behavior from an audio track",
        "Music & sound": "generate music, ambience, or sound from text or image guidance",
        "Captioning & transcription": "extract structured text or prompts from media",
        "Prompt batching": "assemble, vary, queue, or iterate over prompt text",
        "Workflow controls": "demonstrate reusable control and annotation nodes",
        "Prompt enhancement": "rewrite a short idea into a production-ready prompt",
        "Lists & iteration": "demonstrate reusable list, loop, and value-carry patterns",
        "General utilities": "demonstrate a focused reusable ComfyUI utility",
    }
    return tasks.get(subcategory, f"run a {category.casefold()} task")


def build_description(
    name: str,
    category: str,
    subcategory: str,
    families: list[str],
    requirements: dict[str, Any],
    node_count: int,
) -> str:
    models = ", ".join(families) if families else "the models configured in the graph"
    media_count = len(requirements["media_inputs"])
    prompt_count = requirements["prompt_field_count"]
    output_count = requirements["output_node_count"]
    readiness = (
        "The imported graph contains unresolved custom-node classes, so install or map "
        "the listed nodes and reconvert from the included editor graph before production use."
        if requirements["unresolved_node_classes"]
        else "The ComfyUI editor graph was converted to API format and is ready for live "
        "validation against the connected node and model registry."
    )
    return (
        f"{name} is a {subcategory.casefold()} workflow designed to "
        f"{task_sentence(category, subcategory)} using {models}. "
        f"Its {node_count}-node graph exposes {prompt_count} prompt/text field(s), "
        f"{media_count} media input target(s), and {output_count} save/preview stage(s), "
        "while preserving the original editor-format graph for reference. "
        f"{readiness}"
    )


def build_instructions(
    category: str,
    subcategory: str,
    requirements: dict[str, Any],
) -> str:
    unresolved = requirements["unresolved_node_classes"]
    model_files = requirements["model_files"]
    media_inputs = requirements["media_inputs"]
    first_step = (
        "Install or map the unresolved node classes listed in Requirements, open the "
        "included editor-format source in the main LTX ComfyUI install, and export API "
        "format again before attempting a run."
        if unresolved
        else "Open the workflow and select Validate. SineForge will compare every node "
        "class and input against the currently connected ComfyUI instance without queueing it."
    )
    model_step = (
        "Review the model-file entries in Requirements and place each checkpoint, text "
        "encoder, VAE, LoRA, or auxiliary model in the folder documented by the source "
        "workflow. Refresh ComfyUI after adding files."
        if model_files
        else "Confirm that any model selectors in the editable inputs resolve to files "
        "available in the main ComfyUI installation."
    )
    media_step = (
        "Upload and assign the required image, mask, video, or audio files to the listed "
        "media inputs. Keep the source dimensions and duration appropriate for the selected model."
        if media_inputs
        else "No required media file was detected in the converted graph; begin with the "
        "prompt and generation controls."
    )
    specialist = {
        "Video & Animation": (
            "Set frame count, FPS, dimensions, conditioning strength, and seed. Start with "
            "one short clip to verify motion, identity, and memory use before scaling up."
        ),
        "Speech, Audio & Music": (
            "Review text, speaker/voice references, language, duration, sample rate, and seed. "
            "For cloning, use a clean reference clip and confirm you have permission to use the voice."
        ),
        "Upscaling & Restoration": (
            "Select the intended scale/model and verify output dimensions before running. "
            "Use one representative asset first to estimate VRAM and processing time."
        ),
        "Image Editing & Composition": (
            "Check image order, masks, crop/resize behavior, denoise strength, and edit prompt. "
            "Preview the mask or composite before spending time on the final sample."
        ),
        "Prompting & Language": (
            "Edit the source text or media, review the system/instruction fields, and inspect "
            "the generated text before passing it into another generation workflow."
        ),
    }.get(
        category,
        "Edit the positive/negative prompt, resolution, sampler, steps, guidance, and seed. "
        "Use a fixed seed while tuning composition, then vary it deliberately.",
    )
    return "\n".join(
        (
            f"1. {first_step}",
            f"2. {model_step}",
            f"3. {media_step}",
            f"4. {specialist}",
            "5. Save a copy before making structural changes. Use Editable inputs for normal "
            "parameters and Raw API JSON only when you need to inspect or change graph wiring.",
            "6. Validate again after every change. Queue one workflow only after validation "
            "passes; then inspect the returned output, logs, duration, dimensions, and media integrity.",
        )
    )


def create_record(
    *,
    source_root: Path,
    source_path: Path,
    api_path: Path,
    custom_node_root: str,
) -> dict[str, Any]:
    ui_workflow = json.loads(source_path.read_text(encoding="utf-8"))
    api_export = json.loads(api_path.read_text(encoding="utf-8"))
    if not isinstance(ui_workflow, dict) or not isinstance(api_export, dict):
        raise ValueError("Workflow payload must be an object")
    workflow, unresolved = repair_api_graph(ui_workflow, api_export)
    relative = source_path.relative_to(source_root).as_posix()
    name = source_path.stem
    episode = episode_from_path(source_path)
    category, subcategory = classify(name, relative)
    documentation = documentation_from_ui(ui_workflow)
    requirements = analyze_requirements(
        workflow,
        unresolved,
        documentation,
        custom_node_root,
    )
    families = model_families(
        f"{name} {relative} {' '.join(requirements['node_classes'])} "
        + " ".join(
            str(model.get("value") or "") for model in requirements["model_files"]
        )
    )
    description = build_description(
        name,
        category,
        subcategory,
        families,
        requirements,
        len(workflow),
    )
    instructions = build_instructions(category, subcategory, requirements)
    stable_id = str(uuid.uuid5(CATALOG_NAMESPACE, relative.casefold()))
    source_archive = f"{relative.split('/', 1)[0]}.zip"
    tags = sorted(
        {
            category,
            subcategory,
            *(families or []),
            *(filter(None, (episode,))),
        },
        key=str.casefold,
    )
    return {
        "schema": RECORD_SCHEMA,
        "id": stable_id,
        "name": name,
        "version": "1.0",
        "description": description,
        "category": category,
        "subcategory": subcategory,
        "episode": episode,
        "instructions": instructions,
        "tags": tags,
        "requirements": requirements,
        "workflow_status": (
            "requires_custom_nodes" if unresolved else "converted"
        ),
        "repository_managed": True,
        "is_overridden": False,
        "source_kind": "repository_workflow_pack",
        "source_id": f"workflow-pack:{relative.casefold()}",
        "source_filename": source_path.name,
        "source_archive": source_archive,
        "source_entry": relative,
        "source_workflow": ui_workflow,
        "source_workflow_sha256": sha256_json(ui_workflow),
        "workflow": workflow,
        "sha256": sha256_json(workflow),
        "created_at": CATALOG_TIMESTAMP,
        "updated_at": CATALOG_TIMESTAMP,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--converted-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--custom-node-root",
        default=r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes",
    )
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()
    converted_root = args.converted_root.resolve()
    output_root = args.output_root.resolve()
    records_root = output_root / "records"
    assets_root = output_root / "assets"
    workflows = source_workflows(source_root)
    if not workflows:
        raise SystemExit("No ComfyUI editor workflows were found.")
    if records_root.exists() and any(records_root.iterdir()) and not args.replace:
        raise SystemExit(f"{records_root} is not empty; pass --replace to rebuild it.")
    records_root.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)
    if args.replace:
        for path in records_root.glob("*.json"):
            path.unlink()

    records: list[dict[str, Any]] = []
    for index, source_path in enumerate(workflows, start=1):
        api_path = api_export_path(
            converted_root,
            source_root,
            source_path,
            index,
        )
        if not api_path.is_file():
            raise SystemExit(f"Missing converted API graph: {api_path}")
        record = create_record(
            source_root=source_root,
            source_path=source_path,
            api_path=api_path,
            custom_node_root=args.custom_node_root,
        )
        destination = records_root / f"{record['id']}.json"
        destination.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        records.append(record)

    support_assets: list[str] = []
    for candidate in source_root.rglob("*.json"):
        if candidate in workflows:
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and {"categories", "tags"}.issubset(payload):
            destination = assets_root / "prompt-tags-example-library.json"
            shutil.copy2(candidate, destination)
            support_assets.append(destination.name)

    category_counts = Counter(record["category"] for record in records)
    episode_counts = Counter(record["episode"] for record in records)
    status_counts = Counter(record["workflow_status"] for record in records)
    manifest = {
        "schema": CATALOG_SCHEMA,
        "generated_at": CATALOG_TIMESTAMP,
        "workflow_count": len(records),
        "category_counts": dict(sorted(category_counts.items())),
        "episode_counts": dict(sorted(episode_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "support_assets": support_assets,
        "records": [
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
            for record in records
        ],
        "archive_notes": {
            "EP12 Workflows.zip": (
                "Contains custom-node Python/JavaScript examples and a readme, but no "
                "ComfyUI workflow JSON; no executable catalog record was created."
            )
        },
    }
    (output_root / "catalog.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "workflow_count": len(records),
                "category_counts": dict(category_counts),
                "status_counts": dict(status_counts),
                "output_root": str(output_root),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
