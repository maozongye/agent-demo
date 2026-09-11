# Evals and ops

## Evaluations

The `evals/` package is the existing Langfuse/LLM evaluation harness:

```bash
make eval            # interactive
make eval-quick      # default settings
make eval-no-report  # skip report generation
```

Entry: `python -m evals.main` (see `evals/main.py`, `evals/evaluator.py`, `evals/metrics/`).

Use a non-test `APP_ENV` with valid LLM credentials when running live evals. Near-E2E product flows are covered by `tests/test_e2e_p5.py` without live LLM/Postgres.

## Ops make targets

| Target | Purpose |
|--------|---------|
| `make install` | `uv sync` |
| `make set-env ENV=...` | Source env files |
| `make dev` / `staging` / `prod` | Run uvicorn |
| `make migrate-up` / `migrate-down` | SQL migrations |
| `make eval*` | Evaluation CLI |

Docker Compose also starts Prometheus under the `monitoring` network; see `docker-compose.yml` and `prometheus/`.
