"""Gmail skill: email management via IMAP/SMTP with App Passwords.

No Google Cloud project needed. Uses standard IMAP4_SSL + SMTP with STARTTLS.
Multi-account support (up to N accounts, designed for 4).

Commands:
    !gmail cuentas                          — List configured accounts
    !gmail auth <email> <app_password>      — Add/update account credentials
    !gmail verificar [--cuenta=email]       — Test connection
    !gmail remover <email>                  — Remove account
    !gmail enviar <dest> <asunto> | <cuerpo> [--cuenta=email] [--adjunto=/path]
    !gmail leer [N] [--cuenta=email]        — Read last N emails (default 5)
    !gmail buscar <query> [--cuenta=email] [--max=N]
    !gmail ver <N> [--cuenta=email]         — Read email N from last listing
    !gmail responder <N> <mensaje> [--cuenta=email]
    !gmail reenviar <N> <dest> [--cuenta=email]
    !gmail borrar <N> [--cuenta=email]      — Move to trash
    !gmail leido <N> [--cuenta=email]       — Mark as read
    !gmail noleido <N> [--cuenta=email]     — Mark as unread
    !gmail carpetas [--cuenta=email]        — List folders/labels
"""

from __future__ import annotations

import asyncio
import email
import email.header
import email.utils
import imaplib
import mimetypes
import os
import re
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.gmail")

_MAX_OUTPUT = 6000
_DOWNLOADS_DIR = Path("data/gmail_downloads")


def _ensure_downloads_dir() -> Path:
    _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return _DOWNLOADS_DIR


def _parse_flags(args: str) -> tuple[str, dict[str, str]]:
    """Extract --flag=value from args string, return (clean_args, flags)."""
    flags: dict[str, str] = {}
    clean_parts: list[str] = []

    for part in args.split():
        match = re.match(r"^--(\w+)=(.+)$", part)
        if match:
            flags[match.group(1)] = match.group(2)
        elif re.match(r"^--(\w+)$", part):
            flags[part[2:]] = "true"
        else:
            clean_parts.append(part)

    return " ".join(clean_parts), flags


