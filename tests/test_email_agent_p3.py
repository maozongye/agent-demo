"""Phase 3 email agent tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.langgraph.email_agent import classify_email, run_email_pipeline
from app.models.email_draft import EmailDraft, EmailStatus
from app.models.tenant import MembershipRole, Tenant
from app.models.user import User
from app.services.email_draft import assert_can_send, create_draft_in_memory


def _tenant(tid: int = 10) -> Tenant:
    return Tenant(id=tid, name="T", slug=f"t-{tid}", status="active", created_at=datetime.now(UTC))


def _user(uid: int = 1) -> User:
    return User(id=uid, email="u@example.com", hashed_password="x")


def test_classify_support_and_sales():
    cat, conf, _ = classify_email("Need help", "There is a bug in login")
    assert cat == "support"
    assert conf >= 0.8
    cat2, _, _ = classify_email("Pricing?", "Can I get a quote for annual?")
    assert cat2 == "sales"


def test_pipeline_builds_reply_draft_not_sent():
    result = run_email_pipeline("Invoice question", "Please refund my payment", "a@b.com")
    assert result["category"] == "billing"
    assert result["reply_subject"].lower().startswith("re:")
    assert "billing" in result["reply_body"].lower() or "received" in result["reply_body"].lower()


def test_unapproved_send_forbidden():
    with pytest.raises(Exception) as ei:
        assert_can_send(EmailStatus.DRAFT)
    assert getattr(ei.value, "status_code", None) == 403


def _build_app(monkeypatch, *, role: str, drafts: dict, audits: list):
    import app.api.v1.agents.email as email_mod
    import app.api.v1.auth as auth_mod

    class FakeDB:
        async def create_email_draft(self, **kwargs):
            did = len(drafts) + 1
            d = EmailDraft(
                id=did,
                tenant_id=kwargs["tenant_id"],
                status=EmailStatus.DRAFT.value,
                subject=kwargs.get("subject", ""),
                body=kwargs.get("body", ""),
                to_address=kwargs.get("to_address", ""),
                category=kwargs.get("category", ""),
                category_confidence=kwargs.get("category_confidence", 0.0),
                inbound_from=kwargs.get("inbound_from", ""),
                inbound_subject=kwargs.get("inbound_subject", ""),
                inbound_body=kwargs.get("inbound_body", ""),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            drafts[did] = d
            return d

        async def get_email_draft(self, draft_id, tenant_id):
            d = drafts.get(draft_id)
            if not d or d.tenant_id != tenant_id:
                return None
            return d

        async def save_email_draft(self, draft):
            drafts[draft.id] = draft
            return draft

        async def add_email_audit(self, **kwargs):
            audits.append(kwargs)
            return MagicAudit(**kwargs, id=len(audits), created_at=datetime.now(UTC))

        async def list_email_audits(self, tenant_id, draft_id):
            return [
                MagicAudit(**a, id=i + 1, created_at=datetime.now(UTC))
                for i, a in enumerate(audits)
                if a["tenant_id"] == tenant_id and a["draft_id"] == draft_id
            ]

    class MagicAudit:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr(email_mod, "db_service", FakeDB())

    async def fake_require(user, tenant, allowed):
        if role not in allowed:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Insufficient tenant role")

    monkeypatch.setattr(email_mod, "require_tenant_role", fake_require)

    app = FastAPI()
    app.include_router(email_mod.router, prefix="/agents/email")

    async def user():
        return _user()

    async def tenant():
        return _tenant(10)

    app.dependency_overrides[email_mod.get_current_user] = user
    app.dependency_overrides[email_mod.get_current_tenant] = tenant
    return TestClient(app)


def test_ingest_creates_draft_and_audit(monkeypatch):
    drafts, audits = {}, []
    client = _build_app(monkeypatch, role="member", drafts=drafts, audits=audits)
    resp = client.post(
        "/agents/email/ingest",
        json={"from_address": "c@x.com", "subject": "Need support help", "body": "bug in checkout"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["category"] == "support"
    assert body["draft"]["status"] == "draft"
    assert body["draft"]["id"] in drafts
    assert any(a["action"] == "ingest_classify_draft" for a in audits)


def test_member_cannot_approve_or_send(monkeypatch):
    drafts, audits = {}, []
    client = _build_app(monkeypatch, role="member", drafts=drafts, audits=audits)
    # seed pending draft
    drafts[1] = create_draft_in_memory(10, "s", "b", "t@x.com", draft_id=1)
    drafts[1].status = EmailStatus.PENDING_APPROVAL.value
    drafts[1].created_at = datetime.now(UTC)
    drafts[1].updated_at = datetime.now(UTC)
    assert client.post("/agents/email/drafts/1/approve").status_code == 403
    drafts[1].status = EmailStatus.APPROVED.value
    assert client.post("/agents/email/drafts/1/send").status_code == 403


def test_admin_approve_send_and_unapproved_403(monkeypatch):
    drafts, audits = {}, []
    client = _build_app(monkeypatch, role="admin", drafts=drafts, audits=audits)
    drafts[1] = create_draft_in_memory(10, "s", "b", "t@x.com", draft_id=1)
    drafts[1].status = EmailStatus.DRAFT.value
    drafts[1].created_at = datetime.now(UTC)
    drafts[1].updated_at = datetime.now(UTC)
    assert client.post("/agents/email/drafts/1/send").status_code == 403
    drafts[1].status = EmailStatus.PENDING_APPROVAL.value
    assert client.post("/agents/email/drafts/1/approve").status_code == 200
    assert drafts[1].status == EmailStatus.APPROVED.value
    assert client.post("/agents/email/drafts/1/send").status_code == 200
    assert drafts[1].status == EmailStatus.SENT.value
    assert any(a["action"] == "approve" for a in audits)
    assert any(a["action"] == "send" for a in audits)


def test_cross_tenant_draft_404(monkeypatch):
    drafts, audits = {}, []
    client = _build_app(monkeypatch, role="owner", drafts=drafts, audits=audits)
    drafts[1] = create_draft_in_memory(99, "s", "b", "t@x.com", draft_id=1)
    drafts[1].created_at = datetime.now(UTC)
    drafts[1].updated_at = datetime.now(UTC)
    assert client.get("/agents/email/drafts/1").status_code == 404
