"""Phase 1 review-fix tests (no live Postgres required).

Covers:
- Open tenant join disabled → 403
- Email approve/send as member → 403
- Cross-tenant draft access denied → 404
- Login must not html-escape passwords (sanitize regression)
- JWT create_access_token refuses empty secret
"""

from datetime import UTC, datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.models.email_draft import EmailDraft, EmailStatus
from app.models.tenant import MembershipRole, Tenant
from app.models.user import User
from app.services.email_draft import create_draft_in_memory


def _tenant(tid: int = 10) -> Tenant:
    return Tenant(
        id=tid,
        name="Home",
        slug=f"home-{tid}",
        status="active",
        created_at=datetime.now(UTC),
    )


def _user(uid: int = 1) -> User:
    return User(id=uid, email="u@example.com", hashed_password="x")


# ---------------------------------------------------------------------------
# 1. Join endpoint always 403
# ---------------------------------------------------------------------------


def test_open_tenant_join_returns_403(monkeypatch):
    """POST /tenants/join must reject with 403 in Phase 1."""
    import app.api.v1.auth as auth_mod

    app = FastAPI()
    app.include_router(auth_mod.router, prefix="/auth")

    async def override_user():
        return _user()

    app.dependency_overrides[auth_mod.get_current_user] = override_user
    # Avoid rate limiter / JWT side effects if any
    monkeypatch.setattr(auth_mod, "limiter", MagicMock())
    # Rate limiter decorator may still wrap; TestClient should be fine without Redis

    client = TestClient(app)
    resp = client.post("/auth/tenants/join", json={"tenant_id": 99})
    assert resp.status_code == 403
    detail = resp.json()["detail"].lower()
    assert "disabled" in detail or "invitation" in detail or "admin" in detail


def test_membership_join_schema_has_no_free_role():
    """Public join body must not expose a client-selectable owner/admin role."""
    from app.schemas.tenant import MembershipJoin

    fields = MembershipJoin.model_fields
    assert "tenant_id" in fields
    assert "role" not in fields


# ---------------------------------------------------------------------------
# 2. Email approve/send role gate (member → 403)
# ---------------------------------------------------------------------------


def _build_email_app(monkeypatch, *, role: str, draft: EmailDraft, tenant_id: int = 10):
    """Minimal email router app with membership role + draft DB mocks."""
    import app.api.v1.agents.email as email_mod
    import app.api.v1.auth as auth_mod

    membership = MagicMock(user_id=1, tenant_id=tenant_id, role=role)
    monkeypatch.setattr(
        auth_mod.db_service,
        "get_membership",
        AsyncMock(return_value=membership),
    )
    monkeypatch.setattr(
        email_mod.db_service,
        "get_email_draft",
        AsyncMock(
            side_effect=lambda draft_id, tid: draft if draft.id == draft_id and draft.tenant_id == tid else None
        ),
    )
    monkeypatch.setattr(email_mod.db_service, "save_email_draft", AsyncMock(side_effect=lambda d, tenant_id=None: d))
    monkeypatch.setattr(email_mod.db_service, "add_email_audit", AsyncMock(return_value=None))

    app = FastAPI()
    app.include_router(email_mod.router, prefix="/agents/email")

    async def override_user():
        return _user()

    async def override_tenant():
        return _tenant(tenant_id)

    app.dependency_overrides[email_mod.get_current_user] = override_user
    app.dependency_overrides[email_mod.get_current_tenant] = override_tenant
    return app


def test_email_approve_as_member_returns_403(monkeypatch):
    """Members cannot approve drafts."""
    draft = create_draft_in_memory(10, "s", "b", "a@example.com", draft_id=1)
    from app.services.email_draft import apply_transition

    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    app = _build_email_app(monkeypatch, role=MembershipRole.MEMBER.value, draft=draft)
    client = TestClient(app)
    resp = client.post("/agents/email/drafts/1/approve")
    assert resp.status_code == 403


def test_email_send_as_member_returns_403(monkeypatch):
    """Members cannot send drafts even if approved."""
    draft = create_draft_in_memory(10, "s", "b", "a@example.com", draft_id=2)
    from app.services.email_draft import apply_transition

    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    apply_transition(draft, EmailStatus.APPROVED)
    app = _build_email_app(monkeypatch, role=MembershipRole.MEMBER.value, draft=draft)
    client = TestClient(app)
    resp = client.post("/agents/email/drafts/2/send")
    assert resp.status_code == 403


