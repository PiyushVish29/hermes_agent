"""Isolation and explicit-mode tests for the Hermes sandbox."""

from pathlib import Path

import pytest

from app.filesystem import ReadFileTool, PathSecurityLayer
from app.config.settings import SecurityPolicy
from app.sandbox import SandboxManager
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy


def permissions() -> PermissionEngine:
    return PermissionEngine(
        PermissionPolicy(
            {
                "filesystem.read": PermissionLevel.SAFE,
                "terminal.development": PermissionLevel.SAFE,
            }
        )
    )


def test_sandbox_filesystem_isolated_and_explicit(tmp_path: Path) -> None:
    sandbox_root = tmp_path / "sandbox"
    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "outside.txt").write_text("real data", encoding="utf-8")
    manager = SandboxManager(sandbox_root)
    sandbox = manager.filesystem(permissions())
    (sandbox_root / "inside.txt").write_text("sandbox data", encoding="utf-8")

    result = sandbox.execute("read_file", {"path": "inside.txt"})
    escaped = sandbox.execute("read_file", {"path": str(real_root / "outside.txt")})

    assert result.success
    assert result.sandbox_mode
    assert result.content == "sandbox data"
    assert not escaped.success
    assert escaped.error.code == "outside_allowed_root"
    assert manager.status_message().startswith("SANDBOX MODE")


def test_sandbox_traversal_cannot_escape(tmp_path: Path) -> None:
    manager = SandboxManager(tmp_path / "sandbox")
    sandbox = manager.filesystem(permissions())
    outside = tmp_path / "outside.txt"
    outside.write_text("real", encoding="utf-8")

    result = sandbox.execute("read_file", {"path": "../outside.txt"})

    assert not result.success
    assert result.error.code == "path_traversal"


def test_sandbox_reset_removes_only_sandbox_state(tmp_path: Path) -> None:
    sandbox_root = tmp_path / "sandbox"
    real_file = tmp_path / "real.txt"
    manager = SandboxManager(sandbox_root)
    (sandbox_root / "temporary.txt").write_text("temporary", encoding="utf-8")
    real_file.write_text("keep", encoding="utf-8")

    manager.reset()

    assert list(sandbox_root.iterdir()) == []
    assert real_file.read_text(encoding="utf-8") == "keep"


def test_sandbox_terminal_is_explicit_and_scoped(tmp_path: Path) -> None:
    manager = SandboxManager(tmp_path / "sandbox")
    terminal = manager.terminal(permissions())

    assert terminal.sandbox_mode
    assert terminal.sandbox_cwd == (tmp_path / "sandbox").resolve()
    assert "SANDBOX MODE" in manager.status_message()


def test_normal_filesystem_tool_is_not_silently_redirected(tmp_path: Path) -> None:
    normal_root = tmp_path / "normal"
    sandbox_root = tmp_path / "sandbox"
    normal_root.mkdir()
    sandbox_root.mkdir()
    (sandbox_root / "only-sandbox.txt").write_text("sandbox", encoding="utf-8")
    normal = ReadFileTool(
        PathSecurityLayer(SecurityPolicy(allowed_filesystem_roots=(normal_root,))),
        permissions(),
    )

    result = normal.execute({"path": "only-sandbox.txt"})

    assert not result.success
    assert result.error.code == "not_found"