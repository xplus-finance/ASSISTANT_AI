"""
Memory management skill — save facts, recall information, view profile.

Integrates with ``MemoryEngine`` to persist and retrieve learned facts
and user-profile entries using the ``learned_facts`` and ``user_profile``
tables defined in the engine schema.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.memory.engine import MemoryEngine, sanitize_fts_query
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.memory")


class MemorySkill(BaseSkill):
    """Manage the assistant's long-term memory."""

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Gestiona la memoria del asistente (guardar hechos, recordar, perfil)"

    @property
    def triggers(self) -> list[str]:
        return ["!memoria", "!recuerda", "!olvida", "!yo"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        """
        Handle memory operations.

        Sub-commands:
            ``!recuerda <hecho>``  — save a fact
            ``!memoria buscar <query>`` — search memory
            ``!memoria todo``  — show all facts
            ``!olvida <id>``   — forget a fact by ID
            ``!yo``            — show user profile
        """
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        # Determine which trigger was used
        trigger_used = ""
        original = context.get("original_text", "").lower().strip()
        for t in self.triggers:
            if original.startswith(t):
                trigger_used = t
                break

        if trigger_used == "!yo":
            return self._show_profile(memory)
        elif trigger_used == "!olvida":
            return self._forget(memory, args)
        elif trigger_used == "!recuerda":
            return self._remember(memory, args)
        else:
            # !memoria — subcommands
            return self._handle_memoria(memory, args)

    # ------------------------------------------------------------------
    # Sub-command handlers
    # ------------------------------------------------------------------

    def _handle_memoria(self, memory: MemoryEngine, args: str) -> SkillResult:
        """Route ``!memoria`` sub-commands."""
        if not args:
            return self._show_stats(memory)

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if sub in ("buscar", "search"):
            return self._search(memory, rest)
        elif sub in ("todo", "all"):
            return self._show_all(memory)
        elif sub in ("stats", "estadisticas"):
            return self._show_stats(memory)
        else:
            # Treat as search query
            return self._search(memory, args)

    def _remember(self, memory: MemoryEngine, fact: str) -> SkillResult:
        """Save a new fact to learned_facts."""
        if not fact.strip():
            return SkillResult(
                success=False,
                message="Uso: !recuerda <hecho a guardar>",
            )

        # Determine category heuristically
        category = self._guess_category(fact)

        fact_id = memory.insert_returning_id(
            """
            INSERT INTO learned_facts (category, fact, source)
            VALUES (?, ?, 'user_explicit')
            """,
            (category, fact.strip()),
        )

        log.info("memory.fact_saved", id=fact_id, category=category)
        return SkillResult(
            success=True,
            message=f"Guardado (#{fact_id}, categoria: {category}):\n{fact.strip()}",
            data={"id": fact_id, "category": category},
        )

    def _forget(self, memory: MemoryEngine, args: str) -> SkillResult:
        """Delete a fact by ID."""
        args = args.strip()
        if not args:
            return SkillResult(
                success=False,
                message="Uso: !olvida <id>\nUsa !memoria todo para ver IDs.",
            )

        try:
            fact_id = int(args.lstrip("#"))
        except ValueError:
            return SkillResult(
                success=False,
                message=f"ID invalido: {args}. Debe ser un numero.",
            )

        # Check existence
        row = memory.fetchone(
            "SELECT fact FROM learned_facts WHERE id = ?", (fact_id,)
        )
        if row is None:
            return SkillResult(success=False, message=f"Hecho #{fact_id} no encontrado.")

        memory.execute("DELETE FROM learned_facts WHERE id = ?", (fact_id,))
        log.info("memory.fact_deleted", id=fact_id)

        return SkillResult(
            success=True,
            message=f"Hecho #{fact_id} eliminado: {row[0][:80]}",
        )

    def _search(self, memory: MemoryEngine, query: str) -> SkillResult:
        """Full-text search across facts."""
        if not query.strip():
            return SkillResult(
                success=False,
                message="Uso: !memoria buscar <termino>",
            )

        safe_query = sanitize_fts_query(query.strip())
        if not safe_query:
            return SkillResult(
                success=False,
                message="La busqueda no contiene terminos validos.",
            )

        rows = memory.fetchall_dicts(
            """
            SELECT f.id, f.category, f.fact, f.confidence, f.learned_at
            FROM learned_facts f
            JOIN facts_fts ON facts_fts.rowid = f.id
            WHERE facts_fts MATCH ?
            ORDER BY rank
            LIMIT 10
            """,
            (safe_query,),
        )

        if not rows:
            return SkillResult(
                success=True,
                message=f"No encontre nada sobre '{query.strip()}'.",
            )

        lines = [f"Resultados para '{query.strip()}':", ""]
        for row in rows:
            lines.append(
                f"  #{row['id']} [{row['category']}] {row['fact'][:100]}"
            )

        # Update use_count for returned facts
        for row in rows:
            memory.execute(
                """
                UPDATE learned_facts
                SET use_count = use_count + 1, last_used = datetime('now')
                WHERE id = ?
                """,
                (row["id"],),
            )

        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"results": rows},
        )

    def _show_all(self, memory: MemoryEngine) -> SkillResult:
        """Show all learned facts."""
        rows = memory.fetchall_dicts(
            """
            SELECT id, category, fact, confidence, use_count
            FROM learned_facts
            ORDER BY category, id
            LIMIT 50
            """,
        )

        if not rows:
            return SkillResult(
                success=True,
                message="No tengo hechos guardados todavia.",
            )

        lines = ["Hechos en memoria:", ""]
        current_cat = ""
        for row in rows:
            if row["category"] != current_cat:
                current_cat = row["category"]
                lines.append(f"\n[{current_cat.upper()}]")
            lines.append(f"  #{row['id']}: {row['fact'][:100]}")

        total = memory.fetchone("SELECT COUNT(*) FROM learned_facts")
        count = total[0] if total else 0
        if count > 50:
            lines.append(f"\n... mostrando 50 de {count} hechos")

        return SkillResult(success=True, message="\n".join(lines))

    def _show_profile(self, memory: MemoryEngine) -> SkillResult:
        """Show the user profile."""
        rows = memory.fetchall_dicts(
            """
            SELECT key, value, updated_at
            FROM user_profile
            WHERE key NOT LIKE '\\_%' ESCAPE '\\'
            ORDER BY key
            """,
        )

        if not rows:
            return SkillResult(
                success=True,
                message="Perfil vacio. Ejecuta el onboarding primero.",
            )

        lines = ["Tu perfil:", ""]
        for row in rows:
            key = row["key"]
            value = row["value"]
            # Don't show hashed PINs in full
            if key == "security_pin":
                value = "****" if value else "(no configurado)"
            lines.append(f"  {key}: {value}")

        return SkillResult(success=True, message="\n".join(lines))

    def _show_stats(self, memory: MemoryEngine) -> SkillResult:
        """Show memory statistics."""
        facts_count = memory.fetchone("SELECT COUNT(*) FROM learned_facts")
        profile_count = memory.fetchone(
            "SELECT COUNT(*) FROM user_profile WHERE key NOT LIKE '\\_%' ESCAPE '\\'"
        )
        knowledge_count = memory.fetchone("SELECT COUNT(*) FROM knowledge")
        conversations_count = memory.fetchone("SELECT COUNT(*) FROM conversations")

        lines = [
            "Estadisticas de memoria:",
            "",
            f"  Hechos aprendidos: {facts_count[0] if facts_count else 0}",
            f"  Entradas de perfil: {profile_count[0] if profile_count else 0}",
            f"  Conocimiento: {knowledge_count[0] if knowledge_count else 0}",
            f"  Mensajes: {conversations_count[0] if conversations_count else 0}",
        ]

        return SkillResult(success=True, message="\n".join(lines))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _guess_category(fact: str) -> str:
        """Heuristically categorize a fact."""
        lower = fact.lower()

        user_keywords = ("mi ", "yo ", "me ", "tengo ", "soy ", "prefiero ")
        if any(lower.startswith(kw) for kw in user_keywords):
            return "user"

        pref_keywords = ("prefiero", "me gusta", "no me gusta", "odio", "favorit")
        if any(kw in lower for kw in pref_keywords):
            return "preference"

        tech_keywords = (
            "python", "javascript", "api", "docker", "git", "linux",
            "servidor", "base de datos", "sql", "codigo", "deploy",
        )
        if any(kw in lower for kw in tech_keywords):
            return "technical"

        project_keywords = ("proyecto", "project", "repo", "repositorio", "app")
        if any(kw in lower for kw in project_keywords):
            return "project"

        return "world"
