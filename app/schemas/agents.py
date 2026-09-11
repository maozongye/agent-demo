
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
    category: str = ""
    category_confidence: float = 0.0
    created_at: datetime
    updated_at: datetime


class EmailIngestRequest(BaseModel):
    """Stub inbound email ingest."""

    from_address: str = Field(..., max_length=320)
    subject: str = Field(default="", max_length=500)
    body: str = ""
    to_address: str = Field(default="", max_length=320)


class EmailIngestResponse(BaseModel):
    """Ingest + classify + draft reply result."""

    draft: "EmailDraftResponse"
    category: str
    confidence: float
    rationale: str


class EmailClassifyResponse(BaseModel):
    """Classification result."""

    draft_id: int
    category: str
    confidence: float
    rationale: str


class EmailAuditLogResponse(BaseModel):
    """Audit log entry."""

    id: int
    tenant_id: int
    draft_id: int
    actor_user_id: int
    action: str
    detail: str
    created_at: datetime


class ReportQueryRequest(BaseModel):
    """Natural-language report query."""

    query: str = Field(..., min_length=1, max_length=2000)
    execute: bool = Field(default=True, description="If true, run SQL in read-only sandbox")


class ReportQueryResponse(BaseModel):
    """NL→SQL preview + analysis report."""

    id: Optional[int] = None
    tenant_id: int
    sql_preview: str
    analysis_report: str
    row_count: int = 0
    status: str = "completed"


class DataReportResponse(BaseModel):
    """Persisted data report with SQL traceability."""

    id: int
    tenant_id: int
    created_by: int
    query_text: str
    sql_text: str
    report_text: str
    row_count: int
    status: str
    created_at: Optional[datetime] = None


class SqlValidateRequest(BaseModel):
    """Validate SQL without executing."""

    sql: str = Field(..., min_length=1)


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class KnowledgeBaseResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    created_at: datetime


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(default="")


class KnowledgeDocumentResponse(BaseModel):
    id: int
    tenant_id: int
    knowledge_base_id: int
    title: str
    content: str
    file_ref: str = ""
    created_at: datetime
