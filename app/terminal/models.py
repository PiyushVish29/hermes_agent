"""Typed command policy and terminal results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class CommandClass(str, Enum):
    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CommandSpec:
    name: str
    executable: str
    fixed_arguments: tuple[str, ...] = ()
    classification: CommandClass = CommandClass.BLOCKED
    permission_requirement: str = "terminal.development"
    allow_user_arguments: bool = False


@dataclass(frozen=True)
class CommandPolicy:
    """Immutable, host-owned command catalog; the model cannot add commands."""

    commands: Mapping[str, CommandSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "commands", MappingProxyType(dict(self.commands)))

    def get(self, name: str) -> CommandSpec | None:
        return self.commands.get(name)


@dataclass(frozen=True)
class TerminalError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class TerminalResult:
    command: str
    success: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    error: TerminalError | None = None