"""Add company_id to user table

Revision ID: 9ca43b058511
Revises: 65ce764b8f7e
Create Date: 2025-02-10 13:11:02.691437

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '9ca43b058511'
down_revision: Union[str, None] = '65ce764b8f7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table, column):
    """
    Checks if a column exists in the specified table.
    
    This function retrieves the list of columns for the given table using SQLAlchemy's Inspector and returns a boolean value indicating whether a column with the provided name is present.
    
    Args:
        table: The name of the table to inspect.
        column: The name of the column to check.
    
    Returns:
        True if the column exists in the table; otherwise, False.
    """
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = inspector.get_columns(table)
    return any(c["name"] == column for c in columns)


def upgrade() -> None:
    # Add company_id column if it doesn't exist
    """Add company_id column and create its foreign key in the user table.
    
    Checks if the company_id column exists in the user table; if not, it adds the column as a nullable string,
    then alters it to be non-nullable. Afterwards, if there is no foreign key constraint linking company_id to the
    company table, it creates one with a cascading delete option.
    """
    if not column_exists("user", "company_id"):
        op.add_column('user', sa.Column('company_id', sa.String(), nullable=True))

    # Make columns non-nullable
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('company_id', nullable=False)

    # Add foreign key constraint if it doesn't exist
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    foreign_keys = inspector.get_foreign_keys('user')
    if not any(fk['referred_table'] == 'company' for fk in foreign_keys):
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.create_foreign_key(
                'fk_user_company_id', 'company',
                ['company_id'], ['id'], ondelete='CASCADE'
            )


def downgrade() -> None:
    """
    Reverts the changes made to the "user" table.
    
    This function removes the foreign key constraint "fk_user_company_id" (if it exists)
    and drops the "company_id" column, effectively undoing the modifications introduced
    in the upgrade migration.
    """
    with op.batch_alter_table('user', schema=None) as batch_op:
        # Remove foreign key constraint if it exists
        foreign_keys = Inspector.from_engine(op.get_bind()).get_foreign_keys('user')
        if any(fk['name'] == 'fk_user_company_id' for fk in foreign_keys):
            batch_op.drop_constraint('fk_user_company_id', type_='foreignkey')

        # Drop columns if they exist
        if column_exists("user", "company_id"):
            batch_op.drop_column('company_id')
