"""Phase 5 near-E2E: auth/tenant → contract → email gates → report NL→SQL.

Uses TestClient + fakes (no live Postgres/LLM/Redis). Cross-tenant denials included.
Attaches a disabled SlowAPI limiter on ``app.state.limiter`` (same pattern as
phase1 auth tests) so ``/auth/register`` is not broken by rate limiting.
Member-role approve/send matrix remains in email unit tests, not this path.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.config import settings
from app.models.contract import ContractDocument, ContractReview
from app.models.data_report import DataReport
from app.models.email_draft import EmailDraft, EmailStatus
from app.models.session import Session as ChatSession
from app.models.tenant import MembershipRole, Tenant, TenantMembership
from app.models.user import User
from app.schemas.auth import Token
from app.services.sql_sandbox import SQLSafetyError, assert_tenant_scope


def _pdf() -> bytes:
    buf = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.write(buf)
    return buf.getvalue()


def _token() -> Token:
    return Token(
        access_token="e2e-token",
        token_type="bearer",
        expires_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def e2e_client(monkeypatch, tmp_path):
    """Single app wiring auth + three agents with in-memory fakes."""
    import app.api.v1.agents.contract as contract_mod
    import app.api.v1.agents.email as email_mod
    import app.api.v1.agents.report as report_mod
    import app.api.v1.auth as auth_mod

    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)

    state = {
        "users": {},
        "tenants": {},
        "memberships": {},  # (user_id, tenant_id) -> role
        "sessions": {},
        "docs": {},
        "reviews": {},
        "drafts": {},
        "audits": [],
        "reports": {},
        "seq": 1,
    }

    def _next_id() -> int:
        state["seq"] += 1
        return state["seq"]

    class FakeDB:
        engine = object()

        async def get_user_by_email(self, email):
            for u in state["users"].values():
                if u.email == email:
                    return u
            return None

        async def register_user_with_default_tenant(self, email, password, tenant_name, tenant_slug, *, role):
            uid = _next_id()
            tid = _next_id()
            user = User(id=uid, email=email, hashed_password=password)
            tenant = Tenant(
                id=tid, name=tenant_name, slug=tenant_slug, status="active", created_at=datetime.now(UTC)
            )
            state["users"][uid] = user
            state["tenants"][tid] = tenant
            state["memberships"][(uid, tid)] = role
            membership = TenantMembership(user_id=uid, tenant_id=tid, role=role)
            return user, tenant, membership

        async def get_membership(self, user_id, tenant_id):
            role = state["memberships"].get((user_id, tenant_id))
            if role is None:
                return None
            return TenantMembership(user_id=user_id, tenant_id=tenant_id, role=role)

        async def get_tenant(self, tenant_id):
            return state["tenants"].get(tenant_id)

        async def get_default_tenant_id_for_user(self, user_id):
            for (uid, tid), _ in state["memberships"].items():
                if uid == user_id:
                    return tid
            return None

        async def create_session(self, session_id, user_id, name="", tenant_id=None):
            s = ChatSession(id=session_id, user_id=user_id, name=name, tenant_id=tenant_id)
            state["sessions"][session_id] = s
            return s

        async def get_session(self, session_id, tenant_id=None):
            s = state["sessions"].get(session_id)
            if s is None:
                return None
            if tenant_id is not None and s.tenant_id != tenant_id:
                return None
            return s

        async def get_user_sessions(self, user_id, tenant_id=None):
            rows = [s for s in state["sessions"].values() if s.user_id == user_id]
            if tenant_id is not None:
                rows = [s for s in rows if s.tenant_id == tenant_id]
            return rows

        async def delete_session(self, session_id, tenant_id=None):
            s = await self.get_session(session_id, tenant_id=tenant_id)
            if s is None:
                return False
            del state["sessions"][session_id]
            return True

        # contract
        def create_document(self, **kwargs):
            did = _next_id()
            doc = ContractDocument(id=did, created_at=datetime.now(UTC), **kwargs)
            state["docs"][did] = doc
            return doc

        def get_document(self, tenant_id, document_id):
            doc = state["docs"].get(document_id)
            if not doc or doc.tenant_id != tenant_id:
                return None
            return doc

        def create_review(self, **kwargs):
            rid = _next_id()
            review = ContractReview(
                id=rid,
                tenant_id=kwargs["tenant_id"],
                document_id=kwargs.get("document_id"),
                status=kwargs.get("status", "completed"),
                report_text=kwargs.get("report_text", ""),
                findings_json=json.dumps(kwargs.get("findings") or []),
                created_at=datetime.now(UTC),
            )
            state["reviews"][rid] = review
            return review

        def get_review(self, tenant_id, review_id):
            r = state["reviews"].get(review_id)
            if not r or r.tenant_id != tenant_id:
                return None
            return r

        # email
        async def create_email_draft(self, **kwargs):
            did = _next_id()
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
            state["drafts"][did] = d
            return d

        async def get_email_draft(self, draft_id, tenant_id):
            d = state["drafts"].get(draft_id)
            if not d or d.tenant_id != tenant_id:
                return None
            return d

        async def save_email_draft(self, draft):
            state["drafts"][draft.id] = draft
            return draft

        async def add_email_audit(self, **kwargs):
            row = {**kwargs, "id": len(state["audits"]) + 1, "created_at": datetime.now(UTC)}
            state["audits"].append(row)
            return type("A", (), row)()

        async def list_email_audits(self, tenant_id, draft_id):
            return [
                type("A", (), a)()
                for a in state["audits"]
                if a["tenant_id"] == tenant_id and a["draft_id"] == draft_id
            ]

        # report
        async def create_data_report(self, **kwargs):
            rid = _next_id()
            row = DataReport(id=rid, created_at=datetime.now(UTC), **kwargs)
            state["reports"][rid] = row
            return row

        async def get_data_report(self, tenant_id, report_id):
            row = state["reports"].get(report_id)
            if not row or row.tenant_id != tenant_id:
                return None
            return row

    fake = FakeDB()
    # contract service is sync wrapper — patch module-level helpers used by routes
    monkeypatch.setattr(auth_mod, "db_service", fake)
    monkeypatch.setattr(email_mod, "db_service", fake)
    monkeypatch.setattr(report_mod, "db_service", fake)
    monkeypatch.setattr(report_mod, "execute_readonly", lambda engine, sql, tenant_id: [{"n": 1}])
    monkeypatch.setattr(auth_mod, "create_access_token", lambda *a, **k: _token())
    monkeypatch.setattr(auth_mod, "validate_password_strength", lambda p: None)

    # Contract routes use contract_service singleton
    class FakeContractService:
        def create_document(self, **kwargs):
            return fake.create_document(**kwargs)

        def get_document(self, tenant_id, document_id):
            return fake.get_document(tenant_id, document_id)

        def create_review(self, **kwargs):
            return fake.create_review(**kwargs)

        def get_review(self, tenant_id, review_id):
            return fake.get_review(tenant_id, review_id)

    monkeypatch.setattr(contract_mod, "contract_service", FakeContractService())
    monkeypatch.setattr(
        contract_mod,
        "extract_text_from_pdf",
        lambda data: (
            "Supplier accepts unlimited liability. Agreement shall auto-renew annually. "
            "Governing law of California."
        ),
    )

    async def fake_require(user, tenant, allowed):
        role = state["memberships"].get((user.id, tenant.id), "member")
        if role not in allowed:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="role")
        return role

    monkeypatch.setattr(email_mod, "require_tenant_role", fake_require)

    from slowapi import Limiter
    from slowapi.util import get_remote_address

    app = FastAPI()
    # SlowAPI requires app.state.limiter; disable so register/login are not rate-limited in tests
    limiter = Limiter(key_func=get_remote_address, enabled=False)
    app.state.limiter = limiter
    monkeypatch.setattr(auth_mod, "limiter", limiter)

    app.include_router(auth_mod.router, prefix="/auth")
    app.include_router(contract_mod.router, prefix="/agents/contract")
    app.include_router(email_mod.router, prefix="/agents/email")
    app.include_router(report_mod.router, prefix="/agents/report")

    # Active tenant/user for agent routes via dependency overrides; auth register uses FakeDB.
    active = {"user": None, "tenant": None}

    async def override_user():
        assert active["user"] is not None
        return active["user"]

    async def override_tenant():
        assert active["tenant"] is not None
        return active["tenant"]

    for mod in (contract_mod, email_mod, report_mod, auth_mod):
        if hasattr(mod, "get_current_user"):
            app.dependency_overrides[mod.get_current_user] = override_user
        if hasattr(mod, "get_current_tenant"):
            app.dependency_overrides[mod.get_current_tenant] = override_tenant

    client = TestClient(app)
    return client, state, active, fake


def test_e2e_happy_path_and_cross_tenant(e2e_client):
    client, state, active, fake = e2e_client

    # --- register (atomic user+tenant+membership) ---
    reg = client.post(
        "/auth/register",
        json={"email": "owner@example.com", "password": "Str0ng-Passw0rd!"},
    )
    assert reg.status_code == 200, reg.text
    body = reg.json()
    assert "token" in body
    user = next(u for u in state["users"].values() if u.email == "owner@example.com")
    tenant = next(iter(state["tenants"].values()))
    assert state["memberships"][(user.id, tenant.id)] == MembershipRole.OWNER.value
    active["user"] = user
    active["tenant"] = tenant

    # second tenant resource for cross-tenant checks
    other = Tenant(id=_unused_id(state), name="Other", slug="other", status="active", created_at=datetime.now(UTC))
    state["tenants"][other.id] = other

    # --- session list scoped ---
    import uuid

    sid = str(uuid.uuid4())
    foreign = str(uuid.uuid4())
    state["sessions"][sid] = ChatSession(id=sid, user_id=user.id, name="home", tenant_id=tenant.id)
    state["sessions"][foreign] = ChatSession(id=foreign, user_id=user.id, name="leak", tenant_id=other.id)
    listed = client.get("/auth/sessions")
    assert listed.status_code == 200
    ids = {row["session_id"] for row in listed.json()}
    assert sid in ids and foreign not in ids
    assert client.delete(f"/auth/session/{foreign}").status_code == 404

    # --- contract upload + review ---
    up = client.post(
        "/agents/contract/upload",
        files={"file": ("c.pdf", _pdf(), "application/pdf")},
    )
    assert up.status_code == 200, up.text
    doc_id = up.json()["id"]
    rev = client.post("/agents/contract/review", json={"document_id": doc_id})
    assert rev.status_code == 200, rev.text
    assert rev.json()["tenant_id"] == tenant.id
    # cross-tenant document fetch
    active["tenant"] = other
    assert client.get(f"/agents/contract/documents/{doc_id}").status_code in (403, 404)
    active["tenant"] = tenant

    # --- email: draft → submit → send blocked → approve → send ---
    draft = client.post(
        "/agents/email/drafts",
        json={"subject": "Hi", "body": "Hello", "to_address": "a@b.com"},
    )
    assert draft.status_code == 200, draft.text
    draft_id = draft.json()["id"]
    assert client.post(f"/agents/email/drafts/{draft_id}/send").status_code == 403
    assert client.post(f"/agents/email/drafts/{draft_id}/submit-for-approval").status_code == 200
    assert client.post(f"/agents/email/drafts/{draft_id}/send").status_code == 403
    assert client.post(f"/agents/email/drafts/{draft_id}/approve").status_code == 200
    sent = client.post(f"/agents/email/drafts/{draft_id}/send")
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == EmailStatus.SENT.value
    # cross-tenant draft
    active["tenant"] = other
    assert client.get(f"/agents/email/drafts/{draft_id}").status_code in (403, 404)
    active["tenant"] = tenant

    # --- report NL→SQL + validate ---
    nl = client.post("/agents/report/nl-query", json={"query": "how many sessions", "execute": True})
    assert nl.status_code == 200, nl.text
    assert f"tenant_id = {tenant.id}" in nl.json()["sql_preview"]
    bad = client.post(
        "/agents/report/validate-sql",
        json={"sql": f"SELECT * FROM session WHERE tenant_id = {other.id}"},
    )
    assert bad.status_code == 400
    with pytest.raises(SQLSafetyError):
        assert_tenant_scope("SELECT * FROM session WHERE tenant_id = 99", tenant.id)


def _unused_id(state) -> int:
    state["seq"] += 1
    return state["seq"]
