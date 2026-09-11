"""Request/response schemas for agent stub endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ContractReviewRequest(BaseModel):
    """Contract review stub input."""

    text: Optional[str] = Field(default=None, description="Contract text to review")
    file_ref: Optional[str] = Field(default=None, description="Optional file reference / URI")


class RiskFinding(BaseModel):
    """Stub risk finding."""

    severity: str
    clause: str
    summary: str


class ContractReviewResponse(BaseModel):
    """Stub contract review report."""

    tenant_id: int
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
