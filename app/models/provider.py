"""Provider-neutral model contracts for Hermes Local."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ToolCallRequest:
    """A tool invocation requested by a model; execution is owned elsewhere."""

    call_id: str
    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolDefinition:
    """Provider-neutral description of a tool available to a model."""

    name: str
    description: str = ""
    parameters: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelRequest:
    """Input accepted by every model provider."""

    prompt: str
    conversation: tuple[Mapping[str, object], ...] = ()
    system_prompt: str | None = None
    response_schema: Mapping[str, object] | None = None
    tools: tuple[ToolDefinition, ...] = ()
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class ModelMetadata:
    """Provider and model identity returned with a response."""

    provider: str
    model: str
    capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ModelResponse:
    """Normalized model output, including optional structured data and tool calls."""

    text: str = ""
    structured_data: Mapping[str, object] | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    metadata: ModelMetadata = field(
        default_factory=lambda: ModelMetadata(provider="unknown", model="unknown")
    )
    finish_reason: str = "stop"


class ModelError(Exception):
    """Base error raised when a provider cannot produce a response."""

    def __init__(self, message: str, *, code: str = "provider_error", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ModelTimeoutError(ModelError):
    """Raised when a provider exceeds the configured request timeout."""

    def __init__(self, message: str = "Model request timed out") -> None:
        super().__init__(message, code="timeout", retryable=True)


class ModelProvider(ABC):
    """Stable interface the agent uses without knowing a model vendor."""

    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a normalized response for a provider-neutral request."""
        raise NotImplementedError
