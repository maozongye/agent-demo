# Multi-tenant rules and the three agents

## Auth & tenant context

- Register (`POST /api/v1/auth/register`) creates **user + personal tenant + owner membership in one DB transaction** and returns a JWT with `tenant_id`.
- Login embeds the user’s default membership `tenant_id` when present.
- Active tenant resolution (`get_current_tenant`):
  - Primary: JWT claim `tenant_id`
  - Optional header `X-Tenant-Id`: same-user switch; **membership required** or **403**
- Open join is disabled (`POST /api/v1/auth/tenants/join` → 403); invite/admin only.
- Sessions (list / get / delete / rename) are filtered by active `tenant_id`; cross-tenant IDs → **404**.

## Agents (all under `/api/v1`, require user + tenant)

| Agent | Prefix | Happy path |
|-------|--------|------------|
| Contract | `/agents/contract` | `POST /upload` → `POST /review` → get document/review |
| Email | `/agents/email` | ingest/draft → classify / generate-reply → submit → approve → send |
| Report | `/agents/report` | `POST /nl-query` (NL→SQL + optional execute) / `POST /validate-sql` / get report |
| Knowledge | `/agents/knowledge` | create KB / upload docs / tenant-scoped search |

Call with `Authorization: Bearer <token>`. Optional `X-Tenant-Id` when the user has multiple memberships.

## Email approval constraints

```
draft → pending_approval → approved | rejected
approved → sent
rejected → draft
```

- **`send` only from `approved`**; otherwise **403**. Never auto-send.
- Role gate: only tenant `owner` or `admin` may approve / reject / send. Members may draft and submit.
- Audits recorded per draft.

## Report SQL sandbox

- Read-only `SELECT` / CTE only; no writes, multi-statements, `OR`, or `UNION`.
- Every relation (JOIN **or** comma `FROM a, b`) needs an **alias-qualified** `tenant_id = <active>` or `:tenant_id`.
- Duplicate predicates on one alias do not cover another table.
- Comments are stripped before checks.

## Cross-tenant expectation

Wrong-tenant document / draft / report / session / SQL must not leak data (404/403/400 as appropriate).
