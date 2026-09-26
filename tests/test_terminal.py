"""Security and execution tests for the controlled terminal tool."""

import sys
import threading
import time

import pytest

from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy
from app.terminal.models import CommandClass, CommandPolicy, CommandSpec
from app.terminal.tool import TerminalTool
from app.tools.base import ToolValidationError


def tool(spec: CommandSpec, *, timeout: float = 2, output_limit: int = 65536) -> TerminalTool:
    permission = PermissionEngine(PermissionPolicy({spec.permission_requirement: PermissionLevel.SAFE}))
    return TerminalTool(
        permission,
        policy=CommandPolicy({spec.name: spec}),
        timeout_seconds=timeout,
        output_limit_bytes=output_limit,
    )


def python_spec(script: str, classification: CommandClass = CommandClass.ALLOWED) -> CommandSpec:
    return CommandSpec("test_command", sys.executable, ("-c", script), classification)


def test_allowed_command_captures_stdout_and_stderr_separately() -> None:
    terminal = tool(python_spec("import sys; print('out'); print('err', file=sys.stderr)"))

    result = terminal.execute({"command": "test_command"})

    assert result.success
    assert result.stdout.strip() == "out"
    assert result.stderr.strip() == "err"


def test_unknown_command_fails_closed() -> None:
    terminal = tool(python_spec("print('safe')"))

    with pytest.raises(ToolValidationError) as error:
        terminal.validate({"command": "powershell"})

    assert error.value.code == "unknown_command"


def test_blocked_command_is_rejected() -> None:
    terminal = tool(python_spec("print('blocked')", CommandClass.BLOCKED))

    with pytest.raises(ToolValidationError, match="blocked"):
        terminal.validate({"command": "test_command"})


def test_malformed_arguments_and_arbitrary_arguments_are_rejected() -> None:
    terminal = tool(python_spec("print('safe')"))

    with pytest.raises(ToolValidationError):
        terminal.validate({"command": "test_command", "arguments": ["--unsafe"]})
    with pytest.raises(ToolValidationError):
        terminal.validate({"command": "test_command", "arguments": "--unsafe"})


def test_timeout_returns_structured_failure() -> None:
    terminal = tool(python_spec("import time; time.sleep(1)"), timeout=0.05)

    result = terminal.execute({"command": "test_command"})

    assert not result.success
    assert result.timed_out
    assert result.error.code == "timeout"


def test_output_is_bounded() -> None:
    terminal = tool(python_spec("print('x' * 5000)"), output_limit=100)

    result = terminal.execute({"command": "test_command"})

    assert result.success
    assert len(result.stdout.encode()) <= 100
    assert result.stdout_truncated


def test_secret_environment_values_are_not_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_TEST_SECRET", "do-not-expose")
    terminal = tool(
        python_spec("import os; print(os.getenv('HERMES_TEST_SECRET', 'missing'))")
    )

    result = terminal.execute({"command": "test_command"})

    assert result.stdout.strip() == "missing"


def test_cancellation_stops_running_command() -> None:
    terminal = tool(python_spec("import time; time.sleep(10)"), timeout=30)
    holder = []

    worker = threading.Thread(
        target=lambda: holder.append(terminal.execute({"command": "test_command"})),
        daemon=True,
    )
    worker.start()
    time.sleep(0.1)
    terminal.cancel()
    worker.join(timeout=2)

    assert holder and holder[0].cancelled