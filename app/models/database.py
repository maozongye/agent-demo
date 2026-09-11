"""Database models for the application.

Importing this module registers SQLModel table metadata used by create_all.
Note: Thread is intentionally omitted here — its Relationship to Message is
legacy/incomplete (Message has no thread_id FK in the current model).
"""

from app.models.email_draft import EmailDraft
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.models.session import Session
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User

__all__ = [
    "Message",
    "Session",
    "User",
    "Tenant",
    "TenantMembership",
    "KnowledgeBase",
    "EmailDraft",
]
