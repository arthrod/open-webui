"""Add time_saved_in_seconds column to completion table

Revision ID: e0cd6c95cb25
Revises: 8b04db1441b0
Create Date: 2025-02-25 08:51:45.692183

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = 'e0cd6c95cb25'
down_revision: Union[str, None] = '8b04db1441b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def column_exists(table, column):
    """
    Check if the specified column exists in the given table.
    
    This function uses SQLAlchemy's Inspector to retrieve column metadata for the 
    specified table and returns True if the column is present, otherwise False.
    
    Parameters:
        table (str): The name of the table to inspect.
        column (str): The name of the column to check for.
    
    Returns:
        bool: True if the column exists in the table, False otherwise.
    """
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = inspector.get_columns(table)
    return any(c["name"] == column for c in columns)

def upgrade() -> None:
    # Add time_saved_in_seconds column if it doesn't exist
    """
    Add time_saved_in_seconds column to completion table if absent.
    
    Checks for the presence of the time_saved_in_seconds column in the completion table
    and adds it as a nullable Float column if it is not present.
    """
    if not column_exists("completion", "time_saved_in_seconds"):
        op.add_column('completion', sa.Column('time_saved_in_seconds', sa.Float (), nullable=True))


def downgrade() -> None:
    """
    Reverts the migration by removing the time_saved_in_seconds column from the completion table.
    
    If the column exists, it is dropped using a batch operation to ensure safe alterations.
    """
    with op.batch_alter_table('completion', schema=None) as batch_op:
        if column_exists("completion", "time_saved_in_seconds"):
            batch_op.drop_column('time_saved_in_seconds')

