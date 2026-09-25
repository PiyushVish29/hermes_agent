"""Registry for explicitly approved tools."""

from __future__ import annotations

from app.tools.base import Tool, ToolValidationError


class ToolRegistry:
    """Store tools by name without providing arbitrary code execution."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register one tool, rejecting accidental name collisions."""
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Return an approved tool, if present."""
        return self._tools.get(name)

    def validate(self, name: str, arguments: dict[str, object]) -> Tool:
        """Retrieve and validate a registered tool before any execution."""
        tool = self.get(name)
        if tool is None:
            raise ToolValidationError(f"tool is not registered: {name}", code="unknown_tool")
        tool.validate(arguments)
        return tool

    def names(self) -> tuple[str, ...]:
        """Return registered names in deterministic order."""
        return tuple(sorted(self._tools))
