"""Authorization, indexing, retrieval, re-indexing, and deletion tests."""

from pathlib import Path

import pytest

from app.config.settings import SecurityPolicy, Settings
from app.rag.manager import RagManager
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy


def rag_manager(root: Path, database: Path | None = None) -> RagManager:
    settings = Settings(
        security_policy=SecurityPolicy(allowed_filesystem_roots=(root,)),
        rag_index_roots=(root,),
        rag_database_location=database or root / "rag.sqlite3",
        rag_chunk_size_chars=100,
        rag_chunk_overlap_chars=20,
    )
    permissions = PermissionEngine(
        PermissionPolicy(
            {
                "rag.index": PermissionLevel.SAFE,
                "rag.retrieve": PermissionLevel.SAFE,
                "rag.delete": PermissionLevel.SAFE,
            }
        )
    )
    return RagManager(settings, permissions)


def test_index_and_retrieve_return_source_references(tmp_path: Path) -> None:
    document = tmp_path / "guide.md"
    document.write_text("Hermes local RAG stores approved project documentation. " * 8, encoding="utf-8")
    manager = rag_manager(tmp_path)

    report = manager.index()
    results = manager.retrieve("approved project documentation")

    assert report.indexed_documents == 1
    assert report.indexed_chunks > 1
    assert results
    assert results[0].source.path == str(document.resolve())
    assert results[0].source.chunk_index >= 0


def test_roots_are_explicit_and_empty_configuration_does_not_index(tmp_path: Path) -> None:
    settings = Settings(
        security_policy=SecurityPolicy(allowed_filesystem_roots=(tmp_path,)),
        rag_database_location=tmp_path / "rag.sqlite3",
    )
    manager = RagManager(settings, PermissionEngine(PermissionPolicy({"rag.index": PermissionLevel.SAFE})))

    with pytest.raises(ValueError, match="no RAG index roots"):
        manager.index()


def test_sensitive_and_unsupported_files_are_excluded(tmp_path: Path) -> None:
    (tmp_path / "safe.txt").write_text("approved content", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=secret", encoding="utf-8")
    (tmp_path / "private.pem").write_text("private key", encoding="utf-8")
    (tmp_path / "image.bin").write_bytes(b"not a document")
    manager = rag_manager(tmp_path)

    report = manager.index()
    results = manager.retrieve("approved content")

    assert report.indexed_documents == 1
    assert report.skipped_files >= 3
    assert all(".env" not in result.source.path and ".pem" not in result.source.path for result in results)


def test_reindex_updates_documents_and_removes_stale_chunks(tmp_path: Path) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("old information", encoding="utf-8")
    manager = rag_manager(tmp_path)
    manager.index()
    document.write_text("new information", encoding="utf-8")

    report = manager.index()

    assert manager.retrieve("new information")[0].content == "new information"
    assert report.removed_documents == 0
    document.unlink()
    report = manager.index()
    assert report.removed_documents == 1
    assert manager.retrieve("new information") == ()


def test_delete_indexed_data_is_separate_from_memory(tmp_path: Path) -> None:
    database = tmp_path / "rag.sqlite3"
    (tmp_path / "doc.txt").write_text("separate retrieval data", encoding="utf-8")
    manager = rag_manager(tmp_path, database)
    manager.index()

    deleted = manager.delete_indexed_data()

    assert deleted == 1
    assert manager.retrieve("separate retrieval data") == ()
    assert database.exists()
    assert not (tmp_path / "memory.sqlite3").exists()


def test_every_rag_operation_requires_permission(tmp_path: Path) -> None:
    settings = Settings(
        security_policy=SecurityPolicy(allowed_filesystem_roots=(tmp_path,)),
        rag_index_roots=(tmp_path,),
        rag_database_location=tmp_path / "rag.sqlite3",
    )
    manager = RagManager(settings, PermissionEngine())

    with pytest.raises(PermissionError):
        manager.index()
    with pytest.raises(PermissionError):
        manager.retrieve("anything")
    with pytest.raises(PermissionError):
        manager.delete_indexed_data()