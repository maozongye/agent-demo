"""Data report agent: NL→SQL (read-only), sandbox exec, persisted reports."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.auth import get_current_tenant, get_current_user
from app.core.langgraph.data_report import run_report_pipeline
from app.core.logging import logger
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.agents import (
    DataReportResponse,
    ReportQueryRequest,
    ReportQueryResponse,
    SqlValidateRequest,
)
from app.services.database import DatabaseService, database_service
from app.services.sql_sandbox import SQLSafetyError, assert_tenant_scope, execute_readonly

router = APIRouter()
db_service = DatabaseService()


@router.post("/nl-query", response_model=ReportQueryResponse)
async def nl_query(
    payload: ReportQueryRequest,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> ReportQueryResponse:
    """Translate NL→SQL, optionally execute in read-only tenant sandbox, persist report."""
    pipeline = run_report_pipeline(payload.query, tenant.id)
    if pipeline.get("error"):
        raise HTTPException(status_code=400, detail=pipeline["error"])
    sql = pipeline["sql"]
    try:
        assert_tenant_scope(sql, tenant.id)
    except SQLSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows: list = []
    status = "completed"
    analysis = pipeline.get("analysis") or ""
    if payload.execute:
        try:
            engine = getattr(db_service, "engine", None) or getattr(database_service, "engine", None)
            rows = execute_readonly(engine, sql, tenant.id)
            analysis = run_report_pipeline(payload.query, tenant.id, rows=rows).get("analysis") or ""
        except SQLSafetyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            analysis = f"Execution failed: {exc}\n\nSQL:\n{sql}"
            logger.warning("report_exec_failed", error=str(exc), tenant_id=tenant.id)
            rows = []

    report = await db_service.create_data_report(
        tenant_id=tenant.id,
        created_by=user.id,
        query_text=payload.query,
        sql_text=sql,
        rows_json=json.dumps(rows, default=str),
        report_text=analysis,
        status=status,
    )
    return ReportQueryResponse(
        id=report.id,
        tenant_id=tenant.id,
        sql_preview=sql,
        analysis_report=analysis,
        row_count=len(rows),
        status=status,
    )


@router.get("/reports/{report_id}", response_model=DataReportResponse)
async def get_report(
    report_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> DataReportResponse:
    _ = user
    row = await db_service.get_data_report(tenant.id, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        parsed = json.loads(row.rows_json or "[]")
    except json.JSONDecodeError:
        parsed = []
    return DataReportResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        created_by=row.created_by,
        query_text=row.query_text,
        sql_text=row.sql_text,
        report_text=row.report_text,
        row_count=len(parsed) if isinstance(parsed, list) else 0,
        status=row.status,
        created_at=row.created_at,
    )


@router.post("/validate-sql")
async def validate_sql(
    payload: SqlValidateRequest,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Validate SQL for read-only + tenant scope without executing."""
    _ = user
    try:
        cleaned = assert_tenant_scope(payload.sql, tenant.id)
    except SQLSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "sql": cleaned, "tenant_id": tenant.id}
