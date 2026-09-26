"""Authorized local document indexing and retrieval."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.config.settings import Settings
from app.filesystem.security import PathSecurityError, PathSecurityLayer
from app.rag.embeddings import LocalEmbedder
from app.rag.models import RagError, RagIndexReport, RagSearchResult, RagSource
from app.rag.storage import RagStorage
from app.security.permissions import PermissionEngine, PermissionRequest


class RagManager:
    """Keep approved-document retrieval separate from personal memory."""

    def __init__(
        self,
        settings: Settings,
        permission_engine: PermissionEngine,
        *,
        storage: RagStorage | None = None,
        security: PathSecurityLayer | None = None,
        embedder: LocalEmbedder | None = None,
    ) -> None:
        self.settings = settings
        self.permission_engine = permission_engine
        self.storage = storage or RagStorage(settings.rag_database_location)
        self.security = security or PathSecurityLayer(settings.security_policy)
        self.embedder = embedder or LocalEmbedder()

    def index(self) -> RagIndexReport:
        self._authorize("rag.index", {"root_count": len(self.settings.rag_index_roots)})
        if not self.settings.rag_index_roots:
            raise ValueError("no RAG index roots are configured")
        indexed_paths: set[str] = set()
        documents = chunks = skipped = 0
        for configured_root in self.settings.rag_index_roots:
            root = self.security.resolve(str(configured_root))
            if not root.path.is_dir():
                raise ValueError(f"RAG index root is not a directory: {configured_root}")
            for current, directories, filenames in os.walk(root.path, followlinks=False):
                directories[:] = [directory for directory in directories if self._safe_directory(Path(current) / directory)]
                for filename in filenames:
                    path = Path(current) / filename
                    if path.suffix.lower() not in self.settings.rag_file_extensions:
                        skipped += 1
                        continue
                    try:
                        resolved = self.security.resolve(str(path))
                        size = self.security.check_file_size(resolved)
                        content = resolved.path.read_text(encoding="utf-8")
                    except (PathSecurityError, OSError, UnicodeError):
                        skipped += 1
                        continue
                    chunks_for_file = self._chunk(content)
                    fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    encoded = [(index, chunk, self.embedder.embed(chunk)) for index, chunk in enumerate(chunks_for_file)]
                    self.storage.upsert(str(resolved.path), str(resolved.root), fingerprint, encoded)
                    indexed_paths.add(str(resolved.path))
                    documents += 1
                    chunks += len(encoded)
        removed = 0
        for stale in self.storage.indexed_paths() - indexed_paths:
            self.storage.delete_path(stale)
            removed += 1
        return RagIndexReport(documents, chunks, skipped, removed)

    def retrieve(self, query: str, *, limit: int = 5) -> tuple[RagSearchResult, ...]:
        self._authorize("rag.retrieve", {"query": "query", "limit": limit})
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        query_embedding = self.embedder.embed(query)
        results = []
        for path, root, chunk_index, content, embedding in self.storage.search():
            results.append(
                RagSearchResult(content, self.embedder.similarity(query_embedding, embedding), RagSource(path, root, chunk_index))
            )
        return tuple(sorted(results, key=lambda result: result.score, reverse=True)[:limit])

    def delete_indexed_data(self, path: str | None = None) -> int:
        self._authorize("rag.delete", {"path": "configured" if path else "all"})
        if path is None:
            return self.storage.delete_all()
        resolved = self.security.resolve(path)
        return self.storage.delete_under(str(resolved.path))

    def _authorize(self, action: str, arguments: dict[str, object]) -> None:
        decision = self.permission_engine.decide(
            PermissionRequest(action, action, arguments, source="rag")
        )
        if not decision.permitted:
            raise PermissionError(decision.reason)

    def _safe_directory(self, path: Path) -> bool:
        try:
            self.security.resolve(str(path))
            return True
        except PathSecurityError:
            return False

    def _chunk(self, content: str) -> list[str]:
        size = self.settings.rag_chunk_size_chars
        overlap = self.settings.rag_chunk_overlap_chars
        chunks: list[str] = []
        start = 0
        while start < len(content):
            end = min(start + size, len(content))
            if end < len(content):
                boundary = content.rfind("\n", start, end)
                if boundary > start + size // 2:
                    end = boundary
            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(content):
                break
            start = max(start + 1, end - overlap)
        return chunks