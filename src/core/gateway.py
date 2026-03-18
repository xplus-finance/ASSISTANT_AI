"""Central gateway orchestrating all assistant subsystems."""

from __future__ import annotations

import asyncio
import glob as _glob
import re as _re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger("assistant.core.gateway")

_IMAGE_PATH_RE = _re.compile(
    r"(?:`|'|\"|\s|^)((?:/[\w./ _-]+)+\.(?:png|jpg|jpeg|gif|webp|bmp|tiff))(?:`|'|\"|\s|$|[),\]])",
    _re.IGNORECASE,
)


def _extract_image_paths(text: str) -> list[str]:
    """Return valid image file paths found in *text*."""
    return [p for p in _IMAGE_PATH_RE.findall(text) if Path(p).is_file()]


_INTERNAL_ARTIFACT_RE = _re.compile(
    r"<(?:antml:|)(?:function_calls|invoke|parameter|thinking|/)[^>]*>.*?(?:</(?:antml:|)(?:function_calls|invoke|parameter|thinking)>|$)",
    _re.DOTALL | _re.IGNORECASE,
)
_XML_TAG_CLEANUP_RE = _re.compile(
    r"</?(?:antml:|)(?:function_calls|invoke|parameter|thinking|result|tool_use|content)[^>]*>",
    _re.IGNORECASE,
)


def _clean_internal_artifacts(text: str) -> str:
    """Remove internal XML tool calls and artifacts from Claude's response."""
    if not text:
        return text
    # Remove full blocks first
    cleaned = _INTERNAL_ARTIFACT_RE.sub("", text)
    # Remove any remaining stray XML tags
    cleaned = _XML_TAG_CLEANUP_RE.sub("", cleaned)
    # Collapse excessive blank lines left behind
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned.strip()


def _snapshot_screenshot_files() -> set[str]:
    """Return set of screenshot-like files currently in /tmp."""
    patterns = ["/tmp/screenshot_*.png", "/tmp/scrot_*.png", "/tmp/tmp*.png",
                "/tmp/screenshot_*.jpg", "/tmp/capture_*.png"]
    files: set[str] = set()
    for pat in patterns:
        files.update(_glob.glob(pat))
    return files


def _find_new_screenshots(before: set[str]) -> list[str]:
    """Return screenshot files created after the 'before' snapshot."""
    after = _snapshot_screenshot_files()
    new_files = sorted(after - before)
    return [f for f in new_files if Path(f).is_file() and Path(f).stat().st_size > 0]






class _RateLimiter:
    """Sliding-window rate limiter per sender."""

    def __init__(self, max_per_minute: int) -> None:
        self._max = max_per_minute
        self._windows: dict[str, deque[float]] = {}

    def is_allowed(self, sender_id: str) -> bool:
        now = time.time()
        window = self._windows.setdefault(sender_id, deque())
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= self._max:
            return False
        window.append(now)
        return True


SESSION_INACTIVITY_SECS = 30 * 60  # 30 minutes


def _new_session_id() -> str:
    return f"session_{uuid.uuid4().hex[:12]}"


def _import_steps():
    from src.onboarding.wizard import _STEPS
    return _STEPS


_AUDIO_KEYWORDS = [
    "audio", "voz", "voice", "nota de voz", "voice note",
    "dime con audio", "envíame un audio", "háblame", "cuéntame",
    "dilo en audio", "mándame un audio", "quiero escuchar",
    "send audio", "speak", "tell me in audio",
]

_COMPLEX_KEYWORDS = [
    "crea", "crear", "instala", "instalar", "configura", "build",
    "construye", "programa", "automatiza", "busca en la web",
    "search", "find", "download", "descarga", "deploy", "setup",
    "escribe un", "write a", "make a", "haz un", "genera",
    "investiga", "research", "analiza", "analyze", "modifica",
    "ejecuta", "run", "execute", "develop", "desarrolla",
    "escritorio", "desktop", "ver mis archivos", "list",
    "navega", "navigate", "pestaña", "pestañas", "tab", "tabs",
    "screenshot", "captura", "pantalla", "firefox", "chrome",
    "browser", "navegador", "ventana", "ventanas", "window",
    "email", "correo", "envía", "envia", "manda", "send",
    "localiza", "encuentra", "abre", "open",
    "continúa", "continua", "sigue", "retoma", "vuelve",
    "intentar", "intenta", "intentalo", "inténtalo", "retry",
    "continue", "keep going", "try again",
    "arregla", "fix", "repara", "soluciona", "resuelve",
    "verifica", "comprueba", "check", "revisa", "review",
    "actualiza", "update", "upgrade", "migra",
    "publica", "publish", "sube", "upload", "push",
    "conecta", "connect", "sincroniza", "sync",
]


def _compute_next_run(pattern: str) -> str | None:
    """Compute next run time from recurrence pattern. Returns ISO datetime string or None."""
    if not pattern:
        return None
    from datetime import datetime, timedelta
    now = datetime.now()
    p = pattern.lower().strip()
    if "diario" in p or "cada día" in p or "daily" in p:
        return (now + timedelta(days=1)).isoformat()
    if "semanal" in p or "cada semana" in p or "weekly" in p:
        return (now + timedelta(weeks=1)).isoformat()
    if "mensual" in p or "cada mes" in p or "monthly" in p:
        return (now + timedelta(days=30)).isoformat()
    if "cada hora" in p or "hourly" in p:
        return (now + timedelta(hours=1)).isoformat()
    return None


