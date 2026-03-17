"""Built-in skills for the personal AI assistant."""
from src.skills.built_in.terminal import TerminalSkill
from src.skills.built_in.files import FilesSkill
from src.skills.built_in.memory_skill import MemorySkill
from src.skills.built_in.tasks_skill import TasksSkill
from src.skills.built_in.learn_skill import LearnSkill
from src.skills.built_in.claude_code import ClaudeCodeSkill
from src.skills.built_in.skill_creator import SkillCreatorSkill
from src.skills.built_in.desktop_control import DesktopControlSkill

__all__ = [
    "TerminalSkill",
    "FilesSkill",
    "MemorySkill",
    "TasksSkill",
    "LearnSkill",
    "ClaudeCodeSkill",
    "SkillCreatorSkill",
    "DesktopControlSkill",
]
