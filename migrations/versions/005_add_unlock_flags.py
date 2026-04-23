"""Add nutrition_unlocked and workout_unlocked to users

Revision ID: 005
Revises: 004
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("nutrition_unlocked", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("workout_unlocked", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "workout_unlocked")
    op.drop_column("users", "nutrition_unlocked")
