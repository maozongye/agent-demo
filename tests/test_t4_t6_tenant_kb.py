"""T4 data-layer tenant filters + T6 knowledge base isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import anyio
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.models.email_draft import EmailDraft, EmailStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_document import KnowledgeDocument
from app.models.session import Session as ChatSession
from app.models.tenant import Tenant
from app.models.user import User
from app.services.database import DatabaseService


def _tenant(tid: int = 10) -> Tenant:
    return Tenant(id=tid, name="T", slug=f"t-{tid}", status="active", created_at=datetime.now(UTC))


def _user(uid: int = 1) -> User:
    return User(id=uid, email="u@example.com", hashed_password="x")


def test_get_messages_requires_tenant_and_blocks_cross_tenant(monkeypatch):
    db = DatabaseService.__new__(DatabaseService)
    db.engine = object()

    async def fake_get_session(session_id, tenant_id=None):
        if session_id == "s1" and tenant_id == 10:
            return ChatSession(id="s1", user_id=1, name="ok", tenant_id=10)
        return None

    monkeypatch.setattr(db, "get_session", fake_get_session)

    async def _cross():
        return await db.get_messages_by_session_id("s1", tenant_id=99)

    assert anyio.run(_cross) == []

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.exec.return_value.all.return_value = []
    monkeypatch.setattr("app.services.database.Session", lambda *a, **k: mock_session)

    async def _ok():
        return await db.get_messages_by_session_id("s1", tenant_id=10)

    assert anyio.run(_ok) == []


def test_save_messages_cross_tenant_404(monkeypatch):
    db = DatabaseService.__new__(DatabaseService)
    db.engine = object()

    async def fake_get_session(session_id, tenant_id=None):
        return None

    monkeypatch.setattr(db, "get_session", fake_get_session)

    async def _run():
        with pytest.raises(HTTPException) as ei:
            await db.save_messages([], "s1", tenant_id=10)
        assert ei.value.status_code == 404

    anyio.run(_run)


def test_save_email_draft_rejects_wrong_tenant():
    db = DatabaseService.__new__(DatabaseService)
    db.engine = object()
    draft = EmailDraft(
        id=1,
        tenant_id=10,
        status=EmailStatus.DRAFT.value,
        subject="x",
        body="y",
        to_address="a@b.com",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def _run():
        with pytest.raises(HTTPException) as ei:
            await db.save_email_draft(draft, tenant_id=99)
        assert ei.value.status_code == 404

    anyio.run(_run)


def test_knowledge_api_tenant_isolation(monkeypatch, tmp_path):
    import app.api.v1.agents.knowledge as kb_mod
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)

    store = {"kbs": {}, "docs": {}, "seq": 1}

    class FakeDB:
        async def create_knowledge_base(self, *, tenant_id, name):
            kid = store["seq"]
            store["seq"] += 1
            kb = KnowledgeBase(id=kid, tenant_id=tenant_id, name=name, created_at=datetime.now(UTC))
            store["kbs"][kid] = kb
            return kb

        async def get_knowledge_base(self, tenant_id, kb_id):
            kb = store["kbs"].get(kb_id)
            if not kb or kb.tenant_id != tenant_id:
                return None
            return kb

        async def list_knowledge_bases(self, tenant_id):
            return [k for k in store["kbs"].values() if k.tenant_id == tenant_id]

        async def create_knowledge_document(self, **kwargs):
            kb = await self.get_knowledge_base(kwargs["tenant_id"], kwargs["knowledge_base_id"])
            if kb is None:
                raise HTTPException(status_code=404, detail="Knowledge base not found")
            did = store["seq"]
            store["seq"] += 1
            doc = KnowledgeDocument(id=did, created_at=datetime.now(UTC), **kwargs)
            store["docs"][did] = doc
            return doc

        async def get_knowledge_document(self, tenant_id, document_id):
            d = store["docs"].get(document_id)
            if not d or d.tenant_id != tenant_id:
                return None
            return d

        async def list_knowledge_documents(self, tenant_id, knowledge_base_id):
            return [
                d
                for d in store["docs"].values()
                if d.tenant_id == tenant_id and d.knowledge_base_id == knowledge_base_id
            ]

        async def search_knowledge_documents(self, tenant_id, query, *, knowledge_base_id=None):
            needle = query.lower()
            out = []
            for d in store["docs"].values():
                if d.tenant_id != tenant_id:
                    continue
                if knowledge_base_id is not None and d.knowledge_base_id != knowledge_base_id:
                    continue
                if needle in d.title.lower() or needle in d.content.lower():
                    out.append(d)
            return out

    monkeypatch.setattr(kb_mod, "db_service", FakeDB())

    app = FastAPI()
    app.include_router(kb_mod.router, prefix="/agents/knowledge")

    active = {"tenant": _tenant(10)}

    async def user():
        return _user()

    async def tenant():
        return active["tenant"]

    app.dependency_overrides[kb_mod.get_current_user] = user
    app.dependency_overrides[kb_mod.get_current_tenant] = tenant
    client = TestClient(app)

    created = client.post("/agents/knowledge/knowledge-bases", json={"name": "Docs"})
    assert created.status_code == 200, created.text
    kb_id = created.json()["id"]
    assert created.json()["tenant_id"] == 10

    doc = client.post(
        f"/agents/knowledge/knowledge-bases/{kb_id}/documents",
        json={"title": "Alpha policy", "content": "refund window is 30 days"},
    )
    assert doc.status_code == 200, doc.text
    doc_id = doc.json()["id"]

    hit = client.get("/agents/knowledge/search", params={"q": "refund"})
    assert hit.status_code == 200
    assert any(r["id"] == doc_id for r in hit.json())

    active["tenant"] = _tenant(99)
    assert client.get(f"/agents/knowledge/knowledge-bases/{kb_id}").status_code == 404
    assert client.get(f"/agents/knowledge/documents/{doc_id}").status_code == 404
    assert client.get("/agents/knowledge/search", params={"q": "refund"}).json() == []
    assert (
        client.post(
            f"/agents/knowledge/knowledge-bases/{kb_id}/documents",
            json={"title": "x", "content": "y"},
        ).status_code
        == 404
    )
