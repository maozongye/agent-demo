"""Audit log for email approval and send actions."""

from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class EmailAuditLog(BaseModel, table=True):
    """Immutable audit entry for email draft lifecycle events."""

    __tablename__ = "email_audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    draft_id: int = Field(index=True)
    actor_user_id: int = Field(foreign_key="user.id")
    action: str = Field(max_length=64, index=True)  # classify|submit|approve|reject|send|generate_reply
    detail: str = Field(default="")
