"""Authentication and authorization endpoints for the API.

This module provides endpoints for user registration, login, session management,
token verification, and tenant context resolution.
"""

import re
import uuid
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Header,
    HTTPException,
    Request,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.models.tenant import MembershipRole, Tenant
from app.models.user import User
from app.schemas.auth import (
    SessionResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.schemas.tenant import (
    MembershipJoin,
    MembershipResponse,
    TenantCreate,
    TenantResponse,
)
from app.services.database import DatabaseService
from app.utils.auth import (
    create_access_token,
    get_tenant_id_from_token,
    verify_token,
)
from app.utils.sanitization import (
    sanitize_email,
    sanitize_string,
    validate_password_strength,
)

router = APIRouter()
security = HTTPBearer()
db_service = DatabaseService()


def _slugify_email(email: str) -> str:
    """Build a default personal-tenant slug from an email local-part."""
    local = email.split("@")[0].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", local).strip("-") or "user"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get the current user from the token.

    Args:
        credentials: The HTTP authorization credentials containing the JWT token.

    Returns:
        User: The user extracted from the token.

    Raises:
        HTTPException: If the token is invalid or missing.
    """
    try:
        token = sanitize_string(credentials.credentials)

        user_id = verify_token(token)
        if user_id is None:
            logger.error("invalid_token", token_part=token[:10] + "...")
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id_int = int(user_id)
        user = await db_service.get_user(user_id_int)
        if user is None:
            logger.error("user_not_found", user_id=user_id_int)
            raise HTTPException(
                status_code=404,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user
    except ValueError as ve:
        logger.error("token_validation_failed", error=str(ve), exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Session:
    """Get the current session ID from the token.

    Args:
        credentials: The HTTP authorization credentials containing the JWT token.

    Returns:
        Session: The session extracted from the token.

    Raises:
        HTTPException: If the token is invalid or missing.
    """
    try:
        token = sanitize_string(credentials.credentials)

        session_id = verify_token(token)
        if session_id is None:
            logger.error("session_id_not_found", token_part=token[:10] + "...")
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        session_id = sanitize_string(session_id)

        session = await db_service.get_session(session_id)
        if session is None:
            logger.error("session_not_found", session_id=session_id)
            raise HTTPException(
                status_code=404,
                detail="Session not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return session
    except ValueError as ve:
        logger.error("token_validation_failed", error=str(ve), exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user: User = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
) -> Tenant:
    """Resolve the active tenant from JWT claim, with optional header override.

    Primary source is the JWT ``tenant_id`` claim. Optional ``X-Tenant-Id`` may
    switch tenant for same-user multi-tenant access, but membership MUST exist
    or a 403 is raised.

    Args:
        credentials: Bearer credentials.
        user: Authenticated user.
        x_tenant_id: Optional override header.

    Returns:
        Tenant: The resolved active tenant.

    Raises:
        HTTPException: 403 if membership missing; 404 if tenant missing; 401 if no claim.
    """
    token = sanitize_string(credentials.credentials)
    jwt_tenant_id = get_tenant_id_from_token(token)

    target_tenant_id: Optional[int] = jwt_tenant_id
    if x_tenant_id is not None and str(x_tenant_id).strip() != "":
        try:
            override_id = int(sanitize_string(str(x_tenant_id)))
        except ValueError:
            raise HTTPException(status_code=422, detail="X-Tenant-Id must be an integer")
        membership = await db_service.get_membership(user.id, override_id)
        if membership is None:
            logger.warning(
                "tenant_header_membership_denied",
                user_id=user.id,
                requested_tenant_id=override_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Not a member of the requested tenant",
            )
        target_tenant_id = override_id

    if target_tenant_id is None:
        # Fall back to user's first membership when JWT lacks tenant_id (legacy tokens)
        target_tenant_id = await db_service.get_default_tenant_id_for_user(user.id)
        if target_tenant_id is None:
            raise HTTPException(status_code=401, detail="No tenant context available")

    # Always validate membership for the resolved tenant
    membership = await db_service.get_membership(user.id, target_tenant_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of the requested tenant")

    tenant = await db_service.get_tenant(target_tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status == "disabled":
        raise HTTPException(status_code=403, detail="Tenant is disabled")

    return tenant




async def require_tenant_role(
    user: User,
    tenant: Tenant,
    allowed_roles: set[str],
) -> str:
    """Ensure the user has one of the allowed roles in the tenant.

    Args:
        user: Authenticated user.
        tenant: Active tenant.
        allowed_roles: Roles permitted for the operation (e.g. {"owner", "admin"}).

    Returns:
        str: The user's membership role.

    Raises:
        HTTPException: 403 if membership missing or role insufficient.
    """
    membership = await db_service.get_membership(user.id, tenant.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of the requested tenant")
    role = membership.role
    if role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Requires one of roles: {', '.join(sorted(allowed_roles))}",
        )
    return role


@router.post("/register", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register_user(request: Request, user_data: UserCreate):
    """Register a new user and create a personal default tenant + owner membership.

    Args:
        request: The FastAPI request object for rate limiting.
        user_data: User registration data

    Returns:
        UserResponse: The created user info (JWT includes tenant_id)
    """
    try:
        sanitized_email = sanitize_email(user_data.email)

        password = user_data.password.get_secret_value()
        validate_password_strength(password)

        if await db_service.get_user_by_email(sanitized_email):
            raise HTTPException(status_code=400, detail="Email already registered")

        user = await db_service.create_user(email=sanitized_email, password=User.hash_password(password))

        # Prefer: register creates a default personal tenant so JWT can include tenant_id
        tenant = await db_service.create_tenant(
            name=f"{sanitized_email} workspace",
            slug=_slugify_email(sanitized_email),
        )
        await db_service.create_membership(user.id, tenant.id, role=MembershipRole.OWNER.value)

        token = create_access_token(str(user.id), tenant_id=tenant.id)

        return UserResponse(id=user.id, email=user.email, token=token)
    except ValueError as ve:
        logger.error("user_registration_validation_failed", error=str(ve), exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["login"][0])
async def login(
    request: Request, username: str = Form(...), password: str = Form(...), grant_type: str = Form(default="password")
):
    """Login a user.

    Args:
        request: The FastAPI request object for rate limiting.
        username: User's email
        password: User's password
        grant_type: Must be "password"

    Returns:
        TokenResponse: Access token information (includes tenant_id when available)

    Raises:
        HTTPException: If credentials are invalid
    """
    try:
        # Do NOT sanitize passwords with html.escape — it breaks & < > " in legitimate passwords.
        username = sanitize_string(username)
        grant_type = sanitize_string(grant_type)

        if grant_type != "password":
            raise HTTPException(
                status_code=400,
                detail="Unsupported grant type. Must be 'password'",
            )

        user = await db_service.get_user_by_email(username)
        if not user or not user.verify_password(password):
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        tenant_id = await db_service.get_default_tenant_id_for_user(user.id)
        token = create_access_token(str(user.id), tenant_id=tenant_id)
        return TokenResponse(access_token=token.access_token, token_type="bearer", expires_at=token.expires_at)
    except ValueError as ve:
        logger.error("login_validation_failed", error=str(ve), exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.post("/session", response_model=SessionResponse)
async def create_session(
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create a new chat session for the authenticated user in the current tenant.

    Args:
        user: The authenticated user
        tenant: The resolved tenant context

    Returns:
        SessionResponse: The session ID, name, and access token
    """
    try:
        session_id = str(uuid.uuid4())

        session = await db_service.create_session(session_id, user.id, tenant_id=tenant.id)

        token = create_access_token(session_id, tenant_id=tenant.id)

        logger.info(
            "session_created",
            session_id=session_id,
            user_id=user.id,
            tenant_id=tenant.id,
            name=session.name,
            expires_at=token.expires_at.isoformat(),
        )

        return SessionResponse(session_id=session_id, name=session.name, token=token)
    except ValueError as ve:
        logger.error("session_creation_validation_failed", error=str(ve), user_id=user.id, exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.patch("/session/{session_id}/name", response_model=SessionResponse)
async def update_session_name(
    session_id: str, name: str = Form(...), current_session: Session = Depends(get_current_session)
):
    """Update a session's name.

    Args:
        session_id: The ID of the session to update
        name: The new name for the session
        current_session: The current session from auth

    Returns:
        SessionResponse: The updated session information
    """
    try:
        sanitized_session_id = sanitize_string(session_id)
        sanitized_name = sanitize_string(name)
        sanitized_current_session = sanitize_string(current_session.id)

        if sanitized_session_id != sanitized_current_session:
            raise HTTPException(status_code=403, detail="Cannot modify other sessions")

        session = await db_service.update_session_name(sanitized_session_id, sanitized_name)

        token = create_access_token(sanitized_session_id, tenant_id=session.tenant_id)

        return SessionResponse(session_id=sanitized_session_id, name=session.name, token=token)
    except ValueError as ve:
        logger.error("session_update_validation_failed", error=str(ve), session_id=session_id, exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.get("/sessions", response_model=List[SessionResponse])
async def get_user_sessions(user: User = Depends(get_current_user)):
    """Get all session IDs for the authenticated user.

    Args:
        user: The authenticated user

    Returns:
        List[SessionResponse]: List of session IDs
    """
    try:
        sessions = await db_service.get_user_sessions(user.id)
        return [
            SessionResponse(
                session_id=sanitize_string(session.id),
                name=sanitize_string(session.name),
                token=create_access_token(session.id, tenant_id=session.tenant_id),
            )
            for session in sessions
        ]
    except ValueError as ve:
        logger.error("get_sessions_validation_failed", user_id=user.id, error=str(ve), exc_info=True)
        raise HTTPException(status_code=422, detail=str(ve))


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(payload: TenantCreate, user: User = Depends(get_current_user)):
    """Create a tenant and add the current user as owner."""
    existing = await db_service.get_tenant_by_slug(payload.slug)
    if existing:
        raise HTTPException(status_code=400, detail="Tenant slug already exists")
    tenant = await db_service.create_tenant(name=payload.name, slug=payload.slug)
    await db_service.create_membership(user.id, tenant.id, role=MembershipRole.OWNER.value)
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status,
        created_at=tenant.created_at,
    )


@router.get("/tenants/memberships", response_model=List[MembershipResponse])
async def list_memberships(user: User = Depends(get_current_user)):
    """List memberships for the current user."""
    memberships = await db_service.list_memberships_for_user(user.id)
    return [
        MembershipResponse(
            id=m.id,
            user_id=m.user_id,
            tenant_id=m.tenant_id,
            role=m.role,
            created_at=m.created_at,
        )
        for m in memberships
    ]


@router.post("/tenants/join", response_model=MembershipResponse)
async def join_tenant(payload: MembershipJoin, user: User = Depends(get_current_user)):
    """Open self-join is disabled in Phase 1 (invite/admin-add only).

    Always returns 403. Kept as a stub so clients get a clear error instead of 404.
    """
    _ = (payload, user)
    raise HTTPException(
        status_code=403,
        detail="Open tenant join is disabled; use invitation/admin add",
    )


@router.get("/tenants/current", response_model=TenantResponse)
async def get_current_tenant_endpoint(tenant: Tenant = Depends(get_current_tenant)):
    """Return the resolved current tenant."""
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status,
        created_at=tenant.created_at,
    )
