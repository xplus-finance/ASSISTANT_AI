"""Task and recurring-job management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from src.memory.engine import MemoryEngine

log = structlog.get_logger("assistant.memory.tasks")

_VALID_STATUSES = {"pending", "in_progress", "done", "recurring", "cancelled"}


class TaskManager:


    def __init__(self, engine: MemoryEngine) -> None:
        self._engine = engine

    def create_task(self, title: str, description: str | None = None, project: str | None = None) -> int:
        sql = "INSERT INTO tasks (title, description, project) VALUES (?, ?, ?)"
        task_id = self._engine.insert_returning_id(sql, (title, description, project))
        log.info("task.created", task_id=task_id, title=title, project=project)
        return task_id

    def update_status(self, task_id: int, status: str) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status: {status!r}. Must be one of {_VALID_STATUSES}")
        sql = "UPDATE tasks SET status = ? WHERE id = ?"
        self._engine.execute(sql, (status, task_id))
        log.info("task.status_updated", task_id=task_id, status=status)

    def make_recurring(self, task_id: int, cron_pattern: str) -> None:
        sql = "UPDATE tasks SET is_recurring = 1, recurrence_pattern = ?, status = 'recurring' WHERE id = ?"
        self._engine.execute(sql, (cron_pattern, task_id))
        log.info("task.made_recurring", task_id=task_id, cron_pattern=cron_pattern)

    def get_pending(self) -> list[dict[str, Any]]:
        sql = "SELECT id, title, description, status, project, created_at FROM tasks WHERE status = 'pending' ORDER BY created_at ASC"
        return self._engine.fetchall_dicts(sql)

    def get_recurring(self) -> list[dict[str, Any]]:
        sql = "SELECT id, title, description, recurrence_pattern, next_run, last_run, project FROM tasks WHERE is_recurring = 1 AND status = 'recurring' ORDER BY next_run ASC"
        return self._engine.fetchall_dicts(sql)

    def get_due_tasks(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sql = "SELECT id, title, description, recurrence_pattern, next_run, last_run, project FROM tasks WHERE is_recurring = 1 AND status = 'recurring' AND next_run IS NOT NULL AND next_run <= ? ORDER BY next_run ASC"
        return self._engine.fetchall_dicts(sql, (now,))

    def cancel_task(self, task_id: int) -> None:
        self.update_status(task_id, "cancelled")

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        sql = "SELECT id, title, description, status, is_recurring, recurrence_pattern, next_run, last_run, created_at, project FROM tasks WHERE id = ?"
        rows = self._engine.fetchall_dicts(sql, (task_id,))
        return rows[0] if rows else None

    def get_by_project(self, project: str) -> list[dict[str, Any]]:
        sql = "SELECT id, title, description, status, is_recurring, created_at FROM tasks WHERE project = ? AND status != 'cancelled' ORDER BY created_at ASC"
        return self._engine.fetchall_dicts(sql, (project,))

    def mark_run(self, task_id: int, next_run: str | None = None) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sql = "UPDATE tasks SET last_run = ?, next_run = ? WHERE id = ?"
        self._engine.execute(sql, (now, next_run, task_id))
        log.debug("task.mark_run", task_id=task_id, next_run=next_run)
