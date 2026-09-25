"""Typed models for short-term and persistent memory."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class MemoryCategory(str, Enum):
    USER_PREFERENCE = "USER_PREFERENCE"
    PROJECT_CONTEXT = "PROJECT_CONTEXT"
    WORKFLOW_PREFERENCE = "WORKFLOW_PREFERENCE"
    IMPORTANT_FACT = "IMPORTANT_FACT"
    RECURRING_PATTERN = "RECURRING_PATTERN"
    EXPLICIT_MEMORY = "EXPLICIT_MEMORY"
    CURRENT_TASK = "CURRENT_TASK"
    TEMPORARY_CONTEXT = "TEMPORARY_CONTEXT"
    SENSITIVE_INFORMATION = "SENSITIVE_INFORMATION"


class MemoryCandidateStatus(str, Enum):
    PENDING = "pending"
    PERSISTED = "persisted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class MemoryCandidate:
    category: MemoryCategory
    content: str
    rationale: str = ""
    explicit: bool = False
    candidate_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: MemoryCandidateStatus = MemoryCandidateStatus.PENDING
    sensitivity_reason: str | None = None


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    category: MemoryCategory
    content: str
    created_at: datetime
    updated_at: datetime
    source: str


@dataclass(frozen=True)
class MemoryDecision:
    candidate_id: str
    decision: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class SensitivityResult:
    sensitive: bool
    reason: str | None = None


@dataclass
class ShortTermMemory:
    """In-session context; this object is intentionally not backed by storage."""

    conversation: list[Mapping[str, object]] = field(default_factory=list)
    current_task: Any = None
    current_plan: Any = None
    observations: list[Any] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    temporary_state: dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.conversation.clear()
        self.current_task = None
        self.current_plan = None
        self.observations.clear()
        self.tool_results.clear()
        self.temporary_state.clear()


@dataclass(frozen=True)
class MemoryTaskCheckpoint:
    """Exact agent state captured while a memory approval is pending."""

    task_id: str
    goal: str
    max_iterations: int
    iteration: int
    conversation: tuple[Mapping[str, object], ...]
    agent_state: str
    plan: Any = None