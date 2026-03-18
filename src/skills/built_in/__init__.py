"""Built-in skills for the personal AI assistant."""
from src.skills.built_in.terminal import TerminalSkill
from src.skills.built_in.files import FilesSkill
from src.skills.built_in.memory_skill import MemorySkill
from src.skills.built_in.tasks_skill import TasksSkill
from src.skills.built_in.learn_skill import LearnSkill
from src.skills.built_in.claude_code import ClaudeCodeSkill
from src.skills.built_in.skill_creator import SkillCreatorSkill
from src.skills.built_in.system_monitor import SystemMonitorSkill
from src.skills.built_in.file_search import FileSearchSkill
from src.skills.built_in.git_skill import GitSkill
from src.skills.built_in.network_skill import NetworkSkill
from src.skills.built_in.package_skill import PackageSkill

__all__ = [
    "TerminalSkill",
    "FilesSkill",
    "MemorySkill",
    "TasksSkill",
    "LearnSkill",
    "ClaudeCodeSkill",
    "SkillCreatorSkill",
    "SystemMonitorSkill",
    "FileSearchSkill",
    "GitSkill",
    "NetworkSkill",
    "PackageSkill",
]
