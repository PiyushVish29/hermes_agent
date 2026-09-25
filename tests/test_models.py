"""Tests for the provider-neutral model boundary."""

import pytest

from app.agent.controller import AgentController
from app.config.settings import Settings
from app.models.factory import ModelProviderFactory
from app.models.mock import MockModelProvider
from app.models.provider import (
    ModelError,
    ModelMetadata,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
    ToolCallRequest,
    ToolDefinition,
)


def test_controller_generates_through_mock_provider() -> None:
    response = ModelResponse(
        text="ready",
        structured_data={"ok": True},
        tool_calls=(ToolCallRequest("call-1", "list_files", {"path": "data/sandbox"}),),
        metadata=ModelMetadata("mock", "test-model", frozenset({"text", "structured", "tools"})),
    )
    provider = MockModelProvider(response)
    controller = AgentController(Settings(), model_provider=provider)
    request = ModelRequest(
        prompt="Prepare a response",
        response_schema={"type": "object"},
        tools=(ToolDefinition("list_files", "List approved files", {"type": "object"}),),
        timeout_seconds=5,
    )

    result = controller.generate(request)

    assert result == response
    assert provider.requests == [request]
    assert "model: connected" in controller.status_message()


def test_controller_propagates_provider_errors_and_timeouts() -> None:
    request = ModelRequest("hello")
    error = ModelError("provider failed", code="unavailable", retryable=True)
    controller = AgentController(Settings(), model_provider=MockModelProvider(error=error))

    with pytest.raises(ModelError) as raised:
        controller.generate(request)
    assert raised.value.code == "unavailable"
    assert raised.value.retryable

    timeout_controller = AgentController(
        Settings(), model_provider=MockModelProvider(error=ModelTimeoutError())
    )
    with pytest.raises(ModelTimeoutError):
        timeout_controller.generate(request)


def test_factory_keeps_provider_selection_out_of_controller() -> None:
    settings = Settings(active_model_provider="mock")

    provider = ModelProviderFactory.create(settings)

    assert isinstance(provider, MockModelProvider)


def test_factory_creates_ollama_provider_from_configuration() -> None:
    settings = Settings(active_model_provider="ollama")

    provider = ModelProviderFactory.create(settings)

    assert provider.host == settings.ollama_host
    assert provider.model == settings.active_model