"""Validated computer-use tool with no arbitrary UI automation surface."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from app.computer.backend import ComputerBackend
from app.computer.models import (
    ComputerAction,
    ComputerError,
    ComputerPolicy,
    ComputerResult,
    VisionProposal,
)
from app.security.permissions import PermissionEngine, PermissionRequest
from app.tools.base import Tool, ToolValidationError


class ComputerUseTool(Tool):
    """Execute only bounded proposed click/type actions in configured targets."""

    name = "computer_use"
    description = "Perform a validated action inside a configured test application target."
    permission_requirement = "computer.click"
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "target_application": {"type": "string"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "text": {"type": "string"},
        },
        "required": ["action", "target_application"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        permission_engine: PermissionEngine,
        policy: ComputerPolicy,
        backend: ComputerBackend,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.permission_engine = permission_engine
        self.policy = policy
        self.backend = backend
        self.timeout_seconds = timeout_seconds
        self._cancelled = False

    def validate(self, arguments: dict[str, Any]) -> None:
        super().validate(arguments)
        action = arguments.get("action")
        target = arguments.get("target_application")
        if action not in {item.value for item in ComputerAction}:
            raise ToolValidationError("unknown computer action", code="unknown_computer_action")
        bounds = self.policy.targets.get(target)
        if bounds is None:
            raise ToolValidationError("target application is not configured", code="unknown_target")
        if action == ComputerAction.CLICK.value:
            if not isinstance(arguments.get("x"), int) or not isinstance(arguments.get("y"), int):
                raise ToolValidationError("click requires integer coordinates")
            if not 0 <= arguments["x"] < bounds.width or not 0 <= arguments["y"] < bounds.height:
                raise ToolValidationError("coordinates are outside target bounds", code="unsafe_coordinates")
        if action == ComputerAction.TYPE_TEXT.value and not isinstance(arguments.get("text"), str):
            raise ToolValidationError("type_text requires text")

    def execute(self, arguments: dict[str, Any]) -> ComputerResult:
        self.validate(arguments)
        action = arguments["action"]
        target = arguments["target_application"]
        if self._cancelled:
            self._cancelled = False
            return self._failure(action, target, "cancelled", "computer action was cancelled")
        requirement = "computer.input" if action == ComputerAction.TYPE_TEXT.value else "computer.click"
        decision = self.permission_engine.decide(
            PermissionRequest(
                action=f"computer:{action}",
                permission_requirement=requirement,
                arguments={"action": action, "target_application": target},
                source="computer_use_tool",
            )
        )
        if not decision.permitted:
            return self._failure(action, target, "permission_denied", decision.reason)
        proposal = VisionProposal(action, target, arguments.get("x"), arguments.get("y"), arguments.get("text"))
        before = self.backend.screenshot(target)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.backend.perform, proposal, self.timeout_seconds)
        try:
            future.result(timeout=self.timeout_seconds)
            if self._cancelled:
                self.backend.cancel()
                return self._failure(action, target, "cancelled", "computer action was cancelled", True)
            after = self.backend.screenshot(target)
            verified = self.backend.verify(before, proposal, after)
            if not verified:
                return self._failure(action, target, "verification_failed", "UI state verification failed", True, after)
            return ComputerResult(action, target, True, verified=True, screenshot=after)
        except FutureTimeoutError:
            self.backend.cancel()
            return self._failure(action, target, "timeout", "computer action timed out", True)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def cancel(self) -> None:
        self._cancelled = True
        self.backend.cancel()

    @staticmethod
    def _failure(action, target, code, message, retryable=False, screenshot=None):
        return ComputerResult(action, target, False, screenshot=screenshot, error=ComputerError(code, message, retryable))