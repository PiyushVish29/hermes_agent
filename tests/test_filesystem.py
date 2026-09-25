"""Security tests for the read-only filesystem tools."""

from pathlib import Path
import subprocess

import pytest

from app.config.settings import SecurityPolicy
from app.filesystem.security import PathSecurityLayer
from app.filesystem.tools import ListDirectoryTool, ReadFileTool, SearchFilesTool
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy


def filesystem_tools(root: Path, *, max_size: int = 1024):
    policy = SecurityPolicy(
        allowed_filesystem_roots=(root,),
        max_filesystem_file_size_bytes=max_size,
    )
    security = PathSecurityLayer(policy)
    permissions = PermissionEngine(PermissionPolicy({"filesystem.read": PermissionLevel.SAFE}))
    return (
        ListDirectoryTool(security, permissions),
        SearchFilesTool(security, permissions),
        ReadFileTool(security, permissions),
    )


def test_read_file_returns_structured_content(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    _, _, read_file = filesystem_tools(tmp_path)

    result = read_file.execute({"path": "note.txt"})

    assert result.success
    assert result.content == "hello"
    assert result.relative_path == "note.txt"


@pytest.mark.parametrize("path", ["../outside.txt", "nested/../../outside.txt"])
def test_traversal_is_rejected(tmp_path: Path, path: str) -> None:
    _, _, read_file = filesystem_tools(tmp_path)

    result = read_file.execute({"path": path})

    assert not result.success
    assert result.error.code == "path_traversal"


def test_absolute_path_outside_allowed_root_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-hermes.txt"
    outside.write_text("private", encoding="utf-8")
    _, _, read_file = filesystem_tools(tmp_path)

    result = read_file.execute({"path": str(outside)})

    assert not result.success
    assert result.error.code == "outside_allowed_root"


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-hermes-dir"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("private", encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction.returncode != 0:
            pytest.skip("symlink and junction creation are unavailable")
    _, _, read_file = filesystem_tools(tmp_path)

    result = read_file.execute({"path": "linked/secret.txt"})

    assert not result.success
    assert result.error.code == "outside_allowed_root"


@pytest.mark.parametrize("filename", [".env", "credentials.json", "private.key", "server.pem"])
def test_sensitive_files_are_blocked(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_text("secret", encoding="utf-8")
    _, _, read_file = filesystem_tools(tmp_path)

    result = read_file.execute({"path": filename})

    assert not result.success
    assert result.error.code == "blocked_path"


def test_oversized_file_is_rejected_before_read(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("12345", encoding="utf-8")
    _, _, read_file = filesystem_tools(tmp_path, max_size=4)

    result = read_file.execute({"path": "large.txt"})

    assert not result.success
    assert result.error.code == "file_too_large"


def test_nonexistent_file_is_structured_failure(tmp_path: Path) -> None:
    _, _, read_file = filesystem_tools(tmp_path)

    result = read_file.execute({"path": "missing.txt"})

    assert not result.success
    assert result.error.code == "not_found"


def test_list_and_search_return_metadata_without_contents(tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_text("one", encoding="utf-8")
    (tmp_path / "two.log").write_text("two", encoding="utf-8")
    list_directory, search_files, _ = filesystem_tools(tmp_path)

    listing = list_directory.execute({"path": "."})
    search = search_files.execute({"path": ".", "pattern": "*.txt"})

    assert listing.success
    assert {entry.relative_path for entry in listing.entries} == {"one.txt", "two.log"}
    assert search.success
    assert [entry.relative_path for entry in search.entries] == ["one.txt"]
    assert all(entry.relative_path != "one" for entry in search.entries)


def test_every_filesystem_operation_requires_permission(tmp_path: Path) -> None:
    policy = SecurityPolicy(allowed_filesystem_roots=(tmp_path,))
    security = PathSecurityLayer(policy)
    blocked = PermissionEngine()
    read_file = ReadFileTool(security, blocked)

    result = read_file.execute({"path": "anything.txt"})

    assert not result.success
    assert result.error.code == "permission_denied"