"""Add company table

Revision ID: 65ce764b8f7e
Revises: 3781e22d8b01
Create Date: 2025-02-10 12:34:00.054493

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db


# revision identifiers, used by Alembic.
revision: str = '65ce764b8f7e'
down_revision: Union[str, None] = '3781e22d8b01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create the 'company' table in the database.
    
    Creates a new table named "company" with columns for storing company details. The table
    includes an "id" column as a non-nullable primary key with a unique constraint, a non-nullable
    "name" column, an optional "profile_image_url" text column, a "default_model" column with a
    server default of "GPT 4o", and an optional "allowed_models" text column.
    """
    op.create_table(
        'company',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('profile_image_url', sa.Text(), nullable=True),
        sa.Column('default_model', sa.String(), server_default='GPT 4o'),
        sa.Column('allowed_models', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id')
    )


def downgrade() -> None:
    """
    Remove the 'company' table.
    
    Rolls back the migration by dropping the 'company' table from the database, reverting the changes applied during the upgrade.
    """
    op.drop_table('company')
