"""add WAN/LTX production selection and the eighth production phase

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c9d0e1f2a3b4"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


LEGACY_PHASE_SEVEN_NAME = "Video Generation, Assembly, and Final QA"
PHASE_SEVEN_NAME = "Video Generation, Continuity, Assembly, and Picture Lock"
PHASE_EIGHT_NAME = "Foley, Audio Mix, Final Mux, and Delivery QA"
LTX_BASE_PROFILE_SNAPSHOT = {
    "ref": "ltx_base@1",
    "key": "ltx_base",
    "version": 1,
    "display_name": "LTX Base",
    "model_family": "ltx",
    "status": "qualified",
    "execution_qualified": True,
    "approved_video_model_keys": ["ltx2_3_22b_distilled_1_1_fp8"],
    "approved_video_models": [
        "ltx-2.3-22b-distilled-1.1-fp8.safetensors"
    ],
    "capabilities": {
        "text_to_video": True,
        "image_to_video": True,
        "video_to_video": True,
        "continuation": True,
        "native_audio": "unknown",
        "external_foley": True,
        "high_low_noise_pair": False,
    },
    "frame_policy": {
        "frame_multiple": 8,
        "frame_remainder": 1,
        "nominal_segment_duration_sec": 8.0,
        "min_segment_duration_sec": 6.0,
        "max_segment_duration_sec": 10.0,
        "min_subscene_duration_sec": 6.0,
        "max_subscene_duration_sec": 10.0,
        "allow_shorter_subscene_with_reason": False,
    },
    "qualification_notes": [],
}


def _uuid():
    return postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _phase_table() -> sa.TableClause:
    return sa.table(
        "production_phases",
        sa.column("id", _uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("story_id", _uuid()),
        sa.column("phase_number", sa.Integer()),
        sa.column("name", sa.Text()),
        sa.column("lifecycle_state", sa.String(32)),
        sa.column("current_version_number", sa.Integer()),
        sa.column("is_locked", sa.Boolean()),
        sa.column("locked_reason", sa.Text()),
        sa.column("is_stale", sa.Boolean()),
        sa.column("stale_reason", sa.Text()),
        sa.column("generation_completed_at", sa.DateTime(timezone=True)),
        sa.column("approved_at", sa.DateTime(timezone=True)),
    )


def _settings_table() -> sa.TableClause:
    return sa.table(
        "project_storyboard_settings",
        sa.column("production_profile_key", sa.String(128)),
        sa.column("production_profile_snapshot_json", _json()),
        sa.column("stitch_stage", sa.String(32)),
    )


def upgrade() -> None:
    with op.batch_alter_table("project_storyboard_settings") as batch:
        batch.add_column(
            sa.Column(
                "production_profile_key",
                sa.String(length=128),
                nullable=False,
                server_default="ltx_base@1",
            )
        )
        batch.add_column(
            sa.Column(
                "production_profile_snapshot_json",
                _json(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch.add_column(
            sa.Column(
                "stitch_stage",
                sa.String(length=32),
                nullable=False,
                server_default="phase7_before_audio",
            )
        )
        batch.create_check_constraint(
            "ck_pss_production_profile_key_nonempty",
            "production_profile_key <> ''",
        )
        batch.create_check_constraint(
            "ck_pss_stitch_stage",
            "stitch_stage IN ('phase7_before_audio', 'phase8_before_foley')",
        )

    with op.batch_alter_table("production_phases") as batch:
        batch.drop_constraint("ck_production_phase_number", type_="check")
        batch.create_check_constraint(
            "ck_production_phase_number",
            "phase_number >= 1 AND phase_number <= 8",
        )

    bind = op.get_bind()
    settings = _settings_table()
    bind.execute(
        settings.update().values(
            production_profile_key="ltx_base@1",
            production_profile_snapshot_json=LTX_BASE_PROFILE_SNAPSHOT,
            stitch_stage="phase7_before_audio",
        )
    )
    phases = _phase_table()
    bind.execute(
        phases.update()
        .where(
            sa.and_(
                phases.c.phase_number == 7,
                phases.c.name == LEGACY_PHASE_SEVEN_NAME,
            )
        )
        .values(name=PHASE_SEVEN_NAME)
    )

    existing_phase_eight = {
        row[0]
        for row in bind.execute(
            sa.select(phases.c.story_id).where(phases.c.phase_number == 8)
        )
    }
    story_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM stories"))]
    now = datetime.now(timezone.utc)
    for story_id in story_ids:
        if story_id in existing_phase_eight:
            continue
        phase_id = uuid.uuid4()
        if bind.dialect.name == "sqlite":
            phase_id = str(phase_id)
        bind.execute(
            phases.insert().values(
                id=phase_id,
                created_at=now,
                updated_at=now,
                story_id=story_id,
                phase_number=8,
                name=PHASE_EIGHT_NAME,
                lifecycle_state="not_started",
                current_version_number=None,
                is_locked=True,
                locked_reason=(
                    "Phase 7 must produce an approved immutable picture lock "
                    "before Phase 8 can begin."
                ),
                is_stale=False,
                stale_reason=None,
                generation_completed_at=None,
                approved_at=None,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    blocking_rows = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM production_phase_versions AS version
            JOIN production_phases AS phase
              ON phase.id = version.production_phase_id
            WHERE phase.phase_number = 8
            """
        )
    ).scalar_one()
    progressed_rows = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM production_phases
            WHERE phase_number = 8
              AND (
                lifecycle_state <> 'not_started'
                OR current_version_number IS NOT NULL
                OR approved_at IS NOT NULL
              )
            """
        )
    ).scalar_one()
    if blocking_rows or progressed_rows:
        raise RuntimeError(
            "Cannot downgrade while Phase 8 contains retained history or progressed state."
        )

    phases = _phase_table()
    bind.execute(phases.delete().where(phases.c.phase_number == 8))
    bind.execute(
        phases.update()
        .where(
            sa.and_(
                phases.c.phase_number == 7,
                phases.c.name == PHASE_SEVEN_NAME,
            )
        )
        .values(name=LEGACY_PHASE_SEVEN_NAME)
    )

    with op.batch_alter_table("production_phases") as batch:
        batch.drop_constraint("ck_production_phase_number", type_="check")
        batch.create_check_constraint(
            "ck_production_phase_number",
            "phase_number >= 1 AND phase_number <= 7",
        )

    with op.batch_alter_table("project_storyboard_settings") as batch:
        batch.drop_constraint("ck_pss_stitch_stage", type_="check")
        batch.drop_constraint(
            "ck_pss_production_profile_key_nonempty", type_="check"
        )
        batch.drop_column("stitch_stage")
        batch.drop_column("production_profile_snapshot_json")
        batch.drop_column("production_profile_key")
