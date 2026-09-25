"""Success, validation, failure, and loop-bound tests for the first agent loop."""

import time

import pytest

from app.agent.controller import AgentController
from app.agent.state import AgentState
from app.config.settings import Settings
from app.models.mock import MockModelProvider
from app.models.provider import ModelResponse, ToolCallRequest
from app.security.permissions import PermissionEngine
from app.tools.base import Tool
from app.tools.registry import ToolRegistry


def test_agent_completes_after_calculator_tool_result() -> None:
    def respond(request):
        if len(request.conversation) == 1:
            return ModelResponse(
                tool_calls=(ToolCallRequest("call-1", "calculator", {"expression": "2 + 3"}),)
            )
        assert '"success": true' in request.conversation[-1]["content"]
        return ModelResponse(text="The answer is 5.")

    provider = MockModelProvider(responder=respond)
    controller = AgentController(Settings(), model_provider=provider)

    response = controller.run_task("What is 2 + 3?")

    assert response.text == "The answer is 5."
    assert controller.state is AgentState.COMPLETED
    assert any(event.event_type == "tool_finished" for event in controller.events)


def test_unregistered_tool_becomes_structured_failure_and_model_recovers() -> None:
    def respond(request):
        if len(request.conversation) == 1:
            return ModelResponse(
                tool_calls=(ToolCallRequest("call-1", "shell", {"command": "whoami"}),)
            )
        assert "tool is not registered" in request.conversation[-1]["content"]
        return ModelResponse(text="I cannot use that unregistered tool.")

    provider = MockModelProvider(responder=respond)
    controller = AgentController(Settings(), model_provider=provider)

    response = controller.run_task("Run a command")

    assert response.text == "I cannot use that unregistered tool."
    assert controller.state is AgentState.COMPLETED
    assert not any(event.event_type == "tool_started" for event in controller.events)


def test_agent_stops_repeating_tool_requests_at_iteration_limit() -> None:
    provider = MockModelProvider(
        responder=lambda request: ModelResponse(
            tool_calls=(ToolCallRequest("repeat", "calculator", {"expression": "1 + 1"}),)
        )
    )
    controller = AgentController(Settings(), model_provider=provider)

    with pytest.raises(RuntimeError, match="maximum iterations"):
        controller.run_task("Keep calculating", max_iterations=2)

    assert controller.state is AgentState.FAILED
    assert controller.events[-1].event_type == "iteration_limit_reached"


class SlowTool(Tool):
    name = "slow"

    def execute(self, arguments):
        time.sleep(0.05)
        return "late"


def test_tool_timeout_becomes_structured_failure() -> None:
    registry = ToolRegistry()
    registry.register(SlowTool())
    permission_engine = PermissionEngine(frozenset({"slow"}))
    provider = MockModelProvider(
        responder=lambda request: (
            ModelResponse(tool_calls=(ToolCallRequest("slow-1", "slow"),))
            if len(request.conversation) == 1
            else ModelResponse(text="The tool timed out.")
        )
    )
    controller = AgentController(
        Settings(tool_timeout_seconds=0.01),
        model_provider=provider,
        tool_registry=registry,
        permission_engine=permission_engine,
    )

    response = controller.run_task("Use the slow tool")

    assert response.text == "The tool timed out."
    assert controller.state is AgentState.COMPLETED