"""Email draft model with forced approval state machine."""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseModel


class EmailStatus(str, Enum):
    """Forced email draft statuses.

    Transitions: draft → pending_approval → approved|rejected → sent.
    Sending is only allowed from approved.
    """

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


class EmailDraft(BaseModel, table=True):
    """Persisted email draft for the email agent approval gate.

    Attributes:
        id: Primary key.
        tenant_id: Owning tenant.
        status: State machine status.
        subject: Email subject.
        body: Email body.
        to_address: Recipient address.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "email_draft"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    status: str = Field(default=EmailStatus.DRAFT.value, max_length=50, index=True)
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="")
    to_address: str = Field(default="", max_length=320)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
