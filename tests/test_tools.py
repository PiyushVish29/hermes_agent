"""Tool contract and registry tests."""

import pytest

from app.agent.controller import AgentController
from app.config.settings import Settings
from app.models.mock import MockModelProvider
from app.models.provider import ModelResponse, ToolCallRequest
from app.tools.base import Tool, ToolValidationError
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry


class FailingTool(Tool):
    name = "failing"

    def execute(self, arguments):
        raise RuntimeError("expected failure")


def test_valid_tool_is_registered_validated_and_executed() -> None:
    registry = ToolRegistry()
    tool = CalculatorTool()
    registry.register(tool)

    validated = registry.validate("calculator", {"expression": "6 * 7"})

    assert validated is tool
    assert validated.execute({"expression": "6 * 7"}) == 42


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(ToolValidationError) as error:
        ToolRegistry().validate("shell", {})

    assert error.value.code == "unknown_tool"


def test_invalid_arguments_are_rejected_before_execution() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    with pytest.raises(ToolValidationError):
        registry.validate("calculator", {"expression": "1 + 1", "command": "unsafe"})


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(CalculatorTool())


def test_execution_failure_is_returned_as_structured_result() -> None:
    registry = ToolRegistry()
    registry.register(FailingTool())
    provider = MockModelProvider(
        responder=lambda request: (
            ModelResponse(tool_calls=(ToolCallRequest("fail-1", "failing"),))
            if len(request.conversation) == 1
            else ModelResponse(text="The tool failed safely.")
        )
    )
    controller = AgentController(
        Settings(),
        model_provider=provider,
        tool_registry=registry,
    )

    response = controller.run_task("Use the failing tool")

    assert response.text == "The tool failed safely."
    tool_result = provider.requests[-1].conversation[-1]["content"]
    assert '"code": "execution_failed"' in tool_result