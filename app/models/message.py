"""This file contains the message model for the application."""

from typing import TYPE_CHECKING

from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class Message(BaseModel, table=True):
    """Message model for storing conversation messages.

    Attributes:
        id: The primary key
        session_id: Foreign key to the session
        role: The role of the message sender
        content: The content of the message
        created_at: When the message was created
        session: Relationship to the parent session
    """

    id: int = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id")
    role: str = Field(max_length=50)
    content: str
    session: "Session" = Relationship(back_populates="messages")
