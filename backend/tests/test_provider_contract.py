"""Provider discovery, bounded connection-test, and routing-preflight safety tests."""

from __future__ import annotations

from collections.abc import Generator
import json
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.routes.providers import get_provider_connection_tester
from backend.app.core.config import Settings
from backend.app.db.base import Base, OrchestrationRun, ProviderProfile
from backend.app.db.session import enable_sqlite_foreign_keys, get_db
from backend.app.main import app
from backend.app.services.planning.provider_contract import (
    ProviderConnectionTester,
    provider_catalog,
    provider_profile_capabilities,
)


@pytest.fixture
def api(tmp_path) -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'provider-contract.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    enable_sqlite_foreign_keys(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    Base.metadata.create_all(engine)

    def override() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app), factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_provider_connection_tester, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def _story(client: TestClient) -> dict:
    project_response = client.post(
        "/projects",
        json={
            "name": "Provider contract",
            "workflow_lane": "cineforge_studio",
        },
    )
    assert project_response.status_code == 201
    response = client.post(
        "/storyboard/stories",
        json={
            "project_id": project_response.json()["id"],
            "title": "Routing preflight",
            "base_story": "A deterministic planning story.",
            "target_duration_sec": 30,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_catalog_is_factual_and_does_not_promote_unconfigured_or_stub_providers(
    tmp_path,
):
    settings = Settings(
        openai_planning_enabled=False,
        openai_api_key=None,
        sulphur_planning_enabled=False,
        sulphur_model_path=tmp_path / "missing-sulphur.gguf",
        qwen_model_path=tmp_path / "missing-qwen.gguf",
    )
    catalog = provider_catalog(settings)
    by_id = {item.provider_identifier: item for item in catalog.providers}

    assert by_id["mock"].availability_status == "available"
    assert by_id["mock"].capabilities == ["planning"]
    assert by_id["mock"].capability_source == "runtime_registry"
    assert by_id["openai"].availability_status == "not_configured"
    assert by_id["qwen"].availability_status == "not_configured"
    assert by_id["qwen"].connection_test_supported is True
    assert by_id["openai"].capabilities == []
    assert by_id["xai"].availability_status == "not_implemented"
    assert by_id["local_cli"].connection_test_supported is False


def test_provider_catalog_and_capability_routes_are_mounted(api):
    client, _factory = api

    response = client.get("/providers")
    assert response.status_code == 200
    assert response.json()["schema_name"] == "planning.provider_catalog.v1"
    assert any(
        item["provider_identifier"] == "mock"
        for item in response.json()["providers"]
    )

    capability = client.get("/providers/mock/capabilities")
    assert capability.status_code == 200
    assert capability.json()["capabilities"] == ["planning"]
    assert capability.json()["capability_source"] == "runtime_registry"
    assert client.get("/providers/not-real").status_code == 404


def test_explicit_openai_connection_test_uses_injected_bounded_http_only(api):
    client, _factory = api
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [{"id": "unit-model"}]})

    transport = httpx.MockTransport(handler)
    settings = Settings(
        openai_planning_enabled=True,
        openai_api_key="sk-unit-boundary",
        openai_base_url="https://provider.invalid/v1",
    )
    tester = ProviderConnectionTester(
        settings,
        http_client_factory=lambda timeout: httpx.Client(
            transport=transport,
            timeout=timeout,
        ),
    )
    app.dependency_overrides[get_provider_connection_tester] = lambda: tester

    response = client.post(
        "/providers/openai/connection-test",
        json={"timeout_sec": 1.25},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attempted"] is True
    assert body["success"] is True
    assert body["availability_status"] == "available"
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/models"
    assert requests[0].headers["authorization"] == "Bearer sk-unit-boundary"
    serialized = json.dumps(body).lower()
    assert "sk-unit-boundary" not in serialized
    assert "unit-model" not in serialized

    # Credentials and arbitrary request fields are outside the request schema,
    # so validation rejects them before any transport call.
    rejected = client.post(
        "/providers/openai/connection-test",
        json={"timeout_sec": 1, "api_key": "sk-request-secret"},
    )
    assert rejected.status_code == 422
    assert len(requests) == 1


def test_stub_connection_test_is_factual_and_never_constructs_transport():
    calls = 0

    def forbidden_factory(_timeout: float) -> httpx.Client:
        nonlocal calls
        calls += 1
        pytest.fail("stub provider attempted to construct an HTTP client")

    tester = ProviderConnectionTester(
        Settings(openai_planning_enabled=False, openai_api_key=None),
        http_client_factory=forbidden_factory,
    )
    result = tester.test("xai", timeout_sec=1)

    assert result.attempted is False
    assert result.success is False
    assert result.availability_status == "not_implemented"
    assert calls == 0


def test_qwen_connection_test_verifies_the_requested_local_model(tmp_path):
    qwen_path = tmp_path / "qwen3-4b-q4_k_m.gguf"
    qwen_path.write_bytes(b"qwen-test-model")
    settings = Settings(
        sulphur_planning_enabled=True,
        qwen_model_id="qwen3-4b",
        qwen_model_path=qwen_path,
        sulphur_model_path=tmp_path / "missing-sulphur.gguf",
        sulphur_base_url="http://127.0.0.1:1234/v1",
    )

    def tester_for(models: list[dict]) -> ProviderConnectionTester:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"models": models})
        )
        return ProviderConnectionTester(
            settings,
            http_client_factory=lambda timeout: httpx.Client(
                transport=transport,
                timeout=timeout,
            ),
        )

    loaded = tester_for(
        [
            {
                "key": "qwen3-4b",
                "loaded_instances": [{"id": "qwen3-4b"}],
            }
        ]
    ).test("qwen", timeout_sec=1)
    wrong_model = tester_for(
        [
            {
                "key": "sulphur-2-base",
                "loaded_instances": [{"id": "sulphur-2-base"}],
            }
        ]
    ).test("qwen", timeout_sec=1)

    assert loaded.attempted is True
    assert loaded.success is True
    assert loaded.availability_status == "available"
    assert wrong_model.attempted is True
    assert wrong_model.success is False
    assert wrong_model.error_code == "model_not_loaded"


