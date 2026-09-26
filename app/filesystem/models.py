"""Structured filesystem tool results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FilesystemError:
    code: str
    message: str


@dataclass(frozen=True)
class FilesystemEntry:
    relative_path: str
    kind: str
    size_bytes: int | None = None


@dataclass(frozen=True)
class FilesystemResult:
    operation: str
    success: bool
    relative_path: str | None = None
    entries: tuple[FilesystemEntry, ...] = ()
    content: str | None = None
    error: FilesystemError | None = None
    match_count: int = 0
    sandbox_mode: bool = False