"""Memory workflow, sensitivity, persistence, and task checkpoint tests."""

from pathlib import Path

import pytest

from app.memory.manager import MemoryManager
from app.memory.models import MemoryCategory, MemoryCandidateStatus, ShortTermMemory


def manager(tmp_path: Path) -> MemoryManager:
    return MemoryManager(tmp_path / "memory.sqlite3")


def test_candidate_requires_approval_before_persistence(tmp_path: Path) -> None:
    memory = manager(tmp_path)

    candidate = memory.propose_memory(
        MemoryCategory.USER_PREFERENCE,
        "I prefer Spring Boot for backend projects.",
        rationale="useful recurring preference",
    )

    assert candidate.status is MemoryCandidateStatus.PENDING
    assert memory.retrieve_memory() == ()

    approved = memory.approve_memory(candidate.candidate_id)

    assert approved.status is MemoryCandidateStatus.PERSISTED
    assert memory.retrieve_memory("Spring Boot")[0].content.startswith("I prefer")


def test_explicit_memory_persists_without_extra_prompt(tmp_path: Path) -> None:
    memory = manager(tmp_path)

    result = memory.remember("editor", "VS Code")

    assert result.status is MemoryCandidateStatus.PERSISTED
    assert memory.recall("editor") == "editor: VS Code"


def test_rejected_candidate_is_not_persisted_and_is_recorded(tmp_path: Path) -> None:
    memory = manager(tmp_path)
    candidate = memory.propose_memory(MemoryCategory.PROJECT_CONTEXT, "Hermes uses Python.")

    rejected = memory.reject_memory(candidate.candidate_id)

    assert rejected.status is MemoryCandidateStatus.REJECTED
    assert memory.retrieve_memory() == ()
    decisions = memory.long_term.storage.decisions(candidate.candidate_id)
    assert decisions[0].decision == "rejected"


@pytest.mark.parametrize("content", ["password: hunter2", "my API key is abc", "private key material"])
def test_sensitive_memory_is_rejected_without_asking(tmp_path: Path, content: str) -> None:
    memory = manager(tmp_path)

    candidate = memory.propose_memory(MemoryCategory.IMPORTANT_FACT, content)

    assert candidate.status is MemoryCandidateStatus.REJECTED
    assert candidate.sensitivity_reason
    assert memory.retrieve_memory() == ()


def test_update_and_delete_are_persistent_operations(tmp_path: Path) -> None:
    memory = manager(tmp_path)
    saved = memory.remember("theme", "dark")
    record = memory.retrieve_memory()[0]

    updated = memory.update_memory(record.memory_id, "theme: light", MemoryCategory.EXPLICIT_MEMORY)
    memory.delete_memory(updated.memory_id)

    assert updated.content == "theme: light"
    assert memory.retrieve_memory() == ()


def test_short_term_memory_is_session_only() -> None:
    short_term = ShortTermMemory()
    short_term.current_task = "temporary task"
    short_term.observations.append("temporary observation")
    short_term.clear()

    assert short_term.current_task is None
    assert short_term.observations == []


def test_memory_approval_checkpoint_resumes_exact_task_state(tmp_path: Path) -> None:
    memory = manager(tmp_path)
    conversation = ({"role": "user", "content": "continue this task"},)

    checkpoint = memory.suspend_task(
        task_id="task-1",
        goal="continue this task",
        max_iterations=10,
        iteration=3,
        conversation=conversation,
        agent_state="waiting_for_approval",
        plan={"next": "observe"},
    )
    resumed = memory.resume_task("task-1")

    assert resumed == checkpoint
    assert resumed.conversation == conversation
    with pytest.raises(KeyError):
        memory.resume_task("task-1")