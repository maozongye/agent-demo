"""Data report agent: NL→SQL (read-only), sandbox exec, persisted reports."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.auth import get_current_tenant, get_current_user
from app.core.langgraph.data_report import run_report_pipeline
from app.core.logging import logger
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.agents import DataReportResponse, ReportQueryRequest, ReportQueryResponse
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
    if payload.execute:
        try:
            engine = getattr(db_service, "engine", None) or getattr(database_service, "engine", None)
            rows = execute_readonly(engine, sql, tenant.id)
        except SQLSafetyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            # Persist failed execution with SQL for traceability
            status = "failed"
            pipeline = run_report_pipeline(payload.query, tenant.id, rows=[])
            pipeline["analysis"] = f"Execution failed: {exc}\n\nSQL:\n{sql}"
            logger.warning("report_exec_failed", error=str(exc), tenant_id=tenant.id)
            rows = []

    # rebuild analysis with rows when successful translate
    if status == "completed":
        pipeline = run_report_pipeline(payload.query, tenant.id, rows=rows)
        if pipeline.get("error"):
            raise HTTPException(status_code=400, detail=pipeline["error"])
        sql = pipeline["sql"]

    report = await db_service.create_data_report(
        tenant_id=tenant.id,
        created_by=user.id,
        query_text=payload.query,
        sql_text=sql,
        rows_json=json.dumps(rows, default=str),
        report_text=pipeline.get("analysis") or "",
        status=status,
    )
    return ReportQueryResponse(
        id=report.id,
        tenant_id=tenant.id,
        sql_preview=sql,
        analysis_report=report.report_text,
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
        rows = json.loads(row.rows_json or "[]")
    except json.JSONDecodeError:
        rows = []
    return DataReportResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        created_by=row.created_by,
        query_text=row.query_text,
        sql_text=row.sql_text,
        report_text=row.report_text,
        row_count=len(rows) if isinstance(rows, list) else 0,
        status=row.status,
        created_at=row.created_at,
    )


@router.post("/validate-sql")
async def validate_sql(
    payload: dict,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Validate SQL for read-only + tenant scope without executing."""
    _ = user
    sql = str(payload.get("sql") or "")
    try:
        cleaned = assert_tenant_scope(sql, tenant.id)
    except SQLSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "sql": cleaned, "tenant_id": tenant.id}
