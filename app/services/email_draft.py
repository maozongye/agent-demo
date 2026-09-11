"""Email draft state machine and service helpers.

Forced transitions:
    draft → pending_approval → approved | rejected
    approved → sent

Sending without approval raises PermissionError (mapped to HTTP 403 by callers).
"""

from datetime import UTC, datetime
from typing import Optional

from fastapi import HTTPException

from app.models.email_draft import EmailDraft, EmailStatus


# Allowed transitions: from_status -> set of to_statuses
ALLOWED_TRANSITIONS = {
    EmailStatus.DRAFT: {EmailStatus.PENDING_APPROVAL},
    EmailStatus.PENDING_APPROVAL: {EmailStatus.APPROVED, EmailStatus.REJECTED},
    EmailStatus.APPROVED: {EmailStatus.SENT},
    EmailStatus.REJECTED: {EmailStatus.DRAFT},  # allow re-draft after reject
    EmailStatus.SENT: set(),
}


def _as_status(value: str | EmailStatus) -> EmailStatus:
    """Normalize a status value to EmailStatus."""
    if isinstance(value, EmailStatus):
        return value
    return EmailStatus(value)


def can_transition(current: str | EmailStatus, target: str | EmailStatus) -> bool:
    """Return whether a transition is allowed.

    Args:
        current: Current status.
        target: Desired status.

    Returns:
        bool: True if transition is permitted.
    """
    cur = _as_status(current)
    tgt = _as_status(target)
    return tgt in ALLOWED_TRANSITIONS.get(cur, set())


def assert_can_transition(current: str | EmailStatus, target: str | EmailStatus) -> None:
    """Raise HTTP 403 if the transition is not allowed.

    Args:
        current: Current status.
        target: Desired status.

    Raises:
        HTTPException: 403 when transition is forbidden.
    """
    if not can_transition(current, target):
        raise HTTPException(
            status_code=403,
            detail=f"Cannot transition email from '{_as_status(current).value}' to '{_as_status(target).value}'",
        )


def assert_can_send(status: str | EmailStatus) -> None:
    """Raise HTTP 403 unless status is approved.

    Args:
        status: Current draft status.

    Raises:
        HTTPException: 403 when not approved.
    """
    if _as_status(status) != EmailStatus.APPROVED:
        raise HTTPException(
            status_code=403,
            detail="Sending without approval is forbidden. Email must be in 'approved' status.",
        )


def apply_transition(draft: EmailDraft, target: EmailStatus) -> EmailDraft:
    """Apply a status transition on an in-memory draft (does not persist).

    Args:
        draft: The email draft instance.
        target: Target status.

    Returns:
        EmailDraft: The mutated draft.

    Raises:
        HTTPException: 403 when transition is forbidden.
    """
    assert_can_transition(draft.status, target)
    draft.status = target.value
    draft.updated_at = datetime.now(UTC)
    return draft


def create_draft_in_memory(
    tenant_id: int,
    subject: str,
    body: str,
    to_address: str,
    draft_id: Optional[int] = None,
) -> EmailDraft:
    """Create an in-memory EmailDraft in draft status (for tests / stubs).

    Args:
        tenant_id: Owning tenant id.
        subject: Email subject.
        body: Email body.
        to_address: Recipient.
        draft_id: Optional id for tests.

    Returns:
        EmailDraft: New draft in draft status.
    """
    return EmailDraft(
        id=draft_id,
        tenant_id=tenant_id,
        status=EmailStatus.DRAFT.value,
        subject=subject,
        body=body,
        to_address=to_address,
    )
