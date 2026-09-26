"""Lifecycle coordinator for the Hermes Local application."""

from __future__ import annotations

import logging
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field, replace
from typing import Any

from app import __version__
from app.config.settings import Settings
from app.applications import ApplicationTool
from app.computer import ComputerPolicy, ComputerUseTool, ControlledTestBackend, WindowBounds
from app.browser import BrowserPolicy, BrowserTool
from app.agent.emergency import EmergencyStop, EmergencyStopStatus
from app.agent.state import (
    AgentEvent,
    AgentPlan,
    AgentState,
    AgentTask,
    PlanStep,
    PlanStepStatus,
    ToolCall,
    ToolError,
    ToolResult,
)
from app.filesystem import ListDirectoryTool, PathSecurityLayer, ReadFileTool, SearchFilesTool
from app.memory.manager import MemoryManager
from app.memory.models import MemoryCandidate, MemoryCandidateStatus
from app.models.provider import ModelError, ModelProvider, ModelRequest, ModelResponse, ToolDefinition
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy, PermissionRequest
from app.terminal import TerminalTool
from app.tools.base import ToolValidationError
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class MemoryApprovalRequired(RuntimeError):
    """Raised to pause a task while the host presents a memory decision."""

    def __init__(self, candidate: MemoryCandidate) -> None:
        super().__init__("User memory approval is required")
        self.candidate = candidate


class EmergencyStopTriggered(RuntimeError):
    """Raised when host emergency stop interrupts agent execution."""


