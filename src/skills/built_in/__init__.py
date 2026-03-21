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
from src.skills.built_in.catalog_skill import CatalogSkill
from src.skills.built_in.gmail_skill import GmailSkill
from src.skills.built_in.daily_briefing_skill import DailyBriefingSkill
from src.skills.built_in.clipboard_skill import ClipboardSkill
from src.skills.built_in.pdf_builder_skill import PDFBuilderSkill
from src.skills.built_in.social_media_skill import SocialMediaSkill
from src.skills.built_in.expense_skill import ExpenseSkill
from src.skills.built_in.automation_skill import AutomationSkill
from src.skills.built_in.notes_skill import NotesSkill
from src.skills.built_in.meeting_skill import MeetingSkill
from src.skills.built_in.seo_skill import SEOSkill
from src.skills.built_in.data_converter_skill import DataConverterSkill
from src.skills.built_in.heartbeat_skill import HeartbeatSkill

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
    "CatalogSkill",
    "GmailSkill",
    "DailyBriefingSkill",
    "ClipboardSkill",
    "PDFBuilderSkill",
    "SocialMediaSkill",
    "ExpenseSkill",
    "AutomationSkill",
    "NotesSkill",
    "MeetingSkill",
    "SEOSkill",
    "DataConverterSkill",
    "HeartbeatSkill",
]
