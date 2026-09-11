"""Email agent stub with forced approval state machine."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.auth import get_current_tenant, get_current_user, require_tenant_role
from app.models.email_draft import EmailStatus
from app.models.tenant import MembershipRole, Tenant
from app.models.user import User
from app.schemas.agents import (
    EmailClassifyResponse,
    EmailDraftCreate,
    EmailDraftResponse,
)
from app.services.database import DatabaseService
from app.services.email_draft import (
    apply_transition,
    assert_can_send,
)

router = APIRouter()
db_service = DatabaseService()

_APPROVER_ROLES = {MembershipRole.OWNER.value, MembershipRole.ADMIN.value}


def _to_response(draft) -> EmailDraftResponse:
    """Map EmailDraft model to response schema."""
    return EmailDraftResponse(
        id=draft.id,
        tenant_id=draft.tenant_id,
        status=draft.status,
        subject=draft.subject,
        body=draft.body,
        to_address=draft.to_address,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


@router.post("/drafts", response_model=EmailDraftResponse)
async def create_draft(
    payload: EmailDraftCreate,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Create an email draft in ``draft`` status. Members may create drafts."""
    _ = user
    draft = await db_service.create_email_draft(
        tenant_id=tenant.id,
        subject=payload.subject,
        body=payload.body,
        to_address=payload.to_address,
    )
    return _to_response(draft)


@router.post("/drafts/{draft_id}/classify", response_model=EmailClassifyResponse)
async def classify_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailClassifyResponse:
    """Stub classify an email draft."""
    _ = user
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return EmailClassifyResponse(
        draft_id=draft.id,
        category="general",
        confidence=0.42,
        rationale="Stub classifier — replace with LangGraph email agent.",
    )


@router.post("/drafts/{draft_id}/submit-for-approval", response_model=EmailDraftResponse)
async def submit_for_approval(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Transition draft → pending_approval. Members may submit for approval."""
    _ = user
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    draft = await db_service.save_email_draft(draft)
    return _to_response(draft)


@router.post("/drafts/{draft_id}/approve", response_model=EmailDraftResponse)
async def approve_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Transition pending_approval → approved. Owner/admin only."""
    await require_tenant_role(user, tenant, _APPROVER_ROLES)
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    apply_transition(draft, EmailStatus.APPROVED)
    draft = await db_service.save_email_draft(draft)
    return _to_response(draft)


@router.post("/drafts/{draft_id}/reject", response_model=EmailDraftResponse)
async def reject_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Transition pending_approval → rejected. Owner/admin only."""
    await require_tenant_role(user, tenant, _APPROVER_ROLES)
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    apply_transition(draft, EmailStatus.REJECTED)
    draft = await db_service.save_email_draft(draft)
    return _to_response(draft)


@router.post("/drafts/{draft_id}/send", response_model=EmailDraftResponse)
async def send_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Send an approved draft. Owner/admin only. Raises 403 if not approved."""
    await require_tenant_role(user, tenant, _APPROVER_ROLES)
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    assert_can_send(draft.status)
    apply_transition(draft, EmailStatus.SENT)
    # Stub: no real SMTP — mark as sent only
    draft = await db_service.save_email_draft(draft)
    return _to_response(draft)
