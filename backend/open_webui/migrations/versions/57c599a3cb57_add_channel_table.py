"""Add channel table

Revision ID: 57c599a3cb57
Revises: 922e7a387820
Create Date: 2024-12-22 03:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "57c599a3cb57"
down_revision = "922e7a387820"
branch_labels = None
depends_on = None


def upgrade():
    """
    Applies database schema migration by creating two tables: 'channel' and 'message'.
    
    This upgrade function is part of an Alembic migration script that sets up the initial schema for channel and message tables. It creates tables with predefined columns to support a messaging or communication system.
    
    The function performs two primary operations:
    1. Creates a 'channel' table with columns for channel metadata, access control, and timestamps
    2. Creates a 'message' table with columns for message content, associated user and channel, and timestamps
    
    Note:
    - Uses SQLAlchemy (sa) and Alembic (op) for database schema manipulation
    - All columns are nullable except for 'id' which is the primary key
    - Supports flexible data storage with JSON columns for 'data', 'meta', and 'access_control'
    """
    op.create_table(
        "channel",
        sa.Column("id", sa.Text(), nullable=False, primary_key=True, unique=True),
        sa.Column("user_id", sa.Text()),
        sa.Column("name", sa.Text()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("access_control", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.BigInteger(), nullable=True),
    )

    op.create_table(
        "message",
        sa.Column("id", sa.Text(), nullable=False, primary_key=True, unique=True),
        sa.Column("user_id", sa.Text()),
        sa.Column("channel_id", sa.Text(), nullable=True),
        sa.Column("content", sa.Text()),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.BigInteger(), nullable=True),
    )


def downgrade():
    """
    Reverts the database migration by dropping the 'channel' and 'message' tables.
    
    This function is part of an Alembic migration script and is responsible for rolling back 
    the schema changes introduced in the corresponding upgrade() function. It removes the 
    previously created database tables to restore the database to its previous state.
    
    Notes:
        - Used in database schema migration rollback scenarios
        - Drops tables without additional error handling
    """
    op.drop_table("channel")

    op.drop_table("message")
