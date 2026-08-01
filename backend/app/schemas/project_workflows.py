"""Project-level workflow lane contracts.

The selected lane is durable project identity, not a transient UI preference.
It decides whether a project may use CineForge's provider-assisted planning
surface or the deterministic Python scene-reset pipeline.
"""

from __future__ import annotations

from copy import deepcopy
from enum import Enum


class ProjectWorkflowLane(str, Enum):
    """Supported project production lanes."""

    cineforge_studio = "cineforge_studio"
    agentless = "agentless"


DEFAULT_PROJECT_WORKFLOW_LANE = ProjectWorkflowLane.cineforge_studio
AGENTLESS_PRODUCTION_PROFILE_REF = "ltx_base@2"


_STUDIO_WORKFLOW_POLICY: dict = {
    "schema_version": 1,
    "lane": ProjectWorkflowLane.cineforge_studio.value,
    "orchestration": "provider_assisted",
}


_AGENTLESS_WORKFLOW_POLICY: dict = {
    "schema_version": 2,
    "lane": ProjectWorkflowLane.agentless.value,
    "orchestration": "deterministic_python",
    "planning": {
        "mode": "local_lm_studio",
        "default_agent": "grok",
        "local_agent_required": True,
        "hosted_agents_allowed": False,
        "prompt_artifact_format": "json",
        "prompt_artifact_extension": ".json",
        "prompt_artifact_filename": "project-planning-prompt.json",
        "prompt_schema_version": "sineforge.local-planning-prompt/v1",
    },
    "production_profile_ref": AGENTLESS_PRODUCTION_PROFILE_REF,
    "max_scenes": 50,
    "anchor": {
        "model_family": "FLUX.2",
        "fresh_per_scene": True,
        "format": "png",
        "previous_frame_handoff": False,
        "initial_resolution": {
            "width": 768,
            "height": 448,
        },
        "candidate_resolution": {
            "width": 960,
            "height": 544,
        },
    },
    "video": {
        "model_family": "LTX-2.3",
        "ingredients_reference_sheet": True,
        "first_frame_i2v": True,
        "bypass_i2v": False,
        "fps": 24,
        "frame_count": 241,
        "duration_sec": 10,
    },
    "seeds": {
        "image_and_video_separate": True,
    },
    "retries": {
        "anchor_max_attempts": 3,
        "video_max_attempts": 3,
    },
    "queue": {
        "max_active_gpu_jobs": 1,
    },
    "mastering": {
        "anchor_format": "png",
        "intermediate_master_formats": ["prores", "ffv1"],
        "final_delivery_encode_count": 1,
    },
}


def normalize_project_workflow_lane(
    value: ProjectWorkflowLane | str | None,
) -> ProjectWorkflowLane:
    """Return the canonical lane, applying the compatibility default."""

    if value is None:
        return DEFAULT_PROJECT_WORKFLOW_LANE
    return value if isinstance(value, ProjectWorkflowLane) else ProjectWorkflowLane(value)


def is_agentless_workflow_lane(
    value: ProjectWorkflowLane | str | None,
) -> bool:
    """Whether ``value`` selects the deterministic agentless lane."""

    try:
        return normalize_project_workflow_lane(value) is ProjectWorkflowLane.agentless
    except ValueError:
        return False


def is_cineforge_studio_workflow_lane(
    value: ProjectWorkflowLane | str | None,
) -> bool:
    """Whether ``value`` explicitly selects the legacy Studio lane.

    Unlike read-side normalization, execution admission does not treat a
    missing value as the compatibility default.
    """

    if value is None:
        return False
    try:
        lane = (
            value
            if isinstance(value, ProjectWorkflowLane)
            else ProjectWorkflowLane(value)
        )
        return lane is ProjectWorkflowLane.cineforge_studio
    except ValueError:
        return False


def workflow_lane_policy_snapshot(
    value: ProjectWorkflowLane | str | None,
) -> dict:
    """Return an isolated JSON-serializable policy snapshot for persistence."""

    lane = normalize_project_workflow_lane(value)
    policy = (
        _AGENTLESS_WORKFLOW_POLICY
        if lane is ProjectWorkflowLane.agentless
        else _STUDIO_WORKFLOW_POLICY
    )
    return deepcopy(policy)
