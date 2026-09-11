"""This file contains the authentication utilities for the application."""

import re
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from typing import (
    Any,
    Dict,
    Optional,
)

from jose import (
    JWTError,
    jwt,
)

from app.core.config import settings
from app.core.logging import logger
from app.schemas.auth import Token
from app.utils.sanitization import sanitize_string


def create_access_token(
    thread_id: str,
    expires_delta: Optional[timedelta] = None,
    tenant_id: Optional[int] = None,
) -> Token:
    """Create a new access token for a user or session.

    Args:
        thread_id: The subject claim (user id or session/thread id). Kept as the first
            positional argument for backward compatibility with existing chatbot tokens.
        expires_delta: Optional expiration time delta.
        tenant_id: Optional tenant claim for multi-tenant context.

    Returns:
        Token: The generated access token.
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=settings.JWT_ACCESS_TOKEN_EXPIRE_DAYS)

    if not settings.JWT_SECRET_KEY or not str(settings.JWT_SECRET_KEY).strip():
        raise RuntimeError("JWT_SECRET_KEY is empty; refusing to create access token")

    to_encode: Dict[str, Any] = {
        "sub": thread_id,
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": sanitize_string(f"{thread_id}-{datetime.now(UTC).timestamp()}"),
    }
    if tenant_id is not None:
        to_encode["tenant_id"] = tenant_id

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    logger.info("token_created", thread_id=thread_id, tenant_id=tenant_id, expires_at=expire.isoformat())

    return Token(access_token=encoded_jwt, expires_at=expire)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode a JWT and return its claims without requiring a specific subject shape.

    Args:
        token: The JWT token to decode.

    Returns:
        Optional[Dict[str, Any]]: Payload claims if valid, None otherwise.

    Raises:
        ValueError: If the token format is invalid.
    """
    if not token or not isinstance(token, str):
        logger.warning("token_invalid_format")
        raise ValueError("Token must be a non-empty string")

    if not re.match(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$", token):
        logger.warning("token_suspicious_format")
        raise ValueError("Token format is invalid - expected JWT format")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.error("token_decode_failed", error=str(e))
        return None


def get_tenant_id_from_token(token: str) -> Optional[int]:
    """Extract tenant_id claim from a JWT if present.

    Args:
        token: The JWT token.

    Returns:
        Optional[int]: tenant_id if present and valid, else None.
    """
    payload = decode_token(token)
    if not payload:
        return None
    tenant_id = payload.get("tenant_id")
    if tenant_id is None:
        return None
    try:
        return int(tenant_id)
    except (TypeError, ValueError):
        return None


def verify_token(token: str) -> Optional[str]:
    """Verify a JWT token and return the subject (user/session/thread id).

    Args:
        token: The JWT token to verify.

    Returns:
        Optional[str]: The subject if token is valid, None otherwise.

    Raises:
        ValueError: If the token format is invalid
    """
    payload = decode_token(token)
    if payload is None:
        return None

    thread_id: Optional[str] = payload.get("sub")
    if thread_id is None:
        logger.warning("token_missing_thread_id")
        return None

    logger.info("token_verified", thread_id=thread_id)
    return thread_id
