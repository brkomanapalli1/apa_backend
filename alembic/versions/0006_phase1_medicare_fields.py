
"""phase1 medicare fields

Revision ID: 0006_phase1_medicare_fields
Revises: 0005_workflow_versions_assignments
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa

revision = '0006_phase1_medicare_fields'
down_revision = '0005_workflow_versions_assignments'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('document_type', sa.String(length=80), nullable=True))
    op.add_column('documents', sa.Column('document_type_confidence', sa.String(length=20), nullable=True))
    op.add_column('documents', sa.Column('extracted_fields', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('recommended_actions', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('generated_letter', sa.Text(), nullable=True))
    op.create_index(op.f('ix_documents_document_type'), 'documents', ['document_type'], unique=False)

    op.add_column('document_versions', sa.Column('document_type', sa.String(length=80), nullable=True))
    op.add_column('document_versions', sa.Column('extracted_fields', sa.Text(), nullable=True))
    op.add_column('document_versions', sa.Column('recommended_actions', sa.Text(), nullable=True))
    op.add_column('document_versions', sa.Column('generated_letter', sa.Text(), nullable=True))
    op.create_index(op.f('ix_document_versions_document_type'), 'document_versions', ['document_type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_document_versions_document_type'), table_name='document_versions')
    op.drop_column('document_versions', 'generated_letter')
    op.drop_column('document_versions', 'recommended_actions')
    op.drop_column('document_versions', 'extracted_fields')
    op.drop_column('document_versions', 'document_type')

    op.drop_index(op.f('ix_documents_document_type'), table_name='documents')
    op.drop_column('documents', 'generated_letter')
    op.drop_column('documents', 'recommended_actions')
    op.drop_column('documents', 'extracted_fields')
    op.drop_column('documents', 'document_type_confidence')
    op.drop_column('documents', 'document_type')
