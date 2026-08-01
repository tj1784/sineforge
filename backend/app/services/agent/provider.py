"""OpenAI-compatible provider adapter for the contextual Operator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.core.config import Settings, get_settings
from backend.app.services.lm_studio_models import get_active_lm_studio_model_id


class AgentProviderError(RuntimeError):
    """Provider failure safe for UI display after sanitization."""


@dataclass(frozen=True)
class AgentProviderCapabilities:
    streaming: bool = True
    structured_output: bool = True
    native_tool_calling: bool = False


class OpenAICompatibleAgentProvider:
    """Narrow LM Studio/OpenAI-compatible chat-completions adapter."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport
        self.base_url = self.settings.ai_base_url.rstrip("/")
        self.timeout = httpx.Timeout(
            self.settings.ai_request_timeout_seconds,
            connect=min(5.0, self.settings.ai_request_timeout_seconds),
        )

    @property
    def configured_model(self) -> str:
        return self.settings.ai_model

    @property
    def capabilities(self) -> AgentProviderCapabilities:
        return AgentProviderCapabilities()

    async def list_models(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=3.0),
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            response = await client.get(f"{self.base_url}/models")
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise AgentProviderError("Provider returned an invalid model catalog")
        return [item for item in data if isinstance(item, dict)]

    async def health(self) -> dict[str, Any]:
        if not self.settings.ai_agent_enabled:
            return {
                "enabled": False,
                "reachable": False,
                "status": "disabled",
                "models": [],
                "active_model_id": None,
                "error": None,
            }
        try:
            models = await self.list_models()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError, AgentProviderError) as exc:
            return {
                "enabled": True,
                "reachable": False,
                "status": "unavailable",
                "models": [],
                "active_model_id": None,
                "error": str(exc)[:500],
            }
        active_model = self._active_model_id(models)
        return {
            "enabled": True,
            "reachable": True,
            "status": "ok",
            "models": models,
            "active_model_id": active_model,
            "error": None,
        }

    async def complete_action(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        idempotency_key: str,
        thinking_enabled: bool = True,
    ) -> dict[str, Any]:
        if not self.settings.ai_agent_enabled:
            raise AgentProviderError("Contextual Operator is disabled")

        # Resolve the persisted SineForge selection against LM Studio's live
        # OpenAI-compatible catalog. The default AI_MODEL can be stale (for
        # example, the historic default is "grok") while the user has selected a
        # different local model. Supplying that stale alias can make LM Studio
        # return HTTP 400 instead of serving the selected model.
        request_model = await self._resolve_request_model()
        body = {
            "model": request_model,
            "messages": messages,
            "temperature": 0.2,
            # LM Studio exposes the model capability as on/off in its native
            # catalog, while its OpenAI-compatible endpoint accepts the OpenAI
            # effort vocabulary. "none" disables reasoning; "medium" is the
            # stable enabled/default-equivalent setting for the Operator.
            "reasoning_effort": "medium" if thinking_enabled else "none",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "cineforge_operator_action",
                    "strict": False,
                    "schema": response_schema,
                },
            },
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.ai_api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key[:128],
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                envelope = response.json()
        except httpx.HTTPStatusError as exc:
            detail = self._http_error_detail(exc.response)
            raise AgentProviderError(detail) from exc
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise AgentProviderError(str(exc)[:500]) from exc

        choices = envelope.get("choices") if isinstance(envelope, dict) else None
        if not isinstance(choices, list) or not choices:
            raise AgentProviderError("Provider response did not include choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise AgentProviderError("Provider response content was empty")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AgentProviderError("Provider response was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise AgentProviderError("Provider action envelope must be a JSON object")
        return parsed

    async def _resolve_request_model(self) -> str:
        """Resolve the model LM Studio can actually serve for this turn."""
        try:
            models = await self.list_models()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError, AgentProviderError):
            return self.settings.ai_model
        return self._active_model_id(models) or self.settings.ai_model

    @staticmethod
    def _http_error_detail(response: httpx.Response) -> str:
        """Keep provider diagnostics useful without returning an unbounded body."""
        status = f"LM Studio request failed with HTTP {response.status_code}"
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return f"{status}: {message.strip()}"[:500]
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return f"{status}: {message.strip()}"[:500]
        text = response.text.strip()
        return (f"{status}: {text}" if text else status)[:500]

    def _active_model_id(self, models: list[dict[str, Any]]) -> str | None:
        ids = [
            str(item.get("id"))
            for item in models
            if isinstance(item.get("id"), str)
        ]
        selected = get_active_lm_studio_model_id(self.settings)
        for candidate in (selected, self.settings.ai_model):
            if candidate in ids:
                return candidate
        return ids[0] if ids else None
