import httpx
import pytest

from backend.app.services.comfy.client import ComfyMutationBlocked, ComfyRuntimeRouteBlocked, ComfyUIClient


@pytest.mark.asyncio
async def test_comfy_client_health_and_object_info_use_mock_transport():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/object_info":
            return httpx.Response(200, json={"KSampler": {"input": {"required": {"seed": ["INT", {}]}}}})
        if request.url.path == "/models/loras":
            return httpx.Response(200, json=["z.safetensors", "a.safetensors", "a.safetensors"])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async with ComfyUIClient("http://comfy.test", transport=transport) as client:
        health = await client.health()
        object_info = await client.get_object_info()
        class_info = await client.get_object_info_class("KSampler")
        missing_class = await client.get_object_info_class("MissingNode")
        loras = await client.get_model_names("loras")

    assert health == {"status": "ok", "reachable": True}
    assert object_info == {"KSampler": {"input": {"required": {"seed": ["INT", {}]}}}}
    assert class_info == {"input": {"required": {"seed": ["INT", {}]}}}
    assert missing_class is None
    assert loras == ["a.safetensors", "z.safetensors"]
    assert [request.url.path for request in requests] == [
        "/",
        "/object_info",
        "/object_info",
        "/object_info",
        "/models/loras",
    ]


@pytest.mark.asyncio
async def test_comfy_client_requires_explicit_mutation_context():
    requests: list[httpx.Request] = []
    transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200, json={}))

    async with ComfyUIClient("http://comfy.test", transport=transport) as client:
        with pytest.raises(ComfyMutationBlocked):
            await client.submit_prompt({"1": {"class_type": "KSampler"}}, "client-1")
        with pytest.raises(ComfyMutationBlocked):
            await client.upload_image(b"image", "frame.png")

    assert requests == []


@pytest.mark.asyncio
async def test_comfy_client_local_mutation_routes_submit_when_allowed():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "prompt-1", "number": 1})
        if request.url.path == "/upload/image":
            return httpx.Response(200, json={"name": "frame.png", "subfolder": "", "type": "input"})
        if request.url.path in {"/interrupt", "/queue", "/free"}:
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async with ComfyUIClient("http://comfy.test", allow_mutation=True, transport=transport) as client:
        prompt = await client.submit_prompt({"1": {"class_type": "KSampler"}}, "client-1")
        upload = await client.upload_image(b"image", "frame.png", content_type="image/png")
        interrupt = await client.interrupt()
        queue = await client.delete_queue_items(["prompt-1"])
        free = await client.free_memory()

    assert prompt["prompt_id"] == "prompt-1"
    assert upload["name"] == "frame.png"
    assert interrupt == {"status": "ok"}
    assert queue == {"status": "ok"}
    assert free == {"status": "ok"}
    assert [request.url.path for request in requests] == [
        "/prompt",
        "/upload/image",
        "/interrupt",
        "/queue",
        "/free",
    ]


@pytest.mark.asyncio
async def test_comfy_client_history_and_view_routes_collect_outputs():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/history/prompt-1":
            return httpx.Response(200, json={"prompt-1": {"outputs": {}}})
        if request.url.path == "/history":
            return httpx.Response(200, json={"history": []})
        if request.url.path == "/view":
            return httpx.Response(200, content=b"image-bytes")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async with ComfyUIClient("http://comfy.test", transport=transport) as client:
        prompt_history = await client.get_history("prompt-1")
        full_history = await client.get_prompt_history()
        output = await client.view_output("frame.png")
        with pytest.raises(ComfyRuntimeRouteBlocked):
            await client.connect_progress_websocket("client-1")

    assert prompt_history == {"prompt-1": {"outputs": {}}}
    assert full_history == {"history": []}
    assert output == b"image-bytes"
    assert [request.url.path for request in requests] == ["/history/prompt-1", "/history", "/view"]
