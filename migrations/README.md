# Database migrations

Lightweight versioned SQL migrations with up/down scripts.

## Layout

```
migrations/
  versions/
    001_multitenant.sql          # up
    001_multitenant_down.sql     # down
  README.md
```

Root `schema.sql` is the full desired schema (kept in sync with models + latest migrations).

**Do not rely only on SQLModel `create_all` for production schema changes.** Use these migrations.

## Apply (up)

```bash
# Using Makefile
make migrate-up VERSION=001

# Or directly with psql
psql "$POSTGRES_URL" -f migrations/versions/001_multitenant.sql
```

Record applied versions in a `schema_migrations` table if desired (created by the runner script).

## Rollback (down)

```bash
make migrate-down VERSION=001

# Or
psql "$POSTGRES_URL" -f migrations/versions/001_multitenant_down.sql
```

## Runner

```bash
python scripts/migrate.py up 001
python scripts/migrate.py down 001
```

The runner applies the matching file under `migrations/versions/` and optionally records it.
