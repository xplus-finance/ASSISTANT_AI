"""Task management skill: create, list, update, cancel."""

from __future__ import annotations

from typing import Any

import structlog

from src.memory.engine import MemoryEngine
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.tasks")


class TasksSkill(BaseSkill):


    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine

    @property
    def name(self) -> str:
        return "tasks"

    @property
    def description(self) -> str:
        return "Gestion de tareas (listar, crear, completar, cancelar)"

    @property
    def triggers(self) -> list[str]:
        return ["!tareas", "!tarea"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        if not args:
            return self._list_pending(memory)

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        dispatch: dict[str, str] = {
            "nueva": "create",
            "new": "create",
            "crear": "create",
            "hecha": "done",
            "done": "done",
            "completar": "done",
            "cancelar": "cancel",
            "cancel": "cancel",
            "detalle": "detail",
            "detail": "detail",
            "ver": "detail",
            "todas": "all",
            "all": "all",
            "pendientes": "pending",
        }

        action = dispatch.get(sub)

        if action == "create":
            return self._create(memory, rest)
        elif action == "done":
            return self._mark_done(memory, rest)
        elif action == "cancel":
            return self._cancel(memory, rest)
        elif action == "detail":
            return self._detail(memory, rest)
        elif action == "all":
            return self._list_all(memory)
        elif action == "pending":
            return self._list_pending(memory)
        else:
            # Treat unknown subcommand as task creation
            return self._create(memory, args)

    def _create(self, memory: MemoryEngine, title: str) -> SkillResult:
        if not title.strip():
            return SkillResult(
                success=False,
                message="Uso: !tarea nueva <titulo de la tarea>",
            )

        project = None
        if "#" in title:
            parts = title.rsplit("#", 1)
            title = parts[0].strip()
            project = parts[1].strip() or None

        task_id = memory.insert_returning_id(
            """
            INSERT INTO tasks (title, project)
            VALUES (?, ?)
            """,
            (title, project),
        )

        log.info("tasks.created", id=task_id, title=title[:60], project=project)
        msg = f"Tarea #{task_id} creada: {title}"
        if project:
            msg += f" (proyecto: {project})"
        return SkillResult(success=True, message=msg, data={"id": task_id})

    def _mark_done(self, memory: MemoryEngine, args: str) -> SkillResult:
        task_id = self._parse_id(args)
        if task_id is None:
            return SkillResult(
                success=False,
                message="Uso: !tarea hecha <id>",
            )

        row = memory.fetchone("SELECT title, status FROM tasks WHERE id = ?", (task_id,))
        if row is None:
            return SkillResult(success=False, message=f"Tarea #{task_id} no encontrada.")

        if row[1] == "done":
            return SkillResult(success=True, message=f"Tarea #{task_id} ya estaba completada.")

        memory.execute(
            "UPDATE tasks SET status = 'done', last_run = datetime('now') WHERE id = ?",
            (task_id,),
        )

        log.info("tasks.completed", id=task_id)
        return SkillResult(
            success=True,
            message=f"Tarea #{task_id} completada: {row[0]}",
        )

    def _cancel(self, memory: MemoryEngine, args: str) -> SkillResult:
        task_id = self._parse_id(args)
        if task_id is None:
            return SkillResult(success=False, message="Uso: !tarea cancelar <id>")

        row = memory.fetchone("SELECT title FROM tasks WHERE id = ?", (task_id,))
        if row is None:
            return SkillResult(success=False, message=f"Tarea #{task_id} no encontrada.")

        memory.execute(
            "UPDATE tasks SET status = 'cancelled' WHERE id = ?",
            (task_id,),
        )

        log.info("tasks.cancelled", id=task_id)
        return SkillResult(
            success=True,
            message=f"Tarea #{task_id} cancelada: {row[0]}",
        )

    def _detail(self, memory: MemoryEngine, args: str) -> SkillResult:
        task_id = self._parse_id(args)
        if task_id is None:
            return SkillResult(success=False, message="Uso: !tarea detalle <id>")

        rows = memory.fetchall_dicts(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        if not rows:
            return SkillResult(success=False, message=f"Tarea #{task_id} no encontrada.")

        task = rows[0]
        lines = [
            f"Tarea #{task['id']}",
            f"  Titulo: {task['title']}",
            f"  Estado: {task['status']}",
            f"  Proyecto: {task['project'] or '(ninguno)'}",
            f"  Creada: {task['created_at']}",
        ]
        if task.get("description"):
            lines.append(f"  Descripcion: {task['description']}")
        if task.get("next_run"):
            lines.append(f"  Proxima ejecucion: {task['next_run']}")
        if task.get("recurrence_pattern"):
            lines.append(f"  Recurrencia: {task['recurrence_pattern']}")

        return SkillResult(success=True, message="\n".join(lines), data=task)

    def _list_pending(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            """
            SELECT id, title, status, project, created_at
            FROM tasks
            WHERE status IN ('pending', 'in_progress', 'recurring')
            ORDER BY
                CASE status
                    WHEN 'in_progress' THEN 0
                    WHEN 'recurring' THEN 1
                    WHEN 'pending' THEN 2
                END,
                created_at DESC
            LIMIT 30
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay tareas pendientes.")

        lines = ["Tareas pendientes:", ""]
        for row in rows:
            status_icon = {
                "pending": "[  ]",
                "in_progress": "[>>]",
                "recurring": "[~~]",
            }.get(row["status"], "[??]")
            project = f" #{row['project']}" if row["project"] else ""
            lines.append(f"  {status_icon} #{row['id']}: {row['title'][:60]}{project}")

        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"tasks": rows},
        )

    def _list_all(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            """
            SELECT id, title, status, project, created_at
            FROM tasks
            ORDER BY created_at DESC
            LIMIT 50
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay tareas registradas.")

        lines = ["Todas las tareas:", ""]
        for row in rows:
            status_icon = {
                "pending": "[  ]",
                "in_progress": "[>>]",
                "recurring": "[~~]",
                "done": "[OK]",
                "cancelled": "[XX]",
            }.get(row["status"], "[??]")
            project = f" #{row['project']}" if row["project"] else ""
            lines.append(f"  {status_icon} #{row['id']}: {row['title'][:60]}{project}")

        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"tasks": rows},
        )

    @staticmethod
    def _parse_id(text: str) -> int | None:
        text = text.strip().lstrip("#")
        try:
            return int(text)
        except (ValueError, TypeError):
            return None
