# Getting started

## Prerequisites

- Python 3.11+ (project uses `uv`)
- Docker + Docker Compose (optional)
- PostgreSQL when running outside the test suite
- Bash (for `source ./scripts/set_env.sh`)

## Environment loading (important)

`make set-env` **cannot** export variables into your current shell (Make always uses a subshell).
Load env into the **current** shell with `source`:

```bash
# development | staging | production | test
source ./scripts/set_env.sh development
# or after sourcing once:  dev_env / stage_env / prod_env / test_env
```

This sets `APP_ENV` and loads `.env.<env>` (created from `.env.example` if missing).
`test` is supported the same way (`source ./scripts/set_env.sh test` / `test_env`).

If you run `make set-env ENV=development`, it only prints the `source` command to copy — it does not mutate your shell.

## Local run

```bash
uv sync
cp .env.example .env.development   # optional; set_env.sh can create it
# Edit .env.development: set a strong JWT_SECRET_KEY
# (weak/default values fail-fast outside APP_ENV=test)

source ./scripts/set_env.sh development
make migrate-up
make dev
```

API base: `http://localhost:8000` — OpenAPI at `/docs`. Health: `GET /api/v1/health`.

## Docker

```bash
# Provide a strong JWT_SECRET_KEY in the environment; the compose default is blacklisted
# and the app will refuse to start outside TEST if that weak value is used.
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export APP_ENV=development
docker compose up --build
```

Compose wires `JWT_SECRET_KEY` from the host; if unset it falls back to a known-weak string that **fails startup** on purpose. Always override it.

## Environment variables (high-signal)

| Variable | Notes |
|----------|--------|
| `APP_ENV` | `development` / `staging` / `production` / `test` |
| `JWT_SECRET_KEY` | Required outside TEST; empty and known weak defaults raise at import/startup |
| `POSTGRES_URL` | SQLAlchemy/Postgres DSN |
| `LLM_API_KEY` / `LLM_MODEL` | LLM calls (agents degrade to rules where designed for tests) |
| `UPLOAD_DIR` | Tenant-scoped contract PDF storage |
| Langfuse keys | Optional tracing |

See `.env.example` for the full list. Never commit real secrets.

## Migrations

Versioned SQL under `migrations/versions/` (`001` … `004`). Prefer migrations over `create_all` for schema changes.

```bash
source ./scripts/set_env.sh development
make migrate-up                 # apply all pending
make migrate-up VERSION=004     # up to a version
make migrate-down VERSION=004   # roll back one version
```

Runner: `scripts/migrate.py`. Root `schema.sql` mirrors the desired schema for reference.

## Tests

```bash
# Preferred for CI/local unit+near-E2E (no need to source .env.test first)
APP_ENV=test uv run pytest tests/ -q

# Or load .env.test into the shell, then run pytest
source ./scripts/set_env.sh test
uv run pytest tests/ -q
```

### Near-E2E scope (`tests/test_e2e_p5.py`)

Covers one wired happy path with fakes (no live Postgres/LLM/Redis):

- register (atomic user+tenant+membership) → tenant-scoped sessions
- contract upload + review + cross-tenant document deny
- email draft → submit → send blocked until approve → send + cross-tenant draft deny
- report NL→SQL / validate-sql + cross-tenant SQL reject

**Out of scope here:** full member-role matrix for email approve/send (covered by unit tests such as `tests/test_email_agent_p3.py` / `tests/test_email_approval.py`), live DB integration, and live LLM evals (`docs/evals-and-ops.md`).
