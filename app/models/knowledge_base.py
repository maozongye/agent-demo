"""Knowledge base namespace model for tenant-isolated document stores."""

from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class KnowledgeBase(BaseModel, table=True):
    """Per-tenant knowledge base namespace.

    Attributes:
        id: Primary key.
        tenant_id: Owning tenant (isolation boundary).
        name: Display name.
        created_at: Creation timestamp.
    """

    __tablename__ = "knowledge_base"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    name: str = Field(max_length=255)
