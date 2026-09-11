# Getting started

## Prerequisites

- Python 3.11+ (project uses `uv`)
- Docker + Docker Compose (optional)
- PostgreSQL when running outside the test suite

## Local run

```bash
uv sync
cp .env.example .env.development
# Set a strong JWT_SECRET_KEY (weak/default values fail-fast outside APP_ENV=test)
make set-env ENV=development
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
make migrate-up                 # apply all pending
make migrate-up VERSION=004     # up to a version
make migrate-down VERSION=004   # roll back one version
```

Runner: `scripts/migrate.py`. Root `schema.sql` mirrors the desired schema for reference.

## Tests

```bash
APP_ENV=test uv run pytest tests/ -q
```

Near-E2E coverage (auth → contract → email gates → report + cross-tenant): `tests/test_e2e_p5.py`.
