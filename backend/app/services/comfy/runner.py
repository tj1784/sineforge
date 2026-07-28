"""Bounded client for the separately supervised local ComfyAPI Runner."""

from __future__ import annotations

from typing import Any

import httpx


class ComfyAPIRunnerMutationBlocked(RuntimeError):
    pass


class ComfyAPIRunnerClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 3.0,
        allow_mutation: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.allow_mutation = allow_mutation
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self) -> "ComfyAPIRunnerClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self, comfy_url: str) -> dict[str, Any]:
        try:
            response = await self._client.get(
                "/api/health",
                params={"url": comfy_url.rstrip("/")},
            )
            response.raise_for_status()
            payload = response.json()
            connected = bool(isinstance(payload, dict) and payload.get("ok"))
            return {
                "status": "ok" if connected else "degraded",
                "reachable": True,
                "comfy_connected": connected,
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "status": "unavailable",
                "reachable": False,
                "comfy_connected": False,
                "error": str(exc),
            }

    async def analyze_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """Use the runner's non-executing workflow analysis endpoint."""

        response = await self._client.post(
            "/api/analyze",
            json={"workflow": workflow},
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"ok": False}

    async def run_workflow(
        self,
        workflow: dict[str, Any],
        *,
        comfy_url: str,
        workflow_name: str = "cineforge",
    ) -> dict[str, Any]:
        """Submit only from an explicitly mutation-enabled controlled context."""

        if not self.allow_mutation:
            raise ComfyAPIRunnerMutationBlocked(
                "ComfyAPI Runner mutation routes require allow_mutation=True"
            )
        response = await self._client.post(
            "/api/run",
            json={
                "workflow": workflow,
                "comfyUrl": comfy_url.rstrip("/"),
                "runMode": "direct",
                "workflowName": workflow_name,
                "queueCount": 1,
                "mergeMovie": False,
                "varySeed": False,
                "saveLatents": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"ok": False}

    async def restart_comfy(self, *, comfy_url: str) -> dict[str, Any]:
        """Request a restart only from an explicit, user-triggered mutation context."""

        if not self.allow_mutation:
            raise ComfyAPIRunnerMutationBlocked(
                "ComfyAPI Runner mutation routes require allow_mutation=True"
            )
        response = await self._client.post(
            "/api/restart-comfy",
            json={"comfyUrl": comfy_url.rstrip("/")},
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"ok": False}

    async def get_restart(self, restart_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/api/restart/{restart_id}")
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"ok": False}

    async def get_job(self, job_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/api/job/{job_id}")
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"ok": False}
