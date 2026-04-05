"""promote starter schema to enum/jsonb release schema

Revision ID: 0007_jsonb_enums_release_schema
Revises: 0006_phase1_medicare_fields
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007_jsonb_enums_release_schema'
down_revision = '0006_phase1_medicare_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in [
        ('user_role_enum', ('admin', 'member', 'viewer')),
        ('subscription_status_enum', ('free', 'trial', 'active', 'past_due', 'canceled')),
        ('document_status_enum', ('uploading', 'uploaded', 'queued', 'processing', 'completed', 'failed', 'quarantined')),
        ('document_type_enum', ('medicare_summary_notice', 'explanation_of_benefits', 'claim_denial_letter', 'itemized_medical_bill', 'medicaid_notice', 'unknown')),
        ('malware_scan_status_enum', ('pending', 'clean', 'infected', 'failed', 'skipped')),
        ('workflow_state_enum', ('new', 'needs_review', 'in_progress', 'waiting_on_user', 'done')),
        ('share_permission_enum', ('viewer', 'reviewer', 'editor')),
        ('notification_channel_enum', ('in_app', 'email', 'push', 'sms')),
        ('reminder_status_enum', ('scheduled', 'sent', 'dismissed', 'failed')),
        ('sso_provider_enum', ('google',)),
    ]:
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # This migration is intentionally conservative. The full conversion steps are documented in README and infra/sql.
    # New installs can create tables from the updated SQLAlchemy models directly; existing installs should adapt
    # this migration to their exact data state before applying in production.


def downgrade() -> None:
    pass
