"""Create completion table

Revision ID: 7bd38c980997
Revises: a3117163d6ce
Create Date: 2025-02-18 14:22:48.782795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db


# revision identifiers, used by Alembic.
revision: str = '7bd38c980997'
down_revision: Union[str, None] = 'a3117163d6ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create the 'completion' table in the database.
    
    This function applies a migration by creating the 'completion' table with the
    following columns:
      - id: a non-nullable string that serves as the unique primary key.
      - user_id: a nullable string referencing the 'user.id' column, with a foreign
        key constraint that sets the value to NULL on deletion of the referenced user.
      - chat_id: a nullable string.
      - model: a nullable text field.
      - credits_used: a nullable integer.
      - created_at: a nullable big integer.
    """
    op.create_table(
        'completion',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('chat_id', sa.String(), nullable=True),
        sa.Column('model', sa.Text(), nullable=True),
        sa.Column('credits_used', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL')
    )


def downgrade() -> None:
    """
    Reverts the migration by dropping the 'completion' table.
    
    This function removes the table created in the upgrade migration, effectively
    undoing the schema changes.
    """
    op.drop_table('completion')
