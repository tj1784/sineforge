"""add durable LTX Sequence Sheet records

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def _uuid():
    return postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "sequence_plans",
        sa.Column("id", _uuid(), nullable=False),
        *_timestamps(),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("active_revision_id", _uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'validated', 'approved', 'executing', "
            "'completed', 'failed', 'canceled')",
            name="ck_sequence_plans_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sequence_plans_project_id",
        "sequence_plans",
        ["project_id"],
    )
    op.create_index(
        "ix_sequence_plans_project_created",
        "sequence_plans",
        ["project_id", "created_at"],
    )

    op.create_table(
        "sequence_plan_revisions",
        sa.Column("id", _uuid(), nullable=False),
        *_timestamps(),
        sa.Column("sequence_plan_id", _uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("profile_ref", sa.String(length=128), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("canonical_sha256", sa.String(length=64), nullable=False),
        sa.Column("compiled_plan_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="validated",
        ),
        sa.Column("source_json", _json(), nullable=False),
        sa.Column("canonical_json", _json(), nullable=False),
        sa.Column("compiled_plan_json", _json(), nullable=False),
        sa.Column("validation_json", _json(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_sequence_plan_revisions_revision_positive",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'invalid', 'validated', 'approved', "
            "'executing', 'completed', 'failed', 'canceled')",
            name="ck_sequence_plan_revisions_status",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_plan_id"],
            ["sequence_plans.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sequence_plan_id",
            "revision",
            name="uq_sequence_plan_revision_number",
        ),
    )
    op.create_index(
        "ix_sequence_plan_revisions_sequence_plan_id",
        "sequence_plan_revisions",
        ["sequence_plan_id"],
    )
    op.create_index(
        "ix_sequence_plan_revisions_plan_created",
        "sequence_plan_revisions",
        ["sequence_plan_id", "created_at"],
    )

    op.create_table(
        "sequence_rows",
        sa.Column("id", _uuid(), nullable=False),
        *_timestamps(),
        sa.Column("sequence_plan_revision_id", _uuid(), nullable=False),
        sa.Column("row_id", sa.String(length=128), nullable=False),
        sa.Column(
            "row_revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("workflow_template_key", sa.String(length=128), nullable=False),
        sa.Column("workflow_version", sa.String(length=80), nullable=False),
        sa.Column("workflow_sha256", sa.String(length=64), nullable=True),
        sa.Column("profile_ref", sa.String(length=128), nullable=False),
        sa.Column("generation_mode", sa.String(length=16), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "negative_prompt",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column("requested_duration_sec", sa.Numeric(), nullable=False),
        sa.Column("compiled_frame_count", sa.Integer(), nullable=False),
        sa.Column("compiled_duration_sec", sa.Numeric(), nullable=False),
        sa.Column("fps_numerator", sa.Integer(), nullable=False),
        sa.Column("fps_denominator", sa.Integer(), nullable=False),
        sa.Column("concrete_seed", sa.BigInteger(), nullable=False),
        sa.Column("seed_origin", sa.String(length=16), nullable=False),
        sa.Column("continuity_source", sa.String(length=32), nullable=False),
        sa.Column("continuity_asset_id", sa.String(length=128), nullable=True),
        sa.Column("continuity_row_id", sa.String(length=128), nullable=True),
        sa.Column("character_ids_json", _json(), nullable=False),
        sa.Column("asset_ids_json", _json(), nullable=False),
        sa.Column("reference_asset_ids_json", _json(), nullable=False),
        sa.Column("output_basename", sa.String(length=120), nullable=False),
        sa.Column("canonical_row_sha256", sa.String(length=64), nullable=False),
        sa.Column("compiled_segment_json", _json(), nullable=False),
        sa.CheckConstraint(
            "row_revision > 0",
            name="ck_sequence_rows_revision_positive",
        ),
        sa.CheckConstraint(
            "order_index > 0",
            name="ck_sequence_rows_order_positive",
        ),
        sa.CheckConstraint(
            "requested_duration_sec >= 8 AND requested_duration_sec <= 15",
            name="ck_sequence_rows_duration_8_15",
        ),
        sa.CheckConstraint(
            "compiled_frame_count > 0 AND compiled_frame_count % 8 = 1",
            name="ck_sequence_rows_frame_policy",
        ),
        sa.CheckConstraint(
            "fps_numerator > 0 AND fps_denominator > 0",
            name="ck_sequence_rows_fps_positive",
        ),
        sa.CheckConstraint(
            "generation_mode IN ('i2v', 't2v')",
            name="ck_sequence_rows_generation_mode",
        ),
        sa.CheckConstraint(
            "seed_origin IN ('explicit', 'derived')",
            name="ck_sequence_rows_seed_origin",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_plan_revision_id"],
            ["sequence_plan_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sequence_plan_revision_id",
            "row_id",
            name="uq_sequence_rows_revision_row_id",
        ),
        sa.UniqueConstraint(
            "sequence_plan_revision_id",
            "order_index",
            name="uq_sequence_rows_revision_order",
        ),
    )
    op.create_index(
        "ix_sequence_rows_sequence_plan_revision_id",
        "sequence_rows",
        ["sequence_plan_revision_id"],
    )
    op.create_index(
        "ix_sequence_rows_revision_order",
        "sequence_rows",
        ["sequence_plan_revision_id", "order_index"],
    )

    op.create_table(
        "sequence_row_dependencies",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence_plan_revision_id", _uuid(), nullable=False),
        sa.Column("predecessor_row_id", _uuid(), nullable=False),
        sa.Column("successor_row_id", _uuid(), nullable=False),
        sa.Column("dependency_kind", sa.String(length=32), nullable=False),
        sa.Column("required_artifact_kind", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "predecessor_row_id <> successor_row_id",
            name="ck_sequence_row_dependencies_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_plan_revision_id"],
            ["sequence_plan_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_row_id"],
            ["sequence_rows.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["successor_row_id"],
            ["sequence_rows.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sequence_plan_revision_id",
            "predecessor_row_id",
            "successor_row_id",
            "dependency_kind",
            name="uq_sequence_row_dependencies_edge",
        ),
    )
    op.create_index(
        "ix_sequence_row_dependencies_sequence_plan_revision_id",
        "sequence_row_dependencies",
        ["sequence_plan_revision_id"],
    )

    op.create_table(
        "sequence_execution_runs",
        sa.Column("id", _uuid(), nullable=False),
        *_timestamps(),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("sequence_plan_revision_id", _uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("profile_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("allow_rendering_snapshot", sa.Boolean(), nullable=False),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'blocked', 'running', 'completed', "
            "'failed', 'canceled')",
            name="ck_sequence_execution_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_plan_revision_id"],
            ["sequence_plan_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_sequence_execution_runs_project_idempotency",
        ),
    )
    op.create_index(
        "ix_sequence_execution_runs_project_id",
        "sequence_execution_runs",
        ["project_id"],
    )
    op.create_index(
        "ix_sequence_execution_runs_sequence_plan_revision_id",
        "sequence_execution_runs",
        ["sequence_plan_revision_id"],
    )
    op.create_index(
        "ix_sequence_execution_runs_revision_status",
        "sequence_execution_runs",
        ["sequence_plan_revision_id", "status"],
    )

    op.create_table(
        "sequence_row_executions",
        sa.Column("id", _uuid(), nullable=False),
        *_timestamps(),
        sa.Column("sequence_execution_run_id", _uuid(), nullable=False),
        sa.Column("sequence_row_id", _uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "current_attempt",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'invalid', 'pending', "
            "'blocked_on_dependency', 'ready', 'leased', 'submitting', "
            "'queued', 'running', 'collecting', 'validating', "
            "'awaiting_selection', 'succeeded', 'retry_wait', 'failed', "
            "'skipped', 'canceled', 'stale')",
            name="ck_sequence_row_executions_status",
        ),
        sa.CheckConstraint(
            "current_attempt >= 0",
            name="ck_sequence_row_executions_attempt_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_execution_run_id"],
            ["sequence_execution_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_row_id"],
            ["sequence_rows.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sequence_execution_run_id",
            "sequence_row_id",
            name="uq_sequence_row_executions_run_row",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_sequence_row_executions_idempotency_key",
        ),
    )
    op.create_index(
        "ix_sequence_row_executions_sequence_execution_run_id",
        "sequence_row_executions",
        ["sequence_execution_run_id"],
    )
    op.create_index(
        "ix_sequence_row_executions_sequence_row_id",
        "sequence_row_executions",
        ["sequence_row_id"],
    )
    op.create_index(
        "ix_sequence_row_executions_status_lease",
        "sequence_row_executions",
        ["status", "lease_expires_at"],
    )

    op.create_table(
        "sequence_row_attempts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence_row_execution_id", _uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("concrete_seed", sa.BigInteger(), nullable=False),
        sa.Column("patched_workflow_sha256", sa.String(length=64), nullable=True),
        sa.Column("workflow_run_id", _uuid(), nullable=True),
        sa.Column("comfy_job_id", _uuid(), nullable=True),
        sa.Column("input_asset_hashes_json", _json(), nullable=False),
        sa.Column("handoff_input_sha256", sa.String(length=64), nullable=True),
        sa.Column("output_clip_asset_id", _uuid(), nullable=True),
        sa.Column("output_audio_asset_id", _uuid(), nullable=True),
        sa.Column("error_class", sa.String(length=128), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_sequence_row_attempts_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_row_execution_id"],
            ["sequence_row_executions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["comfy_job_id"],
            ["comfy_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["output_clip_asset_id"],
            ["generated_assets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["output_audio_asset_id"],
            ["generated_assets.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sequence_row_execution_id",
            "attempt_number",
            name="uq_sequence_row_attempt_number",
        ),
    )
    op.create_index(
        "ix_sequence_row_attempts_sequence_row_execution_id",
        "sequence_row_attempts",
        ["sequence_row_execution_id"],
    )

    op.create_table(
        "continuity_packets",
        sa.Column("id", _uuid(), nullable=False),
        *_timestamps(),
        sa.Column("sequence_execution_run_id", _uuid(), nullable=False),
        sa.Column("predecessor_row_id", _uuid(), nullable=False),
        sa.Column("successor_row_id", _uuid(), nullable=False),
        sa.Column("source_clip_asset_id", _uuid(), nullable=False),
        sa.Column("source_clip_sha256", sa.String(length=64), nullable=False),
        sa.Column("handoff_image_asset_id", _uuid(), nullable=False),
        sa.Column("handoff_image_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_frame_index", sa.Integer(), nullable=False),
        sa.Column("source_pts_sec", sa.Numeric(), nullable=False),
        sa.Column("continuity_metadata_json", _json(), nullable=False),
        sa.Column("qa_json", _json(), nullable=False),
        sa.Column("reanchor_decision", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "source_frame_index >= 0",
            name="ck_continuity_packets_frame_nonnegative",
        ),
        sa.CheckConstraint(
            "source_pts_sec >= 0",
            name="ck_continuity_packets_pts_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["sequence_execution_run_id"],
            ["sequence_execution_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_row_id"],
            ["sequence_rows.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["successor_row_id"],
            ["sequence_rows.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_clip_asset_id"],
            ["generated_assets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["handoff_image_asset_id"],
            ["generated_assets.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sequence_execution_run_id",
            "predecessor_row_id",
            "successor_row_id",
            name="uq_continuity_packets_run_edge",
        ),
    )
    op.create_index(
        "ix_continuity_packets_sequence_execution_run_id",
        "continuity_packets",
        ["sequence_execution_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_continuity_packets_sequence_execution_run_id",
        table_name="continuity_packets",
    )
    op.drop_table("continuity_packets")
    op.drop_index(
        "ix_sequence_row_attempts_sequence_row_execution_id",
        table_name="sequence_row_attempts",
    )
    op.drop_table("sequence_row_attempts")
    op.drop_index(
        "ix_sequence_row_executions_status_lease",
        table_name="sequence_row_executions",
    )
    op.drop_index(
        "ix_sequence_row_executions_sequence_row_id",
        table_name="sequence_row_executions",
    )
    op.drop_index(
        "ix_sequence_row_executions_sequence_execution_run_id",
        table_name="sequence_row_executions",
    )
    op.drop_table("sequence_row_executions")
    op.drop_index(
        "ix_sequence_execution_runs_revision_status",
        table_name="sequence_execution_runs",
    )
    op.drop_index(
        "ix_sequence_execution_runs_sequence_plan_revision_id",
        table_name="sequence_execution_runs",
    )
    op.drop_index(
        "ix_sequence_execution_runs_project_id",
        table_name="sequence_execution_runs",
    )
    op.drop_table("sequence_execution_runs")
    op.drop_index(
        "ix_sequence_row_dependencies_sequence_plan_revision_id",
        table_name="sequence_row_dependencies",
    )
    op.drop_table("sequence_row_dependencies")
    op.drop_index(
        "ix_sequence_rows_revision_order",
        table_name="sequence_rows",
    )
    op.drop_index(
        "ix_sequence_rows_sequence_plan_revision_id",
        table_name="sequence_rows",
    )
    op.drop_table("sequence_rows")
    op.drop_index(
        "ix_sequence_plan_revisions_plan_created",
        table_name="sequence_plan_revisions",
    )
    op.drop_index(
        "ix_sequence_plan_revisions_sequence_plan_id",
        table_name="sequence_plan_revisions",
    )
    op.drop_table("sequence_plan_revisions")
    op.drop_index(
        "ix_sequence_plans_project_created",
        table_name="sequence_plans",
    )
    op.drop_index(
        "ix_sequence_plans_project_id",
        table_name="sequence_plans",
    )
    op.drop_table("sequence_plans")
