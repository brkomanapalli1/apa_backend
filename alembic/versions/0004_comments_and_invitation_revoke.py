from alembic import op
import sqlalchemy as sa


revision = "0004_comments_and_invitation_revoke"
down_revision = "0003_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('invitations', sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'comments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_comments_document_id', 'comments', ['document_id'])
    op.create_index('ix_comments_user_id', 'comments', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_comments_user_id', table_name='comments')
    op.drop_index('ix_comments_document_id', table_name='comments')
    op.drop_table('comments')
    op.drop_column('invitations', 'revoked')
