"""add project creative theme

Revision ID: f4c5d6e7a8b9
Revises: e2f3a4b5c6d7
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f4c5d6e7a8b9"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # Server defaults backfill every existing project to the exact no-op theme.
    # No prompt, media, workflow snapshot, or project asset is rewritten.
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column(
                "theme_id",
                sa.String(length=32),
                nullable=False,
                server_default="default",
            )
        )
        batch_op.add_column(
            sa.Column(
                "theme_version",
                sa.String(length=32),
                nullable=False,
                server_default="1.0.0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "theme_context_json",
                _json(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.create_check_constraint(
            "ck_projects_theme_id",
            "theme_id IN ('default', 'greek_mythology', 'biblical')",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("ck_projects_theme_id", type_="check")
        batch_op.drop_column("theme_context_json")
        batch_op.drop_column("theme_version")
        batch_op.drop_column("theme_id")
