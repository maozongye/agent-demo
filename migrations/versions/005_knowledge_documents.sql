-- 005_knowledge_documents (up)

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

INSERT INTO schema_migrations (version)
VALUES ('005')
ON CONFLICT (version) DO NOTHING;
