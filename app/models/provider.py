"""Provider abstraction for future local or remote model adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ModelProvider(ABC):
    """Stable interface the agent can use without knowing a model vendor."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a response for a prompt."""
        raise NotImplementedError
