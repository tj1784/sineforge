"""Factual provider discovery and non-mutating routing validation.

The only network-capable operations in this module are explicit, bounded
connection tests. Hosted credentials remain at the ``Settings`` secret
boundary; Qwen and Sulphur tests target their configured loopback-only LM
Studio API.
Catalog reads and routing preflight never call any provider.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import Project, ProviderProfile, Story, TaskProviderAssignment
from backend.app.schemas.project_workflows import is_agentless_workflow_lane
from backend.app.schemas.orchestration import ManualTaskRoute, PlanningTaskType, RoutingMode
from backend.app.schemas.providers import (
    ProviderCapabilitiesResponse,
    ProviderCatalogEntry,
    ProviderCatalogResponse,
    ProviderConnectionTestResponse,
    ProviderProfileCapabilitiesResponse,
    RoutingPreflightRequest,
    RoutingPreflightResponse,
    RoutingPreflightRoute,
    RoutingValidationIssue,
)
from backend.app.services import storyboard_settings as storyboard_settings_service
from backend.app.services.lm_studio_models import get_active_lm_studio_model_id
from backend.app.services.planning.engine import DEFAULT_PIPELINE
from backend.app.services.planning.errors import PlanningError
from backend.app.services.planning.provider_registry import (
    ProviderDescriptor,
    describe_providers,
)
from backend.app.services.planning.routing import build_routing_snapshot, select_route


MAX_CONNECTION_TEST_RESPONSE_BYTES = 65_536
CONNECTION_TEST_CAPABLE = frozenset({"mock", "openai", "qwen", "sulphur", "grok"})


class ProviderContractNotFoundError(LookupError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _entry(
    descriptor: ProviderDescriptor,
    *,
    checked_at: datetime,
) -> ProviderCatalogEntry:
    return ProviderCatalogEntry(
        provider_identifier=descriptor.provider_identifier,
        display_name=descriptor.display_name,
        availability_status=descriptor.availability_status.value,
        execution_mode=descriptor.execution_mode,
        privacy_classification=descriptor.privacy_classification,
        capabilities=list(descriptor.capabilities),
        capability_source="runtime_registry",
        checked_at=checked_at,
        connection_test_supported=(
            descriptor.provider_identifier in CONNECTION_TEST_CAPABLE
        ),
        detail=descriptor.detail,
    )


def provider_catalog(settings: Settings | None = None) -> ProviderCatalogResponse:
    """Return current in-process configuration facts without probing providers."""

    checked_at = _utcnow()
    descriptors = describe_providers(settings or get_settings())
    return ProviderCatalogResponse(
        generated_at=checked_at,
        providers=[_entry(item, checked_at=checked_at) for item in descriptors],
    )


def provider_descriptor(
    provider_identifier: str,
    settings: Settings | None = None,
) -> ProviderCatalogEntry:
    identifier = (provider_identifier or "").strip().lower()
    catalog = provider_catalog(settings)
    for item in catalog.providers:
        if item.provider_identifier == identifier:
            return item
    raise ProviderContractNotFoundError(
        f"Provider '{identifier}' is not registered for planning."
    )


def provider_capabilities(
    provider_identifier: str,
    settings: Settings | None = None,
) -> ProviderCapabilitiesResponse:
    item = provider_descriptor(provider_identifier, settings)
    return ProviderCapabilitiesResponse(
        provider_identifier=item.provider_identifier,
        availability_status=item.availability_status,
        capabilities=item.capabilities,
        capability_source=item.capability_source,
        checked_at=item.checked_at,
    )


def _declared_capability_names(raw: dict[str, Any] | None) -> list[str]:
    """Extract declaration labels without treating arbitrary metadata as facts."""

    value = dict(raw or {})
    candidates = value.get("declared_capabilities", value.get("capabilities"))
    if isinstance(candidates, list):
        return sorted(
            {
                str(item).strip()
                for item in candidates
                if str(item).strip()
            }
        )
    # Compatibility for older profiles that stored boolean declarations.
    return sorted(
        str(key)
        for key, enabled in value.items()
        if isinstance(enabled, bool) and enabled
    )


def provider_profile_capabilities(
    db: Session,
    profile_id: UUID,
    settings: Settings | None = None,
) -> ProviderProfileCapabilitiesResponse:
    profile = db.get(ProviderProfile, profile_id)
    if profile is None:
        raise ProviderContractNotFoundError("Provider profile not found.")
    live = provider_capabilities(profile.provider_identifier, settings)
    return ProviderProfileCapabilitiesResponse(
        profile_id=profile.id,
        provider_identifier=profile.provider_identifier,
        declared_capabilities=_declared_capability_names(profile.capabilities_json),
        declaration_source=profile.capability_source,
        verified_capabilities=live.capabilities,
        verified_capability_source=live.capability_source,
        verified_availability_status=live.availability_status,
        checked_at=live.checked_at,
    )


HttpClientFactory = Callable[[float], httpx.Client]


class ProviderConnectionTester:
    """Explicit, bounded provider health check with an injectable transport."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client_factory: HttpClientFactory | None = None,
        max_response_bytes: int = MAX_CONNECTION_TEST_RESPONSE_BYTES,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client_factory = http_client_factory
        self.max_response_bytes = min(
            MAX_CONNECTION_TEST_RESPONSE_BYTES,
            max(1_024, int(max_response_bytes)),
        )

    def _client(self, timeout_sec: float) -> httpx.Client:
        if self.http_client_factory is not None:
            return self.http_client_factory(timeout_sec)
        return httpx.Client(
            timeout=httpx.Timeout(timeout_sec),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        )

    def _test_local_lm_studio(
        self,
        *,
        provider_identifier: str,
        timeout_sec: float,
        checked_at: datetime,
        capabilities: list[str],
    ) -> ProviderConnectionTestResponse:
        if provider_identifier == "qwen":
            configured = self.settings.qwen_configured
            model_id = self.settings.qwen_model_id
            display_name = "Qwen3 4B Hivemind"
        elif provider_identifier == "grok":
            configured = self.settings.sulphur_planning_enabled
            model_id = get_active_lm_studio_model_id(self.settings) or self.settings.grok_model_id
            display_name = "Grok"
        else:
            configured = self.settings.sulphur_configured
            model_id = self.settings.sulphur_model_id
            display_name = "Sulphur 2 Base"
        if not configured:
            return self._result(
                provider_identifier=provider_identifier,
                attempted=False,
                success=False,
                availability_status="not_configured",
                checked_at=checked_at,
                capabilities=capabilities,
                detail=(
                    f"{display_name} planning is disabled or its configured "
                    "GGUF is missing."
                ),
                error_code="not_configured",
            )

        started_at = time.monotonic()
        try:
            parsed = urlsplit(self.settings.sulphur_base_url)
            models_url = urlunsplit(
                (parsed.scheme, parsed.netloc, "/api/v1/models", "", "")
            )
            with self._client(timeout_sec) as client:
                response = client.get(
                    models_url,
                    timeout=timeout_sec,
                )
                content = response.content
                if len(content) > self.max_response_bytes:
                    return self._result(
                        provider_identifier=provider_identifier,
                        attempted=True,
                        success=False,
                        availability_status="unavailable",
                        checked_at=checked_at,
                        capabilities=capabilities,
                        detail=(
                            f"{display_name} response exceeded the "
                            "connection-test byte limit."
                        ),
                        started_at=started_at,
                        error_code="response_too_large",
                    )
                if not 200 <= response.status_code < 300:
                    return self._result(
                        provider_identifier=provider_identifier,
                        attempted=True,
                        success=False,
                        availability_status="unavailable",
                        checked_at=checked_at,
                        capabilities=capabilities,
                        detail=(
                            "LM Studio returned an unexpected status for "
                            f"{display_name}."
                        ),
                        started_at=started_at,
                        error_code="unexpected_status",
                    )
                payload = json.loads(content.decode("utf-8"))
                entries = payload.get("models") if isinstance(payload, dict) else None
                loaded = any(
                    isinstance(item, dict)
                    and (
                        any(
                            isinstance(instance, dict)
                            and instance.get("id") == model_id
                            for instance in (
                                item.get("loaded_instances")
                                if isinstance(item.get("loaded_instances"), list)
                                else []
                            )
                        )
                        or (
                            item.get("key") == model_id
                            and bool(item.get("loaded_instances"))
                        )
                    )
                    for item in (entries if isinstance(entries, list) else [])
                )
                return self._result(
                    provider_identifier=provider_identifier,
                    attempted=True,
                    success=loaded,
                    availability_status="available" if loaded else "unavailable",
                    checked_at=checked_at,
                    capabilities=capabilities,
                    detail=(
                        f"The configured {display_name} model is loaded in LM Studio."
                        if loaded
                        else (
                            "LM Studio is reachable, but the configured "
                            f"{display_name} model is not loaded."
                        )
                    ),
                    started_at=started_at,
                    error_code=None if loaded else "model_not_loaded",
                )
        except httpx.TimeoutException:
            return self._result(
                provider_identifier=provider_identifier,
                attempted=True,
                success=False,
                availability_status="unavailable",
                checked_at=checked_at,
                capabilities=capabilities,
                detail=(
                    f"{display_name} connection check timed out within the "
                    "requested bound."
                ),
                started_at=started_at,
                error_code="timeout",
            )
        except (httpx.TransportError, UnicodeDecodeError, json.JSONDecodeError):
            return self._result(
                provider_identifier=provider_identifier,
                attempted=True,
                success=False,
                availability_status="unavailable",
                checked_at=checked_at,
                capabilities=capabilities,
                detail=(
                    f"{display_name} could not be verified through the "
                    "loopback LM Studio API."
                ),
                started_at=started_at,
                error_code="transport_failed",
            )

    @staticmethod
    def _result(
        *,
        provider_identifier: str,
        attempted: bool,
        success: bool,
        availability_status: str,
        checked_at: datetime,
        capabilities: list[str],
        detail: str,
        started_at: float | None = None,
        error_code: str | None = None,
    ) -> ProviderConnectionTestResponse:
        latency_ms = None
        if started_at is not None:
            latency_ms = max(0, int((time.monotonic() - started_at) * 1_000))
        return ProviderConnectionTestResponse(
            provider_identifier=provider_identifier,
            attempted=attempted,
            success=success,
            availability_status=availability_status,
            checked_at=checked_at,
            latency_ms=latency_ms,
            capabilities=capabilities,
            detail=detail,
            error_code=error_code,
        )

    def test(
        self,
        provider_identifier: str,
        *,
        timeout_sec: float,
    ) -> ProviderConnectionTestResponse:
        descriptor = provider_descriptor(provider_identifier, self.settings)
        checked_at = _utcnow()
        capabilities = list(descriptor.capabilities)

        if descriptor.provider_identifier == "mock":
            started_at = time.monotonic()
            return self._result(
                provider_identifier="mock",
                attempted=True,
                success=True,
                availability_status="available",
                checked_at=checked_at,
                capabilities=capabilities,
                detail="Deterministic local mock is available; no network call was made.",
                started_at=started_at,
            )

        if descriptor.provider_identifier in {"qwen", "sulphur", "grok"}:
            return self._test_local_lm_studio(
                provider_identifier=descriptor.provider_identifier,
                timeout_sec=timeout_sec,
                checked_at=checked_at,
                capabilities=capabilities,
            )

        if descriptor.provider_identifier != "openai":
            # Explicit stubs are facts, not probes.  In particular this branch
            # never constructs an HTTP client or shells out to a CLI.
            return self._result(
                provider_identifier=descriptor.provider_identifier,
                attempted=False,
                success=False,
                availability_status=descriptor.availability_status,
                checked_at=checked_at,
                capabilities=capabilities,
                detail=descriptor.detail,
                error_code=descriptor.availability_status,
            )

        if not self.settings.openai_configured:
            return self._result(
                provider_identifier="openai",
                attempted=False,
                success=False,
                availability_status="not_configured",
                checked_at=checked_at,
                capabilities=capabilities,
                detail="OpenAI planning is disabled or its settings-owned credential is absent.",
                error_code="not_configured",
            )

        # Secret boundary: the key can only come from Settings.  Requests do
        # not accept it and no provider-profile field is consulted for it.
        assert self.settings.openai_api_key is not None
        api_key = self.settings.openai_api_key.get_secret_value().strip()
        started_at = time.monotonic()
        url = f"{self.settings.openai_base_url.rstrip('/')}/models"
        try:
            with self._client(timeout_sec) as client:
                with client.stream(
                    "GET",
                    url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    params={"limit": "1"},
                    timeout=timeout_sec,
                ) as response:
                    declared_length = response.headers.get("content-length")
                    if declared_length is not None:
                        try:
                            if int(declared_length) > self.max_response_bytes:
                                return self._result(
                                    provider_identifier="openai",
                                    attempted=True,
                                    success=False,
                                    availability_status="unavailable",
                                    checked_at=checked_at,
                                    capabilities=capabilities,
                                    detail="Provider response exceeded the connection-test byte limit.",
                                    started_at=started_at,
                                    error_code="response_too_large",
                                )
                        except ValueError:
                            # An invalid content-length is not trusted; the
                            # streamed byte counter below remains authoritative.
                            pass

                    byte_count = 0
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if byte_count > self.max_response_bytes:
                            return self._result(
                                provider_identifier="openai",
                                attempted=True,
                                success=False,
                                availability_status="unavailable",
                                checked_at=checked_at,
                                capabilities=capabilities,
                                detail="Provider response exceeded the connection-test byte limit.",
                                started_at=started_at,
                                error_code="response_too_large",
                            )

                    if 200 <= response.status_code < 300:
                        return self._result(
                            provider_identifier="openai",
                            attempted=True,
                            success=True,
                            availability_status="available",
                            checked_at=checked_at,
                            capabilities=capabilities,
                            detail="OpenAI planning endpoint accepted the bounded connection check.",
                            started_at=started_at,
                        )
                    if response.status_code in {401, 403}:
                        error_code = "authentication_failed"
                        detail = "OpenAI rejected the settings-owned credential."
                    elif response.status_code == 429:
                        error_code = "rate_limited"
                        detail = "OpenAI was reached but rate-limited the connection check."
                    elif response.status_code >= 500:
                        error_code = "provider_error"
                        detail = "OpenAI returned a server error during the connection check."
                    else:
                        error_code = "unexpected_status"
                        detail = "OpenAI returned an unexpected status during the connection check."
                    return self._result(
                        provider_identifier="openai",
                        attempted=True,
                        success=False,
                        availability_status="unavailable",
                        checked_at=checked_at,
                        capabilities=capabilities,
                        detail=detail,
                        started_at=started_at,
                        error_code=error_code,
                    )
        except httpx.TimeoutException:
            return self._result(
                provider_identifier="openai",
                attempted=True,
                success=False,
                availability_status="unavailable",
                checked_at=checked_at,
                capabilities=capabilities,
                detail="OpenAI connection check timed out within the requested bound.",
                started_at=started_at,
                error_code="timeout",
            )
        except httpx.TransportError:
            return self._result(
                provider_identifier="openai",
                attempted=True,
                success=False,
                availability_status="unavailable",
                checked_at=checked_at,
                capabilities=capabilities,
                detail="OpenAI could not be reached during the bounded connection check.",
                started_at=started_at,
                error_code="transport_failed",
            )


