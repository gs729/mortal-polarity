"""Removed the AutopostServers table

Revision ID: 994928bdc1a8
Revises: 17b9c71c9e71
Create Date: 2022-07-03 13:19:49.844337

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "994928bdc1a8"
down_revision = "17b9c71c9e71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("autopostservers")
    op.rename_table("lostsectorautopostchannels", "lostsectorautopostchannel")
    op.add_column(
        "lostsectorautopostchannel", sa.Column("server_id", sa.BIGINT(), nullable=True)
    )
    op.add_column(
        "lostsectorautopostchannel", sa.Column("enabled", sa.BOOLEAN(), nullable=True)
    )


def downgrade() -> None:
    op.create_table(
        "autopostservers",
        sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "enabled",
            sa.BOOLEAN(),
            server_default=sa.text("true"),
            autoincrement=False,
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="autopostservers_pkey"),
    )
    op.drop_column("lostsectorautopostchannel", "server_id")
    op.drop_column("lostsectorautopostchannel", "enabled")
    op.rename_table("lostsectorautopostchannel", "lostsectorautopostchannels")
