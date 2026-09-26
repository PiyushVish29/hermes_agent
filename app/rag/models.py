"""Structured local RAG records and results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RagSource:
    path: str
    root: str
    chunk_index: int


@dataclass(frozen=True)
class RagSearchResult:
    content: str
    score: float
    source: RagSource


@dataclass(frozen=True)
class RagIndexReport:
    indexed_documents: int
    indexed_chunks: int
    skipped_files: int
    removed_documents: int


@dataclass(frozen=True)
class RagError:
    code: str
    message: str