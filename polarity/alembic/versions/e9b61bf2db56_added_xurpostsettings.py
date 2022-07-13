"""Added XurPostSettings

Revision ID: e9b61bf2db56
Revises: 994928bdc1a8
Create Date: 2022-07-10 17:34:39.715914

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e9b61bf2db56"
down_revision = "994928bdc1a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "xurpostsettings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "autoannounce_enabled", sa.Boolean(), server_default="t", nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("xurpostsettings")
