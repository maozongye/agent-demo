"""Phase 2 contract review tests (no live Postgres required for core path)."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.config import settings
from app.core.langgraph.contract_review import run_contract_review
from app.models.contract import ContractDocument, ContractReview
from app.models.tenant import Tenant
from app.models.user import User
from app.services.pdf_extract import extract_text_from_pdf
from app.services.storage import read_tenant_file, resolve_tenant_file, save_tenant_upload


def _tenant(tid: int = 10) -> Tenant:
    return Tenant(id=tid, name="T", slug=f"t-{tid}", status="active", created_at=datetime.now(UTC))


def _user(uid: int = 1) -> User:
    return User(id=uid, email="u@example.com", hashed_password="x")


def _pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    # pypdf cannot easily embed text on blank page without reportlab;
    # for extract tests we also cover ValueError on empty; for risk rules we use text path.
    buf = io.BytesIO()
    writer.write(buf)
    raw = buf.getvalue()
    # Inject text stream crudely so extract_text may or may not see it — prefer text API for findings.
    return raw


def test_run_contract_review_finds_risks():
    text = (
        "The Supplier accepts unlimited liability for all damages. "
        "This agreement shall auto-renew for successive one-year terms. "
        "Governing law shall be the laws of the State of California."
    )
    findings, report = run_contract_review(text)
    assert findings
    severities = {f["clause"] for f in findings}
    assert any("liability" in c for c in severities)
    assert any("auto-renewal" in c for c in severities)
    assert "Contract Review Report" in report


def test_run_contract_review_empty_raises():
    with pytest.raises(ValueError):
        run_contract_review("   ")


def test_extract_invalid_pdf_raises():
    with pytest.raises(ValueError):
        extract_text_from_pdf(b"not-a-pdf")


def test_extract_empty_pdf_raises():
    with pytest.raises(ValueError):
        extract_text_from_pdf(b"")


def test_tenant_storage_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    ref = save_tenant_upload(7, "a b.pdf", b"%PDF-1.4 demo")
    assert ref.startswith("7/")
    data = read_tenant_file(7, ref)
    assert data.startswith(b"%PDF")
    with pytest.raises(PermissionError):
        resolve_tenant_file(8, ref)


def test_upload_and_review_http(monkeypatch, tmp_path):
    import app.api.v1.agents.contract as contract_mod
    import app.api.v1.auth as auth_mod

    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)

    store = {"docs": {}, "reviews": {}, "seq": 1}

    class FakeContractService:
        def create_document(self, **kwargs):
            did = store["seq"]
            store["seq"] += 1
            doc = ContractDocument(id=did, created_at=datetime.now(UTC), **kwargs)
            store["docs"][did] = doc
            return doc

        def get_document(self, tenant_id, document_id):
            doc = store["docs"].get(document_id)
            if not doc or doc.tenant_id != tenant_id:
                return None
            return doc

        def create_review(self, **kwargs):
            rid = store["seq"]
            store["seq"] += 1
            import json

            review = ContractReview(
                id=rid,
                tenant_id=kwargs["tenant_id"],
                document_id=kwargs.get("document_id"),
                status=kwargs.get("status", "completed"),
                report_text=kwargs.get("report_text", ""),
                findings_json=json.dumps(kwargs.get("findings") or []),
                created_at=datetime.now(UTC),
            )
            store["reviews"][rid] = review
            return review

        def get_review(self, tenant_id, review_id):
            rev = store["reviews"].get(review_id)
            if not rev or rev.tenant_id != tenant_id:
                return None
            return rev

    monkeypatch.setattr(contract_mod, "contract_service", FakeContractService())

    app = FastAPI()
    app.include_router(contract_mod.router, prefix="/agents/contract")

    async def user():
        return _user()

    async def tenant():
        return _tenant(10)

    app.dependency_overrides[auth_mod.get_current_user] = user
    app.dependency_overrides[auth_mod.get_current_tenant] = tenant
    # contract module imports deps from auth — override those symbols too
    app.dependency_overrides[contract_mod.get_current_user] = user
    app.dependency_overrides[contract_mod.get_current_tenant] = tenant

    client = TestClient(app)

    # Text review happy path
    resp = client.post(
        "/agents/contract/review",
        json={"text": "Party accepts unlimited liability and auto-renewal applies."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == 10
    assert body["findings"]
    assert body["id"] is not None

    # Cross-tenant review fetch denied
    async def other_tenant():
        return _tenant(99)

    app.dependency_overrides[contract_mod.get_current_tenant] = other_tenant
    bad = client.get(f"/agents/contract/reviews/{body['id']}")
    assert bad.status_code == 404

    # Restore tenant and upload PDF
    app.dependency_overrides[contract_mod.get_current_tenant] = tenant
    files = {"file": ("c.pdf", b"%PDF-1.4 fake but named pdf", "application/pdf")}
    up = client.post("/agents/contract/upload", files=files)
    assert up.status_code == 200, up.text
    doc_id = up.json()["id"]

    # Bad PDF on review by document_id → 400
    rev_bad = client.post("/agents/contract/review", json={"document_id": doc_id})
    assert rev_bad.status_code == 400

    # Missing document
    missing = client.post("/agents/contract/review", json={"document_id": 99999})
    assert missing.status_code == 404

    # Empty review payload
    empty = client.post("/agents/contract/review", json={})
    assert empty.status_code == 400


def test_storage_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    save_tenant_upload(1, "ok.pdf", b"%PDF-1.4 x")
    with pytest.raises(PermissionError):
        resolve_tenant_file(1, "../1/secret")
    with pytest.raises(PermissionError):
        resolve_tenant_file(1, "/etc/passwd")
    with pytest.raises(PermissionError):
        resolve_tenant_file(1, "2/other.pdf")


def test_upload_rejects_oversized_file(monkeypatch, tmp_path):
    import app.api.v1.agents.contract as contract_mod
    import app.api.v1.auth as auth_mod
    from datetime import UTC, datetime
    from app.models.contract import ContractDocument

    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 16)

    class FakeContractService:
        def create_document(self, **kwargs):
            return ContractDocument(id=1, created_at=datetime.now(UTC), **kwargs)

    monkeypatch.setattr(contract_mod, "contract_service", FakeContractService())
    app = FastAPI()
    app.include_router(contract_mod.router, prefix="/agents/contract")

    async def user():
        return _user()

    async def tenant():
        return _tenant(10)

    app.dependency_overrides[contract_mod.get_current_user] = user
    app.dependency_overrides[contract_mod.get_current_tenant] = tenant
    client = TestClient(app)
    files = {"file": ("big.pdf", b"x" * 64, "application/pdf")}
    resp = client.post("/agents/contract/upload", files=files)
    assert resp.status_code == 413
