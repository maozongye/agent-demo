# Knowledge Base Agent

Per-tenant namespaces under `/api/v1/agents/knowledge`.

- `POST /knowledge-bases` / `GET /knowledge-bases`
- `POST /knowledge-bases/{id}/documents` (JSON) or `/upload` (file → `UPLOAD_DIR/{tenant_id}/…`)
- `GET /search?q=` — **tenant-scoped only**

Cross-tenant KB/document IDs return **404**.
