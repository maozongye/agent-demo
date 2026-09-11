
"""Request/response schemas for agent endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ContractReviewRequest(BaseModel):
    """Contract review input (document id and/or raw text)."""

    document_id: Optional[int] = Field(default=None, description="Uploaded document id")
    text: Optional[str] = Field(default=None, description="Inline contract text")
    file_ref: Optional[str] = Field(default=None, description="Legacy file reference")


class RiskFinding(BaseModel):
    """A detected contract risk."""

    severity: str
    clause: str
    summary: str
    excerpt: Optional[str] = None


class ContractDocumentResponse(BaseModel):
    """Uploaded contract document metadata."""

    id: int
    tenant_id: int
    filename: str
    file_ref: str
    content_type: str
    created_at: Optional[datetime] = None


class ContractReviewResponse(BaseModel):
    """Contract review report response."""

    id: Optional[int] = None
    tenant_id: int
    document_id: Optional[int] = None
    status: str = "completed"
    findings: List[RiskFinding]
    report: str

class EmailDraftCreate(BaseModel):
    """Create an email draft."""

    subject: str = Field(..., max_length=500)
    body: str = ""
    to_address: str = Field(..., max_length=320)


class EmailDraftResponse(BaseModel):
    """Email draft response."""

    id: int
    tenant_id: int
    status: str
    subject: str
    body: str
    to_address: str
    created_at: datetime
    updated_at: datetime


class EmailClassifyResponse(BaseModel):
    """Stub classification result."""

    draft_id: int
    category: str
    confidence: float
    rationale: str


class ReportQueryRequest(BaseModel):
    """Natural-language report query."""

    query: str = Field(..., min_length=1, max_length=2000)


class ReportQueryResponse(BaseModel):
    """Stub NL→SQL preview + analysis."""

    tenant_id: int
    sql_preview: str
    analysis_report: str
