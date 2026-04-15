-- AI Paperwork Assistant
-- PostgreSQL production-oriented schema
-- Uses ENUMs + JSONB for structured fields
-- PostgreSQL 13+

BEGIN;

-- =========================
-- ENUM TYPES
-- =========================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role_enum') THEN
        CREATE TYPE user_role_enum AS ENUM ('admin', 'member', 'viewer');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'subscription_status_enum') THEN
        CREATE TYPE subscription_status_enum AS ENUM ('free', 'trial', 'active', 'past_due', 'canceled');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'document_status_enum') THEN
        CREATE TYPE document_status_enum AS ENUM (
            'uploading',
            'uploaded',
            'queued',
            'processing',
            'processed',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'document_type_enum') THEN
        CREATE TYPE document_type_enum AS ENUM (
            'medicare_summary_notice',
            'explanation_of_benefits',
            'claim_denial_letter',
            'itemized_medical_bill',
            'medicaid_notice',
            'unknown'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'malware_scan_status_enum') THEN
        CREATE TYPE malware_scan_status_enum AS ENUM (
            'pending',
            'clean',
            'infected',
            'failed',
            'skipped'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'workflow_state_enum') THEN
        CREATE TYPE workflow_state_enum AS ENUM (
            'new',
            'needs_review',
            'in_progress',
            'waiting_on_user',
            'done'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'share_permission_enum') THEN
        CREATE TYPE share_permission_enum AS ENUM ('viewer', 'editor');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notification_channel_enum') THEN
        CREATE TYPE notification_channel_enum AS ENUM ('in_app', 'email', 'push', 'sms');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reminder_status_enum') THEN
        CREATE TYPE reminder_status_enum AS ENUM ('scheduled', 'sent', 'dismissed', 'failed');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sso_provider_enum') THEN
        CREATE TYPE sso_provider_enum AS ENUM ('google');
    END IF;
END$$;

-- =========================
-- UPDATED_AT TRIGGER
-- =========================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================
-- users
-- =========================

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    role user_role_enum NOT NULL DEFAULT 'member',
    stripe_customer_id VARCHAR(255) UNIQUE,
    subscription_status subscription_status_enum NOT NULL DEFAULT 'free',
    push_token VARCHAR(255),
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    totp_secret VARCHAR(255),
    sso_provider sso_provider_enum,
    profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_users_email_lowercase
        CHECK (email = LOWER(email))
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_subscription_status ON users(subscription_status);

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- =========================
-- refresh_tokens
-- =========================

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_jti VARCHAR(128) NOT NULL UNIQUE,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_refresh_tokens_expires_future
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_is_revoked ON refresh_tokens(is_revoked);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);

-- =========================
-- invitations
-- =========================

CREATE TABLE IF NOT EXISTS invitations (
    id BIGSERIAL PRIMARY KEY,
    inviter_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invitee_email VARCHAR(255) NOT NULL,
    token VARCHAR(255) NOT NULL UNIQUE,
    role user_role_enum NOT NULL DEFAULT 'viewer',
    accepted BOOLEAN NOT NULL DEFAULT FALSE,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    accepted_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_invitations_email_lowercase
        CHECK (invitee_email = LOWER(invitee_email))
);

CREATE INDEX IF NOT EXISTS idx_invitations_inviter_id ON invitations(inviter_id);
CREATE INDEX IF NOT EXISTS idx_invitations_invitee_email ON invitations(invitee_email);
CREATE INDEX IF NOT EXISTS idx_invitations_accepted ON invitations(accepted);
CREATE INDEX IF NOT EXISTS idx_invitations_revoked ON invitations(revoked);
CREATE INDEX IF NOT EXISTS idx_invitations_expires_at ON invitations(expires_at);

-- =========================
-- documents
-- =========================

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_to_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,

    name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(120) NOT NULL,
    file_size_bytes BIGINT,
    storage_key VARCHAR(500) NOT NULL UNIQUE,
    storage_bucket VARCHAR(255),
    checksum_sha256 VARCHAR(64),

    status document_status_enum NOT NULL DEFAULT 'uploading',
    processing_job_id VARCHAR(255),

    extracted_text TEXT,
    summary TEXT,

    deadlines JSONB NOT NULL DEFAULT '[]'::jsonb,
    document_type document_type_enum NOT NULL DEFAULT 'unknown',
    document_type_confidence NUMERIC(5,4),

    extracted_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    recommended_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_letter JSONB NOT NULL DEFAULT '{}'::jsonb,

    has_ocr BOOLEAN NOT NULL DEFAULT FALSE,

    malware_scan_status malware_scan_status_enum NOT NULL DEFAULT 'pending',
    malware_scan_result JSONB NOT NULL DEFAULT '{}'::jsonb,

    workflow_state workflow_state_enum NOT NULL DEFAULT 'new',
    version_number INTEGER NOT NULL DEFAULT 1,

    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    processing_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_documents_file_size_nonnegative
        CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),

    CONSTRAINT chk_documents_version_number_positive
        CHECK (version_number >= 1),

    CONSTRAINT chk_documents_confidence_range
        CHECK (
            document_type_confidence IS NULL OR
            (document_type_confidence >= 0 AND document_type_confidence <= 1)
        )
);

CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_id);
CREATE INDEX IF NOT EXISTS idx_documents_assigned_to_user_id ON documents(assigned_to_user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_document_type ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_workflow_state ON documents(workflow_state);
CREATE INDEX IF NOT EXISTS idx_documents_processing_job_id ON documents(processing_job_id);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_checksum_sha256 ON documents(checksum_sha256);

CREATE INDEX IF NOT EXISTS idx_documents_extracted_fields_gin
    ON documents USING GIN (extracted_fields);

CREATE INDEX IF NOT EXISTS idx_documents_deadlines_gin
    ON documents USING GIN (deadlines);

CREATE INDEX IF NOT EXISTS idx_documents_recommended_actions_gin
    ON documents USING GIN (recommended_actions);

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- =========================
-- document_versions
-- =========================

CREATE TABLE IF NOT EXISTS document_versions (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,

    storage_key VARCHAR(500) NOT NULL,

    summary TEXT,
    deadlines JSONB NOT NULL DEFAULT '[]'::jsonb,
    document_type document_type_enum NOT NULL DEFAULT 'unknown',
    document_type_confidence NUMERIC(5,4),
    extracted_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    recommended_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_letter JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    change_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_document_versions_version_number_positive
        CHECK (version_number >= 1),

    CONSTRAINT chk_document_versions_confidence_range
        CHECK (
            document_type_confidence IS NULL OR
            (document_type_confidence >= 0 AND document_type_confidence <= 1)
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_versions_document_version
    ON document_versions(document_id, version_number);

CREATE INDEX IF NOT EXISTS idx_document_versions_document_id ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_created_by_user_id ON document_versions(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_document_type ON document_versions(document_type);
CREATE INDEX IF NOT EXISTS idx_document_versions_created_at ON document_versions(created_at);

CREATE INDEX IF NOT EXISTS idx_document_versions_extracted_fields_gin
    ON document_versions USING GIN (extracted_fields);

-- =========================
-- shares
-- =========================

CREATE TABLE IF NOT EXISTS shares (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    shared_with_email VARCHAR(255) NOT NULL,
    permission share_permission_enum NOT NULL DEFAULT 'viewer',
    shared_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_shares_email_lowercase
        CHECK (shared_with_email = LOWER(shared_with_email))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_shares_document_email
    ON shares(document_id, shared_with_email);

CREATE INDEX IF NOT EXISTS idx_shares_document_id ON shares(document_id);
CREATE INDEX IF NOT EXISTS idx_shares_shared_with_email ON shares(shared_with_email);

-- =========================
-- comments
-- =========================

CREATE TABLE IF NOT EXISTS comments (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    mentions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_comments_body_not_blank
        CHECK (LENGTH(BTRIM(body)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_comments_document_id ON comments(document_id);
CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments(user_id);
CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at);

CREATE INDEX IF NOT EXISTS idx_comments_mentions_gin
    ON comments USING GIN (mentions);

DROP TRIGGER IF EXISTS trg_comments_updated_at ON comments;
CREATE TRIGGER trg_comments_updated_at
BEFORE UPDATE ON comments
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- =========================
-- notifications
-- =========================

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    channel notification_channel_enum NOT NULL DEFAULT 'in_app',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_channel ON notifications(channel);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

CREATE INDEX IF NOT EXISTS idx_notifications_payload_gin
    ON notifications USING GIN (payload);

-- =========================
-- reminders
-- =========================

CREATE TABLE IF NOT EXISTS reminders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    due_at TIMESTAMPTZ,
    status reminder_status_enum NOT NULL DEFAULT 'scheduled',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_reminders_title_not_blank
        CHECK (LENGTH(BTRIM(title)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_document_id ON reminders(document_id);
CREATE INDEX IF NOT EXISTS idx_reminders_due_at ON reminders(due_at);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);

CREATE INDEX IF NOT EXISTS idx_reminders_payload_gin
    ON reminders USING GIN (payload);

-- =========================
-- audit_logs
-- =========================

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(120) NOT NULL,
    entity_type VARCHAR(80),
    entity_id VARCHAR(80),
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT,
    request_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_type_entity_id ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_audit_logs_detail_gin
    ON audit_logs USING GIN (detail);

-- =========================
-- OPTIONAL: document_activity
-- useful for timeline feeds
-- =========================

CREATE TABLE IF NOT EXISTS document_activity (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    actor_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    activity_type VARCHAR(80) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_activity_document_id ON document_activity(document_id);
CREATE INDEX IF NOT EXISTS idx_document_activity_actor_user_id ON document_activity(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_document_activity_activity_type ON document_activity(activity_type);
CREATE INDEX IF NOT EXISTS idx_document_activity_created_at ON document_activity(created_at);

CREATE INDEX IF NOT EXISTS idx_document_activity_payload_gin
    ON document_activity USING GIN (payload);

COMMIT;