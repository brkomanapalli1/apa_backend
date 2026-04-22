"""0008 — APA Phase 2/3/4/5 schema additions

New columns on users:
  - phone                    (SMS reminders, Twilio)
  - sms_reminders_enabled    (user opt-in for SMS)
  - preferred_language       (translation feature)
  - accessibility_settings   (JSONB: large_text, high_contrast, voice_mode)
  - notification_prefs       (JSONB: email, sms, push, caregiver_alerts)

New columns on documents:
  - scam_risk_level          (enum: none/low/medium/high — Phase 2)
  - language_detected        (ISO 639-1 code — Phase 5 translation)
  - retention_expires_at     ([HIPAA] when document should be deleted)

New tables:
  - vault_items              (Emergency Document Vault — Phase 3)
  - medication_reminders     (Structured medication schedule — Phase 2)
  - renewal_trackers         (Smart renewal tracking — Phase 3)
  - timeline_events          (Smart timeline generator — Phase 5)
  - financial_snapshots      (Financial change detection — Phase 4)

Revision: 0008
Revises: 0007_jsonb_enums_release_schema
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, INET

revision = "0008"
down_revision = "0007_jsonb_enums_release_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users: Phase 2/3/5 new columns ────────────────────────────────────

    op.add_column("users", sa.Column(
        "phone", sa.String(20), nullable=True,
        comment="E.164 format US phone for SMS reminders"
    ))
    op.add_column("users", sa.Column(
        "sms_reminders_enabled", sa.Boolean(),
        nullable=False, server_default=sa.false(),
        comment="User opt-in for SMS deadline/medication reminders"
    ))
    op.add_column("users", sa.Column(
        "preferred_language", sa.String(10),
        nullable=False, server_default="en",
        comment="ISO 639-1 code — Phase 5 translation"
    ))
    op.add_column("users", sa.Column(
        "accessibility_settings", JSONB,
        nullable=False, server_default='{}',
        comment="large_text, high_contrast, voice_mode, simple_mode"
    ))
    op.add_column("users", sa.Column(
        "notification_prefs", JSONB,
        nullable=False, server_default='{}',
        comment="email, sms, push, caregiver_alerts, medication_reminders"
    ))
    op.add_column("users", sa.Column(
        "caregiver_notes", sa.Text(),
        nullable=True,
        comment="Caregiver-only notes about this senior user"
    ))

    # ── documents: Phase 2/3/5 new columns ────────────────────────────────

    op.add_column("documents", sa.Column(
        "scam_risk_level", sa.String(10),
        nullable=False, server_default="none", index=True,
        comment="Phase 2 scam detection result: none/low/medium/high"
    ))
    op.add_column("documents", sa.Column(
        "language_detected", sa.String(10),
        nullable=True,
        comment="ISO 639-1 language code detected in document"
    ))
    op.add_column("documents", sa.Column(
        "retention_expires_at", sa.DateTime(timezone=True),
        nullable=True, index=True,
        comment="[HIPAA] Date document should be purged per retention policy"
    ))

    # ── vault_items table (Phase 3: Emergency Document Vault) ─────────────

    op.create_table(
        "vault_items",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("document_id", sa.Integer(),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False,
                  comment="Medical, Financial, Legal, Identity, Contacts"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("encrypted_data", sa.Text(), nullable=True,
                  comment="AES-256 encrypted sensitive data"),
        sa.Column("is_accessible_offline", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        comment="Emergency Document Vault — Phase 3",
    )
    op.create_index("ix_vault_items_user_category", "vault_items", ["user_id", "category"])

    # ── medication_reminders table (Phase 2) ──────────────────────────────

    op.create_table(
        "medication_reminders",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("document_id", sa.Integer(),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("medication_name", sa.String(255), nullable=False),
        sa.Column("dosage", sa.String(100), nullable=True),
        sa.Column("frequency", sa.String(100), nullable=True),
        sa.Column("reminder_times", JSONB, nullable=False,
                  server_default="[]",
                  comment='["08:00","20:00"] — 24h format'),
        sa.Column("with_food", sa.Boolean(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("refill_date", sa.String(50), nullable=True),
        sa.Column("prescriber", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default=sa.true(), index=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        comment="Medication reminder schedule — Phase 2",
    )

    # ── renewal_trackers table (Phase 3) ──────────────────────────────────

    op.create_table(
        "renewal_trackers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("document_id", sa.Integer(),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("title", sa.String(255), nullable=False,
                  comment="Medicare Enrollment, Insurance Renewal, etc."),
        sa.Column("renewal_type", sa.String(80), nullable=False, index=True,
                  comment="medicare, insurance, medicaid, license, passport, benefits"),
        sa.Column("renewal_date", sa.DateTime(timezone=True),
                  nullable=True, index=True),
        sa.Column("reminder_days_before", sa.Integer(),
                  nullable=False, server_default="30"),
        sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        comment="Smart renewal tracking — Phase 3",
    )

    # ── timeline_events table (Phase 5) ───────────────────────────────────

    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("document_id", sa.Integer(),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("event_date", sa.DateTime(timezone=True),
                  nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(50), nullable=False, index=True,
                  comment="medical, financial, legal, utility, government, housing"),
        sa.Column("event_metadata", JSONB,
                  nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        comment="Smart timeline generator — Phase 5",
    )
    op.create_index("ix_timeline_events_user_date", "timeline_events",
                    ["user_id", "event_date"])

    # ── financial_snapshots table (Phase 4) ───────────────────────────────

    op.create_table(
        "financial_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("snapshot_date", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("category", sa.String(80), nullable=False, index=True,
                  comment="electricity, insurance, telecom, rent, etc."),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("provider_name", sa.String(255), nullable=True),
        sa.Column("document_id", sa.Integer(),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("change_from_previous", sa.Numeric(10, 2), nullable=True),
        sa.Column("change_pct", sa.Numeric(7, 2), nullable=True),
        sa.Column("is_anomaly", sa.Boolean(),
                  nullable=False, server_default=sa.false(), index=True),
        sa.Column("anomaly_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        comment="Financial change detection — Phase 4",
    )

    # ── Performance indexes ────────────────────────────────────────────────

    # Scam detection fast lookups
    op.create_index("ix_documents_scam_risk", "documents", ["owner_id", "scam_risk_level"])

    # [HIPAA] Retention policy enforcement
    op.create_index("ix_documents_retention", "documents", ["retention_expires_at"],
                    postgresql_where=sa.text("retention_expires_at IS NOT NULL"))

    # Audit log performance (very high write volume)
    op.create_index("ix_audit_logs_action_date", "audit_logs", ["action", "created_at"])

    # Notification read/unread fast query
    op.create_index("ix_notifications_user_unread", "notifications",
                    ["user_id", "is_read", "created_at"])


def downgrade() -> None:
    # Remove indexes
    op.drop_index("ix_notifications_user_unread", "notifications")
    op.drop_index("ix_audit_logs_action_date", "audit_logs")
    op.drop_index("ix_documents_retention", "documents")
    op.drop_index("ix_documents_scam_risk", "documents")
    op.drop_index("ix_timeline_events_user_date", "timeline_events")
    op.drop_index("ix_vault_items_user_category", "vault_items")

    # Drop new tables
    op.drop_table("financial_snapshots")
    op.drop_table("timeline_events")
    op.drop_table("renewal_trackers")
    op.drop_table("medication_reminders")
    op.drop_table("vault_items")

    # Drop new columns from documents
    op.drop_column("documents", "retention_expires_at")
    op.drop_column("documents", "language_detected")
    op.drop_column("documents", "scam_risk_level")

    # Drop new columns from users
    op.drop_column("users", "caregiver_notes")
    op.drop_column("users", "notification_prefs")
    op.drop_column("users", "accessibility_settings")
    op.drop_column("users", "preferred_language")
    op.drop_column("users", "sms_reminders_enabled")
    op.drop_column("users", "phone")
