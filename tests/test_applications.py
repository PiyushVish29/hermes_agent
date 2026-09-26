"""Tests for the controlled Windows application tool."""

import subprocess

import pytest

from app.applications.backend import ApplicationBackend
from app.applications.models import ApplicationPolicy, ApplicationSpec
from app.applications.tool import ApplicationTool
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy
from app.tools.base import ToolValidationError


class FakeApplicationBackend(ApplicationBackend):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def launch(self, spec):
        self.calls.append(("launch", spec.name))
        return True, (1234,)

    def status(self, spec, timeout_seconds):
        self.calls.append(("status", spec.name))
        return True, (1234,)

    def focus(self, spec, timeout_seconds):
        self.calls.append(("focus", spec.name))
        return True, (1234,)

    def close(self, spec, timeout_seconds):
        self.calls.append(("close", spec.name))
        return True, (1234,)


def application_tool(policy_engine=None, backend=None):
    policy = ApplicationPolicy(
        {"demo": ApplicationSpec("demo", "demo.exe", ("demo.exe",))}
    )
    engine = policy_engine or PermissionEngine(
        PermissionPolicy({"application.safe": PermissionLevel.SAFE})
    )
    return ApplicationTool(engine, policy=policy, backend=backend or FakeApplicationBackend())


@pytest.mark.parametrize("action", ["launch", "status", "focus"])
def test_safe_application_operations_are_structured(action: str) -> None:
    backend = FakeApplicationBackend()
    tool = application_tool(backend=backend)

    result = tool.execute({"action": action, "application": "demo"})

    assert result.success
    assert result.process_ids == (1234,)
    assert backend.calls == [(action, "demo")]


def test_unknown_application_and_operation_fail_validation() -> None:
    tool = application_tool()

    with pytest.raises(ToolValidationError, match="supported"):
        tool.validate({"action": "launch", "application": "powershell"})
    with pytest.raises(ToolValidationError, match="unknown application action"):
        tool.validate({"action": "run_script", "application": "demo"})


def test_close_requires_separate_permission() -> None:
    backend = FakeApplicationBackend()
    tool = application_tool(backend=backend)

    result = tool.execute({"action": "close", "application": "demo"})

    assert not result.success
    assert result.error.code == "permission_denied"
    assert backend.calls == []


def test_close_can_only_run_when_host_policy_allows_it() -> None:
    backend = FakeApplicationBackend()
    engine = PermissionEngine(
        PermissionPolicy({"application.safe": PermissionLevel.SAFE, "application.close": PermissionLevel.SAFE})
    )
    tool = application_tool(engine, backend)

    result = tool.execute({"action": "close", "application": "demo"})

    assert result.success
    assert backend.calls == [("close", "demo")]


def test_cancellation_and_timeout_are_structured() -> None:
    tool = application_tool()
    tool.cancel()
    cancelled = tool.execute({"action": "status", "application": "demo"})
    assert not cancelled.success
    assert cancelled.error.code == "cancelled"

    class TimeoutBackend(FakeApplicationBackend):
        def status(self, spec, timeout_seconds):
            raise subprocess.TimeoutExpired("tasklist", timeout_seconds)

    timed_tool = application_tool(backend=TimeoutBackend())
    timed = timed_tool.execute({"action": "status", "application": "demo"})
    assert not timed.success
    assert timed.error.code == "timeout"


def test_permission_audit_contains_no_argument_values() -> None:
    engine = PermissionEngine(PermissionPolicy({"application.safe": PermissionLevel.SAFE}))
    tool = application_tool(engine)

    tool.execute({"action": "status", "application": "demo"})

    audit = engine.audit_events[-1]
    assert audit.argument_keys == ("action", "application")
    assert "demo.exe" not in repr(audit)