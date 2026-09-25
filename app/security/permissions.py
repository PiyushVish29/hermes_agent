"""Permission boundary for future tool requests."""

from __future__ import annotations


class PermissionEngine:
    """Allow only explicitly approved registered tool names."""

    def __init__(self, allowed_tool_names: frozenset[str] = frozenset()) -> None:
        self._allowed_tool_names = allowed_tool_names

    def is_allowed(
        self,
        tool_name: str,
        arguments: dict[str, object],
        permission_requirement: str | None = None,
    ) -> bool:
        """Approve a name only when it was explicitly granted to this engine."""
        return (permission_requirement or tool_name) in self._allowed_tool_names
