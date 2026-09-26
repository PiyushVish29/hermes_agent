"""Approval-aware behavior over long-term memory storage."""

from __future__ import annotations

from datetime import datetime, timezone
from app.memory.models import MemoryCandidate, MemoryCategory, MemoryDecision, MemoryRecord, MemoryCandidateStatus
from app.memory.policy import MemoryPolicy
from app.memory.storage import MemoryStorage


class LongTermMemory:
    """Apply sensitivity and approval rules before using SQLite storage."""

    def __init__(self, storage: MemoryStorage, policy: MemoryPolicy | None = None) -> None:
        self.storage = storage
        self.policy = policy or MemoryPolicy()
        self._pending: dict[str, MemoryCandidate] = {}

    def propose(self, candidate: MemoryCandidate) -> MemoryCandidate:
        sensitivity = self.policy.assess(candidate.category, candidate.content)
        if sensitivity.sensitive:
            rejected = MemoryCandidate(
                **{**candidate.__dict__, "status": MemoryCandidateStatus.REJECTED, "sensitivity_reason": sensitivity.reason}
            )
            self.storage.record_decision(
                MemoryDecision(candidate.candidate_id, "rejected", sensitivity.reason or "sensitive information")
            )
            return rejected
        if self.policy.can_persist_without_approval(candidate.category, candidate.explicit):
            return self.approve(candidate.candidate_id, candidate)
        self._pending[candidate.candidate_id] = candidate
        return candidate

    def approve(self, candidate_id: str, candidate: MemoryCandidate | None = None) -> MemoryCandidate:
        pending = candidate or self._pending.get(candidate_id)
        if pending is None:
            raise KeyError(f"memory candidate not found: {candidate_id}")
        sensitivity = self.policy.assess(pending.category, pending.content)
        if sensitivity.sensitive:
            raise ValueError("sensitive memory cannot be persisted")
        now = datetime.now(timezone.utc)
        self.storage.insert(MemoryRecord(pending.candidate_id, pending.category, pending.content, now, now, "user_approved"))
        self.storage.record_decision(MemoryDecision(pending.candidate_id, "approved", "approved by user"))
        self._pending.pop(candidate_id, None)
        return MemoryCandidate(**{**pending.__dict__, "status": MemoryCandidateStatus.PERSISTED})

    def reject(self, candidate_id: str) -> MemoryCandidate:
        candidate = self._pending.pop(candidate_id)
        self.storage.record_decision(MemoryDecision(candidate_id, "rejected", "rejected by user"))
        return MemoryCandidate(**{**candidate.__dict__, "status": MemoryCandidateStatus.REJECTED})

    def retrieve(self, query: str = "", category: MemoryCategory | None = None) -> tuple[MemoryRecord, ...]:
        return self.storage.search(query, category)

    def update(self, memory_id: str, content: str, category: MemoryCategory) -> MemoryRecord:
        sensitivity = self.policy.assess(category, content)
        if sensitivity.sensitive:
            raise ValueError("sensitive memory cannot be persisted")
        return self.storage.update(memory_id, content, category)

    def delete(self, memory_id: str) -> None:
        self.storage.delete(memory_id)