"""add durable project workflow lane

Revision ID: e2f3a4b5c6d7
Revises: d0e1f2a3b4c5
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e2f3a4b5c6d7"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The server default upgrades every legacy project into the compatibility
    # Studio lane and also protects inserts from older application binaries.
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column(
                "workflow_lane",
                sa.String(length=32),
                nullable=False,
                server_default="cineforge_studio",
            )
        )
        batch_op.create_check_constraint(
            "ck_projects_workflow_lane",
            "workflow_lane IN ('cineforge_studio', 'agentless')",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint(
            "ck_projects_workflow_lane",
            type_="check",
        )
        batch_op.drop_column("workflow_lane")
