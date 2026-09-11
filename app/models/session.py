"""This file contains the session model for the application."""

from typing import (
    TYPE_CHECKING,
    List,
    Optional,
)

from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.user import User


class Session(BaseModel, table=True):
    """Session model for storing chat sessions.

    Attributes:
        id: The primary key
        user_id: Foreign key to the user
        tenant_id: Foreign key to the tenant (nullable for legacy rows; required for new sessions)
        name: Name of the session (defaults to empty string)
        created_at: When the session was created
        messages: Relationship to session messages
        user: Relationship to the session owner
    """

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    name: str = Field(default="")
    messages: List["Message"] = Relationship(back_populates="session")
    user: "User" = Relationship(back_populates="sessions")


# Avoid circular imports
from app.models.message import Message  # noqa: E402
