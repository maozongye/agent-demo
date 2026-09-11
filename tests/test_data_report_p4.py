"""Phase 4 data report agent tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.langgraph.data_report import nl_to_sql, run_report_pipeline
from app.models.data_report import DataReport
from app.models.tenant import Tenant
from app.models.user import User
from app.services.sql_sandbox import SQLSafetyError, assert_readonly_sql, assert_tenant_scope


def _tenant(tid: int = 10) -> Tenant:
    return Tenant(id=tid, name="T", slug=f"t-{tid}", status="active", created_at=datetime.now(UTC))


def _user(uid: int = 1) -> User:
    return User(id=uid, email="u@example.com", hashed_password="x")


def test_nl_to_sql_includes_tenant():
    sql = nl_to_sql("how many sessions", 42)
    assert "tenant_id = 42" in sql
    assert_tenant_scope(sql, 42)


def test_write_sql_rejected():
    with pytest.raises(SQLSafetyError):
        assert_readonly_sql("DELETE FROM session WHERE tenant_id = 1")
    with pytest.raises(SQLSafetyError):
        assert_readonly_sql("DROP TABLE session")
    with pytest.raises(SQLSafetyError):
        nl_to_sql("please delete all sessions", 1)


def test_cross_tenant_sql_rejected():
    with pytest.raises(SQLSafetyError):
        assert_tenant_scope("SELECT * FROM session WHERE tenant_id = 99", 10)
    with pytest.raises(SQLSafetyError):
        assert_tenant_scope("SELECT * FROM session", 10)


def test_pipeline_builds_report():
    result = run_report_pipeline("count sessions", 7, rows=[{"n": 3}])
    assert result["error"] == ""
    assert "tenant_id = 7" in result["sql"]
    assert "Data Report" in result["analysis"]
    assert "SELECT" in result["sql"].upper()


def test_nl_query_api_happy_and_persist(monkeypatch):
    import app.api.v1.agents.report as report_mod

    store = {}

    class FakeDB:
        engine = object()

        async def create_data_report(self, **kwargs):
            rid = 1
            row = DataReport(id=rid, created_at=datetime.now(UTC), **kwargs)
            store[rid] = row
            return row

        async def get_data_report(self, tenant_id, report_id):
            row = store.get(report_id)
            if not row or row.tenant_id != tenant_id:
                return None
            return row

    monkeypatch.setattr(report_mod, "db_service", FakeDB())
    monkeypatch.setattr(report_mod, "execute_readonly", lambda engine, sql, tenant_id: [{"n": 2}])

    app = FastAPI()
    app.include_router(report_mod.router, prefix="/agents/report")

    async def user():
        return _user()

    async def tenant():
        return _tenant(10)

    app.dependency_overrides[report_mod.get_current_user] = user
    app.dependency_overrides[report_mod.get_current_tenant] = tenant
    client = TestClient(app)

    resp = client.post("/agents/report/nl-query", json={"query": "how many sessions", "execute": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == 10
    assert "tenant_id = 10" in body["sql_preview"]
    assert body["id"] == 1
    assert body["row_count"] == 1
    assert "SELECT" in body["sql_preview"].upper()

    got = client.get("/agents/report/reports/1")
    assert got.status_code == 200
    assert got.json()["sql_text"] == body["sql_preview"]


def test_validate_sql_rejects_writes_and_cross_tenant(monkeypatch):
    import app.api.v1.agents.report as report_mod

    app = FastAPI()
    app.include_router(report_mod.router, prefix="/agents/report")

    async def user():
        return _user()

    async def tenant():
        return _tenant(10)

    app.dependency_overrides[report_mod.get_current_user] = user
    app.dependency_overrides[report_mod.get_current_tenant] = tenant
    client = TestClient(app)

    bad = client.post("/agents/report/validate-sql", json={"sql": "DELETE FROM session WHERE tenant_id = 10"})
    assert bad.status_code == 400
    cross = client.post("/agents/report/validate-sql", json={"sql": "SELECT 1 FROM session WHERE tenant_id = 99"})
    assert cross.status_code == 400
    ok = client.post(
        "/agents/report/validate-sql",
        json={"sql": "SELECT COUNT(*) FROM session WHERE tenant_id = 10"},
    )
    assert ok.status_code == 200


def test_cross_tenant_get_report_404(monkeypatch):
    import app.api.v1.agents.report as report_mod

    row = DataReport(
        id=5,
        tenant_id=99,
        created_by=1,
        query_text="q",
        sql_text="SELECT 1",
        rows_json="[]",
        report_text="r",
        status="completed",
        created_at=datetime.now(UTC),
    )

    class FakeDB:
        async def get_data_report(self, tenant_id, report_id):
            if row.tenant_id != tenant_id:
                return None
            return row

    monkeypatch.setattr(report_mod, "db_service", FakeDB())
    app = FastAPI()
    app.include_router(report_mod.router, prefix="/agents/report")

    async def user():
        return _user()

    async def tenant():
        return _tenant(10)

    app.dependency_overrides[report_mod.get_current_user] = user
    app.dependency_overrides[report_mod.get_current_tenant] = tenant
    client = TestClient(app)
    assert client.get("/agents/report/reports/5").status_code == 404
