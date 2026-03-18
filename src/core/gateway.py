"""
Central orchestrator for the Personal AI Assistant.

The Gateway ties together every subsystem — security, memory, AI bridge,
channels, learning, skills — and implements the main message-processing
pipeline.  All inbound messages flow through ``handle_message``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from typing import Any

import structlog

log = structlog.get_logger("assistant.core.gateway")


# ---------------------------------------------------------------------------
# Rate limiter (sliding-window per sender)
# ---------------------------------------------------------------------------

class _RateLimiter:
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
    "email", "correo", "localiza", "encuentra", "abre",
]


def _compute_next_run(pattern: str) -> str | None:
    """Compute next run time from recurrence pattern. Returns ISO datetime string or None."""
    return None  # TODO: implement recurrence parsing


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

class Gateway:
    """Central orchestrator. Lifecycle: start() → runs → stop()."""

    def __init__(self, config: Any) -> None:
        self._config = config
        self._running = False

        # All subsystems — initialized in start()
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        log.info("gateway.starting")
        cfg = self._config

        # -- Database / memory
        from src.memory.engine import MemoryEngine
        db_path = f"{cfg.data_dir}/assistant.db"
        encryption_key = cfg.db_encryption_key or None
        self.memory = MemoryEngine(db_path, encryption_key=encryption_key)

        # -- Memory stores
        from src.memory.conversation import ConversationStore
        from src.memory.relationships import RelationshipTracker
        from src.memory.tasks import TaskManager
        from src.memory.learning import LearningStore

        self.conversations = ConversationStore(self.memory)
        self.relationships = RelationshipTracker(self.memory)
        self.tasks = TaskManager(self.memory)
        self.learning_store = LearningStore(self.memory)

        # -- Security
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

        # -- Approval gate
        from src.utils.approval import ApprovalGate
        self.approval_gate = ApprovalGate()

        # -- Audio (lazy init)
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

        # -- Claude bridge
        try:
            from src.core.claude_bridge import ClaudeBridge
            self.claude = ClaudeBridge(
                cli_path=getattr(cfg, "claude_cli_path", "claude"),
                default_timeout=getattr(cfg, "claude_timeout", 120),
            )
            if not await self.claude.check_available():
                log.warning("gateway.claude_not_available")
                self.claude = None
            else:
                log.info("gateway.claude_ready_direct_api")
        except Exception:
            log.warning("gateway.claude_bridge_init_failed", exc_info=True)

        # -- Context builder
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

        # -- Onboarding
        try:
            from src.onboarding.wizard import OnboardingWizard
            self.onboarding = OnboardingWizard(
                memory_engine=self.memory,
                claude_bridge=self.claude,
            )
        except Exception:
            log.info("gateway.onboarding_not_available", exc_info=True)

        # -- Skills
        try:
            from src.skills.registry import SkillRegistry
            self.skill_registry = SkillRegistry(
                skills_dir=getattr(cfg, "skills_dir", "skills"),
                memory_engine=self.memory,
            )
        except Exception:
            log.info("gateway.skill_registry_not_available", exc_info=True)

        # -- Learning
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

        # -- Scheduler
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

        # -- Hot-reload
        self.hot_reloader = None
        try:
            from src.core.hot_reload import HotReloader
            self.hot_reloader = HotReloader()
            self.hot_reloader.start()
        except Exception:
            log.info("gateway.hot_reload_not_available", exc_info=True)

        # -- Telegram channel
        try:
            from src.channels.telegram import TelegramChannel
            tg = TelegramChannel(token=cfg.telegram_bot_token)
            tg.set_message_handler(self._on_telegram_message)
            self.channels["telegram"] = tg
        except Exception:
            log.warning("gateway.telegram_init_failed", exc_info=True)

        self._running = True

        # Start all channels
        if self.channels:
            log.info("gateway.ready", channels=list(self.channels.keys()))
            for ch in self.channels.values():
                await ch.start()
        else:
            log.warning("gateway.no_channels")

        # Keep alive — wait until stop() is called
        self._stop_event = asyncio.Event()
        await self._stop_event.wait()

    async def stop(self) -> None:
        log.info("gateway.stopping")
        self._running = False

        # Unblock the keep-alive wait
        if hasattr(self, '_stop_event'):
            self._stop_event.set()

        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                pass

        # Stop hot-reloader
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

    # ------------------------------------------------------------------
    # Telegram message adapter
    # ------------------------------------------------------------------

    async def _on_telegram_message(self, incoming: Any) -> None:
        """Adapter: converts IncomingMessage from telegram.py to handle_message."""
        await self.handle_message(incoming)

    # ------------------------------------------------------------------
    # Main message pipeline
    # ------------------------------------------------------------------

    async def handle_message(self, message: Any) -> None:
        """Process an inbound message end-to-end."""

        chat_id = message.chat_id
        text = message.text or ""
        audio_path = getattr(message, "audio_path", None)
        message_type = getattr(message, "message_type", "text")
        channel_name = getattr(message, "channel", "telegram")

        # -- Authorization
        if self.security is not None:
            if not self.security.is_authorized(int(chat_id)):
                log.warning("gateway.unauthorized", chat_id=chat_id)
                return

        # -- Rate limiting
        if not self._rate_limiter.is_allowed(str(chat_id)):
            log.warning("gateway.rate_limited", chat_id=chat_id)
            await self._send(channel_name, chat_id,
                             "Has enviado demasiados mensajes. Espera un momento.")
            return

        # -- Prompt injection detection (log only — owner has full control)
        if self.security and text:
            is_injection, patterns = self.security.detect_prompt_injection(text)
            if is_injection:
                log.warning("gateway.prompt_injection_detected",
                            chat_id=chat_id, patterns=patterns)

        # -- Audio transcription
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

        if not text.strip():
            return

        # -- Session management
        now = time.time()
        if (self.last_message_time > 0
                and (now - self.last_message_time) > SESSION_INACTIVITY_SECS):
            self.current_session_id = _new_session_id()
            log.info("gateway.new_session", session_id=self.current_session_id)
        self.last_message_time = now

        # -- Pending approval response
        if self.approval_gate:
            pending = self.approval_gate.get_pending()
            if pending:
                request_id = pending[0]["request_id"]
                approved = self.approval_gate.check_response(request_id, text)
                status = "aprobada" if approved else "rechazada"
                await self._send(channel_name, chat_id, f"Operación {status}.")
                return

        # -- Command routing
        if text.startswith("!"):
            await self._handle_command(text, channel_name, chat_id)
            return

        # -- Onboarding
        if self.onboarding is not None:
            try:
                is_complete = await self.onboarding.is_onboarding_complete()
                if not is_complete:
                    state = self.onboarding._state

                    if not state.waiting_for_answer:
                        # First contact or question not yet sent — send the question
                        step_def = _import_steps()[state.current_step]
                        prompt = step_def["prompt_fn"](state.answers)
                        state.waiting_for_answer = True
                        self.onboarding._persist_state()
                        await self._send(channel_name, chat_id, prompt)
                        return

                    # User is responding to a question — process the answer
                    response, done = await self.onboarding.process_step(
                        state.current_step, text
                    )
                    if not done:
                        state.current_step += 1
                        state.waiting_for_answer = True  # next question included in response
                        self.onboarding._persist_state()
                    else:
                        state.is_complete = True
                        await self.onboarding._save_all()
                    await self._send(channel_name, chat_id, response)
                    return
            except Exception:
                log.exception("gateway.onboarding_error")

        # -- Voice parameter changes (local, no Claude needed)
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

        # -- Typing indicator
        await self._send_typing(channel_name, chat_id)

        # -- Claude conversation
        try:
            response_text = await self._ask_claude(text)
        except asyncio.CancelledError:
            log.warning("gateway.request_cancelled", chat_id=chat_id)
            return  # Shutdown o cancelación externa — salir limpiamente
        if not response_text:
            response_text = "No pude generar una respuesta. Intenta de nuevo."
        elif "max turns" in response_text.lower() or "reached max" in response_text.lower():
            response_text = (
                "La tarea necesitó más pasos de los permitidos. "
                "Intenta dividirla en partes más pequeñas, o dime "
                "'continúa' para que retome donde quedé."
            )

        # -- Detect if user wants audio response
        wants_audio = (
            message_type == "audio"
            or any(kw in text.lower() for kw in _AUDIO_KEYWORDS)
        )

        # -- Audio synthesis
        audio_response_path = None
        if wants_audio and self.synthesizer:
            try:
                raw_audio = await asyncio.to_thread(
                    self.synthesizer.synthesize, response_text
                )
                # Convert to OGG/Opus for Telegram voice notes
                if raw_audio and not raw_audio.endswith(".ogg"):
                    try:
                        from src.audio.processor import convert_wav_to_ogg
                        audio_response_path = convert_wav_to_ogg(raw_audio)
                    except Exception:
                        audio_response_path = raw_audio  # Send as-is
                else:
                    audio_response_path = raw_audio
            except Exception:
                log.exception("gateway.synthesis_failed")

        # -- Scan output for accidentally leaked secrets
        if self.security and response_text:
            output_ok, output_reason = self.security.validate_output(response_text)
            if not output_ok:
                log.warning("gateway.sensitive_output_detected", reason=output_reason)

        # -- Reply
        if audio_response_path:
            await self._send_audio(channel_name, chat_id, audio_response_path)
        else:
            await self._send(channel_name, chat_id, response_text)

        # -- Persist to memory
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

        # -- Periodic fact extraction (every 5 messages)
        self._message_counter += 1
        if self._message_counter % 5 == 0 and self.learner:
            asyncio.create_task(self._extract_facts_bg())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _ask_claude(self, user_text: str) -> str:
        """Build context, call Claude CLI, return response."""
        if self.claude is None:
            return "Perdona, no puedo responder en este momento. Intenta de nuevo en unos minutos."

        # Build context
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

        # Detect if this is a complex task that needs more autonomy
        is_complex = any(kw in user_text.lower() for kw in _COMPLEX_KEYWORDS)

        try:
            return await self.claude.ask(
                prompt=user_text,
                system_prompt=system_prompt,
                complex_task=is_complex,
            )
        except asyncio.CancelledError:
            raise  # No swallowear — dejar que se propague ordenadamente
        except Exception:
            log.exception("gateway.claude_failed")
            return "Perdona, tuve un problema procesando tu solicitud. Dame un momento e intenta de nuevo."

    def _build_system_prompt(self, ctx: Any) -> str:
        """Convert a ConversationContext into a clean system prompt string."""
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

        # Recent conversation history
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

        # Relevant facts
        if ctx.relevant_facts:
            facts_text = "\n".join(
                f"- {f.get('fact', f.get('content', ''))}"
                for f in ctx.relevant_facts if f.get('fact') or f.get('content')
            )
            if facts_text:
                parts.append(f"Datos relevantes:\n{facts_text}")

        # Pending tasks
        if ctx.pending_tasks:
            tasks_text = "\n".join(
                f"- {t.get('title', '')}" for t in ctx.pending_tasks if t.get('title')
            )
            if tasks_text:
                parts.append(f"Tareas pendientes:\n{tasks_text}")

        # Active projects
        if ctx.active_projects:
            projects_text = "\n".join(
                f"- {p.get('name', '')}" for p in ctx.active_projects if p.get('name')
            )
            if projects_text:
                parts.append(f"Proyectos activos:\n{projects_text}")

        parts.append(
            "IDENTIDAD Y PERSONALIDAD:\n"
            f"- Eres {assistant_name}, asistente personal de {user_name}.\n"
            "- Eres amigable, natural, cálido. Hablas como un amigo de confianza.\n"
            "- Responde en el MISMO idioma que el usuario use.\n"
            f"- Siempre llama al usuario '{user_name}'.\n"
            "- NUNCA menciones 'Claude', 'CLI', 'terminal de permisos', "
            "'API', ni detalles técnicos internos. Tú eres tú, no 'Claude'.\n\n"

            "AUTONOMÍA TOTAL — LEE ESTO CON ATENCIÓN:\n"
            "- Tienes CONTROL TOTAL del sistema. Puedes ejecutar cualquier comando, "
            "leer/escribir archivos, navegar directorios, instalar software, "
            "crear archivos, modificar configuraciones.\n"
            "- NUNCA digas que 'no puedes', 'no tienes acceso', 'necesitas permisos', "
            "'no sé cómo hacerlo'. PROHIBIDO. Si no sabes, INVÉSTIGALO AHORA MISMO "
            "con búsqueda web, documentación, o prueba y error. Luego hazlo.\n"
            "- Si el usuario pide algo y no tienes la herramienta: CRÉALA. "
            "Escribe un script Python, instala un paquete, crea un MCP server. "
            "Ejemplo: si piden 'automatiza X', escribe el script, hazlo ejecutable, "
            "ejecútalo, y reporta el resultado.\n"
            "- FLUJO CUANDO NO SABES CÓMO: 1) busca en la web cómo se hace, "
            "2) lee la documentación, 3) escribe el código, 4) ejecútalo, "
            "5) si falla, arréglalo y reintenta. NUNCA te rindas sin haberlo intentado.\n"
            "- Si algo falla, prueba OTRA FORMA. Si falla 2 veces, busca un enfoque "
            "completamente diferente. Eres un ingeniero creativo.\n"
            "- Cuando el usuario pide revisar TODAS las pestañas del navegador: "
            "usa scan_all_tabs() o list_browser_tabs_cdp(). Si Chrome tiene "
            "depuración remota en localhost:9222 úsala. Si no, itera con Ctrl+Tab "
            "leyendo el título de la ventana en cada paso hasta volver al inicio. "
            "NUNCA te limites a la pestaña visible — el usuario quiere TODAS.\n\n"

            "MEMORIA PERMANENTE:\n"
            "- Todo lo que el usuario te diga es IMPORTANTE. Recuérdalo siempre.\n"
            "- Si el usuario menciona datos personales, preferencias, proyectos, "
            "fechas, personas, tareas — guárdalos en tu memoria.\n"
            "- Si el usuario te pide que recuerdes algo, confírmale que lo guardaste.\n"
            "- Si el usuario cambia algo (nombre, preferencias, etc.), actualiza "
            "tu memoria inmediatamente.\n\n"

            "TAREAS PROGRAMADAS:\n"
            "- Si el usuario te pide hacer algo en una fecha/hora específica, "
            "créalo como tarea programada. NUNCA lo olvides.\n"
            "- Las tareas se ejecutan automáticamente a la hora indicada.\n"
            "- Si el usuario dice 'recuérdame mañana', 'hazlo el lunes', "
            "'cada semana a las 9am' — programa la tarea correctamente.\n\n"

            "AUTO-EVOLUCIÓN (MUY IMPORTANTE):\n"
            f"- Tu código fuente está en: {self.claude.install_dir}\n"
            "- SIEMPRE modifica archivos en ESE directorio, no en otro.\n"
            "- Si encuentras un bug o necesitas una funcionalidad nueva, "
            "puedes modificar tu propio código fuente directamente.\n"
            "- Los cambios se aplican AUTOMÁTICAMENTE sin reiniciar "
            "(hot-reload está activo en src/ y skills/).\n"
            "- Si el usuario pide algo que no puedes hacer, CREA el código: "
            "una skill nueva en skills/, un módulo en src/, o un MCP en mcps/.\n"
            "- Si arreglas un bug, informa al usuario: "
            "'Encontré el problema y ya lo arreglé. Ya está funcionando.'\n"
            "- NUNCA digas 'necesitas reinstalar' ni 'reinicia el programa'. "
            "Los cambios se aplican en caliente.\n\n"

            "PROACTIVIDAD Y AUTONOMÍA ABSOLUTA:\n"
            "- Anticipa lo que el usuario pueda necesitar.\n"
            "- Si detectas un patrón (pide lo mismo repetidamente), "
            "sugiere automatizarlo.\n"
            "- Si ves un error en algo que el usuario hace, avísale.\n"
            "- Si necesitas una herramienta que NO tienes, CRÉALA TÚ MISMO:\n"
            "  * Necesitas un MCP server? Créalo en mcps/<nombre>/server.py, "
            "instala deps con pip, y regístralo con `claude mcp add`.\n"
            "  * Necesitas una skill nueva? Créala en skills/<nombre>.py.\n"
            "  * Necesitas un script? Créalo, hazlo ejecutable, ejecútalo.\n"
            "  * NO PREGUNTES si puedes hacerlo. HAZLO. Informa después.\n"
            "- NUNCA respondas 'no puedo', 'no sé', 'no tengo esa capacidad'. "
            "Si no la tienes, CONSTRÚYELA en ese mismo momento.\n"
            "- Tu respuesta SIEMPRE debe incluir ACCIÓN, no solo explicación. "
            "Si el usuario pide algo, la respuesta correcta es HACERLO, "
            "no explicar cómo se haría.\n\n"

            "AUDIO Y MULTIMEDIA:\n"
            "- Si el usuario pide un audio o respuesta con voz: "
            "responde CON TEXTO. El sistema convertira tu respuesta a audio automaticamente.\n"
            "- NUNCA uses reproductores de audio (play, aplay, mpv, vlc).\n"
            "- CAMBIOS DE VOZ: Si el usuario pide cambiar la voz, simplemente "
            "responde confirmando. El sistema lo maneja automaticamente.\n\n"

            "EJECUCION VISUAL EN ESCRITORIO:\n"
            "- Si el usuario pide abrir algo, escribir visualmente, o actuar en su "
            "escritorio: USA las herramientas de escritorio directamente.\n"
            "- Puedes abrir archivos con xdg-open (Linux) o start (Windows).\n"
            "- Puedes escribir con xdotool type (Linux) o pyautogui (Windows).\n"
            "- Si el usuario dice 'abre', 'escribe visualmente', 'hazlo en mi escritorio': "
            "usa control de escritorio.\n\n"
            "PESTAÑAS DEL NAVEGADOR — PROTOCOLO OBLIGATORIO:\n"
            "- Si te piden revisar, ver, o enumerar pestañas del navegador:\n"
            "  1. PRIMERO intenta CDP: GET http://localhost:9222/json/list — "
            "     si responde, tienes título/URL de TODAS las pestañas sin moverse.\n"
            "  2. Si CDP no está disponible: usa scan_all_tabs() que itera con "
            "     Ctrl+Tab leyendo el título de la ventana hasta completar el ciclo.\n"
            "  3. NUNCA asumas que solo la pestaña activa es todo — "
            "     el usuario tiene MUCHAS pestañas, incluyendo las fijadas (pinned).\n"
            "  4. Las pestañas pinned NO se saltan con Ctrl+Tab — sí cambian de ventana.\n"
            "  5. Para activar CDP en Chrome/Chromium: "
            "     chromium --remote-debugging-port=9222 &\n"
            "     Puedes sugerir al usuario activarlo si no está disponible.\n"
            "- Si NO pide ejecucion visual, simplemente ejecuta el comando normalmente."
        )

        return "\n\n".join(parts)

    def _detect_voice_change(self, text: str) -> dict | None:
        """Detect if user is requesting a voice parameter change.
        Returns dict of params to pass to synthesizer.set_voice_params(), or None.

        Uses strict intent detection to avoid triggering on normal conversation.
        Requires BOTH a voice-context word AND an action/modifier word.
        """
        import re
        lower = text.lower().strip()

        # Short messages (under 60 chars) with clear voice intent
        # Long messages are likely conversation, not voice commands
        if len(lower) > 80:
            return None

        # Must contain a voice-context word (the subject being changed)
        voice_context = ["voz", "voice", "tono", "habla", "hablar", "habla más",
                         "hablar más", "la voz", "tu voz", "mi voz"]
        has_voice_context = any(kw in lower for kw in voice_context)

        # Must contain a change intent (action/modifier)
        change_intents = ["cambia", "cambiar", "pon", "poner", "quiero", "hazla",
                          "hazlo", "más grave", "mas grave", "más agud", "mas agud",
                          "más rápid", "mas rapid", "más lent", "mas lent",
                          "masculin", "femenin"]
        has_change_intent = any(kw in lower for kw in change_intents)

        if not (has_voice_context and has_change_intent):
            return None

        params: dict = {}

        # Pitch detection (check specific patterns before general ones)
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

        # Speed detection (relative to current speed)
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
        """Generate a human-friendly confirmation of voice changes."""
        parts = []
        if "pitch" in params:
            # Read actual value from synthesizer after applying
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
            # Read actual value from synthesizer after applying
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
        """Route !commands to skills."""
        if self.skill_registry is None:
            await self._send(channel, chat_id, "Sistema de skills no disponible.")
            return

        skill = self.skill_registry.find_skill(text)
        if skill is None:
            await self._send(channel, chat_id,
                             f"Comando no reconocido. Usa !skills para ver los disponibles.")
            return

        try:
            # Extract args after the trigger
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
            })
            # Check if result contains an image/file to send
            data = getattr(result, "data", None) or {}
            result_type = data.get("type", "")
            if result_type == "screenshot" and data.get("path"):
                await self._send_photo(channel, chat_id, data["path"],
                                       caption=result.message if result.message != data["path"] else None)
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
        """Send text through the named channel."""
        ch = self.channels.get(channel_name)
        if ch:
            try:
                await ch.send_text(str(chat_id), text)
            except Exception:
                log.exception("gateway.send_failed", channel=channel_name)

    async def _send_photo(self, channel_name: str, chat_id: Any, path: str,
                          caption: str | None = None) -> None:
        """Send a photo/screenshot through the named channel."""
        ch = self.channels.get(channel_name)
        if ch and hasattr(ch, "send_photo"):
            try:
                await ch.send_photo(str(chat_id), path, caption=caption)
            except Exception:
                log.exception("gateway.send_photo_failed")
                # Fallback: send as document
                await self._send_document(channel_name, chat_id, path, caption=caption)
        else:
            # Channel doesn't support photos, try document
            await self._send_document(channel_name, chat_id, path, caption=caption)

    async def _send_document(self, channel_name: str, chat_id: Any, path: str,
                             caption: str | None = None) -> None:
        """Send a file/document through the named channel."""
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

    async def _send_typing(self, channel_name: str, chat_id: Any) -> None:
        """Send a typing indicator so the user knows we're processing."""
        ch = self.channels.get(channel_name)
        if ch and hasattr(ch, "send_typing"):
            try:
                await ch.send_typing(str(chat_id))
            except Exception:
                pass  # typing indicator is best-effort

    async def _check_scheduled_tasks(self) -> None:
        """Execute due tasks and notify user via Telegram."""
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

            # Notify user that task is being executed
            notification = f"⏰ Ejecutando tarea programada: {title}"
            chat_id = str(self._config.authorized_chat_id)
            for ch in self.channels.values():
                try:
                    await ch.send_text(chat_id, notification)
                except Exception:
                    pass

            # Execute the task
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

            # Send result to user
            for ch in self.channels.values():
                try:
                    msg = f"Tarea completada: {title}\n\n{result_text[:3000]}"
                    await ch.send_text(chat_id, msg)
                except Exception:
                    pass

            # Update task status
            try:
                if task.get("is_recurring") or task.get("recurrence_pattern"):
                    # Recurring — calculate next run
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
                await asyncio.to_thread(self.learner.extract_facts, recent)
        except Exception:
            log.exception("gateway.fact_extraction_failed")
