"""Unit tests for email approval state machine — no live DB required."""

import pytest
from fastapi import HTTPException

from app.models.email_draft import EmailStatus
from app.services.email_draft import (
    apply_transition,
    assert_can_send,
    can_transition,
    create_draft_in_memory,
)


def test_cannot_send_from_draft():
    """Sending from draft must raise HTTP 403."""
    draft = create_draft_in_memory(
        tenant_id=1,
        subject="Hi",
        body="Body",
        to_address="a@example.com",
        draft_id=1,
    )
    assert draft.status == EmailStatus.DRAFT.value
    with pytest.raises(HTTPException) as exc:
        assert_can_send(draft.status)
    assert exc.value.status_code == 403


def test_cannot_send_from_pending_approval():
    """Sending from pending_approval must raise HTTP 403."""
    draft = create_draft_in_memory(
        tenant_id=1,
        subject="Hi",
        body="Body",
        to_address="a@example.com",
        draft_id=2,
    )
    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    assert draft.status == EmailStatus.PENDING_APPROVAL.value
    with pytest.raises(HTTPException) as exc:
        assert_can_send(draft.status)
    assert exc.value.status_code == 403


def test_can_send_only_when_approved():
    """Approved drafts may transition to sent."""
    draft = create_draft_in_memory(
        tenant_id=1,
        subject="Hi",
        body="Body",
        to_address="a@example.com",
        draft_id=3,
    )
    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    apply_transition(draft, EmailStatus.APPROVED)
    assert_can_send(draft.status)  # does not raise
    apply_transition(draft, EmailStatus.SENT)
    assert draft.status == EmailStatus.SENT.value


def test_forbidden_transition_draft_to_sent():
    """Direct draft → sent is forbidden."""
    assert not can_transition(EmailStatus.DRAFT, EmailStatus.SENT)
    draft = create_draft_in_memory(1, "s", "b", "a@example.com", draft_id=4)
    with pytest.raises(HTTPException) as exc:
        apply_transition(draft, EmailStatus.SENT)
    assert exc.value.status_code == 403


def test_reject_then_redraft():
    """rejected → draft is allowed for re-edit."""
    draft = create_draft_in_memory(1, "s", "b", "a@example.com", draft_id=5)
    apply_transition(draft, EmailStatus.PENDING_APPROVAL)
    apply_transition(draft, EmailStatus.REJECTED)
    apply_transition(draft, EmailStatus.DRAFT)
    assert draft.status == EmailStatus.DRAFT.value
