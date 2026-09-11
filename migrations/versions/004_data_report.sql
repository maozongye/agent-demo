-- 004_data_report (up)

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

INSERT INTO schema_migrations (version)
VALUES ('004')
ON CONFLICT (version) DO NOTHING;
