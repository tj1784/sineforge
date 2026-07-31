"""Public provider discovery, connection-test, and routing-preflight contracts.

These schemas deliberately separate user-declared profile metadata from facts
derived from the live in-process provider registry.  No request accepts a
credential, command, executable path, or arbitrary provider URL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.orchestration import (
    ManualTaskRoute,
    PlanningTaskType,
    RoutingMode,
)


class ProviderCatalogEntry(BaseModel):
    provider_identifier: str
    display_name: str
    availability_status: str
    execution_mode: str
    privacy_classification: str
    capabilities: list[str] = Field(default_factory=list)
    capability_source: str
    checked_at: datetime
    connection_test_supported: bool
    detail: str


class ProviderCatalogResponse(BaseModel):
    schema_name: str = "planning.provider_catalog.v1"
    generated_at: datetime
    providers: list[ProviderCatalogEntry]


class ProviderCapabilitiesResponse(BaseModel):
    provider_identifier: str
    availability_status: str
    capabilities: list[str] = Field(default_factory=list)
    capability_source: str
    checked_at: datetime


class ProviderProfileCapabilitiesResponse(BaseModel):
    profile_id: UUID
    provider_identifier: str
    declared_capabilities: list[str] = Field(default_factory=list)
    declaration_source: str | None = None
    verified_capabilities: list[str] = Field(default_factory=list)
    verified_capability_source: str
    verified_availability_status: str
    checked_at: datetime


class ProviderConnectionTestRequest(BaseModel):
    """A bounded explicit probe request; secrets are settings-owned only."""

    model_config = ConfigDict(extra="forbid")

    timeout_sec: float = Field(default=3.0, ge=0.1, le=10.0)


class ProviderConnectionTestResponse(BaseModel):
    provider_identifier: str
    attempted: bool
    success: bool
    availability_status: str
    checked_at: datetime
    latency_ms: int | None = None
    capabilities: list[str] = Field(default_factory=list)
    detail: str
    error_code: str | None = None


class RoutingPreflightRequest(BaseModel):
    """Non-mutating subset of orchestration-run routing configuration."""

    model_config = ConfigDict(extra="forbid")

    routing_mode: RoutingMode = RoutingMode.automatic
    manual_routes: list[ManualTaskRoute] = Field(default_factory=list)
    prefer_local_providers: bool = True
    prefer_hosted_providers: bool = False
    max_steps: int = Field(default=6, ge=1, le=50)
    transport_retry_limit: int = Field(default=2, ge=0, le=5)
    time_budget_sec: int = Field(default=300, ge=30, le=3600)
    task_types: list[PlanningTaskType] | None = None

    @field_validator("manual_routes")
    @classmethod
    def unique_manual_tasks(
        cls, value: list[ManualTaskRoute]
    ) -> list[ManualTaskRoute]:
        seen: set[PlanningTaskType] = set()
        for route in value:
            if route.task_type in seen:
                raise ValueError(
                    f"Duplicate manual route for task_type={route.task_type.value}"
                )
            seen.add(route.task_type)
        return value

    @field_validator("task_types")
    @classmethod
    def unique_task_types(
        cls, value: list[PlanningTaskType] | None
    ) -> list[PlanningTaskType] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("task_types must not contain duplicates")
        return value


class RoutingValidationIssue(BaseModel):
    code: str
    message: str
    task_type: str | None = None
    provider_identifier: str | None = None


class RoutingPreflightRoute(BaseModel):
    task_type: str
    source: str
    provider_identifier: str | None = None
    logical_model: str | None = None
    resolved_model: str | None = None
    availability_status: str | None = None
    privacy_classification: str | None = None


class RoutingPreflightResponse(BaseModel):
    story_id: UUID
    valid: bool
    requested_mode: RoutingMode
    effective_mode: RoutingMode
    routes: list[RoutingPreflightRoute] = Field(default_factory=list)
    provider_facts: list[ProviderCatalogEntry] = Field(default_factory=list)
    errors: list[RoutingValidationIssue] = Field(default_factory=list)
    warnings: list[RoutingValidationIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
