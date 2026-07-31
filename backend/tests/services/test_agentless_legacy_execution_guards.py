"""Fail-closed coverage for Agentless projects on legacy render services."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from backend.app.api.routes.production import _error
from backend.app.db.base import Project, Story
from backend.app.services import (
    phase_seven_videos,
    phase_six_images,
    production_phases,
)


@pytest.fixture()
def agentless_story_context() -> tuple[MagicMock, Story, Project]:
    project = Project(
        id=uuid4(),
        name="Agentless legacy guard",
        description=None,
        workflow_lane="agentless",
    )
    story = Story(
        id=uuid4(),
        project_id=project.id,
        title="Guarded story",
        base_story="A deterministic scene-reset production.",
        target_duration_sec=10,
    )
    db = MagicMock(spec=Session)

    def _get(model, entity_id):  # noqa: ANN001
        if model is Story and entity_id == story.id:
            return story
        if model is Project and entity_id == project.id:
            return project
        return None

    db.get.side_effect = _get
    return db, story, project


def _expected_dry_run_path(project: Project) -> str:
    return f"/projects/{project.id}/agentless-workflow/dry-run"


def test_production_route_maps_lane_conflicts_to_http_409() -> None:
    response = _error(
        production_phases.ProductionPhaseError(
            "workflow_lane_mismatch: use the Agentless dry-run route."
        )
    )

    assert response.status_code == 409


def test_phase_six_prepare_rejects_before_mutation(
    agentless_story_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, story, project = agentless_story_context
    shot_read = Mock()
    monkeypatch.setattr(phase_six_images, "_shots", shot_read)

    with pytest.raises(
        phase_six_images.PhaseSixImageError,
        match="workflow_lane_mismatch",
    ) as error:
        phase_six_images.prepare(
            db,
            story.id,
            requested_by="test",
        )

    assert _expected_dry_run_path(project) in str(error.value)
    shot_read.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "entrypoint",
    [
        "generate_shot",
        "generate_character_reference",
        "generate_asset_reference",
        "generate_phase_five_handoff",
    ],
)
def test_phase_six_generation_entrypoints_reject_before_side_effects(
    agentless_story_context,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    db, story, project = agentless_story_context
    comfy_client = Mock()
    asset_upload = Mock()
    shot_read = Mock()
    character_read = Mock()
    asset_target_read = Mock()
    monkeypatch.setattr(phase_six_images.httpx, "Client", comfy_client)
    monkeypatch.setattr(
        phase_six_images.reference_assets,
        "upload_asset",
        asset_upload,
    )
    monkeypatch.setattr(phase_six_images, "_shot_rows", shot_read)
    monkeypatch.setattr(phase_six_images, "_characters", character_read)
    monkeypatch.setattr(
        phase_six_images,
        "_asset_reference_targets",
        asset_target_read,
    )

    if entrypoint == "generate_shot":
        invoke = lambda: phase_six_images.generate_shot(  # noqa: E731
            db,
            story.id,
            uuid4(),
            requested_by="test",
        )
    elif entrypoint == "generate_character_reference":
        invoke = lambda: phase_six_images.generate_character_reference(  # noqa: E731
            db,
            story.id,
            uuid4(),
            requested_by="test",
        )
    elif entrypoint == "generate_asset_reference":
        target = phase_six_images.AssetReferenceTarget(
            label="SET-01",
            target_type="location",
            name="Podcast studio",
            prompt="A clean studio reference.",
            scene_ids=(),
            shot_ids=(),
        )
        invoke = lambda: phase_six_images.generate_asset_reference(  # noqa: E731
            db,
            story.id,
            target,
            requested_by="test",
        )
    else:
        invoke = lambda: phase_six_images.generate_phase_five_handoff(  # noqa: E731
            db,
            story.id,
            requested_by="test",
        )

    with pytest.raises(
        phase_six_images.PhaseSixImageError,
        match="workflow_lane_mismatch",
    ) as error:
        invoke()

    assert _expected_dry_run_path(project) in str(error.value)
    comfy_client.assert_not_called()
    asset_upload.assert_not_called()
    shot_read.assert_not_called()
    character_read.assert_not_called()
    asset_target_read.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_phase_seven_queue_rejects_before_reads_copy_or_runner_submission(
    agentless_story_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, story, project = agentless_story_context
    shot_read = Mock()
    workflow_read = Mock()
    copy_to_input = Mock()
    runner_submit = Mock()
    filesystem_copy = Mock()
    runner_client = Mock()
    monkeypatch.setattr(phase_seven_videos, "_shot_rows", shot_read)
    monkeypatch.setattr(phase_seven_videos, "_load_workflow", workflow_read)
    monkeypatch.setattr(
        phase_seven_videos,
        "_copy_starting_image_to_comfy_input",
        copy_to_input,
    )
    monkeypatch.setattr(
        phase_seven_videos,
        "_post_runner_job",
        runner_submit,
    )
    monkeypatch.setattr(phase_seven_videos.shutil, "copy2", filesystem_copy)
    monkeypatch.setattr(phase_seven_videos.httpx, "Client", runner_client)

    with pytest.raises(
        phase_seven_videos.PhaseSevenVideoError,
        match="workflow_lane_mismatch",
    ) as error:
        phase_seven_videos.queue_story_videos(
            db,
            story.id,
            requested_by="test",
        )

    assert _expected_dry_run_path(project) in str(error.value)
    shot_read.assert_not_called()
    workflow_read.assert_not_called()
    copy_to_input.assert_not_called()
    runner_submit.assert_not_called()
    filesystem_copy.assert_not_called()
    runner_client.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()
