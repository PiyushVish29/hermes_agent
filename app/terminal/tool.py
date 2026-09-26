"""Controlled, non-shell Windows command execution."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Any

from app.security.permissions import PermissionEngine, PermissionRequest
from app.terminal.models import CommandPolicy, CommandClass, TerminalError, TerminalResult
from app.terminal.policy import default_command_policy
from app.tools.base import Tool, ToolValidationError


class TerminalTool(Tool):
    """Execute only catalogued development commands without a shell."""

    name = "terminal"
    description = "Run one explicitly catalogued harmless development command."
    permission_requirement = "terminal.development"
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "arguments": {"type": "array"},
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        permission_engine: PermissionEngine,
        *,
        policy: CommandPolicy | None = None,
        timeout_seconds: float = 30.0,
        output_limit_bytes: int = 65_536,
        sandbox_cwd=None,
        sandbox_mode: bool = False,
    ) -> None:
        self.permission_engine = permission_engine
        self.policy = policy or default_command_policy()
        self.timeout_seconds = timeout_seconds
        self.output_limit_bytes = output_limit_bytes
        self.sandbox_cwd = sandbox_cwd
        self.sandbox_mode = sandbox_mode
        self._process: subprocess.Popen[bytes] | None = None
        self._process_lock = threading.Lock()
        self._cancel_requested = threading.Event()

    def validate(self, arguments: dict[str, Any]) -> None:
        super().validate(arguments)
        command = arguments.get("command")
        spec = self.policy.get(command) if isinstance(command, str) else None
        if spec is None:
            raise ToolValidationError("unknown terminal command", code="unknown_command")
        if spec.classification is CommandClass.BLOCKED:
            raise ToolValidationError("terminal command is blocked", code="blocked_command")
        requested_arguments = arguments.get("arguments", [])
        if not isinstance(requested_arguments, list) or any(not isinstance(value, str) for value in requested_arguments):
            raise ToolValidationError("command arguments must be a list of strings")
        if requested_arguments and not spec.allow_user_arguments:
            raise ToolValidationError("command arguments are not allowed", code="arguments_not_allowed")

    def execute(self, arguments: dict[str, Any]) -> TerminalResult:
        self.validate(arguments)
        spec = self.policy.get(arguments["command"])
        if spec is None:
            return self._failure(arguments["command"], "unknown_command", "unknown terminal command")
        permission = self.permission_engine.decide(
            PermissionRequest(
                action=f"terminal:{spec.name}",
                permission_requirement=spec.permission_requirement,
                arguments={"command": spec.name},
                source="terminal_tool",
            )
        )
        if not permission.permitted:
            return self._failure(arguments["command"], "permission_denied", permission.reason)
        if spec.classification is not CommandClass.ALLOWED:
            return self._failure(arguments["command"], "approval_required", "host approval is required")

        self._cancel_requested.clear()
        command = [spec.executable, *spec.fixed_arguments, *arguments.get("arguments", [])]
        environment = self._safe_environment()
        try:
            process = subprocess.Popen(
                command,
                cwd=self.sandbox_cwd or os.getcwd(),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._process_lock:
                self._process = process
            stdout_buffer: list[bytes] = []
            stderr_buffer: list[bytes] = []
            stdout_thread = threading.Thread(target=self._drain, args=(process.stdout, stdout_buffer), daemon=True)
            stderr_thread = threading.Thread(target=self._drain, args=(process.stderr, stderr_buffer), daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            deadline = time.monotonic() + self.timeout_seconds
            while process.poll() is None:
                if self._cancel_requested.is_set():
                    self._terminate(process)
                    return self._result(command[0], process, stdout_buffer, stderr_buffer, cancelled=True)
                if time.monotonic() >= deadline:
                    self._terminate(process)
                    return self._result(command[0], process, stdout_buffer, stderr_buffer, timed_out=True)
                time.sleep(0.02)
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            if self._cancel_requested.is_set():
                return self._result(command[0], process, stdout_buffer, stderr_buffer, cancelled=True)
            return self._result(command[0], process, stdout_buffer, stderr_buffer)
        except OSError as error:
            return self._failure(arguments["command"], "execution_failed", "controlled command could not start")
        finally:
            with self._process_lock:
                self._process = None

    def cancel(self) -> None:
        """Cancel the active command from the host without model authority."""
        self._cancel_requested.set()
        with self._process_lock:
            process = self._process
        if process is not None:
            self._terminate(process)

    def _drain(self, stream: Any, buffer: list[bytes]) -> None:
        if stream is None:
            return
        total = 0
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            remaining = self.output_limit_bytes - total
            if remaining > 0:
                buffer.append(chunk[:remaining])
                total += min(len(chunk), remaining)

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

    def _result(
        self,
        command: str,
        process: subprocess.Popen[bytes],
        stdout_buffer: list[bytes],
        stderr_buffer: list[bytes],
        *,
        timed_out: bool = False,
        cancelled: bool = False,
    ) -> TerminalResult:
        stdout = b"".join(stdout_buffer).decode("utf-8", errors="replace")
        stderr = b"".join(stderr_buffer).decode("utf-8", errors="replace")
        return TerminalResult(
            command=command,
            success=not timed_out and not cancelled and process.returncode == 0,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            cancelled=cancelled,
            stdout_truncated=sum(map(len, stdout_buffer)) >= self.output_limit_bytes,
            stderr_truncated=sum(map(len, stderr_buffer)) >= self.output_limit_bytes,
            error=(
                TerminalError("timeout", "command execution timed out", True)
                if timed_out
                else TerminalError("cancelled", "command execution was cancelled", True)
                if cancelled
                else TerminalError("command_failed", "command returned a non-zero exit code")
                if process.returncode != 0
                else None
            ),
            sandbox_mode=self.sandbox_mode,
        )

    @staticmethod
    def _safe_environment() -> dict[str, str]:
        environment: dict[str, str] = {}
        for name in ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
        return environment

    def _failure(self, command: str, code: str, message: str) -> TerminalResult:
        return TerminalResult(
            command=command,
            success=False,
            error=TerminalError(code, message),
            sandbox_mode=self.sandbox_mode,
        )