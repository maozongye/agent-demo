"""Contract document and review models (tenant-isolated)."""

from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class ContractDocument(BaseModel, table=True):
    """Uploaded contract PDF metadata, scoped to a tenant."""

    __tablename__ = "contract_document"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    uploaded_by: int = Field(foreign_key="user.id")
    filename: str = Field(max_length=512)
    file_ref: str = Field(max_length=1024)
    content_type: str = Field(default="application/pdf", max_length=128)


class ContractReview(BaseModel, table=True):
    """Persisted contract review report for a tenant."""

    __tablename__ = "contract_review"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    document_id: Optional[int] = Field(default=None, foreign_key="contract_document.id", index=True)
    status: str = Field(default="completed", max_length=50, index=True)
    report_text: str = Field(default="")
    findings_json: str = Field(default="[]")
