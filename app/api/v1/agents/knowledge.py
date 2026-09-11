"""Tenant-scoped knowledge base upload and search APIs."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.api.v1.auth import get_current_tenant, get_current_user
from app.core.config import settings
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.agents import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeDocumentCreate,
    KnowledgeDocumentResponse,
)
from app.services.database import database_service as db_service
from app.services.storage import save_tenant_kb_upload

router = APIRouter()


def _kb_resp(kb) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=kb.id, tenant_id=kb.tenant_id, name=kb.name, created_at=kb.created_at
    )


def _doc_resp(doc) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=doc.id,
        tenant_id=doc.tenant_id,
        knowledge_base_id=doc.knowledge_base_id,
        title=doc.title,
        content=doc.content,
        file_ref=doc.file_ref or "",
        created_at=doc.created_at,
    )


@router.post("/knowledge-bases", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create a knowledge base namespace for the active tenant."""
    _ = user
    kb = await db_service.create_knowledge_base(tenant_id=tenant.id, name=payload.name.strip())
    return _kb_resp(kb)


@router.get("/knowledge-bases", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases(
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    _ = user
    rows = await db_service.list_knowledge_bases(tenant.id)
    return [_kb_resp(k) for k in rows]


@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    _ = user
    kb = await db_service.get_knowledge_base(tenant.id, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return _kb_resp(kb)


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=KnowledgeDocumentResponse,
)
async def create_document_json(
    kb_id: int,
    payload: KnowledgeDocumentCreate,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Add a text document to a tenant KB (JSON body)."""
    _ = user
    try:
        doc = await db_service.create_knowledge_document(
            tenant_id=tenant.id,
            knowledge_base_id=kb_id,
            title=payload.title.strip(),
            content=payload.content or "",
        )
    except HTTPException:
        raise
    return _doc_resp(doc)


@router.post(
    "/knowledge-bases/{kb_id}/upload",
    response_model=KnowledgeDocumentResponse,
)
async def upload_document_file(
    kb_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Upload a file into ``UPLOAD_DIR/{tenant_id}/kb/{kb_id}/`` (chunked, size-capped)."""
    _ = user
    kb = await db_service.get_knowledge_base(tenant.id, kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

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

    try:
        file_ref = save_tenant_kb_upload(tenant.id, kb_id, file.filename or "upload.bin", data)
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    content = ""
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = ""
    doc = await db_service.create_knowledge_document(
        tenant_id=tenant.id,
        knowledge_base_id=kb_id,
        title=(title or file.filename or "upload").strip(),
        content=content,
        file_ref=file_ref,
    )
    return _doc_resp(doc)


@router.get(
    "/knowledge-bases/{kb_id}/documents",
    response_model=List[KnowledgeDocumentResponse],
)
async def list_documents(
    kb_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    _ = user
    rows = await db_service.list_knowledge_documents(tenant.id, kb_id)
    return [_doc_resp(d) for d in rows]


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentResponse)
async def get_document(
    document_id: int,
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    _ = user
    doc = await db_service.get_knowledge_document(tenant.id, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_resp(doc)


@router.get("/search", response_model=List[KnowledgeDocumentResponse])
async def search_documents(
    q: str = Query(..., min_length=1),
    knowledge_base_id: Optional[int] = Query(default=None),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Search documents inside the active tenant only (optional KB filter)."""
    _ = user
    rows = await db_service.search_knowledge_documents(
        tenant.id, q, knowledge_base_id=knowledge_base_id
    )
    return [_doc_resp(d) for d in rows]
