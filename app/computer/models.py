"""Structured computer-use proposals, screenshots, and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ComputerAction(str, Enum):
    CLICK = "click"
    TYPE_TEXT = "type_text"


@dataclass(frozen=True)
class WindowBounds:
    width: int
    height: int


@dataclass(frozen=True)
class Screenshot:
    target_application: str
    bounds: WindowBounds
    digest: str
    captured_at: float


@dataclass(frozen=True)
class VisionProposal:
    """Untrusted vision output; it has no execution authority."""

    action: str
    target_application: str
    x: int | None = None
    y: int | None = None
    text: str | None = None


@dataclass(frozen=True)
class ComputerPolicy:
    """Host-owned target bounds; empty by default to prevent desktop-wide use."""

    targets: Mapping[str, WindowBounds] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", MappingProxyType(dict(self.targets)))


@dataclass(frozen=True)
class ComputerError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class ComputerResult:
    action: str
    target_application: str
    success: bool
    verified: bool = False
    screenshot: Screenshot | None = None
    error: ComputerError | None = None