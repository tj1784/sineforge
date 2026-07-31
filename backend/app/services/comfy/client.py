from typing import Any, BinaryIO

import httpx


class ComfyMutationBlocked(RuntimeError):
    pass


class ComfyRuntimeRouteBlocked(RuntimeError):
    pass


class ComfyUIClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 2.0,
        allow_mutation: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.allow_mutation = allow_mutation
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=transport)

    async def __aenter__(self) -> "ComfyUIClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            response = await self._client.get("/")
            return {"status": "ok" if response.status_code < 500 else "degraded", "reachable": True}
        except httpx.HTTPError as exc:
            return {"status": "unavailable", "reachable": False, "error": str(exc)}

    async def get_object_info(self) -> dict[str, Any]:
        response = await self._client.get("/object_info")
        response.raise_for_status()
        return response.json()

    async def get_object_info_class(self, class_type: str) -> dict[str, Any] | None:
        object_info = await self.get_object_info()
        class_info = object_info.get(class_type)
        return class_info if isinstance(class_info, dict) else None

    async def get_model_names(self, folder: str) -> list[str]:
        """Return ComfyUI's live filename list for one registered model folder."""

        response = await self._client.get(f"/models/{folder}")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"ComfyUI returned a non-list model payload for {folder}.")
        return sorted({str(item) for item in payload if isinstance(item, str) and item.strip()})

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/history/{prompt_id}")
        response.raise_for_status()
        return response.json()

    async def get_prompt_history(self) -> dict[str, Any]:
        response = await self._client.get("/history")
        response.raise_for_status()
        return response.json()

    async def get_queue(self) -> dict[str, Any]:
        response = await self._client.get("/queue")
        response.raise_for_status()
        return response.json()

    async def connect_progress_websocket(self, client_id: str) -> None:
        raise ComfyRuntimeRouteBlocked(f"WebSocket progress for client {client_id} is not enabled in this slice")

    async def view_output(self, filename: str, subfolder: str = "", output_type: str = "output") -> bytes:
        response = await self._client.get(
            "/view",
            params={"filename": filename, "subfolder": subfolder, "type": output_type},
        )
        response.raise_for_status()
        return response.content

    def _require_mutation_context(self) -> None:
        if not self.allow_mutation:
            raise ComfyMutationBlocked("ComfyUI mutation routes require allow_mutation=True")

    async def submit_prompt(self, prompt: dict[str, Any], client_id: str) -> dict[str, Any]:
        self._require_mutation_context()
        response = await self._client.post("/prompt", json={"prompt": prompt, "client_id": client_id})
        response.raise_for_status()
        return response.json()

    async def stage_editor_workflow(
        self,
        *,
        name: str,
        workflow: dict[str, Any],
    ) -> dict[str, Any]:
        """Stage an editor graph for one-time loading by the ComfyUI frontend."""

        self._require_mutation_context()
        response = await self._client.post(
            "/sineforge/workflow-transfer",
            json={"name": name, "workflow": workflow, "source": "sineforge"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ComfyUI returned an invalid workflow-transfer response.")
        return payload

    async def upload_image(
        self,
        image: bytes,
        filename: str,
        *,
        subfolder: str = "",
        overwrite: bool = False,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        self._require_mutation_context()
        response = await self._client.post(
            "/upload/image",
            data={"subfolder": subfolder, "overwrite": str(overwrite).lower()},
            files={"image": (filename, image, content_type)},
        )
        response.raise_for_status()
        return response.json()

    async def upload_image_file(
        self,
        image: BinaryIO,
        filename: str,
        *,
        subfolder: str = "",
        overwrite: bool = False,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Stream a seekable file object to ComfyUI's input upload endpoint."""

        self._require_mutation_context()
        response = await self._client.post(
            "/upload/image",
            data={"subfolder": subfolder, "overwrite": str(overwrite).lower()},
            files={"image": (filename, image, content_type)},
        )
        response.raise_for_status()
        return response.json()

    async def interrupt(self) -> dict[str, Any]:
        self._require_mutation_context()
        response = await self._client.post("/interrupt")
        response.raise_for_status()
        return response.json() if response.content else {"status": "ok"}

    async def delete_queue_items(self, delete_ids: list[str]) -> dict[str, Any]:
        self._require_mutation_context()
        response = await self._client.post("/queue", json={"delete": delete_ids})
        response.raise_for_status()
        return response.json() if response.content else {"status": "ok"}

    async def free_memory(self, *, unload_models: bool = True, free_memory: bool = True) -> dict[str, Any]:
        self._require_mutation_context()
        response = await self._client.post("/free", json={"unload_models": unload_models, "free_memory": free_memory})
        response.raise_for_status()
        return response.json() if response.content else {"status": "ok"}
