"""Persisted data report with SQL traceability."""

from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class DataReport(BaseModel, table=True):
    """Tenant-scoped analytics report produced by the report agent."""

    __tablename__ = "data_report"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    created_by: int = Field(foreign_key="user.id")
    query_text: str = Field(default="")
    sql_text: str = Field(default="")
    rows_json: str = Field(default="[]")
    report_text: str = Field(default="")
    status: str = Field(default="completed", max_length=50, index=True)
