"""Initial harmless Windows application catalog."""

from __future__ import annotations

from types import MappingProxyType

from app.applications.models import ApplicationPolicy, ApplicationSpec


def default_application_policy() -> ApplicationPolicy:
    """Return explicit harmless applications with fixed launch arguments."""
    return ApplicationPolicy(
        MappingProxyType(
            {
                "notepad": ApplicationSpec("notepad", "notepad.exe", ("notepad.exe",)),
                "calculator": ApplicationSpec("calculator", "calc.exe", ("calculator.exe", "calc.exe")),
            }
        )
    )