"""Planning provider registry for Storyboard Phase 1.

Responsibilities:
- Prefer the configured local Qwen3 4B Hivemind GGUF for automatic planning.
- Keep the configured local Sulphur GGUF available as an alternative.
- Keep the deterministic mock as the offline/test fallback.
- Expose OpenAI only when configuration enables it and an API key is present.
- Represent anthropic / xai / local_cli / custom as explicitly not_implemented
  or not_configured — never silently invent adapters.
- Refuse shell commands and arbitrary executable paths for any provider
  registration path (especially local_cli / custom).

No credential persistence. No render/media/execution side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from backend.app.core.config import Settings, get_settings
from backend.app.services.planning.errors import PlanningError, PlanningErrorCode
from backend.app.services.planning.openai_provider import (
    OpenAIPlanningProvider,
    build_openai_provider_from_settings,
)
from backend.app.services.planning.provider import MockPlanningProvider, PlanningProvider
from backend.app.services.planning.sulphur_provider import (
    QwenPlanningProvider,
    SulphurPlanningProvider,
    build_qwen_provider_from_settings,
    build_sulphur_provider_from_settings,
)


class ProviderAvailability(StrEnum):
    available = "available"
    not_configured = "not_configured"
    not_implemented = "not_implemented"
    disabled = "disabled"


# Identifiers that must never be constructed from shell/exec paths in Phase 1.
_SHELL_REFUSED_PROVIDERS = frozenset({"local_cli", "custom"})
_HOSTED_STUBS = frozenset({"anthropic", "xai"})
_KNOWN_PROVIDERS = frozenset(
    {"mock", "sulphur", "openai", "anthropic", "xai", "qwen", "local_cli", "custom"}
)

_FORBIDDEN_REGISTRATION_KEYS = frozenset(
    {
        "shell_command",
        "cli_command",
        "command",
        "executable",
        "executable_path",
        "bin",
        "binary",
        "argv",
        "script",
        "cwd_exec",
    }
)


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_identifier: str
    display_name: str
    availability_status: ProviderAvailability
    execution_mode: str
    privacy_classification: str
    capabilities: tuple[str, ...]
    detail: str
    routing_priority: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_identifier": self.provider_identifier,
            "display_name": self.display_name,
            "availability_status": self.availability_status.value,
            "execution_mode": self.execution_mode,
            "privacy_classification": self.privacy_classification,
            "capabilities": list(self.capabilities),
            "detail": self.detail,
            "routing_priority": self.routing_priority,
        }


def _assert_no_shell_registration(options: dict[str, Any] | None) -> None:
    if not options:
        return
    for key in options:
        key_l = str(key).lower()
        if key_l in _FORBIDDEN_REGISTRATION_KEYS:
            raise PlanningError(
                PlanningErrorCode.ROUTING_FAILED,
                "Provider registration refuses shell commands and executable paths",
                details={"rejected_key": key_l},
            )
        value = options[key]
        if isinstance(value, str):
            lowered = value.lower()
            if any(
                token in lowered
                for token in (
                    "powershell",
                    "cmd.exe",
                    "/bin/sh",
                    "/bin/bash",
                    ".exe",
                    ".bat",
                    ".ps1",
                )
            ):
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    "Provider registration refuses shell commands and executable paths",
                    details={"rejected_key": key_l},
                )


def describe_providers(settings: Settings | None = None) -> list[ProviderDescriptor]:
    """Catalog of planning providers with explicit availability."""
    cfg = settings or get_settings()
    openai_status = (
        ProviderAvailability.available
        if cfg.openai_configured
        else ProviderAvailability.not_configured
    )
    openai_detail = (
        "OpenAI planning adapter enabled"
        if cfg.openai_configured
        else (
            "OpenAI disabled or API key not configured; local Qwen, Sulphur, "
            "or explicit test fallback routing remains available"
        )
    )
    sulphur_status = (
        ProviderAvailability.available
        if cfg.sulphur_configured
        else ProviderAvailability.not_configured
    )
    sulphur_detail = (
        "Local Sulphur Q8 GGUF is configured through LM Studio"
        if cfg.sulphur_configured
        else "Local Sulphur planning is disabled or its configured GGUF is missing"
    )
    qwen_status = (
        ProviderAvailability.available
        if cfg.qwen_configured
        else ProviderAvailability.not_configured
    )
    qwen_detail = (
        "Local Qwen3 4B Hivemind GGUF is configured through LM Studio"
        if cfg.qwen_configured
        else "Local Qwen planning is disabled or its configured GGUF is missing"
    )

    return [
        ProviderDescriptor(
            provider_identifier=QwenPlanningProvider.identifier,
            display_name="Qwen3 4B Hivemind · local LM Studio",
            availability_status=qwen_status,
            execution_mode="local_http" if cfg.qwen_configured else "disabled",
            privacy_classification="local",
            capabilities=(
                ("planning", "script_generation", "prompt_enhancement")
                if cfg.qwen_configured
                else tuple()
            ),
            detail=qwen_detail,
            routing_priority=110,
        ),
        ProviderDescriptor(
            provider_identifier=SulphurPlanningProvider.identifier,
            display_name="Sulphur Prompt Enhancer Q8",
            availability_status=sulphur_status,
            execution_mode="local_http" if cfg.sulphur_configured else "disabled",
            privacy_classification="local",
            capabilities=(
                ("planning", "script_generation", "prompt_enhancement")
                if cfg.sulphur_configured
                else tuple()
            ),
            detail=sulphur_detail,
            routing_priority=100,
        ),
        ProviderDescriptor(
            provider_identifier=MockPlanningProvider.identifier,
            display_name="Deterministic Mock",
            availability_status=ProviderAvailability.available,
            execution_mode="local",
            privacy_classification="local",
            capabilities=("planning",),
            detail="Deterministic provider reserved for tests and explicit fallback",
            routing_priority=0,
        ),
        ProviderDescriptor(
            provider_identifier=OpenAIPlanningProvider.identifier,
            display_name="OpenAI",
            availability_status=openai_status,
            execution_mode="hosted" if cfg.openai_configured else "disabled",
            privacy_classification="hosted",
            capabilities=("planning",) if cfg.openai_configured else tuple(),
            detail=openai_detail,
        ),
        ProviderDescriptor(
            provider_identifier="anthropic",
            display_name="Anthropic",
            availability_status=ProviderAvailability.not_implemented,
            execution_mode="disabled",
            privacy_classification="hosted",
            capabilities=tuple(),
            detail="Not implemented in Storyboard Phase 1",
        ),
        ProviderDescriptor(
            provider_identifier="xai",
            display_name="xAI",
            availability_status=ProviderAvailability.not_implemented,
            execution_mode="disabled",
            privacy_classification="hosted",
            capabilities=tuple(),
            detail="Not implemented in Storyboard Phase 1",
        ),
        ProviderDescriptor(
            provider_identifier="local_cli",
            display_name="Local CLI",
            availability_status=ProviderAvailability.not_implemented,
            execution_mode="disabled",
            privacy_classification="local",
            capabilities=tuple(),
            detail=(
                "Not implemented; never accepts shell commands or arbitrary "
                "executable paths"
            ),
        ),
        ProviderDescriptor(
            provider_identifier="custom",
            display_name="Custom",
            availability_status=ProviderAvailability.not_implemented,
            execution_mode="disabled",
            privacy_classification="unknown",
            capabilities=tuple(),
            detail="Not implemented; custom executable providers are refused",
        ),
    ]


def provider_status_map(settings: Settings | None = None) -> dict[str, str]:
    return {
        d.provider_identifier: d.availability_status.value
        for d in describe_providers(settings)
    }


def build_provider_registry(
    settings: Settings | None = None,
    *,
    extra: dict[str, PlanningProvider] | None = None,
) -> dict[str, PlanningProvider]:
    """Build the live provider map.

    Mock is always present. Qwen, Sulphur, and OpenAI are included only when
    configured.
    """
    cfg = settings or get_settings()
    registry: dict[str, PlanningProvider] = {
        MockPlanningProvider.identifier: MockPlanningProvider(),
    }

    openai = build_openai_provider_from_settings(cfg)
    if openai is not None:
        registry[OpenAIPlanningProvider.identifier] = openai
    sulphur = build_sulphur_provider_from_settings(cfg)
    if sulphur is not None:
        registry[SulphurPlanningProvider.identifier] = sulphur
    qwen = build_qwen_provider_from_settings(cfg)
    if qwen is not None:
        registry[QwenPlanningProvider.identifier] = qwen

    if extra:
        for key, provider in extra.items():
            if key in _SHELL_REFUSED_PROVIDERS:
                raise PlanningError(
                    PlanningErrorCode.ROUTING_FAILED,
                    f"Provider '{key}' is not implemented and cannot be registered",
                    details={"provider_identifier": key},
                )
            registry[key] = provider

    return registry


def resolve_provider(
    provider_identifier: str,
    *,
    registry: dict[str, PlanningProvider] | None = None,
    settings: Settings | None = None,
    registration_options: dict[str, Any] | None = None,
) -> PlanningProvider:
    """Resolve a provider or raise a routing failure with explicit status."""
    _assert_no_shell_registration(registration_options)

    if registry is not None and provider_identifier in registry:
        return registry[provider_identifier]

    if provider_identifier == MockPlanningProvider.identifier:
        return MockPlanningProvider()

    if provider_identifier == SulphurPlanningProvider.identifier:
        cfg = settings or get_settings()
        if not cfg.sulphur_configured:
            raise PlanningError(
                PlanningErrorCode.ROUTING_FAILED,
                "Provider 'sulphur' is not configured for planning",
                details={
                    "provider_identifier": "sulphur",
                    "availability_status": ProviderAvailability.not_configured.value,
                    "sulphur_planning_enabled": cfg.sulphur_planning_enabled,
                },
            )
        return SulphurPlanningProvider.from_settings(cfg)

    if provider_identifier == QwenPlanningProvider.identifier:
        cfg = settings or get_settings()
        if not cfg.qwen_configured:
            raise PlanningError(
                PlanningErrorCode.ROUTING_FAILED,
                "Provider 'qwen' is not configured for planning",
                details={
                    "provider_identifier": "qwen",
                    "availability_status": ProviderAvailability.not_configured.value,
                    "sulphur_planning_enabled": cfg.sulphur_planning_enabled,
                },
            )
        return QwenPlanningProvider.from_settings(cfg)

    if provider_identifier in _SHELL_REFUSED_PROVIDERS:
        raise PlanningError(
            PlanningErrorCode.ROUTING_FAILED,
            (
                f"Provider '{provider_identifier}' is not implemented and does not "
                "accept shell commands or executable paths"
            ),
            details={
                "provider_identifier": provider_identifier,
                "availability_status": ProviderAvailability.not_implemented.value,
            },
        )

    if provider_identifier in _HOSTED_STUBS:
        raise PlanningError(
            PlanningErrorCode.ROUTING_FAILED,
            f"Provider '{provider_identifier}' is not implemented for planning",
            details={
                "provider_identifier": provider_identifier,
                "availability_status": ProviderAvailability.not_implemented.value,
            },
        )

    if provider_identifier == OpenAIPlanningProvider.identifier:
        cfg = settings or get_settings()
        if not cfg.openai_configured:
            raise PlanningError(
                PlanningErrorCode.ROUTING_FAILED,
                "Provider 'openai' is not configured for planning",
                details={
                    "provider_identifier": "openai",
                    "availability_status": ProviderAvailability.not_configured.value,
                    "openai_planning_enabled": cfg.openai_planning_enabled,
                },
            )
        return OpenAIPlanningProvider.from_settings(cfg)

    # Unknown identifier — do not invent adapters.
    status = (
        ProviderAvailability.not_implemented.value
        if provider_identifier in _KNOWN_PROVIDERS
        else ProviderAvailability.not_implemented.value
    )
    raise PlanningError(
        PlanningErrorCode.ROUTING_FAILED,
        f"Provider '{provider_identifier}' is not available for planning",
        details={
            "provider_identifier": provider_identifier,
            "availability_status": status,
        },
    )


def refuse_local_cli_registration(
    *,
    command: str | None = None,
    executable_path: str | None = None,
    **_: Any,
) -> None:
    """Hard refusal helper — local_cli never accepts commands or paths."""
    raise PlanningError(
        PlanningErrorCode.ROUTING_FAILED,
        "local_cli is not implemented and never accepts shell commands or executable paths",
        details={
            "provider_identifier": "local_cli",
            "command_provided": bool(command),
            "executable_path_provided": bool(executable_path),
            "availability_status": ProviderAvailability.not_implemented.value,
        },
    )


# Optional factory type for tests.
ProviderFactory = Callable[[], PlanningProvider]
