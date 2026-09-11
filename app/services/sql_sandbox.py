"""Read-only SQL sandbox with strict tenant scope enforcement."""

from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, text

# Avoid matching FOR UPDATE as a write verb.
_WRITE_PATTERN = re.compile(
    r"\b(INSERT|(?<!FOR\s)UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|"
    r"MERGE|REPLACE|CALL|EXECUTE|EXEC|(?<!\w)INTO\b|ATTACH|DETACH|VACUUM|REINDEX)\b",
    re.I,
)
_MULTI_STMT = re.compile(r";\s*\S")
_UNION = re.compile(r"\bUNION\b", re.I)
_OR = re.compile(r"\bOR\b", re.I)
_TENANT_EQ = re.compile(
    r"tenant_id\s*=\s*(?P<val>:tenant_id|%\(tenant_id\)s|\d+)",
    re.I,
)
_TENANT_COL = re.compile(r"(?<![:\w])tenant_id\b", re.I)
_BAD_TENANT_OP = re.compile(
    r"(?<![:\w])tenant_id\s*(?:!=|<>|NOT\s+IN|IN\s*\(|IS\s+|<|>|<=|>=)",
    re.I,
)


class SQLSafetyError(ValueError):
    """Raised when SQL fails sandbox checks."""


def strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments before safety scans."""
    no_block = re.sub(r"/\*.*?\*/", " ", sql or "", flags=re.S)
    no_line = re.sub(r"--.*?$", " ", no_block, flags=re.M)
    return no_line


def normalize_sql(sql: str) -> str:
    return (sql or "").strip().rstrip(";").strip()


def assert_readonly_sql(sql: str) -> str:
    """Reject write/DDL/multi-statement SQL. Return normalized SQL."""
    cleaned = normalize_sql(sql)
    if not cleaned:
        raise SQLSafetyError("SQL is empty")
    if _MULTI_STMT.search(sql or ""):
        raise SQLSafetyError("Multiple SQL statements are not allowed")
    scanned = strip_sql_comments(cleaned)
    if _WRITE_PATTERN.search(scanned):
        raise SQLSafetyError("Write/DDL SQL is forbidden in the report sandbox")
    if not re.match(r"^\s*(WITH|SELECT)\b", scanned, re.I):
        raise SQLSafetyError("Only SELECT/CTE queries are allowed")
    return cleaned


def _tenant_predicates(scanned: str) -> list[str]:
    return [m.group("val") for m in _TENANT_EQ.finditer(scanned)]


def assert_tenant_scope(sql: str, tenant_id: int) -> str:
    """Force tenant isolation for sandbox SQL.

    - No UNION / UNION ALL
    - No OR (blocks ``tenant_id = N OR 1=1``)
    - Require ``tenant_id = <active>`` and/or ``tenant_id = :tenant_id``
    - Reject other tenant literals / bind names / unsupported operators
    - Comments are stripped so filters hidden in comments do not count
    """
    cleaned = assert_readonly_sql(sql)
    scanned = strip_sql_comments(cleaned)

    if _UNION.search(scanned):
        raise SQLSafetyError("UNION queries are forbidden in the report sandbox")
    if _OR.search(scanned):
        raise SQLSafetyError("OR conditions are forbidden in tenant-scoped sandbox SQL")
    if _BAD_TENANT_OP.search(scanned):
        raise SQLSafetyError(
            "Unsupported tenant_id predicate; use tenant_id = <active> or :tenant_id"
        )

    preds = _tenant_predicates(scanned)
    if not preds:
        raise SQLSafetyError(
            "SQL must include a tenant_id equality filter for the active tenant"
        )

    ok_binds = {":tenant_id", "%(tenant_id)s"}
    for val in preds:
        if val.isdigit():
            if int(val) != int(tenant_id):
                raise SQLSafetyError("Cross-tenant SQL is forbidden")
        elif val not in ok_binds:
            raise SQLSafetyError(
                "Only tenant_id = :tenant_id (or matching literal) is allowed"
            )

    tenant_cols = len(_TENANT_COL.findall(scanned))
    if tenant_cols != len(preds):
        raise SQLSafetyError(
            "Unsupported tenant_id predicate; use tenant_id = <active> or :tenant_id"
        )

    return cleaned


def execute_readonly(
    engine, sql: str, tenant_id: int, limit: int = 200
) -> list[dict[str, Any]]:
    """Validate then execute a read-only query with tenant bind params."""
    cleaned = assert_tenant_scope(sql, tenant_id)
    run_sql = cleaned
    if not re.search(r"\bLIMIT\b", strip_sql_comments(cleaned), re.I):
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
