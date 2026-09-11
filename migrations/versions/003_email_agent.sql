-- 003_email_agent (up)

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
CREATE INDEX IF NOT EXISTS idx_email_audit_log_action ON email_audit_log(action);

INSERT INTO schema_migrations (version)
VALUES ('003')
ON CONFLICT (version) DO NOTHING;
