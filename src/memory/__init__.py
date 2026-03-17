"""
Memory engine — the core persistence layer for the AI assistant.

Public API:
    MemoryEngine        — SQLite/APSW database connection and schema manager.
    ConversationStore   — Conversation history with FTS5 search.
    RelationshipTracker — Relationship observations and stage tracking.
    TaskManager         — Task and recurring-job CRUD.
    LearningStore       — Facts and knowledge with FTS5 search.
    ContextBuilder      — Aggregates all sub-systems into a ConversationContext.
    ConversationContext  — Immutable dataclass with full turn context.
"""

from src.memory.context import ContextBuilder, ConversationContext
from src.memory.conversation import ConversationStore
from src.memory.engine import MemoryEngine
from src.memory.learning import LearningStore
from src.memory.relationships import RelationshipTracker
from src.memory.tasks import TaskManager

__all__ = [
    "MemoryEngine",
    "ConversationStore",
    "RelationshipTracker",
    "TaskManager",
    "LearningStore",
    "ContextBuilder",
    "ConversationContext",
]
