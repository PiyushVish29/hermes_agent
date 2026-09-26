"""Safe development command catalog for Windows."""

from __future__ import annotations

import shutil
import sys
from types import MappingProxyType

from app.terminal.models import CommandClass, CommandPolicy, CommandSpec


def default_command_policy() -> CommandPolicy:
    """Return the fixed initial catalog; no shell or arbitrary arguments are allowed."""
    git = shutil.which("git") or "git"
    ollama = shutil.which("ollama") or "ollama"
    commands = {
        "python_version": CommandSpec("python_version", sys.executable, ("--version",), CommandClass.ALLOWED),
        "git_version": CommandSpec("git_version", git, ("--version",), CommandClass.ALLOWED),
        "git_status": CommandSpec("git_status", git, ("status", "--short"), CommandClass.ALLOWED),
        "ollama_version": CommandSpec("ollama_version", ollama, ("--version",), CommandClass.ALLOWED),
    }
    return CommandPolicy(MappingProxyType(commands))