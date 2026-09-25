"""Lifecycle coordinator for the Hermes Local application."""

from __future__ import annotations

import logging
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any

from app import __version__
from app.config.settings import Settings
from app.agent.state import AgentEvent, AgentPlan, AgentState, AgentTask, ToolCall, ToolError, ToolResult
from app.filesystem import ListDirectoryTool, PathSecurityLayer, ReadFileTool, SearchFilesTool
from app.models.provider import ModelError, ModelProvider, ModelRequest, ModelResponse, ToolDefinition
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy, PermissionRequest
from app.tools.base import ToolValidationError
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentController:
    """Own application lifecycle; future orchestration will be added here."""

    settings: Settings
    model_provider: ModelProvider | None = None
    running: bool = False
    state: AgentState = AgentState.IDLE
    tool_registry: ToolRegistry | None = None
    permission_engine: PermissionEngine | None = None
    events: list[AgentEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.tool_registry is None:
            self.tool_registry = ToolRegistry()
            self.tool_registry.register(CalculatorTool())
        if self.permission_engine is None:
            safe_defaults = {
                getattr(self.tool_registry.get(name), "permission_requirement", name): PermissionLevel.SAFE
                for name in self.tool_registry.names()
                if name == "calculator"
            }
            self.permission_engine = PermissionEngine(PermissionPolicy(safe_defaults))
        if self.tool_registry is not None and self.permission_engine is not None:
            security = PathSecurityLayer(self.settings.security_policy)
            for tool in (
                ListDirectoryTool(security, self.permission_engine),
                SearchFilesTool(security, self.permission_engine),
                ReadFileTool(security, self.permission_engine),
            ):
                if self.tool_registry.get(tool.name) is None:
                    self.tool_registry.register(tool)

    def start(self) -> None:
        """Initialize the safe application shell."""
        self.running = True
        logger.info("Hermes Local started")

    def status_message(self) -> str:
        """Return human-readable status without invoking any external capability."""
        state = "running" if self.running else "stopped"
        model_state = "connected" if self.model_provider is not None else "disconnected"
        return f"Hermes Local {__version__} - {state} - model: {model_state}"

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Delegate generation through the provider abstraction."""
        if self.model_provider is None:
            raise RuntimeError("No model provider is configured")
        return self.model_provider.generate(request)

    def run_task(self, goal: str, *, max_iterations: int | None = None) -> ModelResponse:
        """Run a bounded model/tool/model loop for one user goal."""
        if self.model_provider is None:
            raise RuntimeError("No model provider is configured")
        if not goal.strip():
            raise ValueError("goal must not be empty")
        iteration_limit = self.settings.max_agent_iterations if max_iterations is None else max_iterations
        if iteration_limit < 1:
            raise ValueError("max_iterations must be positive")
        task = AgentTask(uuid.uuid4().hex, goal, iteration_limit)
        conversation: tuple[dict[str, object], ...] = (
            {"role": "user", "content": goal},
        )
        self.state = AgentState.IDLE
        self.events.clear()
        self._record(task, "task_started", AgentState.IDLE)

        for iteration in range(1, task.max_iterations + 1):
            if self.state == AgentState.CANCELLED:
                raise RuntimeError("Agent task was cancelled")
            self.state = AgentState.THINKING
            self._record(task, "model_requested", self.state, iteration=iteration)
            try:
                response = self.generate(
                    ModelRequest(
                        prompt=goal,
                        conversation=conversation,
                        tools=self._tool_definitions(),
                        timeout_seconds=self.settings.tool_timeout_seconds,
                    )
                )
            except ModelError:
                self.state = AgentState.FAILED
                self._record(task, "model_failed", self.state, iteration=iteration)
                raise

            plan = AgentPlan(
                task_id=task.task_id,
                iteration=iteration,
                tool_calls=tuple(
                    ToolCall(call.call_id, call.name, dict(call.arguments))
                    for call in response.tool_calls
                ),
                final_response=response.text if not response.tool_calls else None,
            )
            if plan.final_response is not None:
                self.state = AgentState.COMPLETED
                self._record(task, "task_completed", self.state, iteration=iteration)
                return response

            self.state = AgentState.WAITING_FOR_APPROVAL
            self._record(task, "tool_requests_received", self.state, count=len(plan.tool_calls))
            results = tuple(self._handle_tool_call(task, call, iteration) for call in plan.tool_calls)
            self.state = AgentState.OBSERVING
            self._record(task, "tool_results_received", self.state, count=len(results))
            conversation = self._append_results(conversation, response, results)

        self.state = AgentState.FAILED
        self._record(task, "iteration_limit_reached", self.state, limit=task.max_iterations)
        raise RuntimeError("Agent maximum iterations exceeded")

    def cancel(self) -> None:
        """Request cancellation before the next model or tool step."""
        self.state = AgentState.CANCELLED

    def _handle_tool_call(self, task: AgentTask, call: ToolCall, iteration: int) -> ToolResult:
        try:
            tool = self.tool_registry.validate(call.name, call.arguments) if self.tool_registry else None
            if tool is None:
                raise ToolValidationError("tool registry is unavailable", code="registry_unavailable")
        except ToolValidationError as error:
            result = ToolResult(
                call.call_id,
                call.name,
                False,
                error=ToolError(error.code, str(error)),
            )
            self._record(task, "tool_rejected", AgentState.WAITING_FOR_APPROVAL, iteration=iteration, tool=call.name)
            return result
        permission_request = PermissionRequest(
            action=call.name,
            permission_requirement=tool.permission_requirement,
            arguments=call.arguments,
            request_id=call.call_id,
        )
        decision = self.permission_engine.decide(permission_request) if self.permission_engine else None
        if decision is None or not decision.permitted:
            result = ToolResult(
                call.call_id,
                call.name,
                False,
                error=ToolError(
                    "permission_denied",
                    decision.reason if decision else "permission engine is unavailable",
                ),
            )
            self._record(task, "tool_rejected", AgentState.WAITING_FOR_APPROVAL, iteration=iteration, tool=call.name)
            return result

        self.state = AgentState.EXECUTING
        self._record(task, "tool_started", self.state, iteration=iteration, tool=call.name)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(tool.execute, call.arguments)
        try:
            value = future.result(timeout=self.settings.tool_timeout_seconds)
            result = ToolResult(call.call_id, call.name, True, value=value)
        except FutureTimeoutError:
            future.cancel()
            result = ToolResult(
                call.call_id,
                call.name,
                False,
                error=ToolError("timeout", "tool execution timed out", retryable=True),
            )
        except Exception as error:
            result = ToolResult(
                call.call_id,
                call.name,
                False,
                error=ToolError("execution_failed", f"tool execution failed: {error}"),
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        self._record(task, "tool_finished", self.state, iteration=iteration, tool=call.name, success=result.success)
        return result

    def _tool_definitions(self) -> tuple[ToolDefinition, ...]:
        if self.tool_registry is None:
            return ()
        definitions = []
        for name in self.tool_registry.names():
            tool = self.tool_registry.get(name)
            definitions.append(
                ToolDefinition(
                    name=name,
                    description=getattr(tool, "description", ""),
                    parameters=getattr(tool, "input_schema", {"type": "object"}),
                )
            )
        return tuple(definitions)

    @staticmethod
    def _append_results(
        conversation: tuple[dict[str, object], ...],
        response: ModelResponse,
        results: tuple[ToolResult, ...],
    ) -> tuple[dict[str, object], ...]:
        messages = list(conversation)
        messages.append(
            {
                "role": "assistant",
                "content": response.text,
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "function": {"name": call.name, "arguments": dict(call.arguments)},
                    }
                    for call in response.tool_calls
                ],
            }
        )
        messages.extend(
            {
                "role": "tool",
                "tool_name": result.tool_name,
                "content": json.dumps(
                    {
                        "success": result.success,
                        "value": result.value,
                        "error": (
                            {
                                "code": result.error.code,
                                "message": result.error.message,
                                "retryable": result.error.retryable,
                            }
                            if result.error
                            else None
                        ),
                    },
                    default=str,
                ),
            }
            for result in results
        )
        return tuple(messages)

    def _record(self, task: AgentTask, event_type: str, state: AgentState, **details: Any) -> None:
        event = AgentEvent(task.task_id, event_type, state, details)
        self.events.append(event)
        logger.info(
            "agent_event task_id=%s event=%s state=%s details=%s",
            task.task_id,
            event_type,
            state.value,
            {key: value for key, value in details.items() if key != "prompt"},
        )

    def shutdown(self) -> None:
        """Stop the application and release future resources in one place."""
        if self.running:
            logger.info("Hermes Local shutting down")
        self.running = False
