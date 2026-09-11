"""Persistence helpers for contract documents and reviews."""

from __future__ import annotations

import json
from typing import Any, List, Optional

from sqlmodel import Session, select

from app.models.contract import ContractDocument, ContractReview
from app.services.database import database_service


class ContractService:
    """Tenant-scoped contract document/review CRUD."""

    def __init__(self, db=None):
        self.db = db or database_service

    def create_document(
        self,
        *,
        tenant_id: int,
        uploaded_by: int,
        filename: str,
        file_ref: str,
        content_type: str = "application/pdf",
    ) -> ContractDocument:
        with Session(self.db.engine) as session:
            doc = ContractDocument(
                tenant_id=tenant_id,
                uploaded_by=uploaded_by,
                filename=filename,
                file_ref=file_ref,
                content_type=content_type,
            )
            session.add(doc)
            session.commit()
            session.refresh(doc)
            return doc

    def get_document(self, tenant_id: int, document_id: int) -> Optional[ContractDocument]:
        with Session(self.db.engine) as session:
            doc = session.get(ContractDocument, document_id)
            if doc is None or doc.tenant_id != tenant_id:
                return None
            return doc

    def create_review(
        self,
        *,
        tenant_id: int,
        document_id: Optional[int],
        findings: List[dict[str, Any]],
        report_text: str,
        status: str = "completed",
    ) -> ContractReview:
        with Session(self.db.engine) as session:
            review = ContractReview(
                tenant_id=tenant_id,
                document_id=document_id,
                status=status,
                report_text=report_text,
                findings_json=json.dumps(findings, ensure_ascii=False),
            )
            session.add(review)
            session.commit()
            session.refresh(review)
            return review

    def get_review(self, tenant_id: int, review_id: int) -> Optional[ContractReview]:
        with Session(self.db.engine) as session:
            review = session.get(ContractReview, review_id)
            if review is None or review.tenant_id != tenant_id:
                return None
            return review


contract_service = ContractService()
