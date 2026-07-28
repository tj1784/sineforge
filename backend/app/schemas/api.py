from datetime import datetime
from uuid import UUID, uuid4

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.storyboard import StoryRead
from backend.app.schemas.storyboard_settings import (
    DEFAULT_FINAL_HEIGHT,
    DEFAULT_FINAL_WIDTH,
    DEFAULT_FPS,
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_WIDTH,
    DEFAULT_SPEAKING_RATE,
    ProjectStoryboardSettingsRead,
)
from backend.app.schemas.production import PhaseOneBaselineKey, ProductionPipelineRead


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    persistence: str = "stub"


class ProjectChapterIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_index: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = None
    source_prompt: str | None = None
    target_duration_sec: float | None = Field(default=None, gt=0, le=21_600)
    narrative_purpose: str | None = None
    dramatic_progression: str | None = None
    production_notes: str | None = None


class ProjectWorkspaceCreate(BaseModel):
    """One complete project-creation request before final video rendering."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    auto_title: bool = False
    description: str | None = Field(default=None, max_length=2000)
    source_mode: Literal["story", "blank", "import"]
    story_title: str = Field(min_length=1, max_length=300)
    base_story: str = ""
    target_duration_sec: float = Field(gt=0)
    audience: str | None = None
    genre: str | None = None
    tone: str | None = None
    point_of_view: str | None = None
    visual_style: str | None = None
    production_notes: str | None = None
    language: str = Field(default="English", min_length=1, max_length=100)
    narration_dialogue_preference: str | None = None
    source_fidelity_constraints: str | None = None
    content_constraints: str | None = None
    requested_chapter_count: int = Field(default=1, ge=1, le=50)
    chapter_intake: list[ProjectChapterIntake] = Field(default_factory=list)
    bootstrap_phase_plan: bool = False
    auto_approve_phases_through: int | None = Field(default=None, ge=1, le=5)
    run_phase_one: bool = False
    comparison_baseline: PhaseOneBaselineKey | None = None

    aspect_ratio: str = Field(default="16:9", min_length=1, max_length=32)
    preview_width: int = Field(default=DEFAULT_PREVIEW_WIDTH, gt=0)
    preview_height: int = Field(default=DEFAULT_PREVIEW_HEIGHT, gt=0)
    final_width: int = Field(default=DEFAULT_FINAL_WIDTH, gt=0)
    final_height: int = Field(default=DEFAULT_FINAL_HEIGHT, gt=0)
    fps: float = Field(default=DEFAULT_FPS, gt=0)
    captions_enabled: bool = True
    audio_enabled: bool = True
    speaking_rate: float = Field(default=DEFAULT_SPEAKING_RATE, gt=0)
    prefer_hosted_providers: bool = False
    prefer_local_providers: bool = True
    # Operators may enable local model/LoRA download and rendering for video quality work.
    allow_model_download: bool = True
    allow_rendering: bool = True
    require_production_plan_approval: bool = True
    orchestration_mode: str = Field(min_length=1, max_length=64)
    privacy_preference: str = Field(min_length=1, max_length=100)
    quality_preference: str = Field(min_length=1, max_length=100)
    cost_sensitivity: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_source_material(self):
        if self.source_mode != "blank" and not self.base_story.strip():
            raise ValueError("base_story is required unless source_mode is blank.")
        if self.run_phase_one and not self.base_story.strip():
            raise ValueError("base_story is required when run_phase_one is enabled.")
        if (self.bootstrap_phase_plan or self.auto_approve_phases_through) and not self.run_phase_one:
            raise ValueError("Phase plan bootstrap and auto-approval require run_phase_one.")
        if len(self.chapter_intake) > self.requested_chapter_count:
            raise ValueError("chapter_intake cannot exceed requested_chapter_count.")
        chapter_indexes = sorted(chapter.order_index for chapter in self.chapter_intake)
        if chapter_indexes and chapter_indexes != list(range(len(chapter_indexes))):
            raise ValueError("chapter_intake order_index values must be contiguous from 0.")
        return self


class ProjectWorkspaceRead(BaseModel):
    project: ProjectRead
    story: StoryRead
    settings: ProjectStoryboardSettingsRead
    idempotent_replay: bool
    production_pipeline: ProductionPipelineRead | None = None


class SulphurProjectPromptCreate(BaseModel):
    """One complete homepage message to turn into an atomic local project."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=128)
    prompt: str = Field(min_length=12, max_length=24_000)


class SulphurProjectWorkspaceRead(ProjectWorkspaceRead):
    intake_provider: Literal["sulphur"] = "sulphur"
    intake_model: str
    source_prompt_preserved: Literal[True] = True
    target_duration_sec: float
    planned_scene_count: int
    nominal_scene_duration_sec: Literal[8] = 8
    clip_duration_range_sec: tuple[Literal[6], Literal[10]] = (6, 10)


class CampaignCreate(BaseModel):
    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    target_duration_sec: float | None = Field(default=None, gt=0)


class CampaignRead(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    target_duration_sec: float | None = None
    created_at: datetime
    persistence: str = "stub"


class JobRead(BaseModel):
    id: UUID
    status: str
    detail: str
    workflow_run_id: UUID | None = None
    comfy_prompt_id: str | None = None
    error_message: str | None = None


class StubStore:
    projects: dict[UUID, ProjectRead] = {}
    campaigns: dict[UUID, CampaignRead] = {}
    jobs: dict[UUID, JobRead] = {}

    @classmethod
    def create_project(cls, payload: ProjectCreate) -> ProjectRead:
        item = ProjectRead(id=uuid4(), name=payload.name, description=payload.description, created_at=datetime.utcnow())
        cls.projects[item.id] = item
        return item

    @classmethod
    def create_campaign(cls, payload: CampaignCreate) -> CampaignRead:
        item = CampaignRead(
            id=uuid4(),
            project_id=payload.project_id,
            name=payload.name,
            target_duration_sec=payload.target_duration_sec,
            created_at=datetime.utcnow(),
        )
        cls.campaigns[item.id] = item
        return item
