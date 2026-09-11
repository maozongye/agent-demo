"""Report / NL-query agent stub endpoints."""

from fastapi import APIRouter, Depends

from app.api.v1.auth import get_current_tenant, get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.agents import ReportQueryRequest, ReportQueryResponse

router = APIRouter()


@router.post("/nl-query", response_model=ReportQueryResponse)
async def nl_query(
    payload: ReportQueryRequest,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> ReportQueryResponse:
    """Stub natural-language query → SQL preview + analysis report.

    Args:
        payload: NL query.
        user: Authenticated user.
        tenant: Active tenant.

    Returns:
        ReportQueryResponse: Stub SQL and analysis scoped to tenant.
    """
    safe_q = payload.query.replace("'", "''")
    sql_preview = (
        f"-- stub for tenant_id={tenant.id}\n"
        f"SELECT COUNT(*) AS n FROM session WHERE tenant_id = {tenant.id};\n"
        f"-- NL: {safe_q}"
    )
    analysis = (
        f"Analysis stub for user={user.id} tenant={tenant.id}: "
        f"interpreted query as a count of sessions. Replace with LangGraph report agent."
    )
    return ReportQueryResponse(
        tenant_id=tenant.id,
        sql_preview=sql_preview,
        analysis_report=analysis,
    )
