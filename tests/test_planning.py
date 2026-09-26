"""Planning, observation, retry, and replan behavior tests."""

import pytest

from app.agent.controller import AgentController
from app.agent.state import AgentState, PlanStepStatus
from app.config.settings import Settings
from app.models.mock import MockModelProvider
from app.models.provider import ModelResponse, ToolCallRequest
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy
from app.tools.base import Tool
from app.tools.registry import ToolRegistry


class FlakyTool(Tool):
    name = "flaky"

    def __init__(self, failures: int) -> None:
        self.remaining_failures = failures

    def execute(self, arguments):
        if self.remaining_failures:
            self.remaining_failures -= 1
            raise RuntimeError("temporary failure")
        return "ok"


def controller_with_tool(provider, tool, *, retries=1, replans=1) -> AgentController:
    registry = ToolRegistry()
    registry.register(tool)
    return AgentController(
        Settings(max_step_retries=retries, max_replans=replans),
        model_provider=provider,
        tool_registry=registry,
        permission_engine=PermissionEngine(
            PermissionPolicy({tool.permission_requirement: PermissionLevel.SAFE})
        ),
    )


def test_successful_multi_step_plan_preserves_observed_steps() -> None:
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(
                tool_calls=(
                    ToolCallRequest("step-1", "calculator", {"expression": "2 + 2"}),
                    ToolCallRequest("step-2", "calculator", {"expression": "3 + 3"}),
                )
            )
        return ModelResponse(text="Both calculations completed.")

    provider = MockModelProvider(responder=respond)
    controller = AgentController(Settings(), model_provider=provider)

    response = controller.run_task("Calculate two values")

    assert response.text == "Both calculations completed."
    assert controller.current_plan is not None
    assert [step.status for step in controller.current_plan.steps] == [
        PlanStepStatus.SUCCEEDED,
        PlanStepStatus.SUCCEEDED,
    ]
    assert all(step.actual_result.success for step in controller.current_plan.steps)
    assert any(event.event_type == "step_observed" for event in controller.events)


def test_recoverable_failure_retries_only_failed_step() -> None:
    provider = MockModelProvider(
        responder=lambda request: ModelResponse(
            tool_calls=(ToolCallRequest("flaky-1", "flaky"),)
        )
        if len(provider.requests) == 1
        else ModelResponse(text="Recovered.")
    )
    controller = controller_with_tool(provider, FlakyTool(1), retries=1)

    response = controller.run_task("Recover from a temporary failure")

    assert response.text == "Recovered."
    assert controller.current_plan.steps[0].status is PlanStepStatus.SUCCEEDED
    assert controller.current_plan.steps[0].attempts == 2
    assert any(event.event_type == "step_retry" for event in controller.events)


def test_unrecoverable_failure_preserves_failed_plan_step() -> None:
    provider = MockModelProvider(
        responder=lambda request: ModelResponse(
            tool_calls=(ToolCallRequest("flaky-1", "flaky"),)
        )
    )
    controller = controller_with_tool(provider, FlakyTool(99), retries=0, replans=0)

    with pytest.raises(RuntimeError, match="maximum replans"):
        controller.run_task("Fail permanently")

    assert controller.state is AgentState.FAILED
    assert controller.current_plan.steps[0].status is PlanStepStatus.FAILED


def test_retry_limit_is_enforced() -> None:
    provider = MockModelProvider(
        responder=lambda request: ModelResponse(
            tool_calls=(ToolCallRequest("flaky-1", "flaky"),)
        )
    )
    controller = controller_with_tool(provider, FlakyTool(99), retries=2, replans=0)

    with pytest.raises(RuntimeError, match="maximum replans"):
        controller.run_task("Retry only within the limit")

    assert controller.current_plan.steps[0].attempts == 3


def test_replan_limit_is_enforced_after_recovery_fails() -> None:
    provider = MockModelProvider(
        responder=lambda request: ModelResponse(
            tool_calls=(ToolCallRequest(f"failure-{len(provider.requests)}", "flaky"),)
        )
    )
    controller = controller_with_tool(provider, FlakyTool(99), retries=0, replans=1)

    with pytest.raises(RuntimeError, match="maximum replans"):
        controller.run_task("Do not replan forever")

    assert controller.state is AgentState.FAILED
    assert len(controller.plan_history) == 2
    assert controller.events[-1].event_type == "replan_limit_reached"