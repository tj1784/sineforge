"""Focused coverage for the three creative generation themes."""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base, Project
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.services.themes import compile_theme_prompts, theme_catalog


VALID_BIBLICAL_CONTEXT = {
    "canon_context": "new_testament",
    "scripture_reference": "Luke 15:11-32",
    "narrative_period": "Early first century CE",
    "historical_preset": "nt_herodian_galilee_judea",
    "region": "rural Galilee",
    "culture": ["Galilean Jewish"],
    "roman_presence": "ambient_rule",
    "sacred_representation_policy": "indirect_manifestation",
    "angel_policy": "human_messenger_default",
    "miracle_intensity": "restrained",
}


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_catalog_has_exact_order_ids_labels_and_default() -> None:
    catalog = theme_catalog()
    assert catalog.default_theme_id == "default"
    assert [theme.id.value for theme in catalog.themes] == [
        "default",
        "greek_mythology",
        "biblical",
    ]
    assert [theme.label for theme in catalog.themes] == [
        "Default",
        "Greek Mythology Theme",
        "Biblical Theme",
    ]


def test_themes_endpoint_returns_exact_catalog(client: TestClient) -> None:
    response = client.get("/themes")
    assert response.status_code == 200
    assert response.json()["default_theme_id"] == "default"
    assert [theme["id"] for theme in response.json()["themes"]] == [
        "default",
        "greek_mythology",
        "biblical",
    ]


def test_omitted_and_explicit_default_are_exact_prompt_passthroughs() -> None:
    positive = "  Keep my spacing, punctuation... exactly.  "
    negative = "one, two,, three "
    omitted = compile_theme_prompts(
        theme_id=None,
        theme_context=None,
        positive_prompt=positive,
        negative_prompt=negative,
    )
    explicit = compile_theme_prompts(
        theme_id="default",
        theme_context=None,
        positive_prompt=positive,
        negative_prompt=negative,
    )
    assert omitted.positive_prompt == explicit.positive_prompt == positive
    assert omitted.negative_prompt == explicit.negative_prompt == negative
    assert omitted.snapshot == explicit.snapshot


def test_greek_and_biblical_are_independent_but_preserve_user_intent() -> None:
    user_intent = "A mother gives her child a cup of water at dawn"
    greek = compile_theme_prompts(
        theme_id="greek_mythology",
        theme_context=None,
        positive_prompt=user_intent,
        negative_prompt="text",
    )
    biblical = compile_theme_prompts(
        theme_id="biblical",
        theme_context=VALID_BIBLICAL_CONTEXT,
        positive_prompt=user_intent,
        negative_prompt="text",
    )
    assert user_intent in greek.positive_prompt
    assert user_intent in biblical.positive_prompt
    assert "Greek mythological" in greek.positive_prompt
    assert "Greek mythological" not in biblical.positive_prompt
    assert "Bronze Age Aegean" not in biblical.positive_prompt
    assert "Luke 15:11-32" in biblical.positive_prompt
    assert biblical.snapshot["prompt_profile_id"] == "biblical_grounded_v1"


@pytest.mark.parametrize(
    "context",
    [
        None,
        {**VALID_BIBLICAL_CONTEXT, "canon_context": "hebrew_bible"},
        {
            **VALID_BIBLICAL_CONTEXT,
            "canon_context": "hebrew_bible",
            "historical_preset": "hb_iron_age_israel_judah",
            "roman_presence": "military",
        },
    ],
)
def test_biblical_context_fails_closed(context) -> None:
    with pytest.raises(ValueError):
        compile_theme_prompts(
            theme_id="biblical",
            theme_context=context,
            positive_prompt="A scene",
            negative_prompt="",
        )


def test_project_creation_defaults_theme_and_update_only_changes_project_policy(
    client: TestClient,
    db_session: Session,
) -> None:
    created = client.post(
        "/projects",
        json={"name": "Theme Project", "workflow_lane": "cineforge_studio"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["theme_id"] == "default"
    assert body["theme_context"] is None

    updated = client.patch(
        f"/projects/{body['id']}/theme",
        json={"theme_id": "biblical", "theme_context": VALID_BIBLICAL_CONTEXT},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["theme_id"] == "biblical"
    assert updated.json()["theme_context"]["region"] == "rural Galilee"

    project = db_session.get(Project, UUID(body["id"]))
    assert project is not None
    assert project.name == "Theme Project"
    assert project.theme_id == "biblical"
    assert project.theme_context_json["scripture_reference"] == "Luke 15:11-32"


def test_unknown_theme_and_context_on_default_are_rejected(client: TestClient) -> None:
    unknown = client.post(
        "/projects",
        json={
            "name": "Unknown",
            "workflow_lane": "cineforge_studio",
            "theme_id": "space_opera",
        },
    )
    context_on_default = client.post(
        "/projects",
        json={
            "name": "Default with context",
            "workflow_lane": "cineforge_studio",
            "theme_id": "default",
            "theme_context": VALID_BIBLICAL_CONTEXT,
        },
    )
    assert unknown.status_code == 422
    assert context_on_default.status_code == 422
