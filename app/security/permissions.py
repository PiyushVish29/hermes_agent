"""Permission boundary for future tool requests."""

from __future__ import annotations


class PermissionEngine:
    """Placeholder for explicit policy checks; deny by default for now."""

    def is_allowed(self, tool_name: str, arguments: dict[str, object]) -> bool:
        """Deny capabilities until a concrete policy and tool exist."""
        return False
