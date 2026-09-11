# Architecture — Phase 1 (Multi-tenant + Agent Skeletons)

## Goals

Phase 1 introduces tenant isolation, versioned SQL migrations, and three agent API skeletons (contract, email, report) alongside the existing chatbot.

## Auth & JWT

- Existing `create_access_token(sub)` / `verify_token` remain for user and session tokens.
- **Extension:** optional JWT claim `tenant_id`.
- Helpers: `decode_token`, `get_tenant_id_from_token`.
- Chatbot session tokens still use `sub` = session id; they may also carry `tenant_id`.

## Tenant context

| Source | Behavior |
|--------|----------|
| JWT `tenant_id` | Primary |
| Header `X-Tenant-Id` | Optional same-user multi-tenant switch — **membership MUST be validated**; otherwise **403** |

Dependency: `get_current_tenant` (requires `get_current_user`).

### Register creates default tenant

On `/api/v1/auth/register`, the API:

1. Creates the user
2. Creates a personal tenant (`{email} workspace`, unique slug)
3. Creates an `owner` membership
4. Issues a JWT that includes `tenant_id`

Login also embeds the user’s first membership `tenant_id` when present.

Thin tenant endpoints:

- `POST /api/v1/auth/tenants` — create + owner membership
- `GET /api/v1/auth/tenants/memberships` — list
- `POST /api/v1/auth/tenants/join` — join stub
- `GET /api/v1/auth/tenants/current` — resolved tenant

## Session + Knowledge Base isolation

- `Session.tenant_id` is **nullable** for legacy migration compatibility; **new sessions require it** (set from `get_current_tenant`).
- `KnowledgeBase` stub: `(id, tenant_id, name, created_at)` — all KB access must filter by tenant.

## Migrations

Lightweight versioned SQL (not Alembic):

- `migrations/versions/001_multitenant.sql` / `001_multitenant_down.sql`
- Runner: `scripts/migrate.py` / `make migrate-up` / `make migrate-down`
- Root `schema.sql` mirrors the full desired schema

**Production changes must use migrations**, not only `SQLModel.create_all`.

## Agent routes

All under `/api/v1`, each Depends on `get_current_user` + `get_current_tenant`:

| Prefix | Stub |
|--------|------|
| `/agents/contract` | `POST /review` → risk findings + report |
| `/agents/email` | draft / classify / submit-for-approval / approve / reject / send |
| `/agents/report` | `POST /nl-query` → SQL preview + analysis |

## Email state machine (forced)

```
draft → pending_approval → approved | rejected
approved → sent
rejected → draft   (re-edit)
```

- Transitions enforced in `app/services/email_draft.py`
- **`send` only from `approved`**; otherwise **HTTP 403**
- Never auto-send

## Models (SQLModel + BaseModel)

- `Tenant`, `TenantMembership`
- `Session.tenant_id`
- `KnowledgeBase`
- `EmailDraft` (+ `EmailStatus` enum)

## Tests

- `tests/test_tenant_context.py` — `X-Tenant-Id` without membership → 403
- `tests/test_email_approval.py` — cannot send from draft / pending_approval
