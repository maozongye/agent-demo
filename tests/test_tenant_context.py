"""Tests for tenant context: X-Tenant-Id without membership → 403.

Uses FastAPI dependency overrides so no live Postgres/JWT_SECRET boot is required
beyond a minimal app with the auth dependency under test.
"""

from datetime import UTC, datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient

from app.api.v1.auth import get_current_tenant, get_current_user
from app.models.tenant import Tenant
from app.models.user import User


@pytest.fixture
def fake_user() -> User:
    """Authenticated user fixture (not persisted)."""
    return User(id=1, email="u@example.com", hashed_password="x")


@pytest.fixture
def fake_tenant() -> Tenant:
    """Tenant the user belongs to."""
    return Tenant(
        id=10,
        name="Home",
        slug="home",
        status="active",
        created_at=datetime.now(UTC),
    )


def _build_app(monkeypatch, *, membership_for: Optional[int], jwt_tenant_id: int = 10):
    """Build a minimal FastAPI app that exercises get_current_tenant."""
    from app.api import v1 as v1pkg  # noqa: F401
    import app.api.v1.auth as auth_mod

    membership_mock = AsyncMock(
        side_effect=lambda user_id, tenant_id: (
            MagicMock(user_id=user_id, tenant_id=tenant_id, role="member")
            if tenant_id == membership_for
            else None
        )
    )
    get_tenant_mock = AsyncMock(
        side_effect=lambda tid: (
            Tenant(id=tid, name="T", slug=f"t-{tid}", status="active", created_at=datetime.now(UTC))
            if tid == membership_for or tid == jwt_tenant_id
            else None
        )
    )
    # When membership_for is set, get_tenant should return that tenant too
    async def _get_tenant(tid: int):
        return Tenant(id=tid, name="T", slug=f"t-{tid}", status="active", created_at=datetime.now(UTC))

    get_tenant_mock.side_effect = _get_tenant

    monkeypatch.setattr(auth_mod.db_service, "get_membership", membership_mock)
    monkeypatch.setattr(auth_mod.db_service, "get_tenant", get_tenant_mock)
    monkeypatch.setattr(auth_mod.db_service, "get_default_tenant_id_for_user", AsyncMock(return_value=jwt_tenant_id))
    monkeypatch.setattr(auth_mod, "get_tenant_id_from_token", lambda token: jwt_tenant_id)
    monkeypatch.setattr(auth_mod, "sanitize_string", lambda s: s)

    app = FastAPI()

    async def override_user():
        return User(id=1, email="u@example.com", hashed_password="x")

    # We still need credentials for the signature; override get_current_tenant's deps carefully.
    # Simpler: mount a route that calls the same logic via Depends after overriding get_current_user
    # and faking HTTPBearer via dependency override on get_current_tenant internals.

    from fastapi.security import HTTPAuthorizationCredentials

    async def override_tenant(
        user: User = Depends(override_user),
        x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    ) -> Tenant:
        # Replicate get_current_tenant membership check for header override
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake.jwt.token")
        return await get_current_tenant(
            credentials=credentials,
            user=user,
            x_tenant_id=x_tenant_id,
        )

    @app.get("/probe")
    async def probe(tenant: Tenant = Depends(override_tenant)):
        return {"tenant_id": tenant.id}

    return app, membership_mock


def test_x_tenant_id_without_membership_returns_403(monkeypatch):
    """X-Tenant-Id for a tenant the user does not belong to → 403."""
    # User is member of 10 only; requesting 999 must 403
    app, membership_mock = _build_app(monkeypatch, membership_for=10, jwt_tenant_id=10)
    client = TestClient(app)

    resp = client.get("/probe", headers={"X-Tenant-Id": "999"})
    assert resp.status_code == 403
    assert "member" in resp.json()["detail"].lower()
    membership_mock.assert_awaited()


def test_x_tenant_id_with_membership_ok(monkeypatch):
    """X-Tenant-Id for a tenant the user belongs to succeeds."""
    app, _ = _build_app(monkeypatch, membership_for=42, jwt_tenant_id=10)
    client = TestClient(app)

    # Override membership so 42 is allowed; jwt still 10
    import app.api.v1.auth as auth_mod

    async def membership(user_id, tenant_id):
        if tenant_id in (10, 42):
            return MagicMock(user_id=user_id, tenant_id=tenant_id, role="member")
        return None

    monkeypatch.setattr(auth_mod.db_service, "get_membership", AsyncMock(side_effect=membership))

    resp = client.get("/probe", headers={"X-Tenant-Id": "42"})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == 42


def test_jwt_tenant_without_header_ok(monkeypatch):
    """Without override header, JWT tenant is used when membership exists."""
    app, _ = _build_app(monkeypatch, membership_for=10, jwt_tenant_id=10)
    client = TestClient(app)
    resp = client.get("/probe")
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == 10
