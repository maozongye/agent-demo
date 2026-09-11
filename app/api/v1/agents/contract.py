"""Contract review agent: upload, parse, risk extract, report."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.v1.auth import get_current_tenant, get_current_user
from app.core.config import settings
from app.core.langgraph.contract_review import run_contract_review
from app.core.logging import logger
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.agents import (
    ContractDocumentResponse,
    ContractReviewRequest,
    ContractReviewResponse,
    RiskFinding,
)
from app.services.contract_service import contract_service
from app.services.pdf_extract import extract_text_from_pdf
from app.services.storage import read_tenant_file, save_tenant_upload

router = APIRouter()

_PDF_TYPES = {"application/pdf", "application/x-pdf", "binary/octet-stream"}


def _to_findings(raw: list) -> list[RiskFinding]:
    return [RiskFinding(**{k: f.get(k) for k in ("severity", "clause", "summary", "excerpt")}) for f in raw]


@router.post("/upload", response_model=ContractDocumentResponse)
async def upload_contract(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> ContractDocumentResponse:
    """Upload a PDF into tenant-isolated storage."""
    filename = file.filename or "contract.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")
    max_bytes = settings.MAX_UPLOAD_BYTES
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds max size of {max_bytes} bytes",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    content_type = file.content_type or "application/pdf"
    if content_type not in _PDF_TYPES and not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")
    try:
        file_ref = save_tenant_upload(tenant.id, filename, data)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc = contract_service.create_document(
        tenant_id=tenant.id,
        uploaded_by=user.id,
        filename=filename,
        file_ref=file_ref,
        content_type="application/pdf",
    )
    logger.info("contract_uploaded", tenant_id=tenant.id, document_id=doc.id)
    return ContractDocumentResponse(
        id=doc.id,
        tenant_id=doc.tenant_id,
        filename=doc.filename,
        file_ref=doc.file_ref,
        content_type=doc.content_type,
        created_at=doc.created_at,
    )


@router.post("/review", response_model=ContractReviewResponse)
async def review_contract(
    payload: ContractReviewRequest,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> ContractReviewResponse:
    """Run PDF/text contract review and persist the report."""
    text = (payload.text or "").strip()
    document_id: Optional[int] = payload.document_id
    if document_id is not None:
        doc = contract_service.get_document(tenant.id, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        try:
            raw = read_tenant_file(tenant.id, doc.file_ref)
            text = extract_text_from_pdf(raw)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Stored file missing") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif payload.file_ref:
        try:
            raw = read_tenant_file(tenant.id, payload.file_ref)
            text = extract_text_from_pdf(raw)
        except (FileNotFoundError, PermissionError, ValueError) as exc:
            code = 404 if isinstance(exc, FileNotFoundError) else 400
            if isinstance(exc, PermissionError):
                code = 403
            raise HTTPException(status_code=code, detail=str(exc)) from exc
    if not text:
        raise HTTPException(status_code=400, detail="Provide document_id or text")
    try:
        findings_raw, report = run_contract_review(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    review = contract_service.create_review(
        tenant_id=tenant.id,
        document_id=document_id,
        findings=findings_raw,
        report_text=report,
    )
    return ContractReviewResponse(
        id=review.id,
        tenant_id=tenant.id,
        document_id=document_id,
        status=review.status,
        findings=_to_findings(findings_raw),
        report=report,
    )


@router.get("/documents/{document_id}", response_model=ContractDocumentResponse)
async def get_document(
    document_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> ContractDocumentResponse:
    doc = contract_service.get_document(tenant.id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return ContractDocumentResponse(
        id=doc.id,
        tenant_id=doc.tenant_id,
        filename=doc.filename,
        file_ref=doc.file_ref,
        content_type=doc.content_type,
        created_at=doc.created_at,
    )


@router.get("/reviews/{review_id}", response_model=ContractReviewResponse)
async def get_review(
    review_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> ContractReviewResponse:
    review = contract_service.get_review(tenant.id, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    findings_raw = json.loads(review.findings_json or "[]")
    return ContractReviewResponse(
        id=review.id,
        tenant_id=review.tenant_id,
        document_id=review.document_id,
        status=review.status,
        findings=_to_findings(findings_raw),
        report=review.report_text,
    )
