# Contract Review Agent (Phase 2)

## Flow
1. `POST /api/v1/agents/contract/upload` — tenant-isolated PDF storage under `UPLOAD_DIR/{tenant_id}/`
2. `POST /api/v1/agents/contract/review` — extract text (pypdf) → LangGraph rules detect risks → persist report
3. `GET .../documents/{id}` / `GET .../reviews/{id}` — tenant-scoped reads

## Isolation
- Files and DB rows always keyed by `tenant_id`
- `file_ref` must stay under the tenant directory (path traversal rejected)

## Risk detection
Rules-first LangGraph (`detect` → `report`) covering liability, indemnity, auto-renewal, termination, IP, governing law, non-compete, confidentiality. Works without LLM for tests.
