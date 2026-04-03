"""Dynamic skill registry with filesystem hot-reload."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

import structlog

from src.memory.engine import MemoryEngine
from src.skills.base_skill import BaseSkill

log = structlog.get_logger("assistant.skills.registry")

_BUILT_IN_DIR = Path(__file__).resolve().parent / "built_in"


class SkillRegistry:


    def __init__(
        self,
        skills_dir: str | Path,
        memory_engine: MemoryEngine,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._skills_dir = Path(skills_dir).resolve()
        self._memory = memory_engine
        self._context = context or {}
        self._skills: dict[str, BaseSkill] = {}
        self._lock = threading.Lock()
        self._observer: Any = None

    def load_built_in(self) -> int:
        count = 0
        if not _BUILT_IN_DIR.is_dir():
            log.warning("registry.no_builtin_dir", path=str(_BUILT_IN_DIR))
            return count

        for path in sorted(_BUILT_IN_DIR.glob("*.py")):
            if path.name.startswith("_"):
                continue
            skill = self._load_skill_file(str(path))
            if skill is not None:
                self.register(skill)
                count += 1

        log.info("registry.built_in_loaded", count=count)
        return count

    def load_user_skills(self) -> int:
        count = 0
        self._skills_dir.mkdir(parents=True, exist_ok=True)

        for path in sorted(self._skills_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            skill = self._load_skill_file(str(path))
            if skill is not None:
                self.register(skill)
                count += 1

        if count:
            log.info("registry.user_skills_loaded", count=count)
        return count

    def start_watching(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            log.warning(
                "registry.watchdog_unavailable",
                hint="pip install watchdog",
            )
            return

        registry = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event: Any) -> None:
                if not event.is_directory and event.src_path.endswith(".py"):
                    registry._on_file_changed(event.src_path)

            def on_modified(self, event: Any) -> None:
                if not event.is_directory and event.src_path.endswith(".py"):
                    registry._on_file_changed(event.src_path)

        self._skills_dir.mkdir(parents=True, exist_ok=True)
        self._observer = Observer()
        self._observer.schedule(_Handler(), str(self._skills_dir), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        log.info("registry.watching", path=str(self._skills_dir))

    def stop_watching(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            log.info("registry.watch_stopped")

    def _on_file_changed(self, path: str) -> None:
        filename = os.path.basename(path)
        if filename.startswith("_"):
            return

        log.info("registry.file_changed", path=path)
        skill = self._load_skill_file(path)
        if skill is not None:
            self.register(skill)
            log.info("registry.hot_reloaded", skill=skill.name)

    def _check_trigger_conflicts(self, skill: BaseSkill) -> None:
        """Warn if new skill has triggers that overlap with existing skills."""
        new_triggers = set(skill.triggers)
        with self._lock:
            for name, existing in self._skills.items():
                if name == skill.name:
                    continue
                overlap = new_triggers & set(existing.triggers)
                if overlap:
                    log.warning(
                        "registry.trigger_conflict",
                        new_skill=skill.name,
                        existing_skill=name,
                        overlapping_triggers=sorted(overlap),
                    )

    def register(self, skill: BaseSkill) -> None:
        self._check_trigger_conflicts(skill)
        with self._lock:
            replacing = skill.name in self._skills
            self._skills[skill.name] = skill

        try:
            self._memory.execute(
                """
                INSERT INTO skills (name, description, file_path, created_by)
                VALUES (?, ?, ?, 'system')
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    file_path = excluded.file_path
                """,
                (skill.name, skill.description, ""),
            )
        except Exception:
            log.warning("registry.db_record_failed", skill=skill.name, exc_info=True)

        action = "replaced" if replacing else "registered"
        log.info(f"registry.{action}", skill=skill.name, triggers=skill.triggers)

    def unregister(self, name: str) -> bool:
        with self._lock:
            removed = self._skills.pop(name, None)
        return removed is not None

    def find_skill(self, text: str) -> BaseSkill | None:
        with self._lock:
            for skill in self._skills.values():
                if skill.matches(text):
                    return skill
        return None

    def find_skill_natural(self, text: str) -> tuple[BaseSkill | None, "NaturalMatch | None"]:
        """Try to match text against natural language patterns of all skills.

        Returns (skill, match) with highest confidence, or (None, None).
        """
        from src.skills.base_skill import NaturalMatch

        best_skill: BaseSkill | None = None
        best_match: NaturalMatch | None = None

        with self._lock:
            for skill in self._skills.values():
                match = skill.matches_natural(text)
                if match and (best_match is None or match.confidence > best_match.confidence):
                    best_skill = skill
                    best_match = match

        return best_skill, best_match

    def get_all(self) -> list[BaseSkill]:
        with self._lock:
            return list(self._skills.values())

    def get(self, name: str) -> BaseSkill | None:
        with self._lock:
            return self._skills.get(name)

    def _load_skill_file(self, path: str) -> BaseSkill | None:
        path = os.path.abspath(path)
        module_name = f"_skill_{Path(path).stem}_{id(path)}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                log.warning("registry.bad_spec", path=path)
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]

            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseSkill)
                    and obj is not BaseSkill
                    and not inspect.isabstract(obj)
                ):
                    instance = self._instantiate_skill(obj)
                    if instance is not None:
                        return instance

            log.debug("registry.no_skill_class", path=path)
            return None

        except Exception:
            log.error("registry.load_error", path=path, exc_info=True)
            return None
        finally:
            sys.modules.pop(module_name, None)

    def _instantiate_skill(self, cls: type) -> BaseSkill | None:
        try:
            sig = inspect.signature(cls.__init__)
            params = list(sig.parameters.keys())

            if len(params) <= 1:
                return cls()  # type: ignore[abstract]

            kwargs: dict[str, Any] = {}
            for p in params[1:]:
                if p in self._context:
                    kwargs[p] = self._context[p]
                elif p == "memory_engine" and "memory" in self._context:
                    kwargs[p] = self._context["memory"]

            return cls(**kwargs)  # type: ignore[abstract]

        except Exception:
            log.error("registry.instantiate_error", cls=cls.__name__, exc_info=True)
            return None

    def __del__(self) -> None:
        self.stop_watching()
