"""Rename commands.text to commands.response

Revision ID: 93c9b7e168c5
Revises: 5314339d0745
Create Date: 2022-06-25 13:42:11.034486

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "93c9b7e168c5"
down_revision = "5314339d0745"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("commands", "text", nullable=False, new_column_name="response")


def downgrade() -> None:
    op.alter_column("commands", "response", nullable=False, new_column_name="text")
