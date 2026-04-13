"""Add nutrition_plans and meal_plan_items tables.

Revision ID: 003
Revises: 002
Create Date: 2026-04-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nutrition_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("generated_by", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date"),
    )
    op.create_index("ix_nutrition_plans_user_id", "nutrition_plans", ["user_id"])

    op.create_table(
        "meal_plan_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("meal_type", sa.String(20), nullable=True),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("weight_g", sa.Float(), nullable=False),
        sa.Column("calories", sa.Float(), nullable=False),
        sa.Column("protein", sa.Float(), nullable=False),
        sa.Column("fat", sa.Float(), nullable=False),
        sa.Column("carbs", sa.Float(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["nutrition_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meal_plan_items_plan_id", "meal_plan_items", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_meal_plan_items_plan_id", table_name="meal_plan_items")
    op.drop_table("meal_plan_items")
    op.drop_index("ix_nutrition_plans_user_id", table_name="nutrition_plans")
    op.drop_table("nutrition_plans")
