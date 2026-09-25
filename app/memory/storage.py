"""SQLite persistence mechanics for long-term memory."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.memory.models import MemoryCategory, MemoryDecision, MemoryRecord


class MemoryStorage:
    """Own SQLite schema and CRUD operations; it makes no approval decisions."""

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
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )

    def insert(self, record: MemoryRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.memory_id,
                    record.category.value,
                    record.content,
                    record.source,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
        return self._record(row) if row else None

    def search(self, query: str = "", category: MemoryCategory | None = None) -> tuple[MemoryRecord, ...]:
        clauses = []
        parameters: list[str] = []
        if query:
            clauses.append("content LIKE ?")
            parameters.append(f"%{query}%")
        if category:
            clauses.append("category = ?")
            parameters.append(category.value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM memories{where} ORDER BY updated_at DESC", parameters
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def update(self, memory_id: str, content: str, category: MemoryCategory) -> MemoryRecord:
        updated_at = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute(
                "UPDATE memories SET category = ?, content = ?, updated_at = ? WHERE memory_id = ?",
                (category.value, content, updated_at.isoformat(), memory_id),
            )
        record = self.get(memory_id)
        if record is None:
            raise KeyError(f"memory not found: {memory_id}")
        return record

    def delete(self, memory_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))

    def record_decision(self, decision: MemoryDecision) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memory_decisions (candidate_id, decision, reason, timestamp) VALUES (?, ?, ?, ?)",
                (decision.candidate_id, decision.decision, decision.reason, decision.timestamp.isoformat()),
            )

    def decisions(self, candidate_id: str | None = None) -> tuple[MemoryDecision, ...]:
        with self._connect() as connection:
            if candidate_id:
                rows = connection.execute(
                    "SELECT candidate_id, decision, reason, timestamp FROM memory_decisions WHERE candidate_id = ? ORDER BY decision_id",
                    (candidate_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT candidate_id, decision, reason, timestamp FROM memory_decisions ORDER BY decision_id"
                ).fetchall()
        return tuple(
            MemoryDecision(row["candidate_id"], row["decision"], row["reason"], datetime.fromisoformat(row["timestamp"]))
            for row in rows
        )

    @staticmethod
    def _record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            category=MemoryCategory(row["category"]),
            content=row["content"],
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )