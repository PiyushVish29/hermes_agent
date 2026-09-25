"""Structured state and events for the Hermes agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    EXECUTING = "executing"
    OBSERVING = "observing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AgentTask:
    """Immutable user goal and execution bound."""

    task_id: str
    goal: str
    max_iterations: int


@dataclass(frozen=True)
class AgentPlan:
    """The current model decision represented independently of a provider."""

    task_id: str
    iteration: int
    tool_calls: tuple["ToolCall", ...] = ()
    final_response: str | None = None


@dataclass(frozen=True)
class ToolCall:
    """A validated model request to invoke a registered tool."""

    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolError:
    """Structured, model-visible tool failure without raw exception objects."""

    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class ToolResult:
    """Structured outcome returned to the model after tool validation/execution."""

    call_id: str
    tool_name: str
    success: bool
    value: Any = None
    error: ToolError | None = None


@dataclass(frozen=True)
class AgentEvent:
    """Audit-friendly state transition or execution event without prompt content."""

    task_id: str
    event_type: str
    state: AgentState
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))