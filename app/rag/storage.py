"""SQLite storage mechanics for the separate RAG database."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from app.rag.models import RagSearchResult, RagSource


class RagStorage:
    """Persist indexed chunks separately from personal memory storage."""

    def __init__(self, database_location: Path | str) -> None:
        self.database_location = Path(database_location)
        self.database_location.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_location)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    path TEXT PRIMARY KEY,
                    root TEXT NOT NULL,
                    fingerprint TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    FOREIGN KEY(path) REFERENCES documents(path) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS chunks_path_idx ON chunks(path);
                """
            )

    def upsert(self, path: str, root: str, fingerprint: str, chunks: list[tuple[int, str, tuple[float, ...]]]) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO documents(path, root, fingerprint) VALUES (?, ?, ?)", (path, root, fingerprint))
            connection.execute("DELETE FROM chunks WHERE path = ?", (path,))
            connection.executemany(
                "INSERT INTO chunks(path, chunk_index, content, embedding) VALUES (?, ?, ?, ?)",
                [(path, index, content, json.dumps(embedding)) for index, content, embedding in chunks],
            )

    def indexed_paths(self) -> set[str]:
        with self._connect() as connection:
            return {row["path"] for row in connection.execute("SELECT path FROM documents")}

    def delete_path(self, path: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chunks WHERE path = ?", (path,))
            connection.execute("DELETE FROM documents WHERE path = ?", (path,))

    def delete_under(self, root: str) -> int:
        prefix = f"{root}{os.sep}%"
        with self._connect() as connection:
            rows = connection.execute("SELECT path FROM documents WHERE path = ? OR path LIKE ?", (root, prefix)).fetchall()
            connection.execute("DELETE FROM chunks WHERE path = ? OR path LIKE ?", (root, prefix))
            connection.execute("DELETE FROM documents WHERE path = ? OR path LIKE ?", (root, prefix))
        return len(rows)

    def delete_all(self) -> int:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")
        return count

    def search(self) -> list[tuple[str, str, int, str, tuple[float, ...]]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT chunks.path, documents.root, chunks.chunk_index, chunks.content, chunks.embedding "
                "FROM chunks JOIN documents ON documents.path = chunks.path"
            ).fetchall()
        return [
            (row["path"], row["root"], row["chunk_index"], row["content"], tuple(json.loads(row["embedding"])))
            for row in rows
        ]