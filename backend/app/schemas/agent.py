"""Contextual Operator API contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRiskClass(StrEnum):
    read = "read"
    low = "low"
    medium = "medium"
    high = "high"
    destructive = "destructive"


class AgentProposalStatus(StrEnum):
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    failed = "failed"
    stale = "stale"
    canceled = "canceled"


class AgentRef(StrictModel):
    type: str = Field(min_length=1, max_length=80)
    id: str = Field(min_length=1, max_length=200)
    version: str | int | None = None


class PageContextEnvelope(StrictModel):
    contextVersion: int = Field(ge=1)
    capturedAt: datetime
    routeId: str = Field(min_length=1, max_length=160)
    pathname: str = Field(min_length=1, max_length=2048)
    pageViewId: str = Field(min_length=1, max_length=128)
    pageTitle: str = Field(min_length=1, max_length=240)
    domain: str = Field(min_length=1, max_length=80)
    tenantId: str | None = Field(default=None, max_length=200)
    projectId: UUID | None = None
    projectVersion: str | int | None = None
    recordType: str | None = Field(default=None, max_length=80)
    recordId: str | None = Field(default=None, max_length=200)
    recordVersion: str | int | None = None
    parentRefs: list[AgentRef] = Field(default_factory=list)
    selectedRefs: list[AgentRef] = Field(default_factory=list)
    activeTab: str | None = Field(default=None, max_length=120)
    activePanel: str | None = Field(default=None, max_length=120)
    filters: dict[str, Any] = Field(default_factory=dict)
    mode: str | None = Field(default="view", max_length=32)
    dirty: bool = False
    capabilities: list[str] = Field(default_factory=list)
    correlationId: str = Field(min_length=1, max_length=128)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in {"view", "edit", "review", "compare"}:
            raise ValueError("mode must be view, edit, review, or compare")
        return value


class AgentSessionCreate(StrictModel):
    actor_id: str = Field(default="local-user", min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=240)
    context: PageContextEnvelope | None = None


class AgentSessionRead(StrictModel):
    id: UUID
    actor_id: str
    title: str | None = None
    provider: str
    model: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class AgentProviderHealth(StrictModel):
    enabled: bool
    provider: str
    base_url: str
    configured_model: str
    reachable: bool
    status: str
    model_count: int = 0
    active_model_id: str | None = None
    error: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)


class AgentProviderModel(StrictModel):
    id: str
    owned_by: str | None = None
    created: int | None = None


class AgentProviderModelsResponse(StrictModel):
    enabled: bool
    reachable: bool
    configured_model: str
    active_model_id: str | None = None
    models: list[AgentProviderModel] = Field(default_factory=list)
    error: str | None = None


class AgentToolDescriptor(StrictModel):
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_permission: str
    allowed_resource_scopes: list[str]
    risk_class: AgentRiskClass
    approval_required: bool
    idempotent: bool
    timeout_seconds: int
    result_size_limit: int


class AgentToolsResponse(StrictModel):
    tools: list[AgentToolDescriptor]


class AgentMessageCreate(StrictModel):
    actor_id: str = Field(default="local-user", min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    context: PageContextEnvelope
    idempotency_key: str | None = Field(default=None, max_length=128)


class AgentToolActivity(StrictModel):
    id: UUID | None = None
    name: str
    status: str
    risk_class: AgentRiskClass
    target: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AgentContextSnapshotRead(StrictModel):
    id: UUID
    context_hash: str
    context: PageContextEnvelope
    hydrated_summary: dict[str, Any]
    source_refs: list[dict[str, Any]]


class AgentMessageRead(StrictModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    status: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentProposalRead(StrictModel):
    id: UUID
    session_id: UUID
    tool_name: str
    proposal_hash: str
    target_type: str
    target_id: UUID | None = None
    target_version: str | None = None
    status: AgentProposalStatus
    arguments: dict[str, Any]
    validation: dict[str, Any]
    approval_required: bool
    approval_token: str | None = None
    approval_expires_at: datetime | None = None
    created_at: datetime


class AgentActionReceiptRead(StrictModel):
    id: UUID
    session_id: UUID
    proposal_id: UUID | None = None
    action: str
    actor_id: str
    target_type: str
    target_id: UUID | None = None
    target_version_before: str | None = None
    target_version_after: str | None = None
    result_resource_type: str | None = None
    result_resource_id: UUID | None = None
    status: str
    undo_status: str
    result: dict[str, Any]
    undo: dict[str, Any]
    created_at: datetime


class AgentMessageTurnResponse(StrictModel):
    session: AgentSessionRead
    user_message: AgentMessageRead
    assistant_message: AgentMessageRead
    context_snapshot: AgentContextSnapshotRead
    provider_health: AgentProviderHealth
    tool_activities: list[AgentToolActivity] = Field(default_factory=list)
    proposals: list[AgentProposalRead] = Field(default_factory=list)
    receipts: list[AgentActionReceiptRead] = Field(default_factory=list)


class AgentProposalApproveRequest(StrictModel):
    actor_id: str = Field(default="local-user", min_length=1, max_length=200)
    approval_token: str = Field(min_length=20, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=128)


class AgentProposalRejectRequest(StrictModel):
    actor_id: str = Field(default="local-user", min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)


class AgentUndoRequest(StrictModel):
    actor_id: str = Field(default="local-user", min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4000)
