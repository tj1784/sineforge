from pydantic import BaseModel, Field
from uuid import UUID


class PhaseSevenVideoQueueRequest(BaseModel):
    requested_by: str = "CineForge local operator"
    seed: int | None = None
    workflow_label: str | None = None
    workflow_source: str | None = None
    workflow_api_json: dict | None = None


class PhaseSevenVideoQueuedJob(BaseModel):
    shot_id: UUID
    starting_image_asset_id: UUID
    runner_job_id: str
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
    runner_url: str
    workflow_label: str
    jobs: list[PhaseSevenVideoQueuedJob] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