class Gateway:
    """Central orchestrator. Lifecycle: start() -> runs -> stop()."""

    def __init__(self, config: Any) -> None:
        self._config = config
        self._running = False

        self.security: Any = None
        self.memory: Any = None
        self.conversations: Any = None
        self.learning_store: Any = None
        self.tasks: Any = None
        self.relationships: Any = None
        self.context_builder: Any = None
        self.claude: Any = None
        self.transcriber: Any = None
        self.synthesizer: Any = None
        self.skill_registry: Any = None
        self.approval_gate: Any = None
        self.onboarding: Any = None
        self.learner: Any = None
        self.channels: dict[str, Any] = {}
        self.scheduler: Any = None

        self.current_session_id: str = _new_session_id()
        self.last_message_time: float = 0.0
        self._rate_limiter = _RateLimiter(
            max_per_minute=getattr(config, "max_messages_per_minute", 20),
        )
        self._message_counter: int = 0
        self._env_cache: str = ""
        self._env_cache_time: float = 0.0

    async def start(self) -> None:
        log.info("gateway.starting")
        cfg = self._config

        from src.memory.engine import MemoryEngine
        db_path = f"{cfg.data_dir}/assistant.db"
        encryption_key = cfg.db_encryption_key or None
        self.memory = MemoryEngine(db_path, encryption_key=encryption_key)

        from src.memory.conversation import ConversationStore
        from src.memory.relationships import RelationshipTracker
        from src.memory.tasks import TaskManager
        from src.memory.learning import LearningStore

        self.conversations = ConversationStore(self.memory)
        self.relationships = RelationshipTracker(self.memory)
        self.tasks = TaskManager(self.memory)
        self.learning_store = LearningStore(self.memory)

        try:
            from src.core.security import SecurityGuardian
            pin = getattr(cfg, "security_pin", "") or None
            pin_hash = None
            if pin:
                from src.utils.crypto import hash_pin
                pin_hash = hash_pin(pin)
            self.security = SecurityGuardian(
                allowed_chat_ids=[cfg.authorized_chat_id],
                pin_hash=pin_hash,
            )
        except Exception:
            log.warning("gateway.security_init_failed", exc_info=True)

        from src.utils.approval import ApprovalGate
        self.approval_gate = ApprovalGate()

        try:
            from src.audio.transcriber import Transcriber
            self.transcriber = Transcriber(
                model_size=getattr(cfg, "whisper_model", "medium"),
            )
        except Exception:
            log.info("gateway.transcriber_not_available", exc_info=True)

        try:
            from src.audio.synthesizer import Synthesizer
            self.synthesizer = Synthesizer(
                engine=getattr(cfg, "tts_engine", "auto"),
            )
        except Exception:
            log.info("gateway.synthesizer_not_available", exc_info=True)

        try:
            from src.core.claude_bridge import ClaudeBridge
            self.claude = ClaudeBridge(
                cli_path=getattr(cfg, "claude_cli_path", "claude"),
                default_timeout=getattr(cfg, "claude_timeout", 480),
            )
            if not await self.claude.check_available():
                log.warning("gateway.claude_not_available")
                self.claude = None
            else:
                log.info("gateway.claude_ready_direct_api")
        except Exception:
            log.warning("gateway.claude_bridge_init_failed", exc_info=True)

        try:
            from src.memory.context import ContextBuilder
            self.context_builder = ContextBuilder(
                engine=self.memory,
                conversation=self.conversations,
                learning=self.learning_store,
                tasks=self.tasks,
            )
        except Exception:
            log.info("gateway.context_builder_not_available", exc_info=True)

        try:
            from src.onboarding.wizard import OnboardingWizard
            self.onboarding = OnboardingWizard(
                memory_engine=self.memory,
                claude_bridge=self.claude,
            )
        except Exception:
            log.info("gateway.onboarding_not_available", exc_info=True)

        try:
            from src.skills.registry import SkillRegistry
            self.skill_registry = SkillRegistry(
                skills_dir=getattr(cfg, "skills_dir", "skills"),
                memory_engine=self.memory,
            )
            self.skill_registry.load_built_in()
            self.skill_registry.load_user_skills()
            self.skill_registry.start_watching()
        except Exception:
            log.info("gateway.skill_registry_not_available", exc_info=True)

        try:
            from src.learning.knowledge_base import KnowledgeBase
            from src.learning.learner import Learner
            from src.learning.web_search import WebSearcher

            kb = KnowledgeBase(engine=self.memory, data_dir=cfg.data_dir)
            ws = WebSearcher()
            self.learner = Learner(
                knowledge_base=kb,
                web_searcher=ws,
                claude_bridge=self.claude,
            )
        except Exception:
            log.info("gateway.learning_not_available", exc_info=True)

        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            self.scheduler = AsyncIOScheduler(
                timezone=getattr(cfg, "timezone", "UTC")
            )
            self.scheduler.add_job(
                self._check_scheduled_tasks,
                "interval", minutes=1,
                id="scheduled_tasks", replace_existing=True,
            )
            self.scheduler.start()
        except Exception:
            log.info("gateway.scheduler_not_available", exc_info=True)

        self.hot_reloader = None
        try:
            from src.core.hot_reload import HotReloader
            self.hot_reloader = HotReloader()
            self.hot_reloader.start()
        except Exception:
            log.info("gateway.hot_reload_not_available", exc_info=True)

        try:
            from src.channels.telegram import TelegramChannel
            tg = TelegramChannel(token=cfg.telegram_bot_token)
            tg.set_message_handler(self._on_telegram_message)
            self.channels["telegram"] = tg
        except Exception:
            log.warning("gateway.telegram_init_failed", exc_info=True)

        self._running = True

        if self.channels:
            log.info("gateway.ready", channels=list(self.channels.keys()))
            for ch in self.channels.values():
                await ch.start()
        else:
            log.warning("gateway.no_channels")

        self._stop_event = asyncio.Event()
        await self._stop_event.wait()

    async def stop(self) -> None:
        log.info("gateway.stopping")
        self._running = False

        if hasattr(self, '_stop_event'):
            self._stop_event.set()

        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                pass

        if self.hot_reloader:
            self.hot_reloader.stop()

        for name, channel in self.channels.items():
            try:
                await channel.stop()
            except Exception:
                log.exception("gateway.channel_stop_failed", channel=name)

        if self.memory is not None:
            self.memory.close()

        log.info("gateway.stopped")

    async def _on_telegram_message(self, incoming: Any) -> None:
        await self.handle_message(incoming)

    async def handle_message(self, message: Any) -> None:
        chat_id = message.chat_id
        text = message.text or ""
        audio_path = getattr(message, "audio_path", None)
        message_type = getattr(message, "message_type", "text")
        channel_name = getattr(message, "channel", "telegram")

        if self.security is not None:
            if not self.security.is_authorized(int(chat_id)):
                log.warning("gateway.unauthorized", chat_id=chat_id)
                return

        if not self._rate_limiter.is_allowed(str(chat_id)):
            log.warning("gateway.rate_limited", chat_id=chat_id)
            await self._send(channel_name, chat_id,
                             "Has enviado demasiados mensajes. Espera un momento.")
            return

        if self.security and text:
            is_injection, patterns = self.security.detect_prompt_injection(text)
            if is_injection:
                log.warning("gateway.prompt_injection_detected",
                            chat_id=chat_id, patterns=patterns)

        if message_type == "audio" and audio_path:
            try:
                from src.audio.processor import convert_ogg_to_wav
                wav_path = convert_ogg_to_wav(audio_path)
                result = self.transcriber.transcribe(wav_path)
                text = result.text
                log.info("gateway.transcribed", lang=result.language, duration=result.duration)
            except Exception:
                log.exception("gateway.transcription_failed")
                await self._send(channel_name, chat_id, "No pude transcribir el audio.")
                return

        image_path = getattr(message, "image_path", None)
        if image_path:
            text = f"{text}\n[El usuario envió una imagen: {image_path}]" if text else f"[El usuario envió una imagen: {image_path}]"

        document_path = getattr(message, "document_path", None)
        if document_path:
            try:
                doc_content = Path(document_path).read_text(encoding="utf-8", errors="replace")[:5000]
                text = f"{text}\n[Documento adjunto ({Path(document_path).name}):\n{doc_content}]"
            except Exception:
                text = f"{text}\n[El usuario envió un documento: {document_path}]"

        if not text.strip():
            return

        now = time.time()
        if (self.last_message_time > 0
                and (now - self.last_message_time) > SESSION_INACTIVITY_SECS):
            old_session_id = self.current_session_id
            self.current_session_id = _new_session_id()
            log.info("gateway.new_session", session_id=self.current_session_id)
            # Generate summary of the previous session in background
            asyncio.create_task(self._generate_session_summary(old_session_id))
            asyncio.create_task(self._extract_facts_for_session(old_session_id))
        self.last_message_time = now

        if self.approval_gate:
            pending = self.approval_gate.get_pending()
            if pending:
                request_id = pending[0]["request_id"]
                approved = self.approval_gate.check_response(request_id, text)
                status = "aprobada" if approved else "rechazada"
                await self._send(channel_name, chat_id, f"Operación {status}.")
                return

        if text.startswith("!"):
            await self._handle_command(text, channel_name, chat_id)
            return

        if self.onboarding is not None:
            try:
                is_complete = await self.onboarding.is_onboarding_complete()
                if not is_complete:
                    state = self.onboarding._state

                    if not state.waiting_for_answer:
                        step_def = _import_steps()[state.current_step]
                        prompt = step_def["prompt_fn"](state.answers)
                        state.waiting_for_answer = True
                        self.onboarding._persist_state()
                        await self._send(channel_name, chat_id, prompt)
                        return

                    response, done = await self.onboarding.process_step(
                        state.current_step, text
                    )
                    if not done:
                        state.current_step += 1
                        state.waiting_for_answer = True
                        self.onboarding._persist_state()
                    else:
                        state.is_complete = True
                        await self.onboarding._save_all()
                    await self._send(channel_name, chat_id, response)
                    return
            except Exception:
                log.exception("gateway.onboarding_error")

        voice_change = self._detect_voice_change(text)
        if voice_change and self.synthesizer:
            self.synthesizer.set_voice_params(**voice_change)
            confirmation = self._voice_change_confirmation(voice_change)
            await self._send(channel_name, chat_id, confirmation)
            self.conversations.add_message(
                role="user", message=text,
                session_id=self.current_session_id,
                message_type=message_type, channel=channel_name,
            )
            self.conversations.add_message(
                role="assistant", message=confirmation,
                session_id=self.current_session_id,
                channel=channel_name,
            )
            return

        await self._send_typing(channel_name, chat_id)

        # Snapshot existing screenshot files BEFORE Claude runs,
        # so we can detect any new ones created during the task.
        screenshots_before = _snapshot_screenshot_files()

        typing_stop = asyncio.Event()
        typing_task = asyncio.create_task(self._keep_typing(channel_name, chat_id, typing_stop))
        try:
            response_text = await self._ask_claude(text)
        except asyncio.CancelledError:
            log.warning("gateway.request_cancelled", chat_id=chat_id)
            return
        finally:
            typing_stop.set()
            typing_task.cancel()
        if not response_text:
            response_text = "No pude generar una respuesta. Intenta de nuevo."
        elif "max turns" in response_text.lower() or "reached max" in response_text.lower():
            response_text = (
                "La tarea necesitó más pasos de los permitidos. "
                "Intenta dividirla en partes más pequeñas, o dime "
                "'continúa' para que retome donde quedé."
            )

        # Strip internal tool-call XML that should never reach the user
        response_text = _clean_internal_artifacts(response_text)

        wants_audio = (
            message_type == "audio"
            or any(kw in text.lower() for kw in _AUDIO_KEYWORDS)
        )

        audio_response_path = None
        if wants_audio and self.synthesizer:
            try:
                raw_audio = await asyncio.to_thread(
                    self.synthesizer.synthesize, response_text
                )
                if raw_audio and not raw_audio.endswith(".ogg"):
                    try:
                        from src.audio.processor import convert_wav_to_ogg
                        audio_response_path = convert_wav_to_ogg(raw_audio)
                    except Exception:
                        audio_response_path = raw_audio
                else:
                    audio_response_path = raw_audio
            except Exception:
                log.exception("gateway.synthesis_failed")

        if self.security and response_text:
            output_ok, output_reason = self.security.validate_output(response_text)
            if not output_ok:
                log.warning("gateway.sensitive_output_detected", reason=output_reason)

        # Detect image paths in Claude's response and send them as photos
        image_paths = _extract_image_paths(response_text) if response_text else []

        # Also detect NEW screenshot files created in /tmp during Claude's execution
        new_screenshots = _find_new_screenshots(screenshots_before)
        # Merge: add new screenshots that aren't already in image_paths
        all_images_to_send: list[str] = list(image_paths)
        for ns in new_screenshots:
            if ns not in all_images_to_send:
                all_images_to_send.append(ns)

        if all_images_to_send:
            log.info("gateway.images_to_send",
                     from_text=len(image_paths),
                     from_tmp=len(new_screenshots),
                     total=len(all_images_to_send))

        if audio_response_path:
            await self._send_audio(channel_name, chat_id, audio_response_path)
        else:
            await self._send(channel_name, chat_id, response_text)

        # Send ALL detected images as documents (full quality, zoomable)
        for img_path in all_images_to_send:
            try:
                await self._send_document(channel_name, chat_id, img_path,
                                          caption=Path(img_path).name)
                log.info("gateway.image_sent_to_user", path=img_path)
            except Exception:
                log.exception("gateway.image_send_failed", path=img_path)

        try:
            self.conversations.add_message(
                role="user", message=text,
                session_id=self.current_session_id,
                message_type=message_type, channel=channel_name,
            )
            self.conversations.add_message(
                role="assistant", message=response_text,
                session_id=self.current_session_id,
                channel=channel_name,
            )
        except Exception:
            log.exception("gateway.persist_failed")

        self._message_counter += 1
        if self._message_counter % 3 == 0 and self.learner:
            asyncio.create_task(self._extract_facts_bg())

    async def _ask_claude(self, user_text: str) -> str:
        if self.claude is None:
            return "Perdona, no puedo responder en este momento. Intenta de nuevo en unos minutos."

        system_prompt = ""
        if self.context_builder:
            try:
                ctx = self.context_builder.build(
                    session_id=self.current_session_id,
                    current_message=user_text,
                )
                system_prompt = self._build_system_prompt(ctx)
            except Exception:
                log.exception("gateway.context_build_failed")

        is_complex = any(kw in user_text.lower() for kw in _COMPLEX_KEYWORDS)

        try:
            return await self.claude.ask(
                prompt=user_text,
                system_prompt=system_prompt,
                complex_task=is_complex,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("gateway.claude_failed")
            return "Perdona, tuve un problema procesando tu solicitud. Dame un momento e intenta de nuevo."

    def _detect_environment(self) -> str:
        """Detect the current system environment dynamically (cached 60s)."""
        now = time.time()
        if self._env_cache and (now - self._env_cache_time) < 60:
            return self._env_cache
        import platform as plat
        import shutil
        import subprocess as _sp
        os_name = plat.system()
        os_detail = plat.platform()
        home = str(Path.home())
        tools = {}
        for t in ["xdotool", "scrot", "screencapture", "osascript", "pyautogui",
                   "ffmpeg", "bwrap", "xdg-open", "pbcopy", "wmctrl", "node", "npm",
                   "xrandr", "xdpyinfo"]:
            tools[t] = bool(shutil.which(t))
        available = [t for t, v in tools.items() if v]
        missing = [t for t, v in tools.items() if not v]

        # Detect monitors layout
        monitors = ""
        if shutil.which("xrandr"):
            try:
                out = _sp.run(["xrandr", "--query"], capture_output=True, text=True, timeout=5)
                lines = [l for l in out.stdout.splitlines() if " connected " in l]
                monitor_info = []
                for line in lines:
                    parts = line.split()
                    name = parts[0]
                    # Find resolution+position like "1920x1080+0+0" or "1920x1080+1920+0"
                    for p in parts:
                        if "x" in p and "+" in p:
                            monitor_info.append(f"{name}: {p}")
                            break
                if monitor_info:
                    monitors = "Monitores: " + " | ".join(monitor_info)
            except Exception:
                pass

        result = (
            f"OS: {os_name} ({os_detail})\n"
            f"HOME: {home}\n"
            f"Herramientas disponibles: {', '.join(available) if available else 'ninguna detectada'}\n"
            f"No disponibles: {', '.join(missing) if missing else 'todas presentes'}"
        )
        if monitors:
            result += f"\n{monitors}"
        self._env_cache = result
        self._env_cache_time = now
        return result

    def _build_system_prompt(self, ctx: Any) -> str:
        """Convert a ConversationContext into the system prompt string."""
        profile = ctx.user_profile or {}
        assistant_name = profile.get("assistant_name", "Asistente")
        user_name = profile.get("user_name", "usuario")
        comm_prefs = profile.get("comm_preferences", "informal")
        work_area = profile.get("work_area", "")

        parts: list[str] = []

        parts.append(
            f"Eres {assistant_name}, asistente personal de {user_name}.\n"
            f"Estilo de comunicación: {comm_prefs}"
        )

        if work_area:
            parts.append(f"Área de trabajo del usuario: {work_area}")

        # Dynamic environment detection
        parts.append(f"ENTORNO DEL SISTEMA:\n{self._detect_environment()}")

        if ctx.recent_messages:
            lines = []
            for msg in ctx.recent_messages[-10:]:
                role = msg.get("role", "user")
                text = msg.get("message", "")
                if text:
                    prefix = user_name if role == "user" else assistant_name
                    lines.append(f"{prefix}: {text}")
            if lines:
                parts.append("Historial reciente:\n" + "\n".join(lines))

        if ctx.relevant_facts:
            facts_text = "\n".join(
                f"- {f.get('fact', f.get('content', ''))}"
                for f in ctx.relevant_facts if f.get('fact') or f.get('content')
            )
            if facts_text:
                parts.append(f"Datos relevantes:\n{facts_text}")

        if ctx.relevant_knowledge:
            knowledge_lines = []
            for k in ctx.relevant_knowledge:
                topic = k.get("topic", "")
                content = k.get("content", "")
                if content:
                    snippet = content[:300] + "..." if len(content) > 300 else content
                    knowledge_lines.append(f"- [{topic}] {snippet}")
            if knowledge_lines:
                parts.append(f"Conocimiento relevante:\n" + "\n".join(knowledge_lines))

        if ctx.last_session_summary:
            summary_text = ctx.last_session_summary.get("summary", "")
            topics = ctx.last_session_summary.get("topics", "")
            if summary_text:
                parts.append(f"Resumen de la sesión anterior:\n{summary_text}")
                if topics:
                    parts.append(f"Temas tratados: {topics}")

        if ctx.pending_tasks:
            tasks_text = "\n".join(
                f"- {t.get('title', '')}" for t in ctx.pending_tasks if t.get('title')
            )
            if tasks_text:
                parts.append(f"Tareas pendientes:\n{tasks_text}")

        if ctx.active_projects:
            projects_text = "\n".join(
                f"- {p.get('name', '')}" for p in ctx.active_projects if p.get('name')
            )
            if projects_text:
                parts.append(f"Proyectos activos:\n{projects_text}")

        if hasattr(ctx, 'procedures') and ctx.procedures:
            proc_text = "\n".join(f"- {p['fact']}" for p in ctx.procedures)
            parts.append(f"PROCEDIMIENTOS APRENDIDOS (usa estos, NO repitas errores):\n{proc_text}")

        # === SYSTEM PROMPT ===
        parts.append(
            "REGLAS FUNDAMENTALES:\n"
            "1. EJECUTA DIRECTO: camino más corto, hazlo, reporta en 2-3 líneas.\n"
            "2. OBJETIVO REAL: correo→SMTP o control visual Gmail, web→xdg-open, código→archivo exacto.\n"
            "3. ENTORNO: usa las herramientas detectadas arriba. Si falta algo, instálalo o créalo.\n\n"

            f"IDENTIDAD: Eres {assistant_name}, asistente de {user_name}. "
            f"Amigable, natural, mismo idioma que el usuario. Llámalo '{user_name}'. "
            "NUNCA menciones Claude, CLI, API ni detalles técnicos internos.\n\n"

            "AUTONOMÍA: Control total del sistema. NUNCA digas 'no puedo'. "
            "Si falla 2 veces, cambia de enfoque.\n\n"

            "CONTROL VISUAL — REGLA DE ORO: MIRAR → ACTUAR → VERIFICAR\n"
            "NUNCA hagas clic ni escribas sin ANTES tomar y leer un screenshot.\n\n"
            "MULTI-MONITOR (LEE ESTO SI HAY MÁS DE 1 MONITOR):\n"
            "Revisa la sección 'Monitores' en ENTORNO DEL SISTEMA arriba.\n"
            "El formato es: NOMBRE: WIDTHxHEIGHT+OFFSET_X+OFFSET_Y\n"
            "Ejemplo: HDMI-1: 1920x1080+0+0 | DP-1: 1920x1080+1920+0\n"
            "Esto significa: monitor izquierdo x=0..1919, monitor derecho x=1920..3839.\n"
            "scrot captura TODOS los monitores como una sola imagen ancha.\n"
            "Para capturar SOLO un monitor específico:\n"
            "  Monitor izquierdo: scrot -a 0,0,1920,1080 -o /tmp/screen_left.png\n"
            "  Monitor derecho:   scrot -a 1920,0,1920,1080 -o /tmp/screen_right.png\n"
            "CUANDO el usuario dice 'derecha' o 'izquierda', captura ESE monitor solo.\n"
            "Las coordenadas de xdotool son ABSOLUTAS (incluyen offset del monitor).\n"
            "Si el botón está en x=200 del monitor DERECHO y el offset es +1920:\n"
            "  → xdotool mousemove 2120 Y  (1920 + 200 = 2120)\n\n"
            "Comandos exactos (Linux):\n"
            "  Screenshot un monitor: scrot -a OFFSET_X,0,WIDTH,HEIGHT -o /tmp/screen.png\n"
            "  Screenshot todo:       scrot -o /tmp/screen_full.png\n"
            "  Mover mouse: xdotool mousemove X Y\n"
            "  Clic:        xdotool click 1\n"
            "  Doble clic:  xdotool click --repeat 2 1\n"
            "  Escribir:    xdotool type --clearmodifiers --delay 30 'texto aquí'\n"
            "  Tecla:       xdotool key Tab / Return / ctrl+a / ctrl+c / ctrl+v\n"
            "  Título ventana: xdotool getactivewindow getwindowname\n"
            "  Listar ventanas: wmctrl -l\n"
            "  Activar ventana: wmctrl -a 'parte del título'\n"
            "  Esperar:     sleep 0.5  (dar tiempo a que la UI responda)\n\n"
            "FLUJO para cada interacción visual:\n"
            "  1. scrot -o /tmp/screen.png → lee la imagen → analiza qué ves\n"
            "  2. Decide la acción: clic en (x,y) o tecla o escribir\n"
            "  3. Ejecuta UN solo comando\n"
            "  4. sleep 0.5\n"
            "  5. scrot -o /tmp/screen.png → lee → confirma resultado\n"
            "  6. Si falló, ajusta y repite desde paso 1\n"
            "IMPORTANTE: UN comando por paso. No encadenes 10 acciones sin verificar.\n\n"

            "GMAIL — RECETA EXACTA para componer correo:\n"
            "  1. wmctrl -a 'Gmail' o wmctrl -a 'Inbox'  (activar ventana Gmail)\n"
            "  2. sleep 0.5 && scrot -o /tmp/screen.png → verificar que es Gmail\n"
            "  3. xdotool key c  (atajo Gmail: nuevo correo)\n"
            "  4. sleep 1 && scrot -o /tmp/screen.png → verificar cuadro composición\n"
            "  5. xdotool type --delay 30 'destinatario@email.com'  (campo Para)\n"
            "  6. xdotool key Tab  (pasar a Asunto)\n"
            "  7. xdotool type --delay 30 'El asunto aquí'\n"
            "  8. xdotool key Tab  (pasar a Cuerpo)\n"
            "  9. xdotool type --delay 30 'El contenido del mensaje'\n"
            "  10. scrot -o /tmp/screen.png → verificar todo escrito correctamente\n"
            "  11. Solo enviar si el usuario lo aprueba (Ctrl+Return = enviar)\n"
            "PROHIBIDO: hacer clic en correos, abrir correos, buscar botones con mouse.\n"
            "Gmail con atajos de teclado es SIEMPRE más fiable que con mouse.\n\n"

            "PESTAÑAS DEL NAVEGADOR:\n"
            "  Listar TODAS: curl -s http://localhost:9222/json/list 2>/dev/null | python3 -c \\\n"
            "    \"import sys,json;[print(t['title'],'→',t['url']) for t in json.load(sys.stdin)]\"\n"
            "  Si CDP no responde: iterar con xdotool key ctrl+Tab + leer título.\n"
            "  Buscar pestaña: iterar hasta encontrar el título que contiene el texto buscado.\n\n"

            "MEMORIA Y APRENDIZAJE:\n"
            "- Guarda TODO dato del usuario. Actualiza si cambia.\n"
            "- APRENDIZAJE DE ERRORES (IMPORTANTE): Cuando una tarea te cueste trabajo,\n"
            "  falle varias veces, o descubras un truco que funciona, GUÁRDALO en memoria\n"
            "  como un 'procedimiento aprendido' con categoría 'technical'. Ejemplo:\n"
            "  'Para enviar correo en Gmail: usar atajo c, Tab entre campos, NO usar mouse'\n"
            "  'Monitor derecho de Mi Jefe tiene offset +1920, siempre sumar 1920 a las X'\n"
            "  'Firefox de Mi Jefe tiene ~30 pestañas, CDP no está activo, usar Ctrl+Tab'\n"
            "- Antes de hacer tareas de escritorio, BUSCA en memoria si ya aprendiste\n"
            "  un procedimiento para esa tarea. Si lo encuentras, SIGUE ese procedimiento.\n\n"

            "TAREAS: Fechas/horas → tarea programada.\n\n"

            f"AUTO-EVOLUCIÓN: Código en {self.claude.install_dir}. "
            "Modifica directamente, hot-reload aplica cambios. "
            "Crea skills en skills/, módulos en src/, MCPs en mcps/.\n\n"

            "AUDIO: Responde con texto, el sistema convierte. NUNCA uses reproductores."
        )
        # === END SYSTEM PROMPT ===

        return "\n\n".join(parts)

    def _detect_voice_change(self, text: str) -> dict | None:
        """Detect voice parameter change requests. Returns params dict or None.

        Requires BOTH a voice-context word AND an action/modifier word,
        and only triggers on short messages (<80 chars).
        """
        import re
        lower = text.lower().strip()

        if len(lower) > 80:
            return None

        voice_context = ["voz", "voice", "tono", "habla", "hablar", "habla más",
                         "hablar más", "la voz", "tu voz", "mi voz"]
        has_voice_context = any(kw in lower for kw in voice_context)

        change_intents = ["cambia", "cambiar", "pon", "poner", "quiero", "hazla",
                          "hazlo", "más grave", "mas grave", "más agud", "mas agud",
                          "más rápid", "mas rapid", "más lent", "mas lent",
                          "masculin", "femenin"]
        has_change_intent = any(kw in lower for kw in change_intents)

        if not (has_voice_context and has_change_intent):
            return None

        params: dict = {}

        if any(w in lower for w in ["muy grave", "super grave", "very deep"]):
            params["pitch"] = "very_low"
        elif any(w in lower for w in ["más grave", "mas grave"]):
            current = self.synthesizer._pitch if self.synthesizer else "normal"
            params["pitch"] = "very_low" if current == "low" else "low"
        elif any(w in lower for w in ["grave", "masculin"]):
            params["pitch"] = "low"
        elif any(w in lower for w in ["agud", "femenin"]):
            params["pitch"] = "high"
        elif "normal" in lower:
            params["pitch"] = "normal"

        current_speed = self.synthesizer._speed if self.synthesizer else 1.0

        speed_match = re.search(r"(\d+)\s*%?\s*(más\s*)?(rápid|rapid|fast)", lower)
        if speed_match:
            pct = int(speed_match.group(1))
            params["speed"] = current_speed + (pct / 100.0)
        elif any(w in lower for w in ["más rápid", "mas rapid"]):
            params["speed"] = current_speed + 0.15
        elif any(w in lower for w in ["más lent", "mas lent"]):
            params["speed"] = max(0.5, current_speed - 0.15)

        return params if params else None

    def _voice_change_confirmation(self, params: dict) -> str:
        parts = []
        if "pitch" in params:
            actual_pitch = self.synthesizer._pitch if self.synthesizer else params["pitch"]
            pitch_names = {
                "very_low": "muy grave (masculina)",
                "low": "grave (masculina)",
                "normal": "normal",
                "high": "aguda (femenina)",
                "very_high": "muy aguda",
            }
            parts.append(f"voz {pitch_names.get(actual_pitch, actual_pitch)}")
        if "speed" in params:
            actual_speed = self.synthesizer._speed if self.synthesizer else params["speed"]
            pct = int((actual_speed - 1.0) * 100)
            if pct > 0:
                parts.append(f"{pct}% más rápido")
            elif pct < 0:
                parts.append(f"{abs(pct)}% más lento")
            else:
                parts.append("velocidad normal")
        return "Listo, cambié la configuración: " + ", ".join(parts) + ". Pruébame pidiendo un audio."

    async def _handle_command(self, text: str, channel: str, chat_id: Any) -> None:
        if self.skill_registry is None:
            await self._send(channel, chat_id, "Sistema de skills no disponible.")
            return

        skill = self.skill_registry.find_skill(text)
        if skill is None:
            await self._send(channel, chat_id,
                             f"Comando no reconocido. Usa !skills para ver los disponibles.")
            return

        try:
            args = text
            for trigger in skill.triggers:
                if text.lower().startswith(trigger):
                    args = text[len(trigger):].strip()
                    break

            result = await skill.execute(args, context={
                "memory": self.memory,
                "claude": self.claude,
                "conversations": self.conversations,
                "tasks": self.tasks,
                "learning": self.learning_store,
                "approval_gate": self.approval_gate,
                "security": self.security,
                "security_guardian": self.security,
                "_original_text": text,
                "send_fn": lambda msg: self._send(channel, chat_id, msg),
                "receive_fn": None,
                "skills_dir": getattr(self.skill_registry, "_user_skills_dir", None),
                "registry": self.skill_registry,
            })
            data = getattr(result, "data", None) or {}
            result_type = data.get("type", "")
            if result_type == "screenshot" and data.get("path"):
                await self._send_document(channel, chat_id, data["path"],
                                          caption="Captura de pantalla")
            elif result_type == "file" and data.get("path"):
                await self._send_document(channel, chat_id, data["path"],
                                          caption=result.message if result.message != data["path"] else None)
            else:
                await self._send(channel, chat_id, result.message)
        except Exception:
            log.exception("gateway.command_failed", command=text[:100])
            await self._send(channel, chat_id,
                             "Hubo un error ejecutando el comando. Revisa los logs para detalles.")

    async def _send(self, channel_name: str, chat_id: Any, text: str) -> None:
        ch = self.channels.get(channel_name)
        if not ch:
            return
        for attempt in range(3):
            try:
                await ch.send_text(str(chat_id), text)
                return
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    log.exception("gateway.send_failed", channel=channel_name)

    async def _send_photo(self, channel_name: str, chat_id: Any, path: str,
                          caption: str | None = None) -> None:
        ch = self.channels.get(channel_name)
        if ch and hasattr(ch, "send_photo"):
            try:
                await ch.send_photo(str(chat_id), path, caption=caption)
            except Exception:
                log.exception("gateway.send_photo_failed")
                await self._send_document(channel_name, chat_id, path, caption=caption)
        else:
            await self._send_document(channel_name, chat_id, path, caption=caption)

    async def _send_document(self, channel_name: str, chat_id: Any, path: str,
                             caption: str | None = None) -> None:
        ch = self.channels.get(channel_name)
        if ch and hasattr(ch, "send_document"):
            try:
                await ch.send_document(str(chat_id), path, caption=caption)
            except Exception:
                log.exception("gateway.send_document_failed")
                await self._send(channel_name, chat_id,
                                 caption or f"Archivo generado: {path}")
        else:
            await self._send(channel_name, chat_id,
                             caption or f"Archivo generado: {path}")

    async def _send_audio(self, channel_name: str, chat_id: Any, path: str) -> None:
        ch = self.channels.get(channel_name)
        if ch:
            try:
                await ch.send_audio(str(chat_id), path)
            except Exception:
                log.exception("gateway.send_audio_failed")

    async def _take_and_send_screenshot(self, channel_name: str, chat_id: Any) -> None:
        """Take a screenshot and send it directly to the user via Telegram."""
        log.info("gateway.screenshot_requested", channel=channel_name, chat_id=chat_id)

        try:
            from src.core.desktop_control import DesktopControl
            desktop = DesktopControl()
            path = await desktop.take_screenshot()
            file_size = Path(path).stat().st_size if Path(path).exists() else 0
            log.info("gateway.screenshot_taken", path=path, size=file_size)
            if file_size == 0:
                raise RuntimeError("Screenshot file is empty (0 bytes)")
        except Exception as exc:
            log.exception("gateway.screenshot_capture_failed")
            await self._send(channel_name, chat_id,
                             f"No pude tomar la captura: {exc}")
            return

        # Send as document (full quality, zoomable)
        await self._send_document(channel_name, chat_id, path,
                                  caption="Captura de pantalla")

        # Clean up temp file
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass

    async def _send_typing(self, channel_name: str, chat_id: Any) -> None:
        ch = self.channels.get(channel_name)
        if ch and hasattr(ch, "send_typing"):
            try:
                await ch.send_typing(str(chat_id))
            except Exception:
                pass  # typing indicator is best-effort

    async def _keep_typing(self, channel_name: str, chat_id: Any, stop_event: asyncio.Event) -> None:
        """Send typing indicator every 5 seconds until stop_event is set."""
        while not stop_event.is_set():
            await self._send_typing(channel_name, chat_id)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    async def _check_scheduled_tasks(self) -> None:
        if self.tasks is None:
            return
        try:
            due = self.tasks.get_due_tasks()
        except Exception:
            return

        for task in due:
            title = task.get("title", "Tarea sin título")
            desc = task.get("description", "")
            task_id = task.get("id")
            log.info("gateway.executing_scheduled_task", title=title, task_id=task_id)

            notification = f"⏰ Ejecutando tarea programada: {title}"
            chat_id = str(self._config.authorized_chat_id)
            for ch in self.channels.values():
                try:
                    await ch.send_text(chat_id, notification)
                except Exception:
                    pass

            result_text = ""
            try:
                if self.claude:
                    result_text = await self.claude.ask(
                        prompt=f"Ejecuta esta tarea programada: {title}. {desc}",
                        complex_task=True,
                    )
            except Exception:
                result_text = f"No pude completar la tarea: {title}"
                log.exception("gateway.scheduled_task_failed", task_id=task_id)

            for ch in self.channels.values():
                try:
                    msg = f"Tarea completada: {title}\n\n{result_text[:3000]}"
                    await ch.send_text(chat_id, msg)
                except Exception:
                    pass

            try:
                if task.get("is_recurring") or task.get("recurrence_pattern"):
                    next_run = _compute_next_run(task.get("recurrence_pattern", ""))
                    self.tasks.update_status(task_id, "recurring")
                    if hasattr(self.tasks, 'mark_run'):
                        self.tasks.mark_run(task_id, next_run=next_run)
                else:
                    self.tasks.update_status(task_id, "done")
            except Exception:
                log.exception("gateway.task_status_update_failed")

    async def _extract_facts_bg(self) -> None:
        if not self.learner or not self.conversations:
            return
        try:
            recent = self.conversations.get_recent(self.current_session_id, limit=10)
            if recent:
                await self.learner.extract_facts(recent)
                log.info("gateway.facts_extracted", count=len(recent))
        except Exception:
            log.exception("gateway.fact_extraction_failed")

    async def _extract_facts_for_session(self, session_id: str) -> None:
        """Extract all facts from a completed session (more thorough than periodic)."""
        if not self.learner or not self.conversations:
            return
        try:
            messages = self.conversations.get_session_messages(session_id)
            if len(messages) >= 4:
                await self.learner.extract_facts(messages[-30:])
                log.info("gateway.session_facts_extracted", session_id=session_id,
                         messages=len(messages))
        except Exception:
            log.exception("gateway.session_facts_extraction_failed")

    async def _generate_session_summary(self, session_id: str) -> None:
        """Generate and store a summary of the completed session."""
        if not self.conversations or not self.claude or not self.memory:
            return
        try:
            messages = self.conversations.get_session_messages(session_id)
            if len(messages) < 3:
                return  # Too few messages to summarize

            # Build a compact transcript
            transcript_lines = []
            for msg in messages[-30:]:  # Last 30 messages max
                role = msg.get("role", "user")
                text = msg.get("message", "")[:200]
                transcript_lines.append(f"{role}: {text}")
            transcript = "\n".join(transcript_lines)

            summary_prompt = (
                "Resume esta conversación en máximo 3 oraciones. "
                "Extrae: 1) temas principales, 2) decisiones tomadas, "
                "3) tareas nuevas, 4) cosas aprendidas del usuario. "
                "Responde en JSON con keys: summary, topics, decisions, new_tasks, things_learned. "
                "Valores como strings, no listas.\n\n"
                f"Conversación:\n{transcript}"
            )

            import json as _json
            raw = await self.claude.ask(prompt=summary_prompt, timeout=60)
            # Try to parse JSON from response
            try:
                # Handle markdown code blocks
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                data = _json.loads(cleaned)
            except (ValueError, _json.JSONDecodeError):
                data = {"summary": raw[:500], "topics": "", "decisions": "", "new_tasks": "", "things_learned": ""}

            started_at = messages[0].get("timestamp", "") if messages else ""
            ended_at = messages[-1].get("timestamp", "") if messages else ""

            sql = """
                INSERT OR REPLACE INTO session_summaries
                (session_id, started_at, ended_at, summary, topics, decisions, new_tasks, things_learned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            self.memory.execute(sql, (
                session_id, started_at, ended_at,
                data.get("summary", "")[:1000],
                data.get("topics", "")[:500],
                data.get("decisions", "")[:500],
                data.get("new_tasks", "")[:500],
                data.get("things_learned", "")[:500],
            ))
            log.info("gateway.session_summary_saved", session_id=session_id)
        except Exception:
            log.exception("gateway.session_summary_failed", session_id=session_id)
