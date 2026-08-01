from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PhaseSevenVideoQueueRequest(BaseModel):
    requested_by: str = "CineForge local operator"
    seed: int | None = None
    workflow_label: str | None = None
    workflow_source: str | None = None
    workflow_api_json: dict | None = None


class PhaseSevenVideoQueuedJob(BaseModel):
    shot_id: UUID
    starting_image_asset_id: UUID
    engine: Literal["comfyui"] = "comfyui"
    comfy_prompt_id: str
    runner_job_id: str = Field(
        description="Deprecated compatibility alias for comfy_prompt_id.",
        deprecated=True,
    )
    shot_code: str
    prompt: str
    negative_prompt: str
    seed: int
    frame_count: int
    input_image: str
    output_prefix: str


class PhaseSevenVideoQueueResponse(BaseModel):
    queued_count: int
    blocked_count: int = 0
    required_count: int
    message: str
    engine: Literal["comfyui"] = "comfyui"
    comfyui_url: str
    runner_url: str = Field(
        description="Deprecated compatibility alias for comfyui_url.",
        deprecated=True,
    )
    workflow_label: str
    jobs: list[PhaseSevenVideoQueuedJob] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
