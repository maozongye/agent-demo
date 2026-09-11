"""Tenant and membership request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    """Request to create a tenant."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class TenantResponse(BaseModel):
    """Tenant response payload."""

    id: int
    name: str
    slug: str
    status: str
    created_at: datetime


class MembershipResponse(BaseModel):
    """Membership response payload."""

    id: int
    user_id: int
    tenant_id: int
    role: str
    created_at: datetime


class MembershipJoin(BaseModel):
    """Request body for the disabled open-join stub (Phase 1 invite/admin-only).

    Role is not client-selectable on public join; open join always returns 403.
    """

    tenant_id: int
