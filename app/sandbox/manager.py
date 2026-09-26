"""Explicit, resettable Hermes sandbox environment."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from app.config.settings import SecurityPolicy
from app.filesystem import ListDirectoryTool, PathSecurityLayer, ReadFileTool, SearchFilesTool
from app.security.permissions import PermissionEngine
from app.terminal import TerminalTool


@dataclass(frozen=True)
class SandboxStatus:
    enabled: bool
    root: Path
    label: str = "SANDBOX MODE"


class SandboxFilesystem:
    """Explicit facade over read-only filesystem tools rooted only in the sandbox."""

    def __init__(self, root: Path, permission_engine: PermissionEngine, policy: SecurityPolicy) -> None:
        self.root = root
        security = PathSecurityLayer(policy)
        self._tools = {
            tool.name: tool
            for tool in (
                ListDirectoryTool(security, permission_engine),
                SearchFilesTool(security, permission_engine),
                ReadFileTool(security, permission_engine),
            )
        }

    def execute(self, tool_name: str, arguments: dict[str, object]):
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"unknown sandbox filesystem tool: {tool_name}")
        result = tool.execute(arguments)
        return replace(result, sandbox_mode=True)

    def status_message(self) -> str:
        return f"SANDBOX MODE: filesystem root={self.root}"


class SandboxManager:
    """Create and reset an explicitly selected sandbox without redirecting normal tools."""

    def __init__(self, root: Path | str = Path("data/sandbox")) -> None:
        self.root = Path(root).expanduser().resolve()
        if self.root.parent == self.root:
            raise ValueError("sandbox root cannot be a filesystem root")
        self.root.mkdir(parents=True, exist_ok=True)
        self.status = SandboxStatus(True, self.root)

    def reset(self) -> None:
        """Delete only children contained by the sandbox root."""
        resolved_root = self.root.resolve()
        for child in tuple(resolved_root.iterdir()):
            resolved_child = child.resolve(strict=False)
            if resolved_child != resolved_root and resolved_root not in resolved_child.parents:
                raise RuntimeError("sandbox child escapes sandbox root")
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        self.root.mkdir(parents=True, exist_ok=True)

    def filesystem(self, permission_engine: PermissionEngine) -> SandboxFilesystem:
        policy = SecurityPolicy(allowed_filesystem_roots=(self.root,))
        return SandboxFilesystem(self.root, permission_engine, policy)

    def terminal(self, permission_engine: PermissionEngine, *, timeout_seconds: float = 30.0, output_limit_bytes: int = 65_536) -> TerminalTool:
        return TerminalTool(
            permission_engine,
            sandbox_cwd=self.root,
            sandbox_mode=True,
            timeout_seconds=timeout_seconds,
            output_limit_bytes=output_limit_bytes,
        )

    def status_message(self) -> str:
        return f"SANDBOX MODE: active root={self.root}"