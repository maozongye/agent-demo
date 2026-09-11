"""Tenant and membership models for multi-tenant isolation."""

from enum import Enum
from typing import (
    TYPE_CHECKING,
    List,
    Optional,
)

from sqlmodel import (
    Field,
    Relationship,
    UniqueConstraint,
)

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class TenantStatus(str, Enum):
    """Lifecycle status for a tenant."""

    ACTIVE = "active"
    DISABLED = "disabled"


class MembershipRole(str, Enum):
    """Role of a user within a tenant."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Tenant(BaseModel, table=True):
    """Tenant (organization) model.

    Attributes:
        id: Primary key.
        name: Display name.
        slug: Unique URL-safe identifier.
        status: active or disabled.
        created_at: Creation timestamp.
        memberships: Related memberships.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=255)
    slug: str = Field(unique=True, index=True, max_length=100)
    status: str = Field(default=TenantStatus.ACTIVE.value, max_length=50)
    memberships: List["TenantMembership"] = Relationship(back_populates="tenant")


class TenantMembership(BaseModel, table=True):
    """Membership linking a user to a tenant with a role.

    Attributes:
        id: Primary key.
        user_id: FK to user.
        tenant_id: FK to tenant.
        role: owner, admin, or member.
        created_at: Creation timestamp.
    """

    __tablename__ = "tenant_membership"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    role: str = Field(default=MembershipRole.MEMBER.value, max_length=50)
    tenant: Optional[Tenant] = Relationship(back_populates="memberships")
