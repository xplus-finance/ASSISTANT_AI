"""Gmail multi-account credential manager using App Passwords.

Stores email + app_password pairs encrypted with AES-256-GCM.
No Google Cloud project needed — just IMAP/SMTP with Gmail App Passwords.

Setup per account:
  1. Enable 2FA on the Google account
  2. Go to https://myaccount.google.com/apppasswords
  3. Generate an App Password (16 chars)
  4. Register with: !gmail auth <email> <app_password>
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger("assistant.utils.gmail_auth")

# Where encrypted credentials live
_CREDENTIALS_FILE = Path("data/gmail_accounts.enc.json")

# IMAP/SMTP endpoints for Gmail
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _ensure_data_dir() -> None:
    """Create data directory with secure permissions."""
    _CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(_CREDENTIALS_FILE.parent, 0o700)
    except OSError:
        pass


def _get_encryption_key() -> str:
    """Get the encryption key for storing credentials.

    Priority: GMAIL_ENCRYPTION_KEY env var > auto-generated key file.
    """
    env_key = os.environ.get("GMAIL_ENCRYPTION_KEY")
    if env_key:
        return env_key

    # Auto-generate and persist a key if none configured
    key_file = Path("data/.gmail_key")
    if key_file.exists():
        return key_file.read_text().strip()

    _ensure_data_dir()
    import secrets
    key = secrets.token_hex(32)
    key_file.write_text(key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    log.info("gmail_auth.key_generated", path=str(key_file))
    return key


class GmailAccount:
    """Represents a single Gmail account with App Password credentials."""

    def __init__(self, email: str, app_password: str) -> None:
        self.email = email
        self._app_password = app_password

    @property
    def app_password(self) -> str:
        return self._app_password

    def __repr__(self) -> str:
        return f"<GmailAccount {self.email}>"


class GmailAuthManager:
    """Manages App Password credentials for multiple Gmail accounts.

    Credentials stored encrypted on disk with AES-256-GCM.
    Supports up to N accounts (designed for 4, no hard limit).
    """

    def __init__(self) -> None:
        self._accounts: dict[str, GmailAccount] = {}

    @property
    def accounts(self) -> dict[str, GmailAccount]:
        return dict(self._accounts)

    @property
    def account_emails(self) -> list[str]:
        return list(self._accounts.keys())

    def get_account(self, email: str | None = None) -> GmailAccount | None:
        """Get account by email. If None, return the first/default account."""
        if email:
            return self._accounts.get(email.lower().strip())
        if self._accounts:
            return next(iter(self._accounts.values()))
        return None

    def load_accounts(self) -> int:
        """Load all saved accounts from encrypted storage."""
        if not _CREDENTIALS_FILE.exists():
            return 0

        try:
            from src.utils.crypto import decrypt_value

            key = _get_encryption_key()
            encrypted = _CREDENTIALS_FILE.read_text().strip()
            decrypted = decrypt_value(encrypted, key)
            accounts_data: list[dict[str, str]] = json.loads(decrypted)

            for acc in accounts_data:
                email = acc["email"].lower().strip()
                self._accounts[email] = GmailAccount(email, acc["app_password"])

            log.info("gmail_auth.loaded", count=len(self._accounts))
            return len(self._accounts)

        except Exception:
            log.warning("gmail_auth.load_failed", exc_info=True)
            return 0

    def _save_accounts(self) -> None:
        """Persist all accounts to encrypted storage."""
        from src.utils.crypto import encrypt_value

        _ensure_data_dir()
        key = _get_encryption_key()

        accounts_data = [
            {"email": acc.email, "app_password": acc.app_password}
            for acc in self._accounts.values()
        ]

        plaintext = json.dumps(accounts_data)
        encrypted = encrypt_value(plaintext, key)
        _CREDENTIALS_FILE.write_text(encrypted)

        try:
            os.chmod(_CREDENTIALS_FILE, 0o600)
        except OSError:
            pass

        log.info("gmail_auth.saved", count=len(self._accounts))

    def add_account(self, email: str, app_password: str) -> GmailAccount:
        """Add or update an account and persist to disk.

        Args:
            email: Gmail address (e.g. user@gmail.com)
            app_password: 16-char App Password from Google account settings

        Returns:
            The created/updated GmailAccount.
        """
        email = email.lower().strip()
        # Clean app password — Google shows it with spaces, remove them
        app_password = app_password.replace(" ", "").strip()

        if not email or "@" not in email:
            raise ValueError(f"Email invalido: {email}")
        if not app_password or len(app_password) < 10:
            raise ValueError(
                "App Password invalido. Debe ser la contraseña de 16 caracteres "
                "generada en https://myaccount.google.com/apppasswords"
            )

        account = GmailAccount(email, app_password)
        self._accounts[email] = account
        self._save_accounts()

        log.info("gmail_auth.account_added", email=email)
        return account

    def remove_account(self, email: str) -> bool:
        """Remove an account and update storage."""
        email = email.lower().strip()
        if email in self._accounts:
            del self._accounts[email]
            self._save_accounts()
            log.info("gmail_auth.account_removed", email=email)
            return True
        return False

    def list_accounts(self) -> list[dict[str, str]]:
        """List all configured accounts."""
        return [
            {"email": acc.email, "status": "configurada"}
            for acc in self._accounts.values()
        ]

    def verify_account(self, email: str | None = None) -> tuple[bool, str]:
        """Test IMAP connection to verify credentials work.

        Returns:
            (success, message) tuple.
        """
        import imaplib
        import ssl

        account = self.get_account(email)
        if not account:
            return False, "No hay cuenta configurada."

        try:
            ctx = ssl.create_default_context()
            with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx) as imap:
                imap.login(account.email, account.app_password)
                imap.logout()
            return True, f"Conexion exitosa para {account.email}"
        except imaplib.IMAP4.error as e:
            return False, f"Error de autenticacion para {account.email}: {e}"
        except Exception as e:
            return False, f"Error de conexion: {e}"
