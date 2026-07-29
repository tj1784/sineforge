"""Canonical local generation-model contract for CineForge.

Still images are local/private Flux-family generation, with Flux2 defaults for
the active Phase 6 workflow. Video remains pinned to the LTX 2.3 Distilled 1.1
FP8 contract until the user explicitly changes it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from backend.app.services.production_profiles import (
    DEFAULT_PRODUCTION_PROFILE_REF,
    LEGACY_LTX_VIDEO_MODEL,
    LEGACY_LTX_VIDEO_MODEL_KEY,
    ProductionProfile,
    resolve_production_profile,
)

PLANNING_IMAGE_MODEL_KEY = "flux2_dev_fp8mixed"
EXPERIMENTAL_PLANNING_IMAGE_MODEL_KEY = "flux2_dev"
VIDEO_MODEL_KEY = LEGACY_LTX_VIDEO_MODEL_KEY

PLANNING_IMAGE_MODEL = "flux2_dev_fp8mixed.safetensors"
EXPERIMENTAL_PLANNING_IMAGE_MODEL = "flux2_dev.safetensors"
VIDEO_MODEL = LEGACY_LTX_VIDEO_MODEL
VIDEO_PRODUCTION_PROFILE = DEFAULT_PRODUCTION_PROFILE_REF

APPROVED_BASE_MODELS = frozenset(
    {PLANNING_IMAGE_MODEL, EXPERIMENTAL_PLANNING_IMAGE_MODEL, VIDEO_MODEL}
)
APPROVED_MODEL_KEYS = frozenset(
    {PLANNING_IMAGE_MODEL_KEY, EXPERIMENTAL_PLANNING_IMAGE_MODEL_KEY, VIDEO_MODEL_KEY}
)
APPROVED_BASE_MODEL_BY_MODALITY: Mapping[str, str] = {
    "image": PLANNING_IMAGE_MODEL,
    "video": VIDEO_MODEL,
}
APPROVED_IMAGE_BASE_MODELS = frozenset(
    {PLANNING_IMAGE_MODEL, EXPERIMENTAL_PLANNING_IMAGE_MODEL}
)

# These nodes can select a generative base checkpoint/UNet. LoRA, VAE and
# control-model loaders are deliberately excluded: they are auxiliary inputs,
# not permission to replace the base model.
BASE_MODEL_LOADER_TYPES = frozenset(
    {
        "CheckpointLoaderSimple",
        "CheckpointLoader",
        "UNETLoader",
        "UNETLoaderGGUF",
        "CheckpointLoaderNF4",
        "LTXVLoader",
        "WanVideoModelLoader",
    }
)
BASE_MODEL_INPUT_NAMES = frozenset(
    {"ckpt_name", "checkpoint", "model_name", "unet_name"}
)


def require_approved_base_model(
    modality: Literal["image", "video"],
    model_name: str,
    *,
    production_profile: str | ProductionProfile | None = None,
) -> None:
    if modality == "image":
        normalized = model_name.replace("\\", "/").split("/")[-1].lower()
        if normalized.startswith("flux") and normalized.endswith((".safetensors", ".gguf", ".ckpt", ".pt")):
            return
        expected = ", ".join(sorted(APPROVED_IMAGE_BASE_MODELS))
        raise ValueError(f"Planning images require a Flux-family local model such as {expected}; got {model_name}.")

    profile = resolve_production_profile(production_profile)
    if production_profile is None:
        # Retain the exact legacy error contract for unscoped callers.
        expected = APPROVED_BASE_MODEL_BY_MODALITY[modality]
        if model_name != expected:
            sentence = f"Video generation requires {expected}"
            raise ValueError(f"{sentence}; got {model_name}.")
        return
    profile.require_video_model(model_name)


def require_approved_planning_image_model(model_name: str) -> None:
    require_approved_base_model("image", model_name)


def require_approved_video_model(
    model_name: str,
    *,
    production_profile: str | ProductionProfile | None = None,
) -> None:
    require_approved_base_model(
        "video",
        model_name,
        production_profile=production_profile,
    )


def _iter_api_nodes(workflow: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for node in workflow.values():
        if isinstance(node, Mapping) and "class_type" in node:
            yield node


def _iter_ui_nodes(workflow: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    nodes = workflow.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, Mapping):
                yield node


def workflow_base_model_references(workflow: Mapping[str, Any]) -> tuple[str, ...]:
    """Return base-model filenames explicitly selected by a workflow graph.

    Both ComfyUI API-format graphs and UI-format graphs are supported. UI-format
    graphs do not name widget inputs, so only known base-loader widgets are
    inspected and only model-looking string values are returned.
    """

    references: list[str] = []
    for node in _iter_api_nodes(workflow):
        if node.get("class_type") not in BASE_MODEL_LOADER_TYPES:
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, Mapping):
            continue
        for input_name in BASE_MODEL_INPUT_NAMES:
            value = inputs.get(input_name)
            if isinstance(value, str):
                references.append(value)

    for node in _iter_ui_nodes(workflow):
        node_type = node.get("type") or node.get("class_type")
        if node_type not in BASE_MODEL_LOADER_TYPES:
            continue
        widgets = node.get("widgets_values")
        if not isinstance(widgets, list):
            continue
        for value in widgets:
            if isinstance(value, str) and (
                value.lower().endswith((".safetensors", ".gguf", ".ckpt", ".pt"))
            ):
                references.append(value)
                break

    return tuple(dict.fromkeys(references))


def validate_workflow_base_models(
    workflow: Mapping[str, Any],
    modality: Literal["image", "video"],
    *,
    require_reference: bool = True,
    production_profile: str | ProductionProfile | None = None,
) -> tuple[str, ...]:
    """Fail closed when a workflow selects a non-product base model."""

    references = workflow_base_model_references(workflow)
    if require_reference and not references:
        raise ValueError("Workflow does not expose an auditable base-model reference.")
    for reference in references:
        require_approved_base_model(
            modality,
            reference,
            production_profile=production_profile,
        )
    return references
