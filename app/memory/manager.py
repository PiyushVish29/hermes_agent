"""Memory lifecycle boundary; persistence is intentionally not implemented yet."""

from __future__ import annotations


class MemoryManager:
    """Future owner of bounded, auditable memory reads and writes."""

    def remember(self, key: str, value: str) -> None:
        """Reserve the write API without persisting data in milestone 1."""
        raise NotImplementedError("Memory persistence is not implemented")

    def recall(self, key: str) -> str | None:
        """Reserve the read API without exposing filesystem access."""
        raise NotImplementedError("Memory retrieval is not implemented")
