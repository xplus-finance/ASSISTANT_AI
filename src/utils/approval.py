"""Approval gate for dangerous operations with 5-minute expiry."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

APPROVAL_TIMEOUT = 300  # 5 minutes

ALWAYS_REQUIRE_APPROVAL: frozenset[str] = frozenset({
    "command_execute",
    "file_delete",
    "file_write",
    "install_package",
    "send_external_request",
    "skill_create",
})

_AFFIRMATIVE_RESPONSES: frozenset[str] = frozenset({
    "si", "sí", "yes", "ok", "dale", "aprobado",
    "approve", "confirmed", "confirmar", "confirmo",
    "adelante", "hazlo", "procede", "va",
})


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
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
        return (time.time() - self.created_at) > APPROVAL_TIMEOUT

    def as_dict(self) -> dict:
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


    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}

    @staticmethod
    def requires_approval(action: str) -> bool:
        return action in ALWAYS_REQUIRE_APPROVAL

    def request_approval(self, action: str, details: str) -> ApprovalRequest:
        self._purge_expired()
        request = ApprovalRequest(action=action, details=details)
        self._pending[request.request_id] = request
        return request

    def check_response(self, request_id: str, response: str) -> bool:
        request = self._pending.get(request_id)
        if request is None:
            return False

        if request.is_expired:
            request.status = ApprovalStatus.EXPIRED
            self._pending.pop(request_id, None)
            return False

        normalized = response.strip().lower()
        if normalized in _AFFIRMATIVE_RESPONSES:
            request.status = ApprovalStatus.APPROVED
            self._pending.pop(request_id, None)
            return True

        request.status = ApprovalStatus.REJECTED
        self._pending.pop(request_id, None)
        return False

    def get_pending(self) -> list[dict]:
        self._purge_expired()
        return [req.as_dict() for req in self._pending.values()]

    def cancel(self, request_id: str) -> bool:
        removed = self._pending.pop(request_id, None)
        return removed is not None

    def cancel_all(self) -> int:
        count = len(self._pending)
        self._pending.clear()
        return count

    def _purge_expired(self) -> None:
        expired_ids = [
            rid for rid, req in self._pending.items() if req.is_expired
        ]
        for rid in expired_ids:
            self._pending[rid].status = ApprovalStatus.EXPIRED
            del self._pending[rid]
