"""Update file table

Revision ID: 7826ab40b532
Revises: 57c599a3cb57
Create Date: 2024-12-23 03:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "7826ab40b532"
down_revision = "57c599a3cb57"
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade the database schema by adding an 'access_control' column to the 'file' table.
    
    This function performs a database migration to introduce a new JSON column named 'access_control'
    to the 'file' table. The column is nullable, allowing flexible storage of access control metadata.
    
    Parameters:
        None
    
    Returns:
        None
    
    Notes:
        - Part of an Alembic database migration script
        - Adds a new column that can store structured access control information
        - Column is nullable, so existing records will not require immediate updates
    """
    op.add_column(
        "file",
        sa.Column("access_control", sa.JSON(), nullable=True),
    )


def downgrade():
    """
    Downgrade the database schema by removing the "access_control" column from the "file" table.
    
    This function is part of an Alembic migration script that reverses the schema changes made in the upgrade process. It removes the previously added JSON column "access_control" from the "file" table.
    
    Notes:
        - This operation is typically used to roll back database schema changes
        - Removes the column without preserving any existing data in that column
    """
    op.drop_column("file", "access_control")