def _issue(
    code: str,
    message: str,
    *,
    task_type: PlanningTaskType | str | None = None,
    provider_identifier: str | None = None,
) -> RoutingValidationIssue:
    return RoutingValidationIssue(
        code=code,
        message=message,
        task_type=(
            task_type.value if isinstance(task_type, PlanningTaskType) else task_type
        ),
        provider_identifier=provider_identifier,
    )


def validate_story_routing(
    db: Session,
    story_id: UUID,
    payload: RoutingPreflightRequest,
    settings: Settings | None = None,
) -> RoutingPreflightResponse:
    """Validate the effective route graph without persisting or calling providers."""

    story = db.get(Story, story_id)
    if story is None:
        raise ProviderContractNotFoundError("Story not found.")

    cfg = settings or get_settings()
    project = db.get(Project, story.project_id)
    agentless = bool(
        project is not None
        and is_agentless_workflow_lane(project.workflow_lane)
    )
    project_settings = storyboard_settings_service.get_settings(db, story.project_id)
    facts = provider_catalog(cfg)
    fact_by_id = {item.provider_identifier: item for item in facts.providers}
    selected_agent: str | None = None
    if agentless:
        selected_agent = str(
            (project_settings.prompting_policy_json or {}).get(
                "planning_agent",
                "qwen",
            )
        )
    errors: list[RoutingValidationIssue] = []
    warnings: list[RoutingValidationIssue] = []

    task_types = list(payload.task_types or DEFAULT_PIPELINE)
    if len(task_types) > payload.max_steps:
        errors.append(
            _issue(
                "max_steps_exceeded",
                "Selected task count exceeds max_steps.",
            )
        )

    if payload.prefer_hosted_providers and not project_settings.prefer_hosted_providers:
        errors.append(
            _issue(
                "hosted_provider_policy_blocked",
                "Hosted planning providers are disabled by project policy.",
            )
        )
    if payload.prefer_local_providers and not project_settings.prefer_local_providers:
        errors.append(
            _issue(
                "local_provider_policy_blocked",
                "Local planning providers are disabled by project policy.",
            )
        )
    if agentless and payload.prefer_hosted_providers:
        errors.append(
            _issue(
                "agentless_hosted_provider_blocked",
                "Agentless projects prohibit hosted/API planning agents.",
            )
        )
    if agentless and not payload.prefer_local_providers:
        errors.append(
            _issue(
                "agentless_local_provider_required",
                "Agentless projects require their selected local planning agent.",
            )
        )
    if (
        payload.routing_mode != RoutingMode.manual
        and not payload.prefer_local_providers
        and not payload.prefer_hosted_providers
    ):
        errors.append(
            _issue(
                "no_provider_class_allowed",
                "Automatic or hybrid routing requires an allowed provider class.",
            )
        )

    selected_tasks = set(task_types)
    route_by_task: dict[PlanningTaskType, tuple[ManualTaskRoute, str]] = {}
    assignment_rows = db.execute(
        select(TaskProviderAssignment, ProviderProfile)
        .join(
            ProviderProfile,
            ProviderProfile.id == TaskProviderAssignment.provider_profile_id,
        )
        .where(
            TaskProviderAssignment.story_id == story_id,
            TaskProviderAssignment.enabled.is_(True),
        )
        .order_by(
            TaskProviderAssignment.priority.desc(),
            TaskProviderAssignment.task_type,
        )
    ).all()
    for assignment, profile in assignment_rows:
        try:
            task = PlanningTaskType(assignment.task_type)
        except ValueError:
            warnings.append(
                _issue(
                    "unsupported_stored_task",
                    "A stored assignment uses an unsupported planning task and was ignored.",
                    task_type=assignment.task_type,
                    provider_identifier=profile.provider_identifier,
                )
            )
            continue
        if task not in selected_tasks:
            continue
        if profile.execution_mode == "disabled":
            errors.append(
                _issue(
                    "provider_profile_disabled",
                    "The stored provider profile is disabled.",
                    task_type=task,
                    provider_identifier=profile.provider_identifier,
                )
            )
        if profile.availability_status != "unknown":
            warnings.append(
                _issue(
                    "stored_availability_ignored",
                    "Stored profile availability is declarative and was ignored in favor of runtime facts.",
                    task_type=task,
                    provider_identifier=profile.provider_identifier,
                )
            )
        route_by_task[task] = (
            ManualTaskRoute(
                task_type=task,
                provider_identifier=profile.provider_identifier,
                resolved_model=profile.provider_model_id,
                rationale=assignment.rationale
                or f"Persisted task assignment {assignment.id}",
            ),
            "persisted_assignment",
        )

    for route in payload.manual_routes:
        if route.task_type not in selected_tasks:
            warnings.append(
                _issue(
                    "unused_manual_route",
                    "Manual route is outside the selected task set and was ignored.",
                    task_type=route.task_type,
                    provider_identifier=route.provider_identifier,
                )
            )
            continue
        route_by_task[route.task_type] = (route, "request_override")

    effective_mode = payload.routing_mode
    if route_by_task and effective_mode == RoutingMode.automatic:
        effective_mode = RoutingMode.hybrid

    effective_routes = [
        route_by_task[task][0]
        for task in task_types
        if task in route_by_task
    ]
    if agentless:
        for route in effective_routes:
            if route.provider_identifier != selected_agent:
                errors.append(
                    _issue(
                        "agentless_selected_agent_required",
                        (
                            "Agentless planning must use the project-selected "
                            f"local agent '{selected_agent}'."
                        ),
                        task_type=route.task_type,
                        provider_identifier=route.provider_identifier,
                    )
                )
    snapshot = build_routing_snapshot(
        mode=effective_mode,
        manual_routes=effective_routes,
        prefer_local_providers=payload.prefer_local_providers,
        prefer_hosted_providers=payload.prefer_hosted_providers,
        transport_retry_limit=payload.transport_retry_limit,
        time_budget_sec=payload.time_budget_sec,
        task_types=task_types,
    )
    routing_facts = [
        item
        for item in facts.providers
        if not agentless or item.provider_identifier == selected_agent
    ]
    snapshot["provider_catalog"] = [
        {
            "provider_identifier": item.provider_identifier,
            "availability_status": item.availability_status,
            "privacy_classification": item.privacy_classification,
            "capabilities": item.capabilities,
        }
        for item in routing_facts
    ]
    if selected_agent is not None:
        snapshot["selected_planning_agent"] = selected_agent

    routes: list[RoutingPreflightRoute] = []
    for task in task_types:
        try:
            decision = select_route(task_type=task, routing_snapshot=snapshot)
        except PlanningError as error:
            errors.append(
                _issue(
                    error.code.value,
                    error.message,
                    task_type=task,
                )
            )
            routes.append(
                RoutingPreflightRoute(
                    task_type=task.value,
                    source=(
                        route_by_task[task][1]
                        if task in route_by_task
                        else "unresolved"
                    ),
                )
            )
            continue

        live = fact_by_id.get(decision.provider_identifier)
        source = route_by_task[task][1] if task in route_by_task else "automatic"
        routes.append(
            RoutingPreflightRoute(
                task_type=task.value,
                source=source,
                provider_identifier=decision.provider_identifier,
                logical_model=decision.logical_model.value,
                resolved_model=decision.resolved_model,
                availability_status=(live.availability_status if live else "not_implemented"),
                privacy_classification=(live.privacy_classification if live else "unknown"),
            )
        )
        if live is None:
            errors.append(
                _issue(
                    "provider_not_registered",
                    "Selected provider is not registered for planning.",
                    task_type=task,
                    provider_identifier=decision.provider_identifier,
                )
            )
            continue
        if live.availability_status != "available":
            errors.append(
                _issue(
                    "provider_unavailable",
                    "Selected provider is not factually available for planning.",
                    task_type=task,
                    provider_identifier=decision.provider_identifier,
                )
            )
        if "planning" not in live.capabilities:
            errors.append(
                _issue(
                    "capability_missing",
                    "Selected provider lacks the verified planning capability.",
                    task_type=task,
                    provider_identifier=decision.provider_identifier,
                )
            )
        if live.privacy_classification == "hosted" and (
            not payload.prefer_hosted_providers
            or not project_settings.prefer_hosted_providers
        ):
            errors.append(
                _issue(
                    "hosted_provider_not_allowed",
                    "Selected hosted provider is disabled by run or project policy.",
                    task_type=task,
                    provider_identifier=decision.provider_identifier,
                )
            )
        if live.privacy_classification == "local" and (
            not payload.prefer_local_providers
            or not project_settings.prefer_local_providers
        ):
            errors.append(
                _issue(
                    "local_provider_not_allowed",
                    "Selected local provider is disabled by run or project policy.",
                    task_type=task,
                    provider_identifier=decision.provider_identifier,
                )
            )

    return RoutingPreflightResponse(
        story_id=story_id,
        valid=not errors,
        requested_mode=payload.routing_mode,
        effective_mode=effective_mode,
        routes=routes,
        provider_facts=routing_facts,
        errors=errors,
        warnings=warnings,
        metadata={
            "task_count": len(task_types),
            "network_calls_performed": False,
            "mutated": False,
            **(
                {"selected_planning_agent": selected_agent}
                if selected_agent is not None
                else {}
            ),
        },
    )
