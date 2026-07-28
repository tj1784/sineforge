"""Prove retained phase versions are immutable after current-record mutation.

Uses disposable SQLite only — never the real Transfiguration database.
"""

from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import (
    Base,
    Chapter,
    Character,
    ProductionPhase,
    ProductionPhaseVersion,
    Project,
    Scene,
    Shot,
    Story,
)
from backend.app.schemas.production import PhaseVersionCreateRequest
from backend.app.services import production_phases


@pytest.fixture
def db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'immutability.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _seed_story(db: Session) -> Story:
    project = Project(name=f"Immutability {uuid4().hex[:8]}", description="disposable")
    db.add(project)
    db.flush()
    story = Story(
        project_id=project.id,
        title="Immutability Story",
        base_story="Original mountain narrative.",
        target_duration_sec=120,
        audience="General",
        genre="Drama",
        tone="Quiet",
        visual_style="Natural light",
        point_of_view="Third person",
        production_notes="Disposable immutability fixture",
        approval_state="draft",
    )
    db.add(story)
    db.flush()
    chapter = Chapter(
        story_id=story.id,
        order_index=0,
        title="Act I",
        summary="Opening",
    )
    db.add(chapter)
    db.flush()
    scene = Scene(
        chapter_id=chapter.id,
        order_index=0,
        title="Ridge",
        summary="Dawn ridge",
        location="Mountain ridge",
    )
    db.add(scene)
    db.flush()
    shot = Shot(
        scene_id=scene.id,
        order_index=0,
        title="Wide establish",
        duration_sec=8,
        story_purpose="Establish place",
        visual_description="Wide ridge at dawn",
        location="Mountain ridge",
        continuity_source_type="none",
        starting_image_required=False,
        approval_state="draft",
        production_status="planned",
    )
    db.add(shot)
    character = Character(
        story_id=story.id,
        name="Original Character",
        role="Lead",
        physical_description="Tall, dark coat",
        age_range="40s",
        personality="Measured",
        approval_state="draft",
    )
    db.add(character)
    db.commit()
    db.refresh(story)
    return story


def _row_fingerprint(row: ProductionPhaseVersion) -> tuple:
    return (
        str(row.id),
        row.version_number,
        row.label,
        row.notes,
        row.source,
        row.snapshot_schema_version,
        row.lifecycle_state,
        row.completed,
        deepcopy(row.input_snapshot_json),
        deepcopy(row.output_json),
        row.input_hash,
        row.output_hash,
        str(row.previous_version_id) if row.previous_version_id else None,
        row.superseded_at,
        row.created_by,
    )


def test_historical_versions_immutable_after_current_mutation(db_session: Session):
    story = _seed_story(db_session)
    production_phases.get_pipeline(db_session, story.id)

    retained: dict[int, tuple[str, tuple]] = {}
    for phase_number in range(1, 9):
        created = production_phases.create_phase_version(
            db_session,
            story.id,
            phase_number,
            PhaseVersionCreateRequest(
                label=f"Freeze P{phase_number}",
                notes="immutability proof",
                requested_by="tester",
            ),
        )
        row = db_session.get(ProductionPhaseVersion, created.version.id)
        assert row is not None
        retained[phase_number] = (str(row.id), _row_fingerprint(row))

    # Mutate current canonical records after retention.
    story.base_story = "MUTATED narrative must not leak into history."
    story.title = "MUTATED TITLE"
    character = db_session.scalar(select(Character).where(Character.story_id == story.id))
    assert character is not None
    character.name = "MUTATED Character"
    character.physical_description = "Completely different"
    shot = db_session.scalar(select(Shot))
    assert shot is not None
    shot.title = "MUTATED shot"
    shot.location = "MUTATED location"
    shot.visual_description = "MUTATED visual"
    db_session.commit()

    # Reload every historical iteration and prove content + prior rows unchanged.
    for phase_number, (version_id, fingerprint) in retained.items():
        detail = production_phases.get_phase_version(
            db_session, story.id, phase_number, __import__("uuid").UUID(version_id)
        )
        assert detail.verified is True
        assert detail.version_number >= 1
        output = detail.output_json
        # Historical content must not include post-mutation values.
        blob = str(output)
        assert "MUTATED" not in blob
        if phase_number == 1:
            narrative = output.get("narrative") or {}
            assert narrative.get("base_story") == "Original mountain narrative."
            assert narrative.get("title") == "Immutability Story"
        if phase_number == 2:
            shots = (output.get("structure") or {}).get("shots") or []
            assert any(item.get("title") == "Wide establish" for item in shots)
            assert all(item.get("title") != "MUTATED shot" for item in shots)
        if phase_number == 3:
            characters = (output.get("identity") or {}).get("characters") or []
            assert any(item.get("name") == "Original Character" for item in characters)
            assert all(item.get("name") != "MUTATED Character" for item in characters)
        if phase_number == 4:
            locations = (output.get("locations") or {}).get("locations") or []
            assert "Mountain ridge" in locations
            assert "MUTATED location" not in locations

        row = db_session.get(ProductionPhaseVersion, __import__("uuid").UUID(version_id))
        assert row is not None
        assert _row_fingerprint(row) == fingerprint

    # Cross-phase rejection
    phase3_id = retained[3][0]
    with pytest.raises(production_phases.ProductionPhaseError):
        production_phases.get_phase_version(
            db_session, story.id, 2, __import__("uuid").UUID(phase3_id)
        )

    # Cross-story rejection
    other = _seed_story(db_session)
    production_phases.get_pipeline(db_session, other.id)
    with pytest.raises(production_phases.ProductionPhaseError):
        production_phases.get_phase_version(
            db_session, other.id, 3, __import__("uuid").UUID(phase3_id)
        )

    # Tamper rejection — never falls back to live data
    phase2 = db_session.scalar(
        select(ProductionPhase).where(
            ProductionPhase.story_id == story.id,
            ProductionPhase.phase_number == 2,
        )
    )
    assert phase2 is not None
    version = db_session.scalar(
        select(ProductionPhaseVersion)
        .where(ProductionPhaseVersion.production_phase_id == phase2.id)
        .order_by(ProductionPhaseVersion.version_number.desc())
    )
    assert version is not None
    version.output_json = {**version.output_json, "tampered": True}
    db_session.commit()
    with pytest.raises(production_phases.ProductionPhaseError) as exc:
        production_phases.get_phase_version(db_session, story.id, 2, version.id)
    assert "integrity" in str(exc.value).lower()
