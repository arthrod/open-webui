"""Add credit_balance to company table

Revision ID: 804d2918bcd7
Revises: 6eb174dec7b4
Create Date: 2025-02-13 15:57:15.692481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '804d2918bcd7'
down_revision: Union[str, None] = '6eb174dec7b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def column_exists(table, column):
    """
    Checks if a specified column exists in a given table.
    
    This function retrieves the current database connection and uses SQLAlchemy's Inspector
    to inspect the columns of the table. It returns True if any column has a name matching
    the provided column name, and False otherwise.
    
    Args:
        table: The name of the table to inspect.
        column: The column name to check for existence.
    
    Returns:
        bool: True if the column exists in the table; otherwise, False.
    """
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = inspector.get_columns(table)
    return any(c["name"] == column for c in columns)


def upgrade() -> None:
    # Add company_id column if it doesn't exist
    """
    Add the 'credit_balance' column to the company table if it is missing.
    
    Checks whether the 'credit_balance' column exists in the company table using a helper function,
    and if absent, adds it as an integer column that permits null values.
    """
    if not column_exists("company", "credit_balance"):
        op.add_column('company', sa.Column('credit_balance', sa.Integer(), nullable=True))


def downgrade() -> None:
    """
    Reverts the migration by removing the credit_balance column from the company table.
    
    This function checks whether the credit_balance column exists in the company table and,
    if present, removes it using a batch operation to safely update the table schema.
    """
    with op.batch_alter_table('company', schema=None) as batch_op:
        if column_exists("company", "credit_balance"):
            batch_op.drop_column('credit_balance')
