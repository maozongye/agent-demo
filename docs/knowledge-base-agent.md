# Knowledge Base Agent

Per-tenant namespaces under `/api/v1/agents/knowledge`.

- `POST /knowledge-bases` / `GET /knowledge-bases`
- `POST /knowledge-bases/{id}/documents` (JSON text)
- `POST /knowledge-bases/{id}/upload` (file)
  - Disk path: `UPLOAD_DIR/{tenant_id}/kb/{kb_id}/…`
  - Same size gate as contracts: `MAX_UPLOAD_BYTES`, chunked read, **413** when over limit
- `GET /search?q=` — **tenant-scoped only**

Cross-tenant KB/document IDs return **404**.
