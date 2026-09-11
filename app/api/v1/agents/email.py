"""Email agent: ingest/classify, reply drafts, approval queue, audit log."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.auth import get_current_tenant, get_current_user, require_tenant_role
from app.core.langgraph.email_agent import classify_email, run_email_pipeline
from app.models.email_draft import EmailStatus
from app.models.tenant import MembershipRole, Tenant
from app.models.user import User
from app.schemas.agents import (
    EmailAuditLogResponse,
    EmailClassifyResponse,
    EmailDraftCreate,
    EmailDraftResponse,
    EmailIngestRequest,
    EmailIngestResponse,
)
from app.services.database import DatabaseService
from app.services.email_draft import apply_transition, assert_can_send

router = APIRouter()
db_service = DatabaseService()

_APPROVER_ROLES = {MembershipRole.OWNER.value, MembershipRole.ADMIN.value}


def _to_response(draft) -> EmailDraftResponse:
    return EmailDraftResponse(
        id=draft.id,
        tenant_id=draft.tenant_id,
        status=draft.status,
        subject=draft.subject,
        body=draft.body,
        to_address=draft.to_address,
        category=getattr(draft, "category", "") or "",
        category_confidence=float(getattr(draft, "category_confidence", 0.0) or 0.0),
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


async def _audit(*, tenant_id: int, draft_id: int, user_id: int, action: str, detail: str = "") -> None:
    await db_service.add_email_audit(
        tenant_id=tenant_id,
        draft_id=draft_id,
        actor_user_id=user_id,
        action=action,
        detail=detail,
    )


@router.post("/ingest", response_model=EmailIngestResponse)
async def ingest_email(
    payload: EmailIngestRequest,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailIngestResponse:
    """Stub inbound email ingest: classify + create reply draft (pending human send)."""
    result = run_email_pipeline(payload.subject, payload.body, payload.from_address)
    to_addr = payload.to_address or payload.from_address
    draft = await db_service.create_email_draft(
        tenant_id=tenant.id,
        subject=result["reply_subject"],
        body=result["reply_body"],
        to_address=to_addr,
        category=result["category"],
        category_confidence=float(result["confidence"]),
        inbound_from=payload.from_address,
        inbound_subject=payload.subject,
        inbound_body=payload.body,
    )
    await _audit(
        tenant_id=tenant.id,
        draft_id=draft.id,
        user_id=user.id,
        action="ingest_classify_draft",
        detail=f"category={result['category']} confidence={result['confidence']}",
    )
    return EmailIngestResponse(
        draft=_to_response(draft),
        category=result["category"],
        confidence=float(result["confidence"]),
        rationale=result["rationale"],
    )


@router.post("/drafts", response_model=EmailDraftResponse)
async def create_draft(
    payload: EmailDraftCreate,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Create an email draft in ``draft`` status. Members may create drafts."""
    draft = await db_service.create_email_draft(
        tenant_id=tenant.id,
        subject=payload.subject,
        body=payload.body,
        to_address=payload.to_address,
    )
    await _audit(tenant_id=tenant.id, draft_id=draft.id, user_id=user.id, action="create_draft")
    return _to_response(draft)


@router.post("/drafts/{draft_id}/classify", response_model=EmailClassifyResponse)
async def classify_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailClassifyResponse:
    """Classify a draft with the rules LangGraph classifier and persist category."""
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    source_subject = draft.inbound_subject or draft.subject
    source_body = draft.inbound_body or draft.body
    category, confidence, rationale = classify_email(source_subject, source_body)
    draft.category = category
    draft.category_confidence = confidence
    draft = await db_service.save_email_draft(draft)
    await _audit(
        tenant_id=tenant.id,
        draft_id=draft.id,
        user_id=user.id,
        action="classify",
        detail=f"category={category}",
    )
    return EmailClassifyResponse(
        draft_id=draft.id,
        category=category,
        confidence=confidence,
        rationale=rationale,
    )


@router.post("/drafts/{draft_id}/generate-reply", response_model=EmailDraftResponse)
async def generate_reply(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Regenerate reply subject/body via pipeline; remains in draft (never auto-sends)."""
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status == EmailStatus.SENT.value:
        raise HTTPException(status_code=403, detail="Cannot regenerate a sent email")
    result = run_email_pipeline(
        draft.inbound_subject or draft.subject,
        draft.inbound_body or draft.body,
        draft.inbound_from or "",
    )
    draft.subject = result["reply_subject"]
    draft.body = result["reply_body"]
    draft.category = result["category"]
    draft.category_confidence = float(result["confidence"])
    draft = await db_service.save_email_draft(draft)
    await _audit(tenant_id=tenant.id, draft_id=draft.id, user_id=user.id, action="generate_reply")
    return _to_response(draft)


@router.post("/drafts/{draft_id}/submit-for-approval", response_model=EmailDraftResponse)
async def submit_for_approval(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Transition draft → pending_approval."""
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    draft = await db_service.save_email_draft(draft)
    await _audit(tenant_id=tenant.id, draft_id=draft.id, user_id=user.id, action="submit")
    return _to_response(draft)


@router.post("/drafts/{draft_id}/approve", response_model=EmailDraftResponse)
async def approve_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """pending_approval → approved. Owner/admin only."""
    await require_tenant_role(user, tenant, _APPROVER_ROLES)
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    apply_transition(draft, EmailStatus.APPROVED)
    draft = await db_service.save_email_draft(draft)
    await _audit(tenant_id=tenant.id, draft_id=draft.id, user_id=user.id, action="approve")
    return _to_response(draft)


@router.post("/drafts/{draft_id}/reject", response_model=EmailDraftResponse)
async def reject_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """pending_approval → rejected. Owner/admin only."""
    await require_tenant_role(user, tenant, _APPROVER_ROLES)
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    apply_transition(draft, EmailStatus.REJECTED)
    draft = await db_service.save_email_draft(draft)
    await _audit(tenant_id=tenant.id, draft_id=draft.id, user_id=user.id, action="reject")
    return _to_response(draft)


@router.post("/drafts/{draft_id}/send", response_model=EmailDraftResponse)
async def send_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    """Send approved draft only. Owner/admin only. Never auto-send."""
    await require_tenant_role(user, tenant, _APPROVER_ROLES)
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    assert_can_send(draft.status)
    apply_transition(draft, EmailStatus.SENT)
    draft = await db_service.save_email_draft(draft)
    await _audit(tenant_id=tenant.id, draft_id=draft.id, user_id=user.id, action="send")
    return _to_response(draft)


@router.get("/drafts/{draft_id}", response_model=EmailDraftResponse)
async def get_draft(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> EmailDraftResponse:
    _ = user
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return _to_response(draft)


@router.get("/drafts/{draft_id}/audit", response_model=List[EmailAuditLogResponse])
async def list_draft_audit(
    draft_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> List[EmailAuditLogResponse]:
    _ = user
    draft = await db_service.get_email_draft(draft_id, tenant.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    rows = await db_service.list_email_audits(tenant.id, draft_id)
    return [
        EmailAuditLogResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            draft_id=r.draft_id,
            actor_user_id=r.actor_user_id,
            action=r.action,
            detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]
