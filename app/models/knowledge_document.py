"""Tenant-scoped knowledge documents inside a knowledge base namespace."""

from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class KnowledgeDocument(BaseModel, table=True):
    """A document stored in a per-tenant knowledge base.

    Attributes:
        id: Primary key.
        tenant_id: Owning tenant (isolation boundary).
        knowledge_base_id: Parent KB namespace.
        title: Display title.
        content: Searchable text body.
        file_ref: Optional tenant-relative file path under UPLOAD_DIR.
    """

    __tablename__ = "knowledge_document"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    knowledge_base_id: int = Field(foreign_key="knowledge_base.id", index=True)
    title: str = Field(max_length=512, default="")
    content: str = Field(default="")
    file_ref: str = Field(default="", max_length=1024)
