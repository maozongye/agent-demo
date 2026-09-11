"""Read-only SQL sandbox with tenant scope enforcement."""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlmodel import Session, text

_WRITE_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|"
    r"MERGE|REPLACE|CALL|EXECUTE|EXEC|INTO|ATTACH|DETACH|VACUUM|REINDEX)\b",
    re.I,
)
_MULTI_STMT = re.compile(r";\s*\S")
_TENANT_LITERAL = re.compile(r"tenant_id\s*=\s*(\d+)", re.I)
_TENANT_BIND = re.compile(r"tenant_id\s*=\s*(:tenant_id|%\(?tenant_id\)?s)", re.I)


class SQLSafetyError(ValueError):
    """Raised when SQL fails sandbox checks."""


def normalize_sql(sql: str) -> str:
    return (sql or "").strip().rstrip(";").strip()


def assert_readonly_sql(sql: str) -> str:
    """Reject write/DDL/multi-statement SQL. Return normalized SQL."""
    cleaned = normalize_sql(sql)
    if not cleaned:
        raise SQLSafetyError("SQL is empty")
    if _MULTI_STMT.search(sql or ""):
        raise SQLSafetyError("Multiple SQL statements are not allowed")
    # Strip line comments for keyword scan
    no_comments = re.sub(r"--.*?$", "", cleaned, flags=re.M)
    if _WRITE_PATTERN.search(no_comments):
        raise SQLSafetyError("Write/DDL SQL is forbidden in the report sandbox")
    if not re.match(r"^\s*(WITH|SELECT)\b", no_comments, re.I):
        raise SQLSafetyError("Only SELECT/CTE queries are allowed")
    return cleaned


def assert_tenant_scope(sql: str, tenant_id: int) -> str:
    """Require tenant_id filter matching the active tenant; reject other tenant literals."""
    cleaned = assert_readonly_sql(sql)
    for match in _TENANT_LITERAL.finditer(cleaned):
        if int(match.group(1)) != tenant_id:
            raise SQLSafetyError("Cross-tenant SQL is forbidden")
    if not (_TENANT_LITERAL.search(cleaned) or _TENANT_BIND.search(cleaned)):
        raise SQLSafetyError("SQL must include a tenant_id filter for the active tenant")
    # If literal present, must equal tenant_id (already checked). If only bind, OK.
    return cleaned


def execute_readonly(engine, sql: str, tenant_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Validate then execute a read-only query with tenant bind params."""
    cleaned = assert_tenant_scope(sql, tenant_id)
    # Soft wrap with LIMIT if absent (best-effort, skip if already has limit)
    run_sql = cleaned
    if not re.search(r"\bLIMIT\b", cleaned, re.I):
        run_sql = f"{cleaned} LIMIT {int(limit)}"
    if engine is None:
        raise SQLSafetyError("Database engine is not available")
    with Session(engine) as session:
        result = session.exec(text(run_sql), params={"tenant_id": tenant_id})
        rows = result.mappings().all() if hasattr(result, "mappings") else result.all()
        out: list[dict[str, Any]] = []
        for row in rows:
            if hasattr(row, "_mapping"):
                out.append(dict(row._mapping))
            elif isinstance(row, dict):
                out.append(row)
            else:
                out.append({"value": row})
        return out
