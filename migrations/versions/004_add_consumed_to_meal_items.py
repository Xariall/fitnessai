"""Add consumed column to meal_plan_items

Revision ID: 004
Revises: 003
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meal_plan_items",
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("meal_plan_items", "consumed")
