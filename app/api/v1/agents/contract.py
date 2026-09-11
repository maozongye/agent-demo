"""Contract review agent stub endpoints."""

from fastapi import APIRouter, Depends

from app.api.v1.auth import get_current_tenant, get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.agents import (
    ContractReviewRequest,
    ContractReviewResponse,
    RiskFinding,
)

router = APIRouter()


@router.post("/review", response_model=ContractReviewResponse)
async def review_contract(
    payload: ContractReviewRequest,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> ContractReviewResponse:
    """Stub contract risk review.

    Args:
        payload: Contract text or file reference.
        user: Authenticated user.
        tenant: Active tenant context.

    Returns:
        ContractReviewResponse: Stub findings and report.
    """
    source = payload.text or payload.file_ref or ""
    snippet = (source[:80] + "...") if len(source) > 80 else source
    findings = [
        RiskFinding(
            severity="medium",
            clause="§ liability (stub)",
            summary="Unlimited liability language may be present (stub detection).",
        ),
        RiskFinding(
            severity="low",
            clause="§ termination (stub)",
            summary="Auto-renewal terms should be reviewed (stub).",
        ),
    ]
    report = (
        f"Contract review stub for tenant={tenant.id} user={user.id}. "
        f"Source preview: {snippet or '(empty)'}. "
        f"Findings: {len(findings)}."
    )
    return ContractReviewResponse(tenant_id=tenant.id, findings=findings, report=report)