def test_connection_test_response_is_byte_bounded_and_sanitized():
    response_content = b'{"secret":"sk-should-never-return","padding":"' + (
        b"x" * 70_000
    ) + b'"}'
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, content=response_content)
    )
    tester = ProviderConnectionTester(
        Settings(
            openai_planning_enabled=True,
            openai_api_key="sk-unit-boundary",
            openai_base_url="https://provider.invalid/v1",
        ),
        http_client_factory=lambda timeout: httpx.Client(
            transport=transport,
            timeout=timeout,
        ),
    )

    result = tester.test("openai", timeout_sec=1)
    serialized = result.model_dump_json().lower()
    assert result.success is False
    assert result.error_code == "response_too_large"
    assert "sk-should-never-return" not in serialized
    assert "padding" not in serialized


def test_profile_crud_only_accepts_declarations_and_live_capabilities_are_separate(api):
    client, factory = api

    factual_assertion = client.post(
        "/storyboard-crud/provider-profiles",
        json={
            "provider_identifier": "openai",
            "display_name": "Untrusted factual claim",
            "availability_status": "available",
        },
    )
    assert factual_assertion.status_code == 422

    created = client.post(
        "/storyboard-crud/provider-profiles",
        json={
            "provider_identifier": "openai",
            "display_name": "Declared OpenAI profile",
            "execution_mode": "assisted",
            "availability_status": "unknown",
            "capabilities_json": {
                "declared_capabilities": ["planning", "planning"],
                "verified_capabilities": ["must-not-be-trusted"],
            },
            "capability_source": "user_declared",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["availability_status"] == "unknown"
    assert body["capabilities_json"] == {"declared_capabilities": ["planning"]}
    assert body["capability_source"] == "user_declared"
    assert body["capabilities_checked_at"] is None
    assert body["health_checked_at"] is None

    with factory() as db:
        profile = db.get(ProviderProfile, UUID(body["id"]))
        split = provider_profile_capabilities(
            db,
            profile.id,
            Settings(openai_planning_enabled=False, openai_api_key=None),
        )
        assert split.declared_capabilities == ["planning"]
        assert split.verified_capabilities == []
        assert split.verified_availability_status == "not_configured"


def test_story_routing_preflight_is_non_mutating_and_uses_runtime_facts(api):
    client, factory = api
    story = _story(client)
    profile = client.post(
        "/storyboard-crud/provider-profiles",
        json={
            "provider_identifier": "mock",
            "display_name": "Local deterministic planning",
            "execution_mode": "automatic",
            "capabilities_json": {"declared_capabilities": ["anything"]},
            "capability_source": "user_declared",
        },
    ).json()
    assignment = client.post(
        f"/storyboard-crud/stories/{story['id']}/task-assignments",
        json={
            "task_type": "story_structure",
            "provider_profile_id": profile["id"],
            "assignment_mode": "manual",
        },
    )
    assert assignment.status_code == 201

    with factory() as db:
        runs_before = db.scalar(select(func.count(OrchestrationRun.id)))

    response = client.post(
        f"/stories/{story['id']}/routing/validate",
        json={
            "routing_mode": "automatic",
            "prefer_local_providers": True,
            "prefer_hosted_providers": False,
            "max_steps": 1,
            "task_types": ["story_structure"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["requested_mode"] == "automatic"
    assert body["effective_mode"] == "hybrid"
    assert body["routes"] == [
        {
            "task_type": "story_structure",
            "source": "persisted_assignment",
            "provider_identifier": "mock",
            "logical_model": "sol",
            "resolved_model": "mock:logical/sol",
            "availability_status": "available",
            "privacy_classification": "local",
        }
    ]
    assert body["metadata"] == {
        "task_count": 1,
        "network_calls_performed": False,
        "mutated": False,
    }

    with factory() as db:
        runs_after = db.scalar(select(func.count(OrchestrationRun.id)))
        assert runs_after == runs_before == 0


def test_story_routing_preflight_rejects_stub_despite_declared_profile_status(api):
    client, _factory = api
    story = _story(client)
    profile = client.post(
        "/storyboard-crud/provider-profiles",
        json={
            "provider_identifier": "xai",
            "display_name": "Declared xAI profile",
            "execution_mode": "assisted",
            "capabilities_json": {"declared_capabilities": ["planning"]},
            "capability_source": "user_declared",
        },
    ).json()
    client.post(
        f"/storyboard-crud/stories/{story['id']}/task-assignments",
        json={
            "task_type": "story_structure",
            "provider_profile_id": profile["id"],
            "assignment_mode": "manual",
        },
    )

    response = client.post(
        f"/stories/{story['id']}/routing/validate",
        json={
            "routing_mode": "manual",
            "prefer_local_providers": False,
            "prefer_hosted_providers": True,
            "max_steps": 1,
            "task_types": ["story_structure"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    codes = {issue["code"] for issue in body["errors"]}
    assert "provider_unavailable" in codes
    assert "capability_missing" in codes
    assert body["routes"][0]["availability_status"] == "not_implemented"
