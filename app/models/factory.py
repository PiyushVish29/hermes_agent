"""Provider construction without vendor-specific logic in the agent."""

from __future__ import annotations

from app.config.settings import Settings
from app.models.mock import MockModelProvider
from app.models.ollama import OllamaModelProvider
from app.models.provider import ModelError, ModelProvider


class ModelProviderFactory:
    """Create supported providers behind one application-facing boundary."""

    @staticmethod
    def create(settings: Settings, *, provider: str | None = None) -> ModelProvider:
        name = provider or settings.active_model_provider
        if name == "mock":
            return MockModelProvider()
        if name == "ollama":
            return OllamaModelProvider(
                host=settings.ollama_host,
                model=settings.active_model,
                default_timeout_seconds=settings.tool_timeout_seconds,
            )
        raise ModelError(
            f"Model provider '{name}' is not implemented",
            code="provider_unavailable",
        )