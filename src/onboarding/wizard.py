"""
First-time setup wizard for the AI assistant.

Runs interactively through a messaging channel (Telegram, CLI, etc.)
using send/receive callbacks.  State is persisted so that the wizard
can be resumed if interrupted mid-flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import structlog

from src.memory.engine import MemoryEngine
from src.utils.crypto import hash_pin

log = structlog.get_logger("assistant.onboarding")


# ---------------------------------------------------------------------------
# Extraction prompts — used to extract clean values from natural language
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPTS: dict[str, str] = {
    "assistant_name": (
        "The user was asked what name they want to give their AI assistant. "
        "Their response is: \"{response}\"\n\n"
        "Extract ONLY the name they want. Remove any surrounding phrases like "
        "'I want you to be called', 'call yourself', 'quiero que te llames', "
        "'llamate', etc. Return ONLY the name itself, nothing else.\n\n"
        "Examples:\n"
        "- 'quiero que te llames Firulais' → Firulais\n"
        "- 'llamate Max' → Max\n"
        "- 'I want you to be called Jarvis' → Jarvis\n"
        "- 'ponle Nova' → Nova\n"
        "- 'Max' → Max\n\n"
        "Return ONLY the extracted name, no quotes, no explanation."
    ),
    "user_name": (
        "The user was asked what name they want to be called by. "
        "Their response is: \"{response}\"\n\n"
        "Extract ONLY the name or nickname. Remove any surrounding phrases like "
        "'my name is', 'call me', 'me llamo', 'me llamas', 'dime', 'llamame', etc. "
        "Return ONLY the name itself.\n\n"
        "Examples:\n"
        "- 'me llamas Mi Jefe' → Mi Jefe\n"
        "- 'my name is Orlando' → Orlando\n"
        "- 'llamame Boss' → Boss\n"
        "- 'soy Carlos' → Carlos\n"
        "- 'Orlando' → Orlando\n\n"
        "Return ONLY the extracted name, no quotes, no explanation."
    ),
    "work_area": (
        "The user was asked about their work area or what they do. "
        "Their response is: \"{response}\"\n\n"
        "Summarize their work area in a clean, concise phrase. "
        "Keep the essential information. If they gave a detailed answer, "
        "keep the key points. Return the clean summary, nothing else."
    ),
    "comm_preferences": (
        "The user was asked about their communication preferences "
        "(text/audio, formal/informal, short/detailed). "
        "Their response is: \"{response}\"\n\n"
        "Summarize their preferences in a clean, concise phrase. "
        "Return the clean summary, nothing else."
    ),
    "timezone": (
        "The user was asked about their timezone. "
        "Their response is: \"{response}\"\n\n"
        "Extract a valid timezone identifier. If they said a city or country, "
        "convert it to a standard timezone format.\n\n"
        "Examples:\n"
        "- 'Florida' → America/New_York\n"
        "- 'Mexico City' → America/Mexico_City\n"
        "- 'Spain' → Europe/Madrid\n"
        "- 'Colombia' → America/Bogota\n"
        "- 'America/New_York' → America/New_York\n"
        "- 'vivo en California' → America/Los_Angeles\n\n"
        "Return ONLY the timezone identifier, nothing else."
    ),
}

# Step definitions — each step has a key and a prompt builder function.
# Prompt builders receive the collected answers so far to interpolate
# previous responses into the messages dynamically.

def _prompt_assistant_name(_answers: dict[str, str]) -> str:
    return (
        "\u00a1Hey! \U0001f44b Soy tu nuevo asistente personal de IA.\n\n"
        "Antes de empezar, quiero que me des un nombre. "
        "Puede ser lo que quieras \u2014 un nombre real, un apodo, "
        "algo creativo... \u00a1t\u00fa decides qui\u00e9n soy!\n\n"
        "\u00bfC\u00f3mo quieres que me llame?"
    )

def _prompt_user_name(answers: dict[str, str]) -> str:
    name = answers.get("assistant_name", "Asistente")
    return (
        f"\u00a1Me encanta! A partir de ahora soy {name}.\n\n"
        "\u00bfY t\u00fa? \u00bfC\u00f3mo quieres que te llame? "
        "Tu nombre, un apodo, lo que prefieras."
    )

def _prompt_work_area(answers: dict[str, str]) -> str:
    user = answers.get("user_name", "")
    return (
        f"\u00a1Perfecto, {user}! Cu\u00e9ntame un poco sobre ti \u2014 "
        "\u00bfa qu\u00e9 te dedicas? \u00bfEn qu\u00e9 \u00e1rea trabajas "
        "o qu\u00e9 proyectos tienes?\n\n"
        "Esto me ayuda a entenderte mejor desde el inicio."
    )

def _prompt_comm_preferences(_answers: dict[str, str]) -> str:
    return (
        "Genial. Ahora necesito saber c\u00f3mo prefieres que me "
        "comunique contigo:\n\n"
        "\u2022 \u00bfTexto, audio, o ambos?\n"
        "\u2022 \u00bfFormal o informal?\n"
        "\u2022 \u00bfRespuestas cortas o detalladas?\n\n"
        "Dime lo que prefieras, no hay respuesta incorrecta."
    )

def _prompt_timezone(_answers: dict[str, str]) -> str:
    return (
        "Casi listo. \u00bfEn qu\u00e9 zona horaria est\u00e1s? "
        "Esto me ayuda con recordatorios y tareas programadas.\n\n"
        "Ejemplo: America/New_York, America/Mexico_City, Europe/Madrid"
    )

def _prompt_security_pin(_answers: dict[str, str]) -> str:
    return (
        "\u00daltima pregunta \u2014 \u00bfquieres configurar un PIN "
        "de seguridad? \U0001f512\n\n"
        "Es una capa extra de protecci\u00f3n para operaciones sensibles. "
        "Si no quieres, simplemente escribe 'no'."
    )


_STEPS: list[dict[str, Any]] = [
    {"key": "assistant_name", "prompt_fn": _prompt_assistant_name},
    {"key": "user_name",      "prompt_fn": _prompt_user_name},
    {"key": "work_area",      "prompt_fn": _prompt_work_area},
    {"key": "comm_preferences", "prompt_fn": _prompt_comm_preferences},
    {"key": "timezone",        "prompt_fn": _prompt_timezone},
    {"key": "security_pin",    "prompt_fn": _prompt_security_pin},
]

# Total number of steps (0-indexed internally)
TOTAL_STEPS = len(_STEPS)


@dataclass
class _WizardState:
    """Mutable wizard state, persisted between messages."""

    current_step: int = 0
    answers: dict[str, str] = field(default_factory=dict)
    is_complete: bool = False
    waiting_for_answer: bool = False  # True = question was sent, waiting for response


# Type aliases for the send/receive callbacks
SendFn = Callable[[str], Coroutine[Any, Any, None]]
ReceiveFn = Callable[[], Coroutine[Any, Any, str]]


class OnboardingWizard:
    """
    Interactive onboarding wizard.

    Usage::

        wizard = OnboardingWizard(memory)
        if not await wizard.is_onboarding_complete():
            await wizard.start(send_fn, receive_fn)
    """

    def __init__(self, memory_engine: MemoryEngine, claude_bridge: Any = None) -> None:
        self._memory = memory_engine
        self._claude = claude_bridge
        self._state = _WizardState()
        self._restore_state()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def is_onboarding_complete(self) -> bool:
        """
        Return ``True`` if the user profile already contains an
        ``assistant_name`` entry, meaning onboarding was completed before.
        """
        row = self._memory.fetchone(
            "SELECT value FROM user_profile WHERE key = ?",
            ("assistant_name",),
        )
        return row is not None

    # ------------------------------------------------------------------
    # Full wizard flow
    # ------------------------------------------------------------------

    async def start(self, send_fn: SendFn, receive_fn: ReceiveFn) -> None:
        """
        Run the wizard end-to-end.

        Args:
            send_fn: Async callable that sends a message to the user.
            receive_fn: Async callable that waits for and returns the
                        user's next text message.
        """
        log.info("onboarding.start", step=self._state.current_step)

        while not self._state.is_complete:
            step_def = _STEPS[self._state.current_step]

            # Send the question for the current step (dynamically built)
            prompt = step_def["prompt_fn"](self._state.answers)
            await send_fn(prompt)

            # Wait for the user's answer
            response = await receive_fn()
            response = response.strip()

            if not response:
                await send_fn("No recibi tu respuesta. Intenta de nuevo.")
                continue

            next_msg, done = await self.process_step(
                self._state.current_step, response
            )

            if done:
                self._state.is_complete = True
                await self._save_all()
                await send_fn(next_msg)
                log.info("onboarding.complete")
            else:
                # Advance to next step
                self._state.current_step += 1
                self._persist_state()

    # ------------------------------------------------------------------
    # Step processing
    # ------------------------------------------------------------------

    async def process_step(
        self, step: int, response: str
    ) -> tuple[str, bool]:
        """
        Process the user's response for a given step.

        Args:
            step: Zero-based step index.
            response: The user's text reply.

        Returns:
            A tuple ``(next_message, is_complete)`` where *next_message*
            is either the next question or a completion summary, and
            *is_complete* is ``True`` when all steps are done.
        """
        if step < 0 or step >= TOTAL_STEPS:
            return ("Paso invalido.", False)

        step_def = _STEPS[step]
        key = step_def["key"]

        # Special handling for the PIN step
        if key == "security_pin":
            normalized = response.lower().strip()
            if normalized in ("no", "n", "omitir", "skip", ""):
                self._state.answers[key] = ""
            else:
                self._state.answers[key] = hash_pin(response)
        else:
            # Use Claude to extract the clean value from natural language
            clean_value = await self._extract_clean_value(key, response)
            self._state.answers[key] = clean_value

        # Check if we just finished the last step
        if step >= TOTAL_STEPS - 1:
            name = self._state.answers.get("assistant_name", "Asistente")
            user = self._state.answers.get("user_name", "usuario")
            msg = (
                f"\u00a1Listo, {user}! \U0001f389\n\n"
                f"Soy {name} y estoy aqu\u00ed para ti 24/7.\n\n"
                "Puedo ayudarte con:\n"
                "\U0001f5e3 Conversaciones por texto y audio\n"
                "\U0001f4bb Ejecutar comandos en tu terminal\n"
                "\U0001f50d Buscar informaci\u00f3n en la web\n"
                "\U0001f9e0 Recordar todo lo que me digas\n"
                "\u23f0 Automatizar tareas repetitivas\n"
                "\U0001f6e0 Trabajar en tus proyectos de c\u00f3digo\n\n"
                "Escribe !skills para ver todos mis comandos, "
                "o simplemente cu\u00e9ntame qu\u00e9 necesitas.\n\n"
                "\u00bfPor d\u00f3nde empezamos?"
            )
            return (msg, True)

        # Return next step's prompt — dynamically built with collected answers
        next_step = _STEPS[step + 1]
        return (next_step["prompt_fn"](self._state.answers), False)

    # ------------------------------------------------------------------
    # Smart extraction
    # ------------------------------------------------------------------

    async def _extract_clean_value(self, key: str, raw_response: str) -> str:
        """Use Claude to extract the clean value from a natural language response."""
        extraction_prompt = _EXTRACTION_PROMPTS.get(key)

        # If no extraction prompt or no Claude bridge, return as-is
        if not extraction_prompt or not self._claude:
            return raw_response.strip()

        prompt = extraction_prompt.format(response=raw_response)

        try:
            import asyncio
            clean = await self._claude.ask(
                prompt=prompt,
                system_prompt="You are a text extraction tool. Return ONLY the extracted value. No quotes, no explanation, no extra text.",
                timeout=30,
            )
            clean = clean.strip().strip('"').strip("'")
            if clean:
                log.info("onboarding.extracted", key=key, raw=raw_response, clean=clean)
                return clean
        except Exception:
            log.warning("onboarding.extraction_failed", key=key, exc_info=True)

        # Fallback: return raw response
        return raw_response.strip()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_state(self) -> None:
        """Save current wizard progress to the database."""
        import json

        state_json = json.dumps({
            "current_step": self._state.current_step,
            "answers": self._state.answers,
            "waiting_for_answer": self._state.waiting_for_answer,
        })
        self._memory.execute(
            """
            INSERT INTO user_profile (key, value, source)
            VALUES ('_onboarding_state', ?, 'onboarding')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                updated_at = datetime('now')
            """,
            (state_json,),
        )

    def _restore_state(self) -> None:
        """Restore wizard state from a previous interrupted session."""
        import json

        row = self._memory.fetchone(
            "SELECT value FROM user_profile WHERE key = ?",
            ("_onboarding_state",),
        )
        if row is None:
            return

        try:
            data = json.loads(row[0])
            self._state.current_step = data.get("current_step", 0)
            self._state.answers = data.get("answers", {})
            self._state.waiting_for_answer = data.get("waiting_for_answer", False)
            log.info(
                "onboarding.restored",
                step=self._state.current_step,
                answers_count=len(self._state.answers),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            log.warning("onboarding.restore_failed")

    async def _save_all(self) -> None:
        """Persist all collected answers to the ``user_profile`` table."""
        for key, value in self._state.answers.items():
            if not value:
                continue
            self._memory.execute(
                """
                INSERT INTO user_profile (key, value, source)
                VALUES (?, ?, 'onboarding')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                    updated_at = datetime('now')
                """,
                (key, value),
            )

        # Clean up the transient wizard state
        self._memory.execute(
            "DELETE FROM user_profile WHERE key = ?",
            ("_onboarding_state",),
        )

        log.info(
            "onboarding.saved",
            keys=list(self._state.answers.keys()),
        )
