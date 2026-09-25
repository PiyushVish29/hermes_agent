"""Read-only filesystem tools guarded by path security and permission policy."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from app.filesystem.models import FilesystemEntry, FilesystemError, FilesystemResult
from app.filesystem.security import PathSecurityError, PathSecurityLayer
from app.security.permissions import PermissionEngine, PermissionRequest
from app.tools.base import Tool, ToolValidationError


class _FilesystemTool(Tool):
    permission_requirement = "filesystem.read"

    def __init__(self, security: PathSecurityLayer, permission_engine: PermissionEngine) -> None:
        self.security = security
        self.permission_engine = permission_engine

    def _authorize(self, operation: str, arguments: dict[str, object]) -> FilesystemError | None:
        decision = self.permission_engine.decide(
            PermissionRequest(operation, self.permission_requirement, arguments, source="filesystem_tool")
        )
        if not decision.permitted:
            return FilesystemError("permission_denied", decision.reason)
        return None

    @staticmethod
    def _failure(operation: str, error: FilesystemError) -> FilesystemResult:
        return FilesystemResult(operation=operation, success=False, error=error)


class ListDirectoryTool(_FilesystemTool):
    name = "list_directory"
    description = "List entries in an approved directory without reading file contents."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any]) -> FilesystemResult:
        denied = self._authorize(self.name, arguments)
        if denied:
            return self._failure(self.name, denied)
        try:
            resolved = self.security.resolve(arguments.get("path", "."))
            if not resolved.path.is_dir():
                return self._failure(self.name, FilesystemError("not_directory", "path is not a directory"))
            entries = []
            for child in sorted(resolved.path.iterdir(), key=lambda item: item.name.lower()):
                try:
                    child_resolved = self.security.resolve(str(child))
                except PathSecurityError:
                    continue
                entries.append(
                    FilesystemEntry(
                        relative_path=child_resolved.relative_path.as_posix(),
                        kind="directory" if child_resolved.path.is_dir() else "file",
                        size_bytes=(child_resolved.path.stat().st_size if child_resolved.path.is_file() else None),
                    )
                )
            return FilesystemResult(self.name, True, resolved.relative_path.as_posix(), tuple(entries))
        except PathSecurityError as error:
            return self._failure(self.name, FilesystemError(error.code, str(error)))
        except OSError as error:
            return self._failure(self.name, FilesystemError("io_error", str(error)))


class SearchFilesTool(_FilesystemTool):
    name = "search_files"
    description = "Find file names matching a pattern under an approved directory."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "pattern": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["pattern"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> None:
        super().validate(arguments)
        if not isinstance(arguments.get("pattern"), str) or not arguments["pattern"].strip():
            raise ToolValidationError("pattern must be a non-empty string")
        if "max_results" in arguments and (
            not isinstance(arguments["max_results"], int) or isinstance(arguments["max_results"], bool)
            or not 1 <= arguments["max_results"] <= 1000
        ):
            raise ToolValidationError("max_results must be between 1 and 1000")

    def execute(self, arguments: dict[str, Any]) -> FilesystemResult:
        denied = self._authorize(self.name, arguments)
        if denied:
            return self._failure(self.name, denied)
        try:
            root = self.security.resolve(arguments.get("path", "."))
            if not root.path.is_dir():
                return self._failure(self.name, FilesystemError("not_directory", "path is not a directory"))
            pattern = arguments["pattern"]
            limit = arguments.get("max_results", 100)
            matches = []
            for current, directories, filenames in os.walk(root.path, followlinks=False):
                directories[:] = [directory for directory in directories if not self._blocked_child(Path(current) / directory)]
                for filename in filenames:
                    candidate = Path(current) / filename
                    try:
                        safe = self.security.resolve(str(candidate))
                    except PathSecurityError:
                        continue
                    if fnmatch.fnmatchcase(filename.lower(), pattern.lower()) or fnmatch.fnmatchcase(safe.relative_path.as_posix().lower(), pattern.lower()):
                        matches.append(FilesystemEntry(safe.relative_path.as_posix(), "file", safe.path.stat().st_size))
                        if len(matches) >= limit:
                            return FilesystemResult(self.name, True, root.relative_path.as_posix(), tuple(matches), match_count=len(matches))
            return FilesystemResult(self.name, True, root.relative_path.as_posix(), tuple(matches), match_count=len(matches))
        except (PathSecurityError, OSError) as error:
            return self._failure(self.name, FilesystemError(getattr(error, "code", "io_error"), str(error)))

    def _blocked_child(self, path: Path) -> bool:
        try:
            self.security.resolve(str(path))
            return False
        except PathSecurityError:
            return True


class ReadFileTool(_FilesystemTool):
    name = "read_file"
    description = "Read a small UTF-8 text file in an approved root."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any]) -> FilesystemResult:
        denied = self._authorize(self.name, arguments)
        if denied:
            return self._failure(self.name, denied)
        try:
            resolved = self.security.resolve(arguments["path"])
            if not resolved.path.is_file():
                return self._failure(self.name, FilesystemError("not_file", "path is not a regular file"))
            self.security.check_file_size(resolved)
            content = resolved.path.read_text(encoding="utf-8")
            return FilesystemResult(self.name, True, resolved.relative_path.as_posix(), content=content)
        except PathSecurityError as error:
            return self._failure(self.name, FilesystemError(error.code, str(error)))
        except (OSError, UnicodeError) as error:
            return self._failure(self.name, FilesystemError("read_failed", str(error)))