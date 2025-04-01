"""Add credits_auto_recharge column to company table

Revision ID: 44f99b8dae57
Revises: 29c6dc90b192
Create Date: 2025-02-19 14:21:03.371744

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '44f99b8dae57'
down_revision: Union[str, None] = '29c6dc90b192'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def column_exists(table, column):
    """
    Checks if a column exists in the specified table.
    
    This function retrieves the current database connection and inspects the list of columns
    in the provided table. It returns True if a column with the given name is found, or False otherwise.
    
    Args:
        table: The name of the table to inspect.
        column: The name of the column to check for.
    
    Returns:
        True if the column exists in the table, False otherwise.
    """
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = inspector.get_columns(table)
    return any(c["name"] == column for c in columns)


def upgrade() -> None:
    # Add company_id column if it doesn't exist
    """
    Adds the 'auto_recharge' column to the 'company' table if it does not exist.
    
    This function checks for the presence of the 'auto_recharge' column using a helper
    function and adds it as a nullable Boolean column via Alembic's operations if missing.
    """
    if not column_exists("company", "auto_recharge"):
        op.add_column('company', sa.Column('auto_recharge', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """
    Remove the `auto_recharge` column from the "company" table if it exists.
    
    This function uses a batch alteration operation to safely modify the table schema.
    It checks for the existence of the column before attempting to drop it.
    """
    with op.batch_alter_table('company', schema=None) as batch_op:
        if column_exists("company", "auto_recharge"):
            batch_op.drop_column('auto_recharge')

