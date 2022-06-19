"""Initial revision

Revision ID: 5314339d0745
Revises: 
Create Date: 2022-06-18 16:41:09.986721

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5314339d0745"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "commands",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("commands")
    # ### end Alembic commands ###
