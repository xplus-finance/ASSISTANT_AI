"""First-time setup wizard with resumable state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import structlog

from src.memory.engine import MemoryEngine
from src.utils.crypto import hash_pin

log = structlog.get_logger("assistant.onboarding")


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
        "\u00daltima pregunta \u2014 configura tu PIN de seguridad \U0001f512\n\n"
        "El PIN es OBLIGATORIO. Se te pedirá antes de ejecutar "
        "cualquier acción invasiva: borrar archivos, modificar código, "
        "instalar software, etc.\n\n"
        "Escribe un PIN numérico (mínimo 4 dígitos):"
    )


_STEPS: list[dict[str, Any]] = [
    {"key": "assistant_name", "prompt_fn": _prompt_assistant_name},
    {"key": "user_name",      "prompt_fn": _prompt_user_name},
    {"key": "work_area",      "prompt_fn": _prompt_work_area},
    {"key": "comm_preferences", "prompt_fn": _prompt_comm_preferences},
    {"key": "timezone",        "prompt_fn": _prompt_timezone},
    {"key": "security_pin",    "prompt_fn": _prompt_security_pin},
]

TOTAL_STEPS = len(_STEPS)


@dataclass
class _WizardState:

    current_step: int = 0
    answers: dict[str, str] = field(default_factory=dict)
    is_complete: bool = False
    waiting_for_answer: bool = False  # True = question was sent, waiting for response


SendFn = Callable[[str], Coroutine[Any, Any, None]]
ReceiveFn = Callable[[], Coroutine[Any, Any, str]]


class OnboardingWizard:


    def __init__(self, memory_engine: MemoryEngine, claude_bridge: Any = None) -> None:
        self._memory = memory_engine
        self._claude = claude_bridge
        self._state = _WizardState()
        self._restore_state()

    async def is_onboarding_complete(self) -> bool:
        row = self._memory.fetchone(
            "SELECT value FROM user_profile WHERE key = ?",
            ("assistant_name",),
        )
        return row is not None

    async def start(self, send_fn: SendFn, receive_fn: ReceiveFn) -> None:
        log.info("onboarding.start", step=self._state.current_step)

        while not self._state.is_complete:
            step_def = _STEPS[self._state.current_step]

            prompt = step_def["prompt_fn"](self._state.answers)
            await send_fn(prompt)

            response = await receive_fn()
            response = response.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()

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
                self._state.current_step += 1
                self._persist_state()

    async def process_step(
        self, step: int, response: str
    ) -> tuple[str, bool]:
        if step < 0 or step >= TOTAL_STEPS:
            return ("Paso invalido.", False)

        step_def = _STEPS[step]
        key = step_def["key"]

        if key == "security_pin":
            cleaned = response.strip()
            # PIN is mandatory — must be at least 4 digits
            if not cleaned or len(cleaned) < 4:
                return (
                    "⚠️ El PIN es obligatorio y debe tener mínimo 4 dígitos.\n"
                    "Escribe tu PIN numérico:",
                    False,
                )
            self._state.answers[key] = hash_pin(cleaned)
        else:
            clean_value = await self._extract_clean_value(key, response)
            self._state.answers[key] = clean_value

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

        next_step = _STEPS[step + 1]
        return (next_step["prompt_fn"](self._state.answers), False)

    async def _extract_clean_value(self, key: str, raw_response: str) -> str:
        raw_response = raw_response.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        raw_response = raw_response.strip()

        if key in ("assistant_name", "user_name"):
            pre_clean = self._local_extract(key, raw_response)
            # If local extract produced something shorter (i.e., it actually stripped preamble),
            # use it directly without calling Claude
            if pre_clean != raw_response and len(pre_clean.split()) <= 4:
                log.info("onboarding.extracted_local", key=key, raw=raw_response, clean=pre_clean)
                return pre_clean

        extraction_prompt = _EXTRACTION_PROMPTS.get(key)

        if extraction_prompt and self._claude:
            prompt = extraction_prompt.format(response=raw_response)
            try:
                raw_clean = await self._claude.ask(
                    prompt=prompt,
                    system_prompt="You are a text extraction tool. Return ONLY the extracted value. No quotes, no explanation, no extra text. Single line only.",
                    timeout=30,
                )
                # Normalize Claude's output: BOM, CRLF, take first non-empty line
                raw_clean = raw_clean.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
                lines = [ln.strip() for ln in raw_clean.split("\n") if ln.strip()]
                clean = lines[0] if lines else ""
                clean = clean.strip().strip('"').strip("'").strip()

                # Final safety pass: run local extract on Claude's output too
                # in case Claude echoed the full phrase back
                if clean and key in ("assistant_name", "user_name"):
                    clean = self._local_extract(key, clean)

                if clean:
                    log.info("onboarding.extracted_claude", key=key, raw=raw_response, clean=clean)
                    return clean
            except Exception:
                log.warning("onboarding.extraction_failed", key=key, exc_info=True)

        return self._local_extract(key, raw_response)

    @staticmethod
    def _local_extract(key: str, raw: str) -> str:
        import re

        text = raw.strip()

        if key == "assistant_name":
            # Remove phrases like "te vas a llamar", "quiero que te llames", "llamate", "ponle"
            text = re.sub(
                r"(?i)^(ok[,.]?\s*)?(perfecto[,.]?\s*)?(tu nombre es|tu nombre será|tu nombre va a ser|"
                r"te vas a llamar|quiero que te llames|que te llames|me gustar[ií]a que te llames|"
                r"podrías llamarte|llamate|llámame|ll[aá]mate|ponle|quiero llamarte|"
                r"voy a llamarte|te voy a llamar|a partir de ahora te llamas|"
                r"i want you to be called|call yourself|your name (is|will be|shall be)|"
                r"from now on (you are|you're|call yourself)|you will be called)\s*",
                "", text,
            ).strip()
            # Also handle trailing punctuation / filler after extraction
            text = re.sub(r"[.,!?]+$", "", text).strip()

        elif key == "user_name":
            # Remove "me llamo", "a mi me llamas", "mi nombre es", "soy", "llamame", "dime"
            text = re.sub(
                r"(?i)^(a mi me llamas|me llamas|me puedes llamar|me llamo|mi nombre es|"
                r"mi apodo es|soy|llamame|llámame|ll[aá]mame|dime|puedes llamarme|"
                r"my name is|you can call me|call me|i am|i'm|just call me)\s*",
                "", text,
            ).strip()
            text = re.sub(r"[.,!?]+$", "", text).strip()

        elif key == "timezone":
            # Try to map common locations to timezone identifiers
            tz_map = {
                r"florida|miami|cape coral|orlando|tampa|jacksonville": "America/New_York",
                r"new york|nyc|boston|philadelphia|washington|atlanta|carolina": "America/New_York",
                r"chicago|illinois|houston|texas|dallas|austin|san antonio": "America/Chicago",
                r"denver|colorado|phoenix|arizona|utah|montana": "America/Denver",
                r"los angeles|california|san francisco|seattle|portland|oregon|nevada|las vegas": "America/Los_Angeles",
                r"mexico|cdmx|ciudad de mexico|guadalajara|monterrey": "America/Mexico_City",
                r"colombia|bogota|bogotá|medell[ií]n": "America/Bogota",
                r"argentina|buenos aires": "America/Argentina/Buenos_Aires",
                r"chile|santiago": "America/Santiago",
                r"spain|españa|madrid|barcelona": "Europe/Madrid",
                r"london|uk|england|united kingdom": "Europe/London",
                r"paris|france|francia|germany|alemania|berlin": "Europe/Paris",
                r"brazil|brasil|sao paulo|são paulo|rio": "America/Sao_Paulo",
                r"peru|lima": "America/Lima",
                r"venezuela|caracas": "America/Caracas",
                r"puerto rico": "America/Puerto_Rico",
                r"hawaii": "Pacific/Honolulu",
                r"alaska": "America/Anchorage",
            }
            lower = text.lower()
            for pattern, tz in tz_map.items():
                if re.search(pattern, lower):
                    text = tz
                    break
            # If it already looks like a timezone ID, keep it
            if "/" in text and text[0].isupper():
                pass  # Already a valid tz

        elif key == "work_area":
            # Remove preamble like "soy", "me dedico a", "trabajo en"
            text = re.sub(
                r"(?i)^(soy|me dedico a|trabajo en|trabajo como|i am a|i work as|i work in|my job is)\s*",
                "", text,
            ).strip()

        elif key == "comm_preferences":
            # Remove preamble like "quiero que", "prefiero"
            text = re.sub(
                r"(?i)^(quiero que sea|quiero que|prefiero|i prefer|i want)\s*",
                "", text,
            ).strip()

        return text if text else raw.strip()

    def _persist_state(self) -> None:
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

        self._memory.execute(
            "DELETE FROM user_profile WHERE key = ?",
            ("_onboarding_state",),
        )

        log.info(
            "onboarding.saved",
            keys=list(self._state.answers.keys()),
        )
