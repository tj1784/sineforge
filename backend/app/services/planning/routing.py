"""Automatic / manual / hybrid provider routing for planning tasks."""

from __future__ import annotations

from typing import Any

from backend.app.schemas.orchestration import (
    LogicalModelProfile,
    ManualTaskRoute,
    PlanningTaskType,
    RoutingDecision,
    RoutingMode,
)
from backend.app.services.planning.errors import PlanningError, PlanningErrorCode
from backend.app.services.planning.profiles import (
    default_profile_for_task,
    next_escalation,
    resolve_model_name,
)


# Logical provider identifiers available to the planning engine. The runtime
# catalog can add configured local/hosted adapters; mock is always available.
MOCK_PROVIDER = "mock"
LOCAL_CLI_PROVIDER = "local_cli"
HOSTED_PROVIDERS = ("openai", "anthropic", "xai", "qwen")


def default_provider_catalog(
    *,
    prefer_local: bool = True,
    prefer_hosted: bool = False,
) -> list[dict[str, Any]]:
    catalog = [
        {
            "provider_identifier": MOCK_PROVIDER,
            "display_name": "Deterministic Mock",
            "execution_mode": "local",
            "availability_status": "available",
            "privacy_classification": "local",
            "capabilities": ["planning"],
        }
    ]
    if prefer_local:
        catalog.append(
            {
                "provider_identifier": LOCAL_CLI_PROVIDER,
                "display_name": "Local CLI (disabled in Phase 1 planning)",
                "execution_mode": "disabled",
                "availability_status": "unavailable",
                "privacy_classification": "local",
                "capabilities": [],
            }
        )
    if prefer_hosted:
        for name in HOSTED_PROVIDERS:
            catalog.append(
                {
                    "provider_identifier": name,
                    "display_name": name,
                    "execution_mode": "disabled",
                    "availability_status": "unavailable",
                    "privacy_classification": "hosted",
                    "capabilities": [],
                }
            )
    return catalog


def build_routing_snapshot(
    *,
    mode: RoutingMode,
    manual_routes: list[ManualTaskRoute] | None,
    prefer_local_providers: bool,
    prefer_hosted_providers: bool,
    transport_retry_limit: int,
    time_budget_sec: int,
    task_types: list[PlanningTaskType],
) -> dict[str, Any]:
    manual = {
        route.task_type.value: {
            "provider_identifier": route.provider_identifier,
            "logical_model": route.logical_model.value if route.logical_model else None,
            "resolved_model": route.resolved_model,
            "rationale": route.rationale,
        }
        for route in (manual_routes or [])
    }
    return {
        "schema_name": "planning.routing_snapshot.v1",
        "mode": mode.value,
        "manual_routes": manual,
        "prefer_local_providers": prefer_local_providers,
        "prefer_hosted_providers": prefer_hosted_providers,
        "transport_retry_limit": transport_retry_limit,
        "time_budget_sec": time_budget_sec,
        "task_types": [t.value for t in task_types],
        "escalation_order": ["luna", "terra", "sol"],
    }


def _pick_automatic_provider(
    *,
    prefer_local: bool,
    prefer_hosted: bool,
    catalog: list[dict[str, Any]] | None = None,
) -> str:
    entries = (
        catalog
        if catalog is not None
        else default_provider_catalog(
            prefer_local=prefer_local, prefer_hosted=prefer_hosted
        )
    )
    available = [
        e for e in entries
        if e.get("availability_status") == "available" and "planning" in (e.get("capabilities") or [])
    ]
    allowed_privacy_classes: set[str] = set()
    if prefer_local:
        allowed_privacy_classes.add("local")
    if prefer_hosted:
        allowed_privacy_classes.add("hosted")
    available = [
        entry
        for entry in available
        if entry.get("privacy_classification") in allowed_privacy_classes
    ]
    available = sorted(
        available,
        key=lambda entry: int(entry.get("routing_priority") or 0),
        reverse=True,
    )
    if not available:
        raise PlanningError(
            PlanningErrorCode.ROUTING_FAILED,
            "No available planning provider satisfies the project/run provider policy",
            details={
                "prefer_local_providers": prefer_local,
                "prefer_hosted_providers": prefer_hosted,
            },
        )
    if prefer_local:
        local = [e for e in available if e.get("privacy_classification") == "local"]
        if local:
            return str(local[0]["provider_identifier"])
    if prefer_hosted:
        hosted = [e for e in available if e.get("privacy_classification") == "hosted"]
        if hosted:
            return str(hosted[0]["provider_identifier"])
    return str(available[0]["provider_identifier"])


