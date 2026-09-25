"""Agent pause/resume integration for memory approval."""

import pytest

from app.agent.controller import AgentController, MemoryApprovalRequired
from app.agent.state import AgentState
from app.config.settings import Settings
from app.memory.manager import MemoryManager
from app.memory.models import MemoryCandidate, MemoryCategory
from app.models.mock import MockModelProvider
from app.models.provider import ModelResponse


def test_memory_approval_resumes_exact_agent_task(tmp_path) -> None:
    manager = MemoryManager(tmp_path / "memory.sqlite3")
    controller: AgentController
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            controller.propose_memory_for_current_task(
                # The model can suggest this, but cannot approve it.
                MemoryCandidate(MemoryCategory.USER_PREFERENCE, "prefers concise responses")
            )
        return ModelResponse(text="Task resumed with the same context.")

    provider = MockModelProvider(responder=respond)
    controller = AgentController(
        Settings(), model_provider=provider, memory_manager=manager
    )

    with pytest.raises(MemoryApprovalRequired) as pending:
        controller.run_task("Continue the original task")

    task_id = controller._suspended_task_id
    assert pending.value.candidate.content == "prefers concise responses"
    assert controller.state is AgentState.WAITING_FOR_APPROVAL
    assert len(provider.requests) == 1

    response = controller.resume_memory_task(approve=True)

    assert response.text == "Task resumed with the same context."
    assert controller.state is AgentState.COMPLETED
    assert controller._active_task.task_id == task_id
    assert len(provider.requests) == 2
    assert manager.retrieve_memory("concise responses")