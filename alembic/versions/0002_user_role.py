"""add user role

Revision ID: 0002_user_role
Revises: 0001_initial
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = '0002_user_role'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('role', sa.String(length=50), nullable=True, server_default='member'))
    op.create_index('ix_users_role', 'users', ['role'])
    op.execute("UPDATE users SET role='admin' WHERE email='admin@example.com'")


def downgrade() -> None:
    op.drop_index('ix_users_role', table_name='users')
    op.drop_column('users', 'role')
