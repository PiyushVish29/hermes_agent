"""Future local retrieval interface."""

from __future__ import annotations


class Retriever:
    """Placeholder for bounded retrieval over approved local indexes."""

    def search(self, query: str) -> list[str]:
        """Search approved indexes once a RAG backend is selected."""
        raise NotImplementedError("RAG is not implemented")
