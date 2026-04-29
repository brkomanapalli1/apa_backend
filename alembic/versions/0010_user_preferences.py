"""add preferences column to users

Revision ID: 0010_user_preferences
Revises: 0009_fix_all_enums
Create Date: 2026-04-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add preferences JSONB column with empty dict default
    op.add_column('users',
        sa.Column('preferences', JSONB, nullable=False, server_default='{}')
    )


def downgrade() -> None:
    op.drop_column('users', 'preferences')