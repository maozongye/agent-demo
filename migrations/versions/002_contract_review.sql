-- 002_contract_review (up)

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
