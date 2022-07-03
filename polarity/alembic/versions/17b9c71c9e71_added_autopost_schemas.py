"""Added autopost schemas

Revision ID: 17b9c71c9e71
Revises: 73bca89f337b
Create Date: 2022-07-03 10:55:32.283079

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "17b9c71c9e71"
down_revision = "73bca89f337b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autopostservers",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="t", nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "lostsectorautopostchannels",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("lostsectorautopostchannels")
    op.drop_table("autopostservers")
