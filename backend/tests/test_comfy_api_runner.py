from __future__ import annotations

import httpx
import pytest

from backend.app.services.comfy.runner import (
    ComfyAPIRunnerClient,
    ComfyAPIRunnerMutationBlocked,
)


@pytest.mark.asyncio
async def test_runner_health_verifies_comfy_connection():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/health"
        assert request.url.params["url"] == "http://127.0.0.1:8888"
        return httpx.Response(200, json={"ok": True, "system": {"devices": []}})

    async with ComfyAPIRunnerClient(
        "http://127.0.0.1:8022",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.health("http://127.0.0.1:8888")

    assert result == {
        "status": "ok",
        "reachable": True,
        "comfy_connected": True,
    }


@pytest.mark.asyncio
async def test_runner_submission_requires_controlled_mutation_context():
    async with ComfyAPIRunnerClient("http://127.0.0.1:8022") as client:
        with pytest.raises(ComfyAPIRunnerMutationBlocked):
            await client.run_workflow(
                {"1": {"class_type": "Test", "inputs": {}}},
                comfy_url="http://127.0.0.1:8888",
            )


@pytest.mark.asyncio
async def test_runner_restart_requires_controlled_mutation_context():
    async with ComfyAPIRunnerClient("http://127.0.0.1:8022") as client:
        with pytest.raises(ComfyAPIRunnerMutationBlocked):
            await client.restart_comfy(comfy_url="http://127.0.0.1:8888")


@pytest.mark.asyncio
async def test_runner_restart_and_status_use_bounded_local_endpoints():
    restart_id = "a" * 32

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/restart-comfy":
            assert request.method == "POST"
            assert request.read() == b'{"comfyUrl":"http://127.0.0.1:8888"}'
            return httpx.Response(200, json={"ok": True, "restartId": restart_id})
        assert request.url.path == f"/api/restart/{restart_id}"
        return httpx.Response(
            200,
            json={"ok": True, "status": "complete", "message": "ComfyUI restarted"},
        )

    async with ComfyAPIRunnerClient(
        "http://127.0.0.1:8022",
        allow_mutation=True,
        transport=httpx.MockTransport(handler),
    ) as client:
        scheduled = await client.restart_comfy(comfy_url="http://127.0.0.1:8888")
        completed = await client.get_restart(restart_id)

    assert scheduled["restartId"] == restart_id
    assert completed["status"] == "complete"
