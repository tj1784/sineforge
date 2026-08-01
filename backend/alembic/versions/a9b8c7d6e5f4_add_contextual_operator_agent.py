"""add contextual operator agent

Revision ID: a9b8c7d6e5f4
Revises: f4c5d6e7a8b9
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a9b8c7d6e5f4"
down_revision = "f4c5d6e7a8b9"
branch_labels = None
depends_on = None


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", _json(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'canceled')",
            name="ck_agent_sessions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_context_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("context_json", _json(), nullable=False),
        sa.Column("hydrated_summary_json", _json(), nullable=False),
        sa.Column("source_refs_json", _json(), nullable=False),
        sa.Column("redaction_report_json", _json(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_context_snapshots_context_hash"),
        "agent_context_snapshots",
        ["context_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_context_snapshots_session_id"),
        "agent_context_snapshots",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", _json(), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'tool', 'system')",
            name="ck_agent_messages_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'streaming', 'complete', 'failed', 'canceled')",
            name="ck_agent_messages_status",
        ),
        sa.ForeignKeyConstraint(
            ["context_snapshot_id"],
            ["agent_context_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_messages_session_created",
        "agent_messages",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_messages_session_id"),
        "agent_messages",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("tool_version", sa.String(length=32), nullable=False),
        sa.Column("risk_class", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_json", _json(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_json", _json(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("error_class", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "risk_class IN ('read', 'low', 'medium', 'high', 'destructive')",
            name="ck_agent_tool_calls_risk_class",
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'validated', 'blocked', 'approval_required', "
            "'running', 'succeeded', 'failed', 'canceled')",
            name="ck_agent_tool_calls_status",
        ),
        sa.ForeignKeyConstraint(
            ["context_snapshot_id"],
            ["agent_context_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["message_id"], ["agent_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_tool_calls_session_created",
        "agent_tool_calls",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_tool_calls_session_id"),
        "agent_tool_calls",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "agent_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_version", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("arguments_json", _json(), nullable=False),
        sa.Column("validation_json", _json(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approval_token_hash", sa.String(length=64), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(length=200), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'executed', "
            "'failed', 'stale', 'canceled')",
            name="ck_agent_proposals_status",
        ),
        sa.ForeignKeyConstraint(
            ["context_snapshot_id"],
            ["agent_context_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_call_id"], ["agent_tool_calls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_token_hash"),
    )
    op.create_index(
        "ix_agent_proposals_session_status",
        "agent_proposals",
        ["session_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_proposals_session_id"),
        "agent_proposals",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_proposals_target_id"),
        "agent_proposals",
        ["target_id"],
        unique=False,
    )

    op.create_table(
        "agent_action_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_version_before", sa.String(length=128), nullable=True),
        sa.Column("target_version_after", sa.String(length=128), nullable=True),
        sa.Column("result_resource_type", sa.String(length=80), nullable=True),
        sa.Column("result_resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("undo_status", sa.String(length=32), nullable=False),
        sa.Column("result_json", _json(), nullable=False),
        sa.Column("undo_json", _json(), nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'partial')",
            name="ck_agent_action_receipts_status",
        ),
        sa.CheckConstraint(
            "undo_status IN ('unavailable', 'available', 'completed', 'failed')",
            name="ck_agent_action_receipts_undo_status",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["agent_proposals.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_action_receipts_proposal_id"),
        "agent_action_receipts",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_action_receipts_session_id"),
        "agent_action_receipts",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "agent_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", sa.String(length=200), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("policy_decision", sa.String(length=64), nullable=True),
        sa.Column("details_json", _json(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_audit_events_event_type"),
        "agent_audit_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_audit_events_session_id"),
        "agent_audit_events",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_audit_events_session_id"), table_name="agent_audit_events")
    op.drop_index(op.f("ix_agent_audit_events_event_type"), table_name="agent_audit_events")
    op.drop_table("agent_audit_events")
    op.drop_index(op.f("ix_agent_action_receipts_session_id"), table_name="agent_action_receipts")
    op.drop_index(op.f("ix_agent_action_receipts_proposal_id"), table_name="agent_action_receipts")
    op.drop_table("agent_action_receipts")
    op.drop_index(op.f("ix_agent_proposals_target_id"), table_name="agent_proposals")
    op.drop_index(op.f("ix_agent_proposals_session_id"), table_name="agent_proposals")
    op.drop_index("ix_agent_proposals_session_status", table_name="agent_proposals")
    op.drop_table("agent_proposals")
    op.drop_index(op.f("ix_agent_tool_calls_session_id"), table_name="agent_tool_calls")
    op.drop_index("ix_agent_tool_calls_session_created", table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")
    op.drop_index(op.f("ix_agent_messages_session_id"), table_name="agent_messages")
    op.drop_index("ix_agent_messages_session_created", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index(op.f("ix_agent_context_snapshots_session_id"), table_name="agent_context_snapshots")
    op.drop_index(op.f("ix_agent_context_snapshots_context_hash"), table_name="agent_context_snapshots")
    op.drop_table("agent_context_snapshots")
    op.drop_table("agent_sessions")
