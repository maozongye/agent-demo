# Data Report Agent (Phase 4)

## Flow
1. `POST /api/v1/agents/report/nl-query` — NL→SQL (rules) → read-only sandbox → persist `data_report`
2. `GET /api/v1/agents/report/reports/{id}` — tenant-scoped report with SQL traceability
3. `POST /api/v1/agents/report/validate-sql` — safety check without execution

## Safety
- Only SELECT/CTE; rejects INSERT/UPDATE/DELETE/DDL and multi-statements
- Requires `tenant_id` filter matching active tenant; rejects other tenant literals
- Reports store `sql_text` for audit/traceability
