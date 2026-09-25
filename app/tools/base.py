"""Base contract for controlled Hermes tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """A capability with an explicit name and bounded execution contract."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable tool name."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> Any:
        """Execute validated arguments; implementations must enforce their bounds."""
        raise NotImplementedError
