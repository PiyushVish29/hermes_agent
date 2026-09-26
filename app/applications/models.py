"""Structured application catalog and operation results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ApplicationAction(str, Enum):
    LAUNCH = "launch"
    STATUS = "status"
    FOCUS = "focus"
    CLOSE = "close"


@dataclass(frozen=True)
class ApplicationSpec:
    name: str
    executable: str
    process_names: tuple[str, ...]
    launch_arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApplicationPolicy:
    """Immutable host-owned application catalog; the model cannot add apps."""

    applications: Mapping[str, ApplicationSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "applications", MappingProxyType(dict(self.applications)))

    def get(self, name: str) -> ApplicationSpec | None:
        return self.applications.get(name)


@dataclass(frozen=True)
class ApplicationError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class ApplicationResult:
    action: str
    application: str
    success: bool
    running: bool | None = None
    process_ids: tuple[int, ...] = ()
    error: ApplicationError | None = None