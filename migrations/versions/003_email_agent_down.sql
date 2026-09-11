-- 003_email_agent (down)

DROP TABLE IF EXISTS email_audit_log;

ALTER TABLE email_draft DROP COLUMN IF EXISTS inbound_body;
ALTER TABLE email_draft DROP COLUMN IF EXISTS inbound_subject;
ALTER TABLE email_draft DROP COLUMN IF EXISTS inbound_from;
ALTER TABLE email_draft DROP COLUMN IF EXISTS category_confidence;
ALTER TABLE email_draft DROP COLUMN IF EXISTS category;

DELETE FROM schema_migrations WHERE version = '003';
