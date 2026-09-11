# Email Agent (Phase 3)

## Flow
1. `POST /api/v1/agents/email/ingest` — stub inbound mail → classify (LangGraph rules) → create reply **draft** (never sent)
2. Draft lifecycle: `draft → pending_approval → approved|rejected → sent`
3. Only `owner`/`admin` may approve, reject, or send
4. `GET /drafts/{id}/audit` — who did what and when

## Safety
- No path auto-sends mail; `assert_can_send` requires `approved`
- Member cannot approve/send (403)
- Drafts and audits are tenant-scoped
