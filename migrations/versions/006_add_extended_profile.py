"""Add extended profile fields to users table

Revision ID: 006
Revises: 005
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("conditions", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("food_allergies", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("meals_per_day", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("diet_type", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("food_budget", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("experience_level", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("training_location", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("training_days", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("session_duration", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("training_budget", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "training_budget")
    op.drop_column("users", "session_duration")
    op.drop_column("users", "training_days")
    op.drop_column("users", "training_location")
    op.drop_column("users", "experience_level")
    op.drop_column("users", "food_budget")
    op.drop_column("users", "diet_type")
    op.drop_column("users", "meals_per_day")
    op.drop_column("users", "food_allergies")
    op.drop_column("users", "conditions")
