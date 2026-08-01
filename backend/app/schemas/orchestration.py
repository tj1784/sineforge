"""API and service schemas for Storyboard Phase 1 orchestration runs.

Planning ends at an immutable proposal awaiting review. These schemas never
carry hidden reasoning, raw provider payloads, credentials, or apply actions.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    canceled = "canceled"


class InvocationStatus(StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class RoutingMode(StrEnum):
    automatic = "automatic"
    manual = "manual"
    hybrid = "hybrid"


class LogicalModelProfile(StrEnum):
    """Logical quality tiers. Escalation order is Luna → Terra → Sol."""

    luna = "luna"
    terra = "terra"
    sol = "sol"


class PlanningTaskType(StrEnum):
    """Provider-neutral planning tasks. No render/media/execution tasks."""

    story_structure = "story_structure"
    character_bible = "character_bible"
    chapter_outline = "chapter_outline"
    scene_breakdown = "scene_breakdown"
    shot_list = "shot_list"
    narration_plan = "narration_plan"
    prompt_package = "prompt_package"
    continuity_plan = "continuity_plan"
    model_recommendation = "model_recommendation"
    production_proposal = "production_proposal"


class FailureCategory(StrEnum):
    validation = "validation"
    transport = "transport"
    provider = "provider"
    budget = "budget"
    canceled = "canceled"
    routing = "routing"
    contract = "contract"
    timeout = "timeout"
    internal = "internal"


class ActorType(StrEnum):
    system = "system"
    user = "user"
    provider = "provider"
    router = "router"
    repair = "repair"


class EventType(StrEnum):
    run_created = "run_created"
    run_started = "run_started"
    run_completed = "run_completed"
    run_failed = "run_failed"
    run_canceled = "run_canceled"
    run_resumed = "run_resumed"
    step_started = "step_started"
    step_completed = "step_completed"
    step_failed = "step_failed"
    step_skipped = "step_skipped"
    step_canceled = "step_canceled"
    step_checkpoint = "step_checkpoint"
    routing_selected = "routing_selected"
    routing_escalated = "routing_escalated"
    invocation_started = "invocation_started"
    invocation_succeeded = "invocation_succeeded"
    invocation_failed = "invocation_failed"
    transport_retry = "transport_retry"
    semantic_repair = "semantic_repair"
    proposal_created = "proposal_created"
    budget_exhausted = "budget_exhausted"


# ---------------------------------------------------------------------------
# Request / response API models
# ---------------------------------------------------------------------------


class ManualTaskRoute(BaseModel):
    task_type: PlanningTaskType
    provider_identifier: str = Field(min_length=1, max_length=80)
    logical_model: LogicalModelProfile | None = None
    resolved_model: str | None = Field(default=None, max_length=200)
    rationale: str | None = Field(default=None, max_length=500)


class CreateOrchestrationRunRequest(BaseModel):
    story_id: UUID
    base_storyboard_version_id: UUID | None = None
    requested_by: str | None = Field(default=None, max_length=200)
    routing_mode: RoutingMode = RoutingMode.automatic
    manual_routes: list[ManualTaskRoute] = Field(default_factory=list)
    prefer_local_providers: bool = True
    prefer_hosted_providers: bool = False
    max_steps: int = Field(default=6, ge=1, le=50)
    repair_budget: int = Field(default=3, ge=0, le=20)
    time_budget_sec: int = Field(default=300, ge=30, le=3600)
    transport_retry_limit: int = Field(default=2, ge=0, le=5)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    planning_instruction: str | None = Field(default=None, max_length=4000)
    proposal_type: Literal["storyboard_full_plan", "storyboard_revision"] = (
        "storyboard_full_plan"
    )
    task_types: list[PlanningTaskType] | None = None

    @field_validator("manual_routes")
    @classmethod
    def unique_manual_tasks(cls, value: list[ManualTaskRoute]) -> list[ManualTaskRoute]:
        seen: set[str] = set()
        for route in value:
            key = route.task_type.value
            if key in seen:
                raise ValueError(f"Duplicate manual route for task_type={key}")
            seen.add(key)
        return value


class CancelOrchestrationRunRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    requested_by: str | None = Field(default=None, max_length=200)


class OrchestrationStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    sequence_index: int
    task_type: str
    status: str
    provider_identifier: str | None = None
    logical_model: str | None = None
    resolved_model: str | None = None
    attempt_number: int
    input_hash: str | None = None
    output_hash: str | None = None
    proposal_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_category: str | None = None
    error_message: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OrchestrationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    step_id: UUID | None = None
    event_type: str
    actor_type: str
    actor_reference: str | None = None
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ProviderInvocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    step_id: UUID | None = None
    provider_identifier: str
    model: str | None = None
    idempotency_key: str
    request_hash: str | None = None
    response_hash: str | None = None
    latency_ms: int | None = None
    usage_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    provider_request_id: str | None = None
    finish_category: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ProposalSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    proposal_type: str
    status: str
    schema_name: str | None = None
    content_hash: str | None = None
    validation_status: str | None = None
    story_id: UUID | None = None
    orchestration_run_id: UUID | None = None
    created_at: datetime


class OrchestrationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    base_storyboard_version_id: UUID | None = None
    status: str
    requested_by: str | None = None
    routing_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    default_provider_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    target_duration_sec_snapshot: float | None = None
    input_hash: str | None = None
    current_step: int
    max_steps: int
    repair_budget: int
    repair_used: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    canceled_at: datetime | None = None
    failure_category: str | None = None
    failure_message: str | None = None
    created_at: datetime
    updated_at: datetime


class OrchestrationRunDetailRead(OrchestrationRunRead):
    steps: list[OrchestrationStepRead] = Field(default_factory=list)
    events: list[OrchestrationEventRead] = Field(default_factory=list)
    invocations: list[ProviderInvocationRead] = Field(default_factory=list)
    proposals: list[ProposalSummaryRead] = Field(default_factory=list)


class CreateOrchestrationRunResponse(BaseModel):
    run: OrchestrationRunRead
    created: bool = True
    idempotent_replay: bool = False


class RunActionResponse(BaseModel):
    run: OrchestrationRunRead
    message: str


# ---------------------------------------------------------------------------
# Internal planning contracts (provider-neutral, strict)
# ---------------------------------------------------------------------------


class SanitizedError(BaseModel):
    category: FailureCategory
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def strip_and_bound(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("error message must not be empty")
        return cleaned[:500]


class PlanningContext(BaseModel):
    """Bounded story context passed into providers. No secrets or hidden state."""

    story_id: UUID
    title: str
    base_story: str
    target_duration_sec: float = Field(gt=0)
    logline: str | None = None
    synopsis: str | None = None
    audience: str | None = None
    tone: str | None = None
    genre: str | None = None
    visual_style: str | None = None
    point_of_view: str | None = None
    production_notes: str | None = None
    characters: list[dict[str, Any]] = Field(default_factory=list)
    existing_structure: dict[str, Any] = Field(default_factory=dict)


class ProviderRequestContract(BaseModel):
    """Strict request envelope. Providers must not receive hidden system reasoning."""

    schema_name: str = Field(default="planning.provider_request.v1")
    task_type: PlanningTaskType
    logical_model: LogicalModelProfile
    resolved_model: str
    provider_identifier: str
    context: PlanningContext
    constraints: dict[str, Any] = Field(default_factory=dict)
    previous_output: dict[str, Any] | None = None
    repair_instructions: list[str] = Field(default_factory=list)
    attempt_number: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("repair_instructions")
    @classmethod
    def bound_repair_instructions(cls, value: list[str]) -> list[str]:
        return [item.strip()[:300] for item in value if item and item.strip()][:20]


class ProviderResponseContract(BaseModel):
    """Strict response envelope. No chain-of-thought / hidden reasoning fields."""

    schema_name: str = Field(default="planning.provider_response.v1")
    task_type: PlanningTaskType
    status: str = Field(description="succeeded | failed")
    payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    finish_category: str | None = None
    error: SanitizedError | None = None

    @field_validator("payload")
    @classmethod
    def forbid_hidden_reasoning(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden = {
            "reasoning",
            "chain_of_thought",
            "cot",
            "hidden_reasoning",
            "system_prompt",
            "raw_prompt",
            "raw_response",
            "credentials",
            "api_key",
            "thinking",
            "scratchpad",
        }
        stack: list[Any] = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key, child in current.items():
                    if str(key).lower() in forbidden:
                        raise ValueError(f"Forbidden response field: {key}")
                    stack.append(child)
            elif isinstance(current, list):
                stack.extend(current)
        return value


class ProposalPayloadContract(BaseModel):
    """Immutable planning proposal awaiting human review. Never auto-applied."""

    schema_name: str = Field(default="planning.storyboard_proposal.v1")
    proposal_type: str = Field(default="storyboard_plan")
    summary: str = Field(min_length=1, max_length=1000)
    story_id: UUID
    orchestration_run_id: UUID
    base_storyboard_version_id: UUID | None = None
    target_duration_sec: float = Field(gt=0)
    chapters: list[dict[str, Any]] = Field(default_factory=list)
    characters: list[dict[str, Any]] = Field(default_factory=list)
    voices: list[dict[str, Any]] = Field(default_factory=list)
    shots: list[dict[str, Any]] = Field(default_factory=list)
    narrations: list[dict[str, Any]] = Field(default_factory=list)
    prompt_packages: list[dict[str, Any]] = Field(default_factory=list)
    continuity: list[dict[str, Any]] = Field(default_factory=list)
    model_recommendations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def no_apply_hooks(cls, value: dict[str, Any]) -> dict[str, Any]:
        banned = {"auto_apply", "apply", "execute", "comfy", "ffmpeg", "queue", "download"}
        for key in value:
            if str(key).lower() in banned:
                raise ValueError(f"Proposal metadata must not include apply/execute hook: {key}")
        return value


class RoutingDecision(BaseModel):
    task_type: PlanningTaskType
    mode: RoutingMode
    provider_identifier: str
    logical_model: LogicalModelProfile
    resolved_model: str
    rationale: str
    escalation_from: LogicalModelProfile | None = None


class CheckpointState(BaseModel):
    """Resume-safe checkpoint stored on step metadata / run routing snapshot."""

    schema_name: str = Field(default="planning.checkpoint.v1")
    run_id: UUID
    sequence_index: int
    task_type: PlanningTaskType
    attempt_number: int = Field(ge=1)
    input_hash: str
    last_output_hash: str | None = None
    repair_used: int = Field(ge=0)
    logical_model: LogicalModelProfile | None = None
    provider_identifier: str | None = None
    partial_payload: dict[str, Any] = Field(default_factory=dict)
    completed_task_types: list[str] = Field(default_factory=list)


class EngineBudgets(BaseModel):
    repair_budget: int = Field(ge=0)
    repair_used: int = Field(ge=0)
    time_budget_sec: int = Field(ge=1)
    transport_retry_limit: int = Field(ge=0)
    started_monotonic: float | None = None

    def remaining_repairs(self) -> int:
        return max(0, self.repair_budget - self.repair_used)

    def can_repair(self) -> bool:
        return self.remaining_repairs() > 0
