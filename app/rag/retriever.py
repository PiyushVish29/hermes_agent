"""Local retrieval interface backed by the separate RAG database."""

from __future__ import annotations


from app.rag.manager import RagManager
from app.rag.models import RagSearchResult


class Retriever:
    """Provider-neutral retrieval facade; it never reads personal memory."""

    def __init__(self, manager: RagManager) -> None:
        self.manager = manager

    def search(self, query: str, limit: int = 5) -> tuple[RagSearchResult, ...]:
        return self.manager.retrieve(query, limit=limit)
