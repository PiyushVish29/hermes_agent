"""Base contract for controlled Hermes tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ToolValidationError(ValueError):
    """Raised when a tool request does not satisfy its input contract."""

    def __init__(self, message: str, *, code: str = "invalid_arguments") -> None:
        super().__init__(message)
        self.code = code


class Tool(ABC):
    """A capability with metadata, validation, security, and execution hooks."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable tool name."""
        raise NotImplementedError

    @property
    def description(self) -> str:
        """Return the safe description exposed to the model."""
        return ""

    @property
    def input_schema(self) -> dict[str, object]:
        """Return the JSON-like input schema exposed to the model."""
        return {"type": "object"}

    @property
    def permission_requirement(self) -> str:
        """Return the permission capability required before execution."""
        return self.name

    def validate(self, arguments: dict[str, Any]) -> None:
        """Validate basic schema constraints before security-approved execution."""
        if not isinstance(arguments, dict):
            raise ToolValidationError("tool arguments must be an object")
        schema = self.input_schema
        required = schema.get("required", [])
        if not isinstance(required, list) or any(key not in arguments for key in required):
            raise ToolValidationError("required tool arguments are missing")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, value in arguments.items():
                definition = properties.get(key)
                if isinstance(definition, dict) and definition.get("type") == "string" and not isinstance(value, str):
                    raise ToolValidationError(f"argument '{key}' must be a string")
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            unknown = set(arguments) - set(properties)
            if unknown:
                raise ToolValidationError(f"unknown tool arguments: {', '.join(sorted(unknown))}")

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> Any:
        """Execute validated arguments; implementations must enforce their bounds."""
        raise NotImplementedError
