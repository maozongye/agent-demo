-- 001_multitenant (down)

DROP TABLE IF EXISTS email_draft;
DROP TABLE IF EXISTS knowledge_base;

DROP INDEX IF EXISTS idx_session_tenant_id;
ALTER TABLE session DROP COLUMN IF EXISTS tenant_id;

DROP TABLE IF EXISTS tenant_membership;
DROP TABLE IF EXISTS tenant;

DELETE FROM schema_migrations WHERE version = '001';
