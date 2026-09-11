-- Database schema for the application
-- Generated from SQLModel classes + Phase 1 multi-tenant migrations
-- Keep in sync with migrations/versions/*

-- Create user table
CREATE TABLE IF NOT EXISTS "user" (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create tenant table
CREATE TABLE IF NOT EXISTS tenant (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create tenant_membership table
CREATE TABLE IF NOT EXISTS tenant_membership (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_tenant UNIQUE (user_id, tenant_id)
);

-- Create session table (tenant_id nullable for legacy; required for new sessions)
CREATE TABLE IF NOT EXISTS session (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    tenant_id INTEGER REFERENCES tenant(id),
    name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create thread table
CREATE TABLE IF NOT EXISTS thread (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create message table
CREATE TABLE IF NOT EXISTS message (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Knowledge base stub (tenant-isolated)
CREATE TABLE IF NOT EXISTS knowledge_base (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Email draft with approval state machine
CREATE TABLE IF NOT EXISTS email_draft (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    subject VARCHAR(500) NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    to_address VARCHAR(320) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_email ON "user"(email);
CREATE INDEX IF NOT EXISTS idx_session_user_id ON session(user_id);
CREATE INDEX IF NOT EXISTS idx_session_tenant_id ON session(tenant_id);
CREATE INDEX IF NOT EXISTS idx_message_session_id ON message(session_id);
CREATE INDEX IF NOT EXISTS idx_tenant_membership_user_id ON tenant_membership(user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_membership_tenant_id ON tenant_membership(tenant_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_tenant_id ON knowledge_base(tenant_id);
CREATE INDEX IF NOT EXISTS idx_email_draft_tenant_id ON email_draft(tenant_id);
CREATE INDEX IF NOT EXISTS idx_email_draft_status ON email_draft(status);

-- Contract review (Phase 2) — Postgres (aligned with 002_contract_review.sql)
CREATE TABLE IF NOT EXISTS contract_document (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    uploaded_by INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    filename VARCHAR(512) NOT NULL,
    file_ref VARCHAR(1024) NOT NULL,
    content_type VARCHAR(128) NOT NULL DEFAULT 'application/pdf',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contract_document_tenant_id ON contract_document(tenant_id);

CREATE TABLE IF NOT EXISTS contract_review (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES contract_document(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'completed',
    report_text TEXT NOT NULL DEFAULT '',
    findings_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contract_review_tenant_id ON contract_review(tenant_id);
CREATE INDEX IF NOT EXISTS idx_contract_review_document_id ON contract_review(document_id);

-- Email agent Phase 3
ALTER TABLE email_draft ADD COLUMN IF NOT EXISTS category VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE email_draft ADD COLUMN IF NOT EXISTS category_confidence DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE email_draft ADD COLUMN IF NOT EXISTS inbound_from VARCHAR(320) NOT NULL DEFAULT '';
ALTER TABLE email_draft ADD COLUMN IF NOT EXISTS inbound_subject VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE email_draft ADD COLUMN IF NOT EXISTS inbound_body TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS email_audit_log (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    draft_id INTEGER NOT NULL,
    actor_user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    action VARCHAR(64) NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_audit_log_tenant_id ON email_audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_email_audit_log_draft_id ON email_audit_log(draft_id);

-- Data report agent Phase 4
CREATE TABLE IF NOT EXISTS data_report (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    created_by INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL DEFAULT '',
    sql_text TEXT NOT NULL DEFAULT '',
    rows_json TEXT NOT NULL DEFAULT '[]',
    report_text TEXT NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_data_report_tenant_id ON data_report(tenant_id);
CREATE INDEX IF NOT EXISTS idx_data_report_status ON data_report(status);

CREATE TABLE IF NOT EXISTS knowledge_document (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    knowledge_base_id INTEGER NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
    title VARCHAR(512) NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    file_ref VARCHAR(1024) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_document_tenant_id ON knowledge_document(tenant_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_document_kb_id ON knowledge_document(knowledge_base_id);