def _decode_header(raw: str) -> str:
    """Decode RFC 2047 encoded email header."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _extract_text(msg: email.message.Message) -> str:
    """Extract text content from email message, preferring plain text."""
    if msg.is_multipart():
        # Try plain text first, then html
        for preferred in ("text/plain", "text/html"):
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == preferred and part.get_content_disposition() != "attachment":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        text = payload.decode(charset, errors="replace")
                        if preferred == "text/html":
                            text = re.sub(r"<[^>]+>", "", text)
                            text = re.sub(r"\s+", " ", text).strip()
                        return text
        return "(sin contenido de texto)"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                text = re.sub(r"<[^>]+>", "", text)
                text = re.sub(r"\s+", " ", text).strip()
            return text
        return "(sin contenido de texto)"


def _list_attachments(msg: email.message.Message) -> list[dict[str, Any]]:
    """List attachments in an email message."""
    attachments = []
    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        disposition = part.get_content_disposition()
        if disposition == "attachment" or (
            disposition == "inline" and part.get_filename()
        ):
            filename = part.get_filename()
            if filename:
                filename = _decode_header(filename)
                size = len(part.get_payload(decode=True) or b"")
                if size > 1024 * 1024:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size} B"

                attachments.append({
                    "filename": filename,
                    "size": size_str,
                    "size_bytes": size,
                    "content_type": part.get_content_type(),
                    "part": part,
                })
    return attachments


def _format_summary(index: int, msg: email.message.Message, uid: bytes) -> str:
    """Format a message into a readable summary line."""
    from_addr = _decode_header(msg.get("From", ""))
    subject = _decode_header(msg.get("Subject", "")) or "(sin asunto)"
    date_raw = msg.get("Date", "")

    try:
        parsed = email.utils.parsedate_to_datetime(date_raw)
        date_short = parsed.strftime("%d/%m %H:%M")
    except Exception:
        date_short = date_raw[:16] if date_raw else "?"

    # Check if unread (Seen flag)
    # We pass flags from outside; for now just show index
    snippet = _extract_text(msg)[:80].replace("\n", " ")

    return f"{index}. [{uid.decode()}] {date_short} | {from_addr}\n   {subject}\n   {snippet}..."


def _format_full(msg: email.message.Message, uid: bytes) -> str:
    """Format a full message for reading."""
    from_addr = _decode_header(msg.get("From", ""))
    to_addr = _decode_header(msg.get("To", ""))
    subject = _decode_header(msg.get("Subject", "")) or "(sin asunto)"
    date_raw = msg.get("Date", "")
    cc = _decode_header(msg.get("Cc", ""))

    body = _extract_text(msg)
    attachments = _list_attachments(msg)

    att_text = ""
    if attachments:
        att_lines = [f"  - {a['filename']} ({a['size']})" for a in attachments]
        att_text = "\nAdjuntos:\n" + "\n".join(att_lines)

    parts = [
        f"UID: {uid.decode()}",
        f"De: {from_addr}",
        f"Para: {to_addr}",
    ]
    if cc:
        parts.append(f"CC: {cc}")
    parts.extend([
        f"Fecha: {date_raw}",
        f"Asunto: {subject}",
        "---",
        body,
    ])
    if att_text:
        parts.append(att_text)

    return "\n".join(parts)


class _ImapSession:
    """Context manager for IMAP connections."""

    def __init__(self, email_addr: str, app_password: str) -> None:
        self.email_addr = email_addr
        self.app_password = app_password
        self._imap: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> imaplib.IMAP4_SSL:
        ctx = ssl.create_default_context()
        self._imap = imaplib.IMAP4_SSL(
            "imap.gmail.com", 993, ssl_context=ctx
        )
        self._imap.login(self.email_addr, self.app_password)
        return self._imap

    def __exit__(self, *args: Any) -> None:
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass


class GmailSkill(BaseSkill):
    """Gmail management via IMAP/SMTP with App Passwords. No Google Cloud needed."""

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def description(self) -> str:
        return "Gmail: enviar, leer, buscar correos via IMAP/SMTP (multi-cuenta, App Passwords)"

    @property
    def triggers(self) -> list[str]:
        return ["!gmail", "!correo", "!email", "!mail"]

    def __init__(self) -> None:
        self._auth_manager: Any = None
        self._initialized = False
        # Cache of last fetched messages for quick reference by index
        self._last_uids: dict[str, list[bytes]] = {}

    def _ensure_init(self) -> None:
        """Lazy initialization of auth manager (synchronous)."""
        if self._initialized:
            return

        from src.utils.gmail_auth import GmailAuthManager

        self._auth_manager = GmailAuthManager()
        count = self._auth_manager.load_accounts()
        self._initialized = True
        log.info("gmail_skill.initialized", accounts_loaded=count)

    def _get_account(self, flags: dict[str, str]) -> tuple[Any, str | None]:
        """Get Gmail account from flags or default. Returns (account, error_msg)."""
        self._ensure_init()
        email_addr = flags.get("cuenta")
        account = self._auth_manager.get_account(email_addr)
        if account is None:
            configured = self._auth_manager.account_emails
            if configured:
                return None, (
                    f"Cuenta '{email_addr}' no encontrada.\n"
                    f"Cuentas disponibles: {', '.join(configured)}"
                )
            return None, (
                "No hay cuentas Gmail configuradas.\n"
                "Usa: !gmail auth <email> <app_password>\n\n"
                "Para obtener un App Password:\n"
                "  1. Activa verificacion en 2 pasos en tu cuenta Google\n"
                "  2. Ve a https://myaccount.google.com/apppasswords\n"
                "  3. Genera una contrasena de aplicacion (16 caracteres)\n"
                "  4. Registrala aqui: !gmail auth tucorreo@gmail.com xxxx-xxxx-xxxx-xxxx"
            )
        return account, None

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        args = args.strip()
        if not args:
            return SkillResult(success=True, message=self._help())

        parts = args.split(None, 1)
        subcmd = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        try:
            handlers: dict[str, Any] = {
                "cuentas": self._cmd_accounts,
                "accounts": self._cmd_accounts,
                "auth": self._cmd_auth,
                "autenticar": self._cmd_auth,
                "verificar": self._cmd_verify,
                "verify": self._cmd_verify,
                "remover": self._cmd_remove,
                "remove": self._cmd_remove,
                "enviar": self._cmd_send,
                "send": self._cmd_send,
                "leer": self._cmd_read,
                "read": self._cmd_read,
                "inbox": self._cmd_read,
                "buscar": self._cmd_search,
                "search": self._cmd_search,
                "ver": self._cmd_view,
                "view": self._cmd_view,
                "responder": self._cmd_reply,
                "reply": self._cmd_reply,
                "reenviar": self._cmd_forward,
                "forward": self._cmd_forward,
                "borrar": self._cmd_trash,
                "trash": self._cmd_trash,
                "delete": self._cmd_trash,
                "leido": self._cmd_mark_read,
                "noleido": self._cmd_mark_unread,
                "unread": self._cmd_mark_unread,
                "carpetas": self._cmd_folders,
                "folders": self._cmd_folders,
                "labels": self._cmd_folders,
                "etiquetas": self._cmd_folders,
                "adjuntos": self._cmd_attachments,
                "attachments": self._cmd_attachments,
                "help": lambda r, c: SkillResult(success=True, message=self._help()),
                "ayuda": lambda r, c: SkillResult(success=True, message=self._help()),
            }

            handler = handlers.get(subcmd)
            if handler:
                # help/ayuda are sync lambdas, rest are async
                result = handler(rest, context)
                if asyncio.iscoroutine(result):
                    return await result
                return result

            return SkillResult(
                success=False,
                message=f"Subcomando desconocido: '{subcmd}'\n\n{self._help()}",
            )

        except Exception as e:
            log.error("gmail_skill.error", subcmd=subcmd, error=str(e), exc_info=True)
            return SkillResult(success=False, message=f"Error en Gmail: {e}")

    # ── Account management ──────────────────────────────────────────────

    async def _cmd_accounts(self, rest: str, context: dict[str, Any]) -> SkillResult:
        self._ensure_init()
        accounts = self._auth_manager.list_accounts()
        if not accounts:
            return SkillResult(
                success=True,
                message=(
                    "No hay cuentas Gmail configuradas.\n"
                    "Usa: !gmail auth <email> <app_password>"
                ),
            )

        lines = ["Cuentas Gmail configuradas:\n"]
        for i, acc in enumerate(accounts, 1):
            lines.append(f"  {i}. {acc['email']} — {acc['status']}")
        return SkillResult(success=True, message="\n".join(lines))

    async def _cmd_auth(self, rest: str, context: dict[str, Any]) -> SkillResult:
        self._ensure_init()
        parts = rest.strip().split(None, 1)

        if len(parts) < 2:
            return SkillResult(
                success=False,
                message=(
                    "Uso: !gmail auth <email> <app_password>\n\n"
                    "Para obtener un App Password:\n"
                    "  1. Activa verificacion en 2 pasos en tu cuenta Google\n"
                    "  2. Ve a https://myaccount.google.com/apppasswords\n"
                    "  3. Genera una contrasena de aplicacion\n"
                    "  4. Copia las 16 letras y usalas aqui\n\n"
                    "Ejemplo: !gmail auth micorreo@gmail.com abcd efgh ijkl mnop"
                ),
            )

        email_addr = parts[0]
        app_password = parts[1].replace(" ", "").strip()

        try:
            account = self._auth_manager.add_account(email_addr, app_password)
        except ValueError as e:
            return SkillResult(success=False, message=str(e))

        # Verify connection
        send_fn = context.get("send_fn")
        if send_fn:
            await send_fn(f"Verificando conexion con {account.email}...")

        ok, msg = await asyncio.to_thread(
            self._auth_manager.verify_account, account.email
        )

        if ok:
            return SkillResult(
                success=True,
                message=f"Cuenta {account.email} configurada y verificada correctamente.",
            )
        else:
            # Remove the account if verification failed
            self._auth_manager.remove_account(account.email)
            return SkillResult(
                success=False,
                message=(
                    f"Error al verificar {account.email}: {msg}\n\n"
                    "La cuenta NO fue guardada. Verifica:\n"
                    "  - Que el email sea correcto\n"
                    "  - Que la App Password sea valida (16 caracteres sin espacios)\n"
                    "  - Que IMAP este habilitado en Gmail (Configuracion > Ver toda la config > "
                    "Reenvio y POP/IMAP > Habilitar IMAP)"
                ),
            )

    async def _cmd_verify(self, rest: str, context: dict[str, Any]) -> SkillResult:
        _, flags = _parse_flags(rest)
        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        ok, msg = await asyncio.to_thread(
            self._auth_manager.verify_account, account.email
        )
        return SkillResult(success=ok, message=msg)

    async def _cmd_remove(self, rest: str, context: dict[str, Any]) -> SkillResult:
        self._ensure_init()
        email_to_remove = rest.strip()
        if not email_to_remove:
            return SkillResult(success=False, message="Uso: !gmail remover <email>")

        removed = self._auth_manager.remove_account(email_to_remove)
        if removed:
            return SkillResult(success=True, message=f"Cuenta {email_to_remove} eliminada.")
        return SkillResult(
            success=False,
            message=f"Cuenta '{email_to_remove}' no encontrada.",
        )

    # ── Send ────────────────────────────────────────────────────────────

    async def _cmd_send(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)

        parts = rest.split(None, 1)
        if len(parts) < 2:
            return SkillResult(
                success=False,
                message="Uso: !gmail enviar <destinatario> <asunto> | <cuerpo> [--cuenta=email] [--adjunto=/path]",
            )

        to_addr = parts[0]
        remainder = parts[1]

        if "|" in remainder:
            subject, body = remainder.split("|", 1)
            subject = subject.strip()
            body = body.strip()
        else:
            subject = remainder.strip()
            body = ""

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        # Build MIME message
        att_path = flags.get("adjunto")
        if att_path:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body, "plain", "utf-8"))
            filepath = Path(att_path).expanduser()
            if filepath.exists():
                content_type, _ = mimetypes.guess_type(str(filepath))
                content_type = content_type or "application/octet-stream"
                with open(filepath, "rb") as f:
                    attachment = MIMEApplication(f.read())
                attachment.add_header(
                    "Content-Disposition", "attachment",
                    filename=os.path.basename(filepath.name),
                )
                msg.attach(attachment)
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["From"] = account.email
        msg["To"] = to_addr
        msg["Subject"] = subject

        # Send via SMTP
        def _send() -> None:
            ctx = ssl.create_default_context()
            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(account.email, account.app_password)
                smtp.send_message(msg)

        await asyncio.to_thread(_send)

        return SkillResult(
            success=True,
            message=f"Correo enviado a {to_addr}\nDe: {account.email}\nAsunto: {subject}",
            data={"to": to_addr, "from": account.email},
        )

    # ── Read inbox ──────────────────────────────────────────────────────

    async def _cmd_read(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        count = 5
        if rest.strip().isdigit():
            count = min(int(rest.strip()), 20)

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        def _fetch() -> tuple[list[str], list[bytes]]:
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX", readonly=True)
                _, data = imap.uid("search", None, "ALL")
                all_uids = data[0].split() if data[0] else []

                if not all_uids:
                    return [], []

                # Get last N UIDs (most recent)
                recent_uids = all_uids[-count:]
                recent_uids.reverse()  # newest first

                lines = []
                for i, uid in enumerate(recent_uids, 1):
                    _, msg_data = imap.uid("fetch", uid, "(RFC822.HEADER)")
                    if msg_data[0] is None:
                        continue
                    raw = msg_data[0][1]
                    parsed = email.message_from_bytes(raw)

                    from_addr = _decode_header(parsed.get("From", ""))
                    subject = _decode_header(parsed.get("Subject", "")) or "(sin asunto)"
                    date_raw = parsed.get("Date", "")
                    try:
                        dt = email.utils.parsedate_to_datetime(date_raw)
                        date_short = dt.strftime("%d/%m %H:%M")
                    except Exception:
                        date_short = date_raw[:16] if date_raw else "?"

                    lines.append(
                        f"{i}. [{uid.decode()}] {date_short} | {from_addr}\n"
                        f"   {subject}"
                    )

                return lines, recent_uids

        lines, uids = await asyncio.to_thread(_fetch)

        if not lines:
            return SkillResult(success=True, message=f"Inbox vacio en {account.email}")

        # Cache UIDs for quick access by index
        self._last_uids[account.email] = uids

        header = f"Inbox de {account.email} ({len(lines)} correos):\n"
        output = header + "\n".join(lines)
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + "\n... (truncado)"

        return SkillResult(success=True, message=output)

    # ── Search ──────────────────────────────────────────────────────────

    async def _cmd_search(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        query = rest.strip()
        if not query:
            return SkillResult(
                success=False,
                message=(
                    "Uso: !gmail buscar <criterio> [--cuenta=email] [--max=N]\n\n"
                    "Ejemplos de busqueda:\n"
                    "  !gmail buscar from:banco\n"
                    "  !gmail buscar subject:factura\n"
                    "  !gmail buscar Amazon\n"
                    "  !gmail buscar is:unread\n"
                    "  !gmail buscar after:2026/03/01 before:2026/03/20"
                ),
            )

        max_results = min(int(flags.get("max", "10")), 30)
        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        def _search() -> tuple[list[str], list[bytes]]:
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX", readonly=True)

                # Gmail supports X-GM-RAW for native Gmail search syntax
                try:
                    _, data = imap.uid("search", None, f'X-GM-RAW "{query}"')
                except imaplib.IMAP4.error:
                    # Fallback to standard IMAP search
                    # Try as subject search
                    _, data = imap.uid("search", None, f'(SUBJECT "{query}")')

                all_uids = data[0].split() if data[0] else []
                if not all_uids:
                    return [], []

                recent_uids = all_uids[-max_results:]
                recent_uids.reverse()

                lines = []
                for i, uid in enumerate(recent_uids, 1):
                    _, msg_data = imap.uid("fetch", uid, "(RFC822.HEADER)")
                    if msg_data[0] is None:
                        continue
                    raw = msg_data[0][1]
                    parsed = email.message_from_bytes(raw)

                    from_addr = _decode_header(parsed.get("From", ""))
                    subject = _decode_header(parsed.get("Subject", "")) or "(sin asunto)"
                    date_raw = parsed.get("Date", "")
                    try:
                        dt = email.utils.parsedate_to_datetime(date_raw)
                        date_short = dt.strftime("%d/%m %H:%M")
                    except Exception:
                        date_short = date_raw[:16] if date_raw else "?"

                    lines.append(
                        f"{i}. [{uid.decode()}] {date_short} | {from_addr}\n"
                        f"   {subject}"
                    )

                return lines, recent_uids

        lines, uids = await asyncio.to_thread(_search)

        if not lines:
            return SkillResult(
                success=True,
                message=f"Sin resultados para: {query}\n(cuenta: {account.email})",
            )

        self._last_uids[account.email] = uids

        header = f"Resultados para '{query}' en {account.email} ({len(lines)}):\n"
        output = header + "\n".join(lines)
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + "\n... (truncado)"

        return SkillResult(success=True, message=output)

    # ── View full message ───────────────────────────────────────────────

    def _resolve_uid(self, ref: str, account_email: str) -> bytes | None:
        """Resolve a reference to a UID. Accepts UID directly or index from last listing."""
        ref = ref.strip()
        cached = self._last_uids.get(account_email, [])

        # If it's a small number and we have cached UIDs, treat as index
        if ref.isdigit():
            idx = int(ref)
            if 1 <= idx <= len(cached):
                return cached[idx - 1]
            # Otherwise treat as raw UID
            return ref.encode()

        return ref.encode()

    async def _cmd_view(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        ref = rest.strip()
        if not ref:
            return SkillResult(success=False, message="Uso: !gmail ver <N> (numero del listado)")

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        uid = self._resolve_uid(ref, account.email)

        def _fetch() -> str:
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX", readonly=True)
                _, msg_data = imap.uid("fetch", uid, "(RFC822)")
                if msg_data[0] is None:
                    return f"No se encontro el correo con UID {uid.decode()}"
                raw = msg_data[0][1]
                parsed = email.message_from_bytes(raw)
                return _format_full(parsed, uid)

        output = await asyncio.to_thread(_fetch)
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + "\n... (truncado)"

        return SkillResult(success=True, message=output)

    # ── Reply ───────────────────────────────────────────────────────────

    async def _cmd_reply(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        parts = rest.split(None, 1)
        if len(parts) < 2:
            return SkillResult(
                success=False,
                message="Uso: !gmail responder <N> <mensaje>",
            )

        ref = parts[0]
        reply_body = parts[1]

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        uid = self._resolve_uid(ref, account.email)

        def _get_original() -> tuple[str, str, str, str]:
            """Returns (from, subject, message_id, references)."""
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX", readonly=True)
                _, msg_data = imap.uid("fetch", uid, "(RFC822.HEADER)")
                if msg_data[0] is None:
                    raise ValueError(f"Correo {uid.decode()} no encontrado")
                raw = msg_data[0][1]
                parsed = email.message_from_bytes(raw)
                return (
                    _decode_header(parsed.get("From", "")),
                    _decode_header(parsed.get("Subject", "")),
                    parsed.get("Message-ID", ""),
                    parsed.get("References", ""),
                )

        original_from, original_subject, message_id, references = await asyncio.to_thread(
            _get_original
        )

        # Build reply
        if not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject

        msg = MIMEText(reply_body, "plain", "utf-8")
        msg["From"] = account.email
        msg["To"] = original_from
        msg["Subject"] = subject
        if message_id:
            msg["In-Reply-To"] = message_id
            msg["References"] = f"{references} {message_id}".strip()

        def _send() -> None:
            ctx = ssl.create_default_context()
            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(account.email, account.app_password)
                smtp.send_message(msg)

        await asyncio.to_thread(_send)

        return SkillResult(
            success=True,
            message=f"Respuesta enviada a {original_from}\nAsunto: {subject}",
        )

    # ── Forward ─────────────────────────────────────────────────────────

    async def _cmd_forward(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        parts = rest.split(None, 1)
        if len(parts) < 2:
            return SkillResult(
                success=False,
                message="Uso: !gmail reenviar <N> <destinatario>",
            )

        ref = parts[0]
        to_addr = parts[1].strip()

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        uid = self._resolve_uid(ref, account.email)

        def _get_original() -> tuple[str, str, str, str]:
            """Returns (from, subject, date, body)."""
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX", readonly=True)
                _, msg_data = imap.uid("fetch", uid, "(RFC822)")
                if msg_data[0] is None:
                    raise ValueError(f"Correo {uid.decode()} no encontrado")
                raw = msg_data[0][1]
                parsed = email.message_from_bytes(raw)
                return (
                    _decode_header(parsed.get("From", "")),
                    _decode_header(parsed.get("Subject", "")),
                    parsed.get("Date", ""),
                    _extract_text(parsed),
                )

        original_from, original_subject, original_date, body = await asyncio.to_thread(
            _get_original
        )

        fwd_body = (
            f"\n\n---------- Forwarded message ----------\n"
            f"De: {original_from}\n"
            f"Fecha: {original_date}\n"
            f"Asunto: {original_subject}\n\n"
            f"{body}"
        )

        subject = (
            f"Fwd: {original_subject}"
            if not original_subject.startswith("Fwd:")
            else original_subject
        )

        msg = MIMEText(fwd_body, "plain", "utf-8")
        msg["From"] = account.email
        msg["To"] = to_addr
        msg["Subject"] = subject

        def _send() -> None:
            ctx = ssl.create_default_context()
            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(account.email, account.app_password)
                smtp.send_message(msg)

        await asyncio.to_thread(_send)

        return SkillResult(
            success=True,
            message=f"Correo reenviado a {to_addr}\nAsunto: {subject}",
        )

    # ── Trash ───────────────────────────────────────────────────────────

    async def _cmd_trash(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        ref = rest.strip()
        if not ref:
            return SkillResult(success=False, message="Uso: !gmail borrar <N>")

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        uid = self._resolve_uid(ref, account.email)

        def _trash() -> None:
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX")
                # Gmail: moving to [Gmail]/Trash
                imap.uid("store", uid, "+X-GM-LABELS", "\\Trash")
                imap.uid("store", uid, "+FLAGS", "\\Deleted")
                imap.expunge()

        await asyncio.to_thread(_trash)
        return SkillResult(success=True, message=f"Correo movido a papelera.")

    # ── Mark read/unread ────────────────────────────────────────────────

    async def _cmd_mark_read(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        ref = rest.strip()
        if not ref:
            return SkillResult(success=False, message="Uso: !gmail leido <N>")

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        uid = self._resolve_uid(ref, account.email)

        def _mark() -> None:
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX")
                imap.uid("store", uid, "+FLAGS", "\\Seen")

        await asyncio.to_thread(_mark)
        return SkillResult(success=True, message="Correo marcado como leido.")

    async def _cmd_mark_unread(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        ref = rest.strip()
        if not ref:
            return SkillResult(success=False, message="Uso: !gmail noleido <N>")

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        uid = self._resolve_uid(ref, account.email)

        def _mark() -> None:
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX")
                imap.uid("store", uid, "-FLAGS", "\\Seen")

        await asyncio.to_thread(_mark)
        return SkillResult(success=True, message="Correo marcado como no leido.")

    # ── Folders/Labels ──────────────────────────────────────────────────

    async def _cmd_folders(self, rest: str, context: dict[str, Any]) -> SkillResult:
        _, flags = _parse_flags(rest)
        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        def _list() -> list[str]:
            with _ImapSession(account.email, account.app_password) as imap:
                _, folders = imap.list()
                result = []
                for f in folders:
                    # Parse IMAP folder line: (\\HasNoChildren) "/" "INBOX"
                    decoded = f.decode("utf-8", errors="replace")
                    # Extract folder name (last quoted string or last part)
                    match = re.search(r'"([^"]*)"$', decoded)
                    if match:
                        result.append(match.group(1))
                    else:
                        parts = decoded.rsplit(" ", 1)
                        result.append(parts[-1] if parts else decoded)
                return sorted(result)

        folders = await asyncio.to_thread(_list)

        if not folders:
            return SkillResult(success=True, message="No se encontraron carpetas.")

        lines = [f"Carpetas/Labels en {account.email}:\n"]
        for folder in folders:
            lines.append(f"  - {folder}")

        return SkillResult(success=True, message="\n".join(lines))

    # ── Attachments ─────────────────────────────────────────────────────

    async def _cmd_attachments(self, rest: str, context: dict[str, Any]) -> SkillResult:
        rest, flags = _parse_flags(rest)
        ref = rest.strip()
        if not ref:
            return SkillResult(
                success=False,
                message="Uso: !gmail adjuntos <N> [--descargar]",
            )

        account, err = self._get_account(flags)
        if err:
            return SkillResult(success=False, message=err)

        uid = self._resolve_uid(ref, account.email)
        should_download = "descargar" in flags or "download" in flags

        def _fetch() -> tuple[list[dict[str, Any]], email.message.Message]:
            with _ImapSession(account.email, account.app_password) as imap:
                imap.select("INBOX", readonly=True)
                _, msg_data = imap.uid("fetch", uid, "(RFC822)")
                if msg_data[0] is None:
                    raise ValueError(f"Correo {uid.decode()} no encontrado")
                raw = msg_data[0][1]
                parsed = email.message_from_bytes(raw)
                return _list_attachments(parsed), parsed

        attachments, parsed_msg = await asyncio.to_thread(_fetch)

        if not attachments:
            return SkillResult(success=True, message="Este correo no tiene adjuntos.")

        if not should_download:
            lines = [f"Adjuntos del correo:\n"]
            for i, att in enumerate(attachments, 1):
                lines.append(f"  {i}. {att['filename']} ({att['size']}) [{att['content_type']}]")
            lines.append("\nUsa --descargar para descargarlos.")
            return SkillResult(success=True, message="\n".join(lines))

        # Download
        download_dir = _ensure_downloads_dir() / uid.decode()
        download_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []

        for att in attachments:
            part = att["part"]
            file_data = part.get_payload(decode=True)
            if not file_data:
                continue
            safe_name = os.path.basename(att["filename"])
            filepath = download_dir / safe_name
            filepath.write_bytes(file_data)
            downloaded.append(str(filepath))

        lines = [f"Adjuntos descargados a {download_dir}:\n"]
        for d in downloaded:
            lines.append(f"  - {d}")

        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"downloaded_files": downloaded},
        )

    # ── Help ────────────────────────────────────────────────────────────

    def _help(self) -> str:
        return (
            "Gmail Skill (IMAP/SMTP + App Passwords)\n"
            "Sin dependencias de Google Cloud.\n\n"
            "Configuracion:\n"
            "  !gmail auth <email> <app_password>    — Agregar cuenta\n"
            "  !gmail cuentas                        — Ver cuentas\n"
            "  !gmail verificar                      — Probar conexion\n"
            "  !gmail remover <email>                — Eliminar cuenta\n\n"
            "Correos:\n"
            "  !gmail leer [N]                       — Ultimos N correos (default 5)\n"
            "  !gmail buscar <criterio>              — Buscar correos\n"
            "  !gmail ver <N>                        — Ver correo completo (N del listado)\n"
            "  !gmail enviar <dest> <asunto> | <cuerpo>\n"
            "  !gmail responder <N> <mensaje>\n"
            "  !gmail reenviar <N> <dest>\n\n"
            "Gestion:\n"
            "  !gmail borrar <N>                     — Mover a papelera\n"
            "  !gmail leido <N>                      — Marcar como leido\n"
            "  !gmail noleido <N>                    — Marcar como no leido\n\n"
            "Otros:\n"
            "  !gmail carpetas                       — Ver carpetas/labels\n"
            "  !gmail adjuntos <N> [--descargar]     — Ver/descargar adjuntos\n\n"
            "Flags globales:\n"
            "  --cuenta=email@gmail.com              — Usar cuenta especifica\n"
            "  --adjunto=/ruta/archivo               — Adjuntar archivo al enviar\n"
            "  --max=N                               — Limite en busqueda\n\n"
            "Para obtener App Password:\n"
            "  1. Activa 2FA en tu cuenta Google\n"
            "  2. Ve a https://myaccount.google.com/apppasswords\n"
            "  3. Genera una contrasena de aplicacion\n"
            "  4. Registrala: !gmail auth tucorreo@gmail.com xxxx-xxxx-xxxx-xxxx"
        )
