import json

import httpx
import pytest

from backend.app.core.config import Settings
from backend.app.services.lm_studio_models import (
    LMStudioModelService,
    get_active_lm_studio_model_filename,
    get_active_lm_studio_model_id,
)
from backend.app.services.planning.sulphur_provider import QwenPlanningProvider


QWEN_ID = (
    "qwen3-4b-hivemind-instruct-heretic-abliterated-uncensored-neo-imatrix"
)


def _settings(tmp_path) -> Settings:
    sulphur = tmp_path / "models" / "SulphurAI" / "Sulphur-2-base" / "sulphur-q8.gguf"
    qwen = tmp_path / "models" / "DavidAU" / "Qwen3-4B-Hivemind" / "qwen3-4b-q4_k_m.gguf"
    sulphur.parent.mkdir(parents=True)
    qwen.parent.mkdir(parents=True)
    sulphur.write_bytes(b"sulphur")
    qwen.write_bytes(b"qwen")
    return Settings(
        storage_root=tmp_path / "storage",
        sulphur_planning_enabled=True,
        sulphur_model_path=sulphur,
        qwen_model_id=QWEN_ID,
        qwen_model_path=qwen,
    )


@pytest.mark.asyncio
async def test_offline_catalog_keeps_both_installed_model_choices(tmp_path) -> None:
    settings = _settings(tmp_path)

    async def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("LM Studio is offline", request=request)

    catalog = await LMStudioModelService(
        settings,
        transport=httpx.MockTransport(offline),
    ).catalog()

    assert catalog.status == "unavailable"
    assert catalog.reachable is False
    assert catalog.active_model_id == QWEN_ID
    assert [(model.model_id, model.installed) for model in catalog.models] == [
        ("sulphur-2-base", True),
        (QWEN_ID, True),
    ]
    assert catalog.models[1].selected is True


@pytest.mark.asyncio
async def test_activate_qwen_loads_then_persists_the_planning_model(tmp_path) -> None:
    settings = _settings(tmp_path)
    requests: list[tuple[str, str, dict | None]] = []

    async def lm_studio(request: httpx.Request) -> httpx.Response:
        request_json = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, request_json))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "type": "llm",
                            "publisher": "SulphurAI",
                            "key": "sulphur-2-base",
                            "display_name": "Sulphur Prompt Enhancer Model",
                            "architecture": "qwen35",
                            "quantization": {"name": "Q8_0"},
                            "size_bytes": 9_527_501_184,
                            "params_string": "9B",
                            "loaded_instances": [
                                {
                                    "id": "sulphur-2-base",
                                    "config": {"context_length": 8192, "parallel": 1},
                                }
                            ],
                            "max_context_length": 262144,
                        },
                        {
                            "type": "llm",
                            "publisher": "DavidAU",
                            "key": "qwen3.5-2b-uncensored",
                            "display_name": "Qwen3.5 2B Uncensored",
                            "architecture": "qwen35",
                            "quantization": {"name": "Q4_K_M"},
                            "size_bytes": 1_500_000_000,
                            "params_string": "2B",
                            "loaded_instances": [
                                {
                                    "id": "qwen3.5-2b-uncensored",
                                    "config": {"context_length": 8192, "parallel": 1},
                                }
                            ],
                            "max_context_length": 262144,
                        },
                        {
                            "type": "llm",
                            "publisher": "DavidAU",
                            "key": QWEN_ID,
                            "display_name": "Qwen3 4B Hivemind Inst Hrtic Ablit Uncensored Imat",
                            "architecture": "qwen3",
                            "quantization": {"name": "Q4_K_M"},
                            "size_bytes": 2_644_759_136,
                            "params_string": "4B",
                            "loaded_instances": [],
                            "max_context_length": 262144,
                        },
                    ]
                },
            )
        if request.url.path.endswith("/unload"):
            return httpx.Response(
                200,
                json={"instance_id": "sulphur-2-base", "status": "unloaded"},
            )
        return httpx.Response(
            200,
            json={
                "type": "llm",
                "instance_id": QWEN_ID,
                "load_time_seconds": 12.5,
                "status": "loaded",
            },
        )

    result = await LMStudioModelService(
        settings,
        transport=httpx.MockTransport(lm_studio),
    ).activate(QWEN_ID)

    assert result.active_model_id == QWEN_ID
    assert result.model.loaded is True
    assert result.load_time_seconds == 12.5
    assert requests[-1] == (
        "POST",
        "/api/v1/models/load",
        {
            "model": QWEN_ID,
            "context_length": 8192,
            "flash_attention": True,
            "echo_load_config": True,
        },
    )
    unload_requests = [
        request
        for request in requests
        if request[1] == "/api/v1/models/unload"
    ]
    assert unload_requests == [
        (
            "POST",
            "/api/v1/models/unload",
            {"instance_id": "sulphur-2-base"},
        ),
        (
            "POST",
            "/api/v1/models/unload",
            {"instance_id": "qwen3.5-2b-uncensored"},
        ),
    ]
    assert get_active_lm_studio_model_id(settings) == QWEN_ID
    assert get_active_lm_studio_model_filename(settings) == "qwen3-4b-q4_k_m.gguf"

    provider = QwenPlanningProvider.from_settings(settings)
    assert provider.model_luna == QWEN_ID
    assert provider.model_terra == QWEN_ID
    assert provider.model_sol == QWEN_ID
