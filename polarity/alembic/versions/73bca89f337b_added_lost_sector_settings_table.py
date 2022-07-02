"""Added lost sector settings table

Revision ID: 73bca89f337b
Revises: 93c9b7e168c5
Create Date: 2022-07-02 13:43:03.097809

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "73bca89f337b"
down_revision = "93c9b7e168c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lostsectorpostsettings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "autoannounce_enabled", sa.Boolean(), server_default="t", nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("lostsectorpostsettings")
