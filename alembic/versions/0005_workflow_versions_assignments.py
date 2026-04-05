"""workflow states, document versions, assignments

Revision ID: 0005_workflow_versions_assignments
Revises: 0004_comments_and_invitation_revoke
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = '0005_workflow_versions_assignments'
down_revision = '0004_comments_and_invitation_revoke'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('workflow_state', sa.String(length=50), nullable=False, server_default='new'))
    op.add_column('documents', sa.Column('assigned_to_user_id', sa.Integer(), nullable=True))
    op.add_column('documents', sa.Column('version_number', sa.Integer(), nullable=False, server_default='1'))
    op.create_index(op.f('ix_documents_workflow_state'), 'documents', ['workflow_state'], unique=False)
    op.create_index(op.f('ix_documents_assigned_to_user_id'), 'documents', ['assigned_to_user_id'], unique=False)
    op.create_foreign_key(None, 'documents', 'users', ['assigned_to_user_id'], ['id'], ondelete='SET NULL')

    op.create_table('document_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('deadlines', sa.Text(), nullable=True),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_versions_id'), 'document_versions', ['id'], unique=False)
    op.create_index(op.f('ix_document_versions_document_id'), 'document_versions', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_versions_version_number'), 'document_versions', ['version_number'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_document_versions_version_number'), table_name='document_versions')
    op.drop_index(op.f('ix_document_versions_document_id'), table_name='document_versions')
    op.drop_index(op.f('ix_document_versions_id'), table_name='document_versions')
    op.drop_table('document_versions')
    op.drop_constraint(None, 'documents', type_='foreignkey')
    op.drop_index(op.f('ix_documents_assigned_to_user_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_workflow_state'), table_name='documents')
    op.drop_column('documents', 'version_number')
    op.drop_column('documents', 'assigned_to_user_id')
    op.drop_column('documents', 'workflow_state')