def select_route(
    *,
    task_type: PlanningTaskType,
    routing_snapshot: dict[str, Any],
    force_logical_model: LogicalModelProfile | None = None,
    escalation_from: LogicalModelProfile | None = None,
) -> RoutingDecision:
    mode = RoutingMode(routing_snapshot.get("mode", RoutingMode.automatic.value))
    manual_routes: dict[str, Any] = routing_snapshot.get("manual_routes") or {}
    prefer_local = bool(routing_snapshot.get("prefer_local_providers", True))
    prefer_hosted = bool(routing_snapshot.get("prefer_hosted_providers", False))

    manual = manual_routes.get(task_type.value)
    if mode == RoutingMode.manual:
        if not manual:
            raise PlanningError(
                PlanningErrorCode.ROUTING_FAILED,
                f"Manual routing requires an assignment for task_type={task_type.value}",
                details={"task_type": task_type.value},
            )
        logical = force_logical_model or (
            LogicalModelProfile(manual["logical_model"])
            if manual.get("logical_model")
            else default_profile_for_task(task_type)
        )
        provider = str(manual["provider_identifier"])
        resolved = resolve_model_name(
            logical,
            provider_identifier=provider,
            explicit=manual.get("resolved_model"),
        )
        return RoutingDecision(
            task_type=task_type,
            mode=mode,
            provider_identifier=provider,
            logical_model=logical,
            resolved_model=resolved,
            rationale=manual.get("rationale") or "Manual task assignment",
            escalation_from=escalation_from,
        )

    if mode == RoutingMode.hybrid and manual:
        logical = force_logical_model or (
            LogicalModelProfile(manual["logical_model"])
            if manual.get("logical_model")
            else default_profile_for_task(task_type)
        )
        provider = str(manual["provider_identifier"])
        # Hybrid still escalates logical model on repair, but keeps provider.
        resolved = resolve_model_name(
            logical,
            provider_identifier=provider,
            explicit=manual.get("resolved_model") if force_logical_model is None else None,
        )
        return RoutingDecision(
            task_type=task_type,
            mode=mode,
            provider_identifier=provider,
            logical_model=logical,
            resolved_model=resolved,
            rationale=manual.get("rationale") or "Hybrid: manual assignment preferred",
            escalation_from=escalation_from,
        )

    # automatic (or hybrid without manual assignment)
    logical = force_logical_model or default_profile_for_task(task_type)
    provider = _pick_automatic_provider(
        prefer_local=prefer_local,
        prefer_hosted=prefer_hosted,
        catalog=routing_snapshot.get("provider_catalog"),
    )
    resolved = resolve_model_name(logical, provider_identifier=provider)
    rationale = (
        f"Automatic routing to {provider} / {logical.value}"
        if escalation_from is None
        else f"Escalated {escalation_from.value} → {logical.value} on {provider}"
    )
    return RoutingDecision(
        task_type=task_type,
        mode=RoutingMode.automatic if mode == RoutingMode.automatic else mode,
        provider_identifier=provider,
        logical_model=logical,
        resolved_model=resolved,
        rationale=rationale,
        escalation_from=escalation_from,
    )


def escalate_route(
    current: RoutingDecision,
    *,
    routing_snapshot: dict[str, Any],
) -> RoutingDecision | None:
    nxt = next_escalation(current.logical_model)
    if nxt is None:
        return None
    return select_route(
        task_type=current.task_type,
        routing_snapshot=routing_snapshot,
        force_logical_model=nxt,
        escalation_from=current.logical_model,
    )
