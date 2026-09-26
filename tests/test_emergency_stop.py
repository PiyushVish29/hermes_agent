"""Emergency-stop behavior across agent states."""

import threading
import time

import pytest

from app.agent.controller import AgentController, EmergencyStopTriggered, MemoryApprovalRequired
from app.agent.state import AgentState, PlanStepStatus
from app.config.settings import Settings
from app.memory.manager import MemoryManager
from app.memory.models import MemoryCandidate, MemoryCategory
from app.models.mock import MockModelProvider
from app.models.provider import ModelResponse, ToolCallRequest
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy
from app.tools.base import Tool
from app.tools.registry import ToolRegistry


class BlockingTool(Tool):
    name = "blocking"

    def __init__(self) -> None:
        self.started = threading.Event()
        self.cancelled = threading.Event()

    def execute(self, arguments):
        self.started.set()
        while not self.cancelled.is_set():
            time.sleep(0.01)
        return "stopped"

    def cancel(self) -> None:
        self.cancelled.set()


def controller_with_tool(provider, tool, *, memory_manager=None) -> AgentController:
    registry = ToolRegistry()
    registry.register(tool)
    return AgentController(
        Settings(max_step_retries=0, max_replans=0),
        model_provider=provider,
        tool_registry=registry,
        memory_manager=memory_manager,
        permission_engine=PermissionEngine(PermissionPolicy({"blocking": PermissionLevel.SAFE})),
    )


def test_idle_emergency_stop_prevents_task_start() -> None:
    provider = MockModelProvider(response=ModelResponse(text="should not run"))
    controller = AgentController(Settings(), model_provider=provider)

    status = controller.trigger_emergency_stop("operator pressed stop")

    with pytest.raises(EmergencyStopTriggered):
        controller.run_task("Do work")
    assert status.triggered
    assert controller.state is AgentState.CANCELLED
    assert provider.requests == []


def test_active_tool_is_cancelled_and_task_stops() -> None:
    blocking = BlockingTool()
    provider = MockModelProvider(
        response=ModelResponse(tool_calls=(ToolCallRequest("block-1", "blocking"),))
    )
    controller = controller_with_tool(provider, blocking)
    errors: list[Exception] = []

    worker = threading.Thread(target=lambda: _run_capture(controller, errors), daemon=True)
    worker.start()
    assert blocking.started.wait(timeout=2)
    controller.trigger_emergency_stop()
    worker.join(timeout=2)

    assert errors and isinstance(errors[0], EmergencyStopTriggered)
    assert blocking.cancelled.is_set()
    assert controller.state is AgentState.CANCELLED


def test_waiting_for_memory_approval_can_be_stopped(tmp_path) -> None:
    manager = MemoryManager(tmp_path / "memory.sqlite3")
    controller: AgentController

    def respond(request):
        controller.propose_memory_for_current_task(
            MemoryCandidate(MemoryCategory.USER_PREFERENCE, "likes concise output")
        )
        return ModelResponse(text="unreachable")

    provider = MockModelProvider(responder=respond)
    controller = AgentController(Settings(), model_provider=provider, memory_manager=manager)
    with pytest.raises(MemoryApprovalRequired):
        controller.run_task("Pause for memory")

    controller.trigger_emergency_stop()
    with pytest.raises(EmergencyStopTriggered):
        controller.resume_memory_task(approve=True)
    assert controller.state is AgentState.CANCELLED


def test_multi_step_stop_preserves_plan_state() -> None:
    blocking = BlockingTool()
    provider = MockModelProvider(
        response=ModelResponse(
            tool_calls=(
                ToolCallRequest("first", "blocking"),
                ToolCallRequest("second", "blocking"),
            )
        )
    )
    controller = controller_with_tool(provider, blocking)
    errors: list[Exception] = []
    worker = threading.Thread(target=lambda: _run_capture(controller, errors), daemon=True)
    worker.start()
    assert blocking.started.wait(timeout=2)
    controller.trigger_emergency_stop()
    worker.join(timeout=2)

    assert controller.current_plan is not None
    assert controller.current_plan.steps[0].status is PlanStepStatus.FAILED or controller.state is AgentState.CANCELLED
    assert controller.current_plan.current_step_index == 0
    assert len(provider.requests) == 1


def test_repeated_stop_requests_are_idempotent() -> None:
    controller = AgentController(Settings())

    first = controller.trigger_emergency_stop("first")
    second = controller.trigger_emergency_stop("second")

    assert first.reason == "first"
    assert second.reason == "first"
    assert second.request_count == 2
    assert controller.emergency_stop.is_triggered()


def _run_capture(controller: AgentController, errors: list[Exception]) -> None:
    try:
        controller.run_task("interrupt me")
    except Exception as error:
        errors.append(error)