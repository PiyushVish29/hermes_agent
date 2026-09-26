"""Controlled computer-use tests using an isolated fake backend."""

import time

import pytest

from app.computer import ComputerPolicy, ComputerUseTool, ControlledTestBackend, WindowBounds
from app.computer.backend import ComputerBackend
from app.computer.models import Screenshot, VisionProposal
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy
from app.tools.base import ToolValidationError


def computer_tool(engine=None, backend=None):
    bounds = WindowBounds(800, 600)
    permission = engine or PermissionEngine(PermissionPolicy({"computer.click": PermissionLevel.SAFE}))
    return ComputerUseTool(
        permission,
        ComputerPolicy({"test_app": bounds}),
        backend or ControlledTestBackend(bounds),
        timeout_seconds=1,
    )


def test_click_is_structured_and_verified() -> None:
    backend = ControlledTestBackend(WindowBounds(800, 600))
    tool = computer_tool(backend=backend)

    result = tool.execute({"action": "click", "target_application": "test_app", "x": 10, "y": 20})

    assert result.success
    assert result.verified
    assert backend.actions[0].x == 10
    assert result.screenshot.digest


def test_coordinates_and_targets_are_validated() -> None:
    tool = computer_tool()

    with pytest.raises(ToolValidationError, match="outside target bounds"):
        tool.validate({"action": "click", "target_application": "test_app", "x": 800, "y": 20})
    with pytest.raises(ToolValidationError, match="not configured"):
        tool.validate({"action": "click", "target_application": "desktop", "x": 1, "y": 1})
    with pytest.raises(ToolValidationError, match="unknown computer action"):
        tool.validate({"action": "run_script", "target_application": "test_app"})


def test_sensitive_typing_requires_separate_permission() -> None:
    tool = computer_tool()

    result = tool.execute({"action": "type_text", "target_application": "test_app", "text": "hello"})

    assert not result.success
    assert result.error.code == "permission_denied"


def test_sensitive_typing_can_be_host_enabled_but_is_not_model_authorized() -> None:
    engine = PermissionEngine(
        PermissionPolicy({"computer.click": PermissionLevel.SAFE, "computer.input": PermissionLevel.SAFE})
    )
    backend = ControlledTestBackend(WindowBounds(800, 600))
    tool = computer_tool(engine, backend)

    result = tool.execute({"action": "type_text", "target_application": "test_app", "text": "approved"})

    assert result.success
    assert backend.actions[0].text == "approved"


def test_verification_failure_is_reported() -> None:
    class NoChangeBackend(ControlledTestBackend):
        def verify(self, before, proposal, after):
            return False

    tool = computer_tool(backend=NoChangeBackend(WindowBounds(800, 600)))

    result = tool.execute({"action": "click", "target_application": "test_app", "x": 2, "y": 3})

    assert not result.success
    assert result.error.code == "verification_failed"


def test_timeout_and_emergency_cancellation() -> None:
    class SlowBackend(ControlledTestBackend):
        def perform(self, proposal, timeout_seconds):
            time.sleep(0.2)

    tool = computer_tool(backend=SlowBackend(WindowBounds(800, 600)))
    tool.timeout_seconds = 0.01
    timed = tool.execute({"action": "click", "target_application": "test_app", "x": 2, "y": 3})
    assert not timed.success
    assert timed.error.code == "timeout"

    tool.cancel()
    cancelled = tool.execute({"action": "click", "target_application": "test_app", "x": 2, "y": 3})
    assert not cancelled.success
    assert cancelled.error.code == "cancelled"