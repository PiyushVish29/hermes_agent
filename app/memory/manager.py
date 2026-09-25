"""Coordinator for short-term context, memory decisions, and persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from app.memory.long_term import LongTermMemory
from app.memory.models import (
    MemoryCandidate,
    MemoryCategory,
    MemoryRecord,
    MemoryTaskCheckpoint,
    ShortTermMemory,
)
from app.memory.policy import MemoryPolicy
from app.memory.storage import MemoryStorage


class MemoryManager:
    """Coordinate candidate workflow without granting authority to the model."""

    def __init__(self, database_location: Path | str, policy: MemoryPolicy | None = None) -> None:
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory(MemoryStorage(database_location), policy)
        self._checkpoints: dict[str, MemoryTaskCheckpoint] = {}

    def propose_memory(
        self,
        category: MemoryCategory,
        content: str,
        *,
        rationale: str = "",
        explicit: bool = False,
    ) -> MemoryCandidate:
        """Propose memory; only explicit intent can bypass user approval."""
        if not content.strip():
            raise ValueError("memory content must not be empty")
        return self.long_term.propose(
            MemoryCandidate(category=category, content=content, rationale=rationale, explicit=explicit)
        )

    def propose_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate:
        """Process a model- or application-generated candidate without approving it."""
        return self.long_term.propose(candidate)

    def approve_memory(self, candidate_id: str) -> MemoryCandidate:
        return self.long_term.approve(candidate_id)

    def reject_memory(self, candidate_id: str) -> MemoryCandidate:
        return self.long_term.reject(candidate_id)

    def retrieve_memory(
        self, query: str = "", category: MemoryCategory | None = None
    ) -> tuple[MemoryRecord, ...]:
        return self.long_term.retrieve(query, category)

    def update_memory(self, memory_id: str, content: str, category: MemoryCategory) -> MemoryRecord:
        return self.long_term.update(memory_id, content, category)

    def delete_memory(self, memory_id: str) -> None:
        self.long_term.delete(memory_id)

    def remember(self, key: str, value: str) -> MemoryCandidate:
        """Compatibility helper for explicit user-directed memory."""
        return self.propose_memory(
            MemoryCategory.EXPLICIT_MEMORY,
            f"{key}: {value}",
            rationale="explicit user request",
            explicit=True,
        )

    def recall(self, query: str) -> str | None:
        records = self.retrieve_memory(query)
        return records[0].content if records else None

    def suspend_task(
        self,
        task_id: str,
        goal: str,
        max_iterations: int,
        iteration: int,
        conversation: tuple[Mapping[str, object], ...],
        agent_state: str,
        plan: object = None,
    ) -> MemoryTaskCheckpoint:
        """Capture exact task context while an approval prompt is displayed."""
        checkpoint = MemoryTaskCheckpoint(
            task_id, goal, max_iterations, iteration, tuple(conversation), agent_state, plan
        )
        self._checkpoints[task_id] = checkpoint
        return checkpoint

    def resume_task(self, task_id: str) -> MemoryTaskCheckpoint:
        """Return and remove the exact checkpoint after a memory decision."""
        try:
            return self._checkpoints.pop(task_id)
        except KeyError as error:
            raise KeyError(f"task checkpoint not found: {task_id}") from error