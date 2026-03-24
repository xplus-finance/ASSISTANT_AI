"""Approval gate for dangerous operations — requires PIN confirmation."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

APPROVAL_TIMEOUT = 300  # 5 minutes
MAX_PIN_ATTEMPTS = 3
LOCKOUT_SECONDS = 86400  # 24 hours

ALWAYS_REQUIRE_APPROVAL: frozenset[str] = frozenset({
    "command_execute",
    "file_delete",
    "file_write",
    "file_overwrite",
    "install_package",
    "install",
    "send_external_request",
    "skill_create",
    "script_create",
    "code_modify",
    "delete",
    "system_control",
    "process_kill",
    "permissions",
    "disk_format",
    "service_control",
    "firewall",
    "git_destructive",
    "privilege_escalation",
    "scheduled_task",
    "move_rename",
    "config_change",
    "database_destructive",
    "docker_destructive",
    "system_update",
    "sensitive_read",
    "data_export",
    "env_modify",
    "network_scan",
    "clipboard_access",
    "remote_access",
    "folder_create",
    "file_create",
    "file_copy",
    "download",
    "archive_operation",
    "user_management",
})

_AFFIRMATIVE_RESPONSES: frozenset[str] = frozenset({
    "si", "sí", "yes", "ok", "dale", "aprobado",
    "approve", "confirmed", "confirmar", "confirmo",
    "adelante", "hazlo", "procede", "va",
})

_NEGATIVE_RESPONSES: frozenset[str] = frozenset({
    "no", "cancelar", "cancel", "rechazar", "reject",
    "negar", "deny", "para", "detente", "stop",
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
    original_message: str = ""
    channel: str = ""
    chat_id: str = ""
    requires_pin: bool = False
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
            "original_message": self.original_message,
            "channel": self.channel,
            "chat_id": self.chat_id,
            "requires_pin": self.requires_pin,
            "status": self.status.value,
            "created_at": self.created_at,
            "expires_in_seconds": max(
                0, APPROVAL_TIMEOUT - (time.time() - self.created_at)
            ),
        }


class ApprovalGate:

    def __init__(self, pin_hash: str | None = None) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self._pin_hash: str | None = pin_hash
        # Brute-force protection: track failed PIN attempts per action category
        self._failed_attempts: dict[str, list[float]] = defaultdict(list)
        self._lockout_until: dict[str, float] = {}

    def set_pin_hash(self, pin_hash: str | None) -> None:
        """Update the PIN hash (called during gateway init)."""
        self._pin_hash = pin_hash

    @property
    def has_pin(self) -> bool:
        return bool(self._pin_hash)

    def is_locked_out(self, action: str = "global") -> tuple[bool, int]:
        """Check if an action is locked out due to failed PIN attempts.

        Returns (is_locked, remaining_seconds).
        """
        until = self._lockout_until.get(action, 0.0)
        if until <= 0:
            return False, 0
        remaining = until - time.time()
        if remaining <= 0:
            # Lockout expired — clear it
            self._lockout_until.pop(action, None)
            self._failed_attempts.pop(action, None)
            return False, 0
        return True, int(remaining)

    def _record_failed_attempt(self, action: str) -> tuple[bool, int]:
        """Record a failed PIN attempt. Returns (now_locked, remaining_attempts).

        If MAX_PIN_ATTEMPTS reached, sets a 24-hour lockout.
        """
        now = time.time()
        # Only keep attempts within the lockout window
        cutoff = now - LOCKOUT_SECONDS
        attempts = [t for t in self._failed_attempts[action] if t > cutoff]
        attempts.append(now)
        self._failed_attempts[action] = attempts

        if len(attempts) >= MAX_PIN_ATTEMPTS:
            self._lockout_until[action] = now + LOCKOUT_SECONDS
            return True, 0
        return False, MAX_PIN_ATTEMPTS - len(attempts)

    @staticmethod
    def requires_approval(action: str) -> bool:
        return action in ALWAYS_REQUIRE_APPROVAL

    def request_approval(
        self,
        action: str,
        details: str,
        original_message: str = "",
        channel: str = "",
        chat_id: str = "",
        requires_pin: bool = False,
    ) -> ApprovalRequest:
        self._purge_expired()
        request = ApprovalRequest(
            action=action,
            details=details,
            original_message=original_message,
            channel=channel,
            chat_id=chat_id,
            requires_pin=requires_pin,
        )
        self._pending[request.request_id] = request
        return request

    def check_response(self, request_id: str, response: str) -> tuple[bool, str]:
        """Check user response to an approval request.

        Returns (approved: bool, reason: str).
        - If requires_pin: response must match the stored PIN hash.
        - If no PIN configured: rejects (PIN is mandatory).
        - Brute-force protection: 3 failed attempts → 24h lockout.

        Possible reasons: pin_verified, rejected, expired, no_pending,
        wrong_pin, locked_out, no_pin_configured, unrecognized.
        """
        request = self._pending.get(request_id)
        if request is None:
            return False, "no_pending"

        if request.is_expired:
            request.status = ApprovalStatus.EXPIRED
            self._pending.pop(request_id, None)
            return False, "expired"

        # Check lockout before anything else
        action_key = request.action
        locked, remaining = self.is_locked_out(action_key)
        if locked:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            return False, f"locked_out:{hours}h{minutes}m"

        normalized = response.strip().lower()

        # Check for explicit rejection first
        if normalized in _NEGATIVE_RESPONSES:
            request.status = ApprovalStatus.REJECTED
            self._pending.pop(request_id, None)
            return False, "rejected"

        # PIN is mandatory — if not configured, block
        if not self._pin_hash:
            return False, "no_pin_configured"

        # PIN verification path
        if request.requires_pin and self._pin_hash:
            from src.utils.crypto import verify_pin
            if verify_pin(response.strip(), self._pin_hash):
                # Successful — clear any failed attempts for this action
                self._failed_attempts.pop(action_key, None)
                request.status = ApprovalStatus.APPROVED
                self._pending.pop(request_id, None)
                return True, "pin_verified"
            else:
                # Wrong PIN — record failure and check for lockout
                now_locked, remaining_attempts = self._record_failed_attempt(action_key)
                if now_locked:
                    request.status = ApprovalStatus.REJECTED
                    self._pending.pop(request_id, None)
                    return False, "locked_out:24h0m"
                return False, f"wrong_pin:{remaining_attempts}"

        # Unrecognized response
        return False, "unrecognized"

    def get_pending(self) -> list[dict]:
        self._purge_expired()
        return [req.as_dict() for req in self._pending.values()]

    def get_pending_request(self) -> ApprovalRequest | None:
        """Return the first pending request object, or None."""
        self._purge_expired()
        for req in self._pending.values():
            if req.status == ApprovalStatus.PENDING:
                return req
        return None

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
