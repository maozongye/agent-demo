"""Tenant and membership request/response schemas."""

from datetime import datetime
from typing import Optional

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
    """Request to join a tenant (thin stub)."""

    tenant_id: int
    role: str = Field(default="member", pattern=r"^(owner|admin|member)$")