@dataclass
class AgentController:
    """Own application lifecycle; future orchestration will be added here."""

    settings: Settings
    model_provider: ModelProvider | None = None
    running: bool = False
    state: AgentState = AgentState.IDLE
    tool_registry: ToolRegistry | None = None
    permission_engine: PermissionEngine | None = None
    memory_manager: MemoryManager | None = None
    events: list[AgentEvent] = field(default_factory=list)
    _active_task: AgentTask | None = field(default=None, init=False, repr=False)
    _active_conversation: tuple[dict[str, object], ...] = field(default=(), init=False, repr=False)
    _active_iteration: int = field(default=1, init=False, repr=False)
    _pending_memory_candidate: MemoryCandidate | None = field(default=None, init=False, repr=False)
    _suspended_task_id: str | None = field(default=None, init=False, repr=False)
    current_plan: AgentPlan | None = field(default=None, init=False)
    plan_history: list[AgentPlan] = field(default_factory=list, init=False)
    _replan_count: int = field(default=0, init=False, repr=False)
    emergency_stop: EmergencyStop = field(default_factory=EmergencyStop)
    _active_tool: Any = field(default=None, init=False, repr=False)

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
            safe_defaults["terminal.development"] = PermissionLevel.SAFE
            safe_defaults["browser.safe"] = PermissionLevel.SAFE
            safe_defaults["application.safe"] = PermissionLevel.SAFE
            safe_defaults["computer.click"] = PermissionLevel.SAFE
            self.permission_engine = PermissionEngine(PermissionPolicy(safe_defaults))
        if self.tool_registry is not None and self.permission_engine is not None:
            security = PathSecurityLayer(self.settings.security_policy)
            for tool in (
                ListDirectoryTool(security, self.permission_engine),
                SearchFilesTool(security, self.permission_engine),
                ReadFileTool(security, self.permission_engine),
                TerminalTool(
                    self.permission_engine,
                    timeout_seconds=self.settings.tool_timeout_seconds,
                    output_limit_bytes=self.settings.terminal_output_limit_bytes,
                ),
                BrowserTool(
                    self.permission_engine,
                    BrowserPolicy(
                        allowed_hosts=self.settings.browser_allowed_hosts,
                        search_url=self.settings.browser_search_url,
                        max_response_bytes=self.settings.browser_max_response_bytes,
                        timeout_seconds=self.settings.browser_timeout_seconds,
                    ),
                ),
                ApplicationTool(
                    self.permission_engine,
                    timeout_seconds=self.settings.tool_timeout_seconds,
                ),
                ComputerUseTool(
                    self.permission_engine,
                    ComputerPolicy(),
                    ControlledTestBackend(WindowBounds(1, 1)),
                    timeout_seconds=self.settings.tool_timeout_seconds,
                ),
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
        return self._run_task_state(task, conversation, 1)

    def _run_task_state(
        self,
        task: AgentTask,
        conversation: tuple[dict[str, object], ...],
        start_iteration: int,
    ) -> ModelResponse:
        self._active_task = task
        self._active_conversation = conversation
        self._replan_count = 0
        self.state = AgentState.IDLE
        self.events.clear()
        self._record(task, "task_started", AgentState.IDLE)

        for iteration in range(start_iteration, task.max_iterations + 1):
            self._raise_if_emergency_stop(task)
            self._active_iteration = iteration
            self._active_conversation = conversation
            if self.state == AgentState.CANCELLED:
                raise RuntimeError("Agent task was cancelled")
            self.state = AgentState.THINKING
            self._record(task, "model_requested", self.state, iteration=iteration)
            try:
                response = self.generate(
                    ModelRequest(
                        prompt=task.goal,
                        conversation=conversation,
                        tools=self._tool_definitions(),
                        timeout_seconds=self.settings.tool_timeout_seconds,
                    )
                )
                self._raise_if_emergency_stop(task)
            except ModelError:
                self.state = AgentState.FAILED
                self._record(task, "model_failed", self.state, iteration=iteration)
                raise

            tool_calls = tuple(
                ToolCall(call.call_id, call.name, dict(call.arguments))
                for call in response.tool_calls
            )
            plan = AgentPlan(
                task_id=task.task_id,
                iteration=iteration,
                steps=tuple(
                    PlanStep(
                        step_id=call.call_id,
                        objective=f"Execute {call.name}",
                        tool=call.name,
                        arguments=call.arguments,
                        expected_result="The registered tool completes successfully",
                    )
                    for call in tool_calls
                ),
                replan_count=self._replan_count,
                tool_calls=tool_calls,
                final_response=response.text if not response.tool_calls else None,
            )
            if plan.final_response is not None:
                self.state = AgentState.COMPLETED
                self._record(task, "task_completed", self.state, iteration=iteration)
                return response

            self.current_plan = plan
            self.plan_history.append(plan)
            self._record(task, "plan_created", AgentState.THINKING, iteration=iteration, steps=len(plan.steps))
            self.state = AgentState.WAITING_FOR_APPROVAL
            self._record(task, "tool_requests_received", self.state, count=len(plan.tool_calls))
            completed, results = self._execute_plan(task, plan, iteration)
            self._raise_if_emergency_stop(task)
            self.state = AgentState.OBSERVING
            self._record(task, "tool_results_received", self.state, count=len(results))
            conversation = self._append_results(conversation, response, results)
            self._active_conversation = conversation
            if not completed:
                if self._replan_count >= self.settings.max_replans:
                    self.state = AgentState.FAILED
                    self._record(task, "replan_limit_reached", self.state, limit=self.settings.max_replans)
                    raise RuntimeError("Agent maximum replans exceeded")
                self._replan_count += 1
                self._record(task, "plan_replanned", AgentState.THINKING, replan=self._replan_count)

        self.state = AgentState.FAILED
        self._record(task, "iteration_limit_reached", self.state, limit=task.max_iterations)
        raise RuntimeError("Agent maximum iterations exceeded")

    def _execute_plan(
        self,
        task: AgentTask,
        plan: AgentPlan,
        iteration: int,
    ) -> tuple[bool, tuple[ToolResult, ...]]:
        """Execute steps in order, preserving successful steps across recovery."""
        results: list[ToolResult] = []
        current = plan
        for index, step in enumerate(plan.steps):
            attempts = 0
            while attempts <= self.settings.max_step_retries:
                self._raise_if_emergency_stop(task)
                attempts += 1
                current = replace(
                    current,
                    current_step_index=index,
                    retry_count=max(0, attempts - 1),
                    steps=tuple(
                        replace(item, status=PlanStepStatus.EXECUTING, attempts=attempts)
                        if item.step_id == step.step_id
                        else item
                        for item in current.steps
                    ),
                )
                self.current_plan = current
                call = ToolCall(step.step_id, step.tool, step.arguments)
                result = self._handle_tool_call(task, call, iteration)
                results.append(result)
                succeeded = self._verify_step(result)
                updated_step = replace(
                    step,
                    actual_result=result,
                    status=PlanStepStatus.SUCCEEDED if succeeded else PlanStepStatus.FAILED,
                    attempts=attempts,
                )
                current = replace(
                    current,
                    steps=tuple(updated_step if item.step_id == step.step_id else item for item in current.steps),
                )
                self.current_plan = current
                self._record(
                    task,
                    "step_observed",
                    AgentState.OBSERVING,
                    step=step.step_id,
                    success=succeeded,
                    attempt=attempts,
                )
                if succeeded:
                    break
                if attempts <= self.settings.max_step_retries:
                    self._record(task, "step_retry", AgentState.THINKING, step=step.step_id, attempt=attempts)
            else:
                self._record(task, "step_failed", AgentState.FAILED, step=step.step_id)
                return False, tuple(results)
        return True, tuple(results)

    @staticmethod
    def _verify_step(result: ToolResult) -> bool:
        """Verify only the structured result, never the model's assertion."""
        return result.success

    def propose_memory_for_current_task(self, candidate: MemoryCandidate) -> MemoryCandidate:
        """Process a candidate and pause the active task if user approval is needed."""
        if self.memory_manager is None or self._active_task is None:
            raise RuntimeError("No active task memory workflow is configured")
        processed = self.memory_manager.propose_candidate(candidate)
        if processed.status is not MemoryCandidateStatus.PENDING:
            return processed
        self.memory_manager.suspend_task(
            task_id=self._active_task.task_id,
            goal=self._active_task.goal,
            max_iterations=self._active_task.max_iterations,
            iteration=self._active_iteration,
            conversation=self._active_conversation,
            agent_state=AgentState.WAITING_FOR_APPROVAL.value,
        )
        self._pending_memory_candidate = processed
        self._suspended_task_id = self._active_task.task_id
        self.state = AgentState.WAITING_FOR_APPROVAL
        self._record(self._active_task, "memory_approval_required", self.state)
        raise MemoryApprovalRequired(processed)

    def resume_memory_task(self, *, approve: bool) -> ModelResponse:
        """Resolve pending memory approval and continue the exact suspended task."""
        if self.memory_manager is None or self._pending_memory_candidate is None or self._suspended_task_id is None:
            raise RuntimeError("No memory approval is pending")
        self._raise_if_emergency_stop(self._active_task)
        candidate = self._pending_memory_candidate
        if approve:
            self.memory_manager.approve_memory(candidate.candidate_id)
        else:
            self.memory_manager.reject_memory(candidate.candidate_id)
        checkpoint = self.memory_manager.resume_task(self._suspended_task_id)
        self._pending_memory_candidate = None
        self._suspended_task_id = None
        resumed_task = AgentTask(checkpoint.task_id, checkpoint.goal, checkpoint.max_iterations)
        return self._run_task_state(resumed_task, checkpoint.conversation, checkpoint.iteration)

    def cancel(self) -> None:
        """Request cancellation before the next model or tool step."""
        self.state = AgentState.CANCELLED

    def trigger_emergency_stop(self, reason: str = "host emergency stop") -> EmergencyStopStatus:
        """Stop from the host/UI independently of the LLM."""
        status = self.emergency_stop.trigger(reason)
        self.state = AgentState.CANCELLED
        tool = self._active_tool
        if tool is not None and hasattr(tool, "cancel"):
            tool.cancel()
        return status

    def _handle_tool_call(self, task: AgentTask, call: ToolCall, iteration: int) -> ToolResult:
        self._raise_if_emergency_stop(task)
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
        self._active_tool = tool
        future = executor.submit(tool.execute, call.arguments)
        try:
            deadline = time.monotonic() + self.settings.tool_timeout_seconds
            while True:
                if self.emergency_stop.is_triggered():
                    future.cancel()
                    if hasattr(tool, "cancel"):
                        tool.cancel()
                    result = ToolResult(
                        call.call_id,
                        call.name,
                        False,
                        error=ToolError("emergency_stop", "agent execution was emergency-stopped", True),
                    )
                    break
                try:
                    value = future.result(timeout=0.05)
                    result = ToolResult(call.call_id, call.name, True, value=value)
                    break
                except FutureTimeoutError:
                    if time.monotonic() >= deadline:
                        future.cancel()
                        result = ToolResult(
                            call.call_id,
                            call.name,
                            False,
                            error=ToolError("timeout", "tool execution timed out", retryable=True),
                        )
                        break
        except Exception as error:
            result = ToolResult(
                call.call_id,
                call.name,
                False,
                error=ToolError("execution_failed", f"tool execution failed: {error}"),
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            self._active_tool = None
        self._record(task, "tool_finished", self.state, iteration=iteration, tool=call.name, success=result.success)
        return result

    def _raise_if_emergency_stop(self, task: AgentTask | None) -> None:
        if not self.emergency_stop.is_triggered():
            return
        self.state = AgentState.CANCELLED
        if task is not None:
            self._record(task, "emergency_stop", self.state)
        raise EmergencyStopTriggered(self.emergency_stop.status.reason or "host emergency stop")

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
