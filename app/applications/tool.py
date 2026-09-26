"""Structured controlled application tool."""

from __future__ import annotations

import subprocess
from typing import Any

from app.applications.backend import ApplicationBackend, WindowsApplicationBackend
from app.applications.models import ApplicationAction, ApplicationError, ApplicationPolicy, ApplicationResult
from app.applications.policy import default_application_policy
from app.security.permissions import PermissionEngine, PermissionRequest
from app.tools.base import Tool, ToolValidationError


class ApplicationTool(Tool):
    """Launch/status/focus fixed applications; close requires host permission."""

    name = "application"
    description = "Interact with explicitly supported Windows applications using safe named operations."
    permission_requirement = "application.safe"
    input_schema = {
        "type": "object",
        "properties": {"action": {"type": "string"}, "application": {"type": "string"}},
        "required": ["action", "application"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        permission_engine: PermissionEngine,
        *,
        policy: ApplicationPolicy | None = None,
        backend: ApplicationBackend | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.permission_engine = permission_engine
        self.policy = policy or default_application_policy()
        self.backend = backend or WindowsApplicationBackend()
        self.timeout_seconds = timeout_seconds
        self._cancelled = False

    def validate(self, arguments: dict[str, Any]) -> None:
        super().validate(arguments)
        if arguments.get("action") not in {item.value for item in ApplicationAction}:
            raise ToolValidationError("unknown application action", code="unknown_application_action")
        if self.policy.get(arguments["application"]) is None:
            raise ToolValidationError("application is not supported", code="unsupported_application")

    def execute(self, arguments: dict[str, Any]) -> ApplicationResult:
        self.validate(arguments)
        action = arguments["action"]
        application = arguments["application"]
        if self._cancelled:
            self._cancelled = False
            return self._failure(action, application, "cancelled", "application operation was cancelled")
        spec = self.policy.get(application)
        requirement = "application.close" if action == ApplicationAction.CLOSE.value else "application.safe"
        decision = self.permission_engine.decide(
            PermissionRequest(
                action=f"application:{action}",
                permission_requirement=requirement,
                arguments={"action": action, "application": application},
                source="application_tool",
            )
        )
        if not decision.permitted:
            return self._failure(action, application, "permission_denied", decision.reason)
        try:
            if action == ApplicationAction.LAUNCH.value:
                success, process_ids = self.backend.launch(spec)
            elif action == ApplicationAction.STATUS.value:
                success, process_ids = self.backend.status(spec, self.timeout_seconds)
            elif action == ApplicationAction.FOCUS.value:
                success, process_ids = self.backend.focus(spec, self.timeout_seconds)
            else:
                success, process_ids = self.backend.close(spec, self.timeout_seconds)
            return ApplicationResult(
                action=action,
                application=application,
                success=success,
                running=bool(process_ids),
                process_ids=process_ids,
                error=None if success else ApplicationError("operation_failed", "application operation did not succeed", True),
            )
        except subprocess.TimeoutExpired:
            return self._failure(action, application, "timeout", "application operation timed out", True)
        except OSError:
            return self._failure(action, application, "backend_error", "application backend operation failed", True)

    def cancel(self) -> None:
        self._cancelled = True

    @staticmethod
    def _failure(action: str, application: str, code: str, message: str, retryable: bool = False) -> ApplicationResult:
        return ApplicationResult(
            action=action,
            application=application,
            success=False,
            error=ApplicationError(code, message, retryable),
        )