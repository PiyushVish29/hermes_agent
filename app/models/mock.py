"""Deterministic model provider used by tests and local development."""

from __future__ import annotations

from collections.abc import Callable

from app.models.provider import (
    ModelError,
    ModelMetadata,
    ModelProvider,
    ModelRequest,
    ModelResponse,
)


class MockModelProvider(ModelProvider):
    """Return a configured response without contacting an external model."""

    def __init__(
        self,
        response: ModelResponse | None = None,
        *,
        error: ModelError | None = None,
        responder: Callable[[ModelRequest], ModelResponse] | None = None,
    ) -> None:
        self.requests: list[ModelRequest] = []
        self._response = response or ModelResponse(
            text="mock response",
            metadata=ModelMetadata(
                provider="mock",
                model="mock-model",
                capabilities=frozenset({"text", "structured", "tools"}),
            ),
        )
        self._error = error
        self._responder = responder

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        if self._responder is not None:
            return self._responder(request)
        return self._response