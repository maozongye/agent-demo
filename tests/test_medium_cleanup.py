"""Medium cleanup: sessions tenant scope, register txn, JWT blacklist, JOIN isolation."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth import get_current_tenant, get_current_user, router as auth_router
from app.core.config import Environment, validate_jwt_secret
from app.models.session import Session as ChatSession
from app.models.tenant import Tenant
from app.models.user import User
from app.services import database as database_mod
from app.services.sql_sandbox import SQLSafetyError, assert_tenant_scope


DOCKER_COMPOSE_JWT_DEFAULT = "supersecretkeythatshouldbechangedforproduction"


def test_docker_compose_jwt_default_is_blacklisted_outside_test():
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_jwt_secret(DOCKER_COMPOSE_JWT_DEFAULT, Environment.DEVELOPMENT)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_jwt_secret(DOCKER_COMPOSE_JWT_DEFAULT, Environment.PRODUCTION)
    # TEST still substitutes a fixed secret
    assert validate_jwt_secret(DOCKER_COMPOSE_JWT_DEFAULT, Environment.TEST) == (
        "test-only-jwt-secret-do-not-use-elsewhere"
    )


def test_register_user_with_default_tenant_is_single_commit():
    src = inspect.getsource(database_mod.DatabaseService.register_user_with_default_tenant)
    assert "session.commit()" in src
    assert src.count("session.commit()") == 1
    assert "Tenant(" in src and "TenantMembership(" in src and "User(" in src


def test_join_requires_tenant_filter_per_table():
    # only one side filtered
    with pytest.raises(SQLSafetyError, match="JOIN"):
        assert_tenant_scope(
            "SELECT s.id FROM session s JOIN message m ON s.id = m.session_id "
            "WHERE s.tenant_id = 10",
            10,
        )
    # both sides filtered
    assert_tenant_scope(
        "SELECT s.id FROM session s JOIN message m ON s.id = m.session_id "
        "WHERE s.tenant_id = 10 AND m.tenant_id = 10",
        10,
    )
    # bind form on both
    assert_tenant_scope(
        "SELECT s.id FROM session s JOIN message m ON s.id = m.session_id "
        "WHERE s.tenant_id = :tenant_id AND m.tenant_id = :tenant_id",
        10,
    )


def _build_auth_client(monkeypatch, *, sessions, user_id=1, tenant_id=10):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")

    user = User(id=user_id, email="u@example.com", hashed_password="x")
    tenant = Tenant(id=tenant_id, name="t", slug="t", status="active")

    class FakeDB:
        async def get_user_sessions(self, uid, tenant_id=None):
            assert uid == user_id
            if tenant_id is None:
                return sessions
            return [s for s in sessions if s.tenant_id == tenant_id]

        async def get_session(self, session_id, tenant_id=None):
            for s in sessions:
                if s.id != session_id:
                    continue
                if tenant_id is not None and s.tenant_id != tenant_id:
                    return None
                return s
            return None

        async def delete_session(self, session_id, tenant_id=None):
            s = await self.get_session(session_id, tenant_id=tenant_id)
            if s is None or s.user_id != user_id:
                return False
            sessions[:] = [x for x in sessions if x.id != session_id]
            return True

    fake = FakeDB()
    monkeypatch.setattr("app.api.v1.auth.db_service", fake)
    from app.schemas.auth import Token
    monkeypatch.setattr(
        "app.api.v1.auth.create_access_token",
        lambda *a, **k: Token(
            access_token="tok",
            token_type="bearer",
            expires_at=datetime.now(timezone.utc),
        ),
    )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: tenant
    return TestClient(app), fake


def test_list_and_delete_sessions_are_tenant_scoped(monkeypatch):
    sessions = [
        ChatSession(id="s-a", user_id=1, name="a", tenant_id=10),
        ChatSession(id="s-b", user_id=1, name="b", tenant_id=99),
    ]
    client, _ = _build_auth_client(monkeypatch, sessions=sessions)

    listed = client.get("/auth/sessions")
    assert listed.status_code == 200
    ids = {row["session_id"] for row in listed.json()}
    assert ids == {"s-a"}

    cross = client.delete("/auth/session/s-b")
    assert cross.status_code == 404
    assert any(s.id == "s-b" for s in sessions)

    ok = client.delete("/auth/session/s-a")
    assert ok.status_code == 200
    assert all(s.id != "s-a" for s in sessions)