def test_email_approve_as_admin_ok(monkeypatch):
    """Admins may approve pending drafts."""
    draft = create_draft_in_memory(10, "s", "b", "a@example.com", draft_id=3)
    from app.services.email_draft import apply_transition

    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    app = _build_email_app(monkeypatch, role=MembershipRole.ADMIN.value, draft=draft)
    client = TestClient(app)
    resp = client.post("/agents/email/drafts/3/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == EmailStatus.APPROVED.value


def test_email_reject_as_member_returns_403(monkeypatch):
    """Members cannot reject drafts."""
    draft = create_draft_in_memory(10, "s", "b", "a@example.com", draft_id=4)
    from app.services.email_draft import apply_transition

    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    app = _build_email_app(monkeypatch, role=MembershipRole.MEMBER.value, draft=draft)
    client = TestClient(app)
    resp = client.post("/agents/email/drafts/4/reject")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. Cross-tenant draft access denied
# ---------------------------------------------------------------------------


def test_cross_tenant_draft_access_denied(monkeypatch):
    """Getting/acting on another tenant's draft must 404 (tenant-scoped lookup)."""
    # Draft belongs to tenant 99; caller is on tenant 10
    other_draft = create_draft_in_memory(99, "secret", "body", "x@example.com", draft_id=50)
    app = _build_email_app(
        monkeypatch,
        role=MembershipRole.OWNER.value,
        draft=other_draft,
        tenant_id=10,
    )
    client = TestClient(app)
    # classify uses get_email_draft(tenant-scoped) — should 404
    resp = client.post("/agents/email/drafts/50/classify")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Password must not be html-escaped on login path
# ---------------------------------------------------------------------------


def test_login_does_not_sanitize_password_with_special_chars(monkeypatch):
    """Passwords containing & < > \" must be verified raw (not html.escaped)."""
    import app.api.v1.auth as auth_mod

    raw_password = 'p@ss&<>"word'
    hashed = User.hash_password(raw_password)
    user = User(id=7, email="special@example.com", hashed_password=hashed)

    monkeypatch.setattr(auth_mod.db_service, "get_user_by_email", AsyncMock(return_value=user))
    monkeypatch.setattr(auth_mod.db_service, "get_default_tenant_id_for_user", AsyncMock(return_value=1))
    monkeypatch.setattr(
        auth_mod,
        "create_access_token",
        lambda *a, **k: MagicMock(access_token="tok", expires_at=datetime.now(UTC)),
    )
    # Bypass rate limiter by calling the endpoint function via a thin app without limiter issues
    app = FastAPI()

    # Re-register login without slowapi if needed — use the real router
    # SlowAPI may require app.state.limiter; attach a no-op limiter
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, enabled=False)
    app.state.limiter = limiter
    monkeypatch.setattr(auth_mod, "limiter", limiter)

    app.include_router(auth_mod.router, prefix="/auth")
    client = TestClient(app)

    resp = client.post(
        "/auth/login",
        data={
            "username": "special@example.com",
            "password": raw_password,
            "grant_type": "password",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"] == "tok"


# ---------------------------------------------------------------------------
# 5. JWT empty secret guard
# ---------------------------------------------------------------------------


def test_create_access_token_refuses_empty_secret(monkeypatch):
    """create_access_token must raise if JWT_SECRET_KEY is empty."""
    from app.utils import auth as auth_utils

    monkeypatch.setattr(auth_utils.settings, "JWT_SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        auth_utils.create_access_token("1", tenant_id=1)


def test_validate_jwt_secret_fails_outside_test():
    """Non-test environments must refuse weak/empty JWT secrets."""
    from app.core.config import Environment, validate_jwt_secret

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_jwt_secret("", Environment.PRODUCTION)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_jwt_secret("your-jwt-secret-key", Environment.DEVELOPMENT)
    assert validate_jwt_secret("", Environment.TEST) == "test-only-jwt-secret-do-not-use-elsewhere"
    assert validate_jwt_secret("strong-enough-secret-value", Environment.PRODUCTION) == "strong-enough-secret-value"
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_jwt_secret(
            "supersecretkeythatshouldbechangedforproduction", Environment.DEVELOPMENT
        )
