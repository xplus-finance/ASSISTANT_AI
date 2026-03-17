"""
Approval gate for dangerous operations.

Certain actions (command execution, file deletion, etc.) require explicit
user approval before the assistant proceeds. Pending approvals auto-expire
after 5 minutes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# Timeout for pending approvals (seconds)
APPROVAL_TIMEOUT = 300  # 5 minutes

# Actions that ALWAYS require explicit user approval
ALWAYS_REQUIRE_APPROVAL: frozenset[str] = frozenset({
    "command_execute",
    "file_delete",
    "file_write",
    "install_package",
    "send_external_request",
    "skill_create",
})

# Accepted affirmative responses (case-insensitive)
_AFFIRMATIVE_RESPONSES: frozenset[str] = frozenset({
    "si", "sí", "yes", "ok", "dale", "aprobado",
    "approve", "confirmed", "confirmar", "confirmo",
    "adelante", "hazlo", "procede", "va",
})


class ApprovalStatus(Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    """A single pending approval request."""
    action: str
    details: str
    created_at: float = field(default_factory=time.time)
    status: ApprovalStatus = ApprovalStatus.PENDING
    request_id: str = ""

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = f"{self.action}_{int(self.created_at * 1000)}"

    @property
    def is_expired(self) -> bool:
        """Check if this request has exceeded the timeout."""
        return (time.time() - self.created_at) > APPROVAL_TIMEOUT

    def as_dict(self) -> dict:
        """Serialize for display / API responses."""
        return {
            "request_id": self.request_id,
            "action": self.action,
            "details": self.details,
            "status": self.status.value,
            "created_at": self.created_at,
            "expires_in_seconds": max(
                0, APPROVAL_TIMEOUT - (time.time() - self.created_at)
            ),
        }


class ApprovalGate:
    """
    Gate that blocks dangerous operations until the user approves them.

    Usage:
        gate = ApprovalGate()
        req = gate.request_approval("file_delete", "/home/user/important.txt")
        # ... show req to user, wait for response ...
        approved = gate.check_response(req.request_id, "dale")
    """

    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}

    @staticmethod
    def requires_approval(action: str) -> bool:
        """Return True if this action type always requires approval."""
        return action in ALWAYS_REQUIRE_APPROVAL

    def request_approval(self, action: str, details: str) -> ApprovalRequest:
        """
        Create a new approval request.

        Args:
            action: The action type (e.g., "file_delete").
            details: Human-readable description of what will happen.

        Returns:
            The ApprovalRequest object (status=PENDING).
        """
        # Clean up expired requests before adding new ones
        self._purge_expired()

        request = ApprovalRequest(action=action, details=details)
        self._pending[request.request_id] = request
        return request

    def check_response(
        self, request_id: str, response: str
    ) -> bool:
        """
        Check if the user's response approves a pending request.

        Args:
            request_id: ID of the approval request.
            response: The user's text response.

        Returns:
            True if approved, False if rejected or expired.
        """
        request = self._pending.get(request_id)
        if request is None:
            return False

        # Check expiration
        if request.is_expired:
            request.status = ApprovalStatus.EXPIRED
            self._pending.pop(request_id, None)
            return False

        # Normalize and check response
        normalized = response.strip().lower()
        if normalized in _AFFIRMATIVE_RESPONSES:
            request.status = ApprovalStatus.APPROVED
            self._pending.pop(request_id, None)
            return True

        # Any non-affirmative response = rejection
        request.status = ApprovalStatus.REJECTED
        self._pending.pop(request_id, None)
        return False

    def get_pending(self) -> list[dict]:
        """
        Return all currently pending (non-expired) approval requests.

        Returns:
            List of serialized approval request dictionaries.
        """
        self._purge_expired()
        return [req.as_dict() for req in self._pending.values()]

    def cancel(self, request_id: str) -> bool:
        """Cancel a pending approval request."""
        removed = self._pending.pop(request_id, None)
        return removed is not None

    def cancel_all(self) -> int:
        """Cancel all pending requests. Returns count of cancelled."""
        count = len(self._pending)
        self._pending.clear()
        return count

    def _purge_expired(self) -> None:
        """Remove all expired requests from the pending map."""
        expired_ids = [
            rid for rid, req in self._pending.items() if req.is_expired
        ]
        for rid in expired_ids:
            self._pending[rid].status = ApprovalStatus.EXPIRED
            del self._pending[rid]
