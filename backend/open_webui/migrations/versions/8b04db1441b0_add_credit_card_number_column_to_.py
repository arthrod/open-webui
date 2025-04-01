"""Add credit_card_number column to company table

Revision ID: 8b04db1441b0
Revises: 44d3227ecc28
Create Date: 2025-02-20 11:34:31.761119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '8b04db1441b0'
down_revision: Union[str, None] = '44d3227ecc28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table, column):
    """
    Checks whether a specified column exists in a given table.
    
    This function inspects the table's schema using SQLAlchemy's Inspector and
    returns True if the column with the specified name is found, otherwise False.
    
    Args:
        table: The table name to inspect.
        column: The name of the column to check for.
        
    Returns:
        bool: True if the column exists, False otherwise.
    """
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = inspector.get_columns(table)
    return any(c["name"] == column for c in columns)


def upgrade() -> None:
    # Add company_id column if it doesn't exist
    """
    Add the 'credit_card_number' column to the 'company' table if it does not exist.
    
    Checks for the presence of the 'credit_card_number' column and adds it as a nullable
    string column when it is missing.
    """
    if not column_exists("company", "credit_card_number"):
        op.add_column('company', sa.Column('credit_card_number', sa.String(), nullable=True))


def downgrade() -> None:
    """
    Removes the credit_card_number column from the company table if it exists.
    
    Reverts the migration by checking for the column's presence and dropping it using a batch
    operation, ensuring a safe rollback of the database schema change.
    """
    with op.batch_alter_table('company', schema=None) as batch_op:
        if column_exists("company", "credit_card_number"):
            batch_op.drop_column('credit_card_number')
