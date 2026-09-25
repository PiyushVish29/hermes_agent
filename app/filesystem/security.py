"""Path normalization and containment checks for filesystem tools."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import SecurityPolicy


class PathSecurityError(ValueError):
    """Raised when a requested path is unsafe or inaccessible by policy."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ResolvedPath:
    path: Path
    root: Path
    relative_path: Path


class PathSecurityLayer:
    """Resolve paths only inside configured roots and reject sensitive targets."""

    _blocked_names = frozenset(
        {
            ".env",
            ".aws",
            ".azure",
            ".ssh",
            "credentials",
            "credentials.json",
            "secrets",
            "id_rsa",
        }
    )

    def __init__(self, policy: SecurityPolicy) -> None:
        self.policy = policy
        self._roots = tuple(root.resolve() for root in policy.allowed_filesystem_roots)

    def resolve(self, requested_path: str, *, must_exist: bool = True) -> ResolvedPath:
        if not isinstance(requested_path, str) or not requested_path.strip():
            raise PathSecurityError("path must be a non-empty string", code="invalid_path")
        if "\x00" in requested_path:
            raise PathSecurityError("path contains a null byte", code="invalid_path")
        requested = Path(requested_path)
        if any(part == ".." for part in requested.parts):
            raise PathSecurityError("path traversal is not allowed", code="path_traversal")
        candidates = (requested,) if requested.is_absolute() else tuple(root / requested for root in self._roots)
        for candidate, root in self._candidate_roots(candidates, requested):
            try:
                resolved = candidate.resolve(strict=False)
            except OSError as error:
                raise PathSecurityError("path could not be resolved", code="resolve_failed") from error
            if not self._within(resolved, root):
                continue
            if must_exist and not resolved.exists():
                raise PathSecurityError("path does not exist", code="not_found")
            relative = resolved.relative_to(root)
            if self._is_blocked(relative):
                raise PathSecurityError("path is blocked by security policy", code="blocked_path")
            return ResolvedPath(resolved, root, relative)
        raise PathSecurityError("path is outside allowed filesystem roots", code="outside_allowed_root")

    def check_file_size(self, path: ResolvedPath) -> int:
        try:
            size = path.path.stat().st_size
        except OSError as error:
            raise PathSecurityError("file metadata is unavailable", code="stat_failed") from error
        if size > self.policy.max_filesystem_file_size_bytes:
            raise PathSecurityError("file exceeds configured size limit", code="file_too_large")
        return size

    def _candidate_roots(self, candidates: tuple[Path, ...], requested: Path):
        if requested.is_absolute():
            yield candidates[0], self._root_for_absolute(candidates[0])
        else:
            yield from zip(candidates, self._roots)

    def _root_for_absolute(self, candidate: Path) -> Path:
        resolved = candidate.resolve(strict=False)
        for root in self._roots:
            if self._within(resolved, root):
                return root
        return self._roots[0]

    @staticmethod
    def _within(path: Path, root: Path) -> bool:
        return path == root or root in path.parents

    def _is_blocked(self, relative: Path) -> bool:
        parts = tuple(part.lower() for part in relative.parts)
        if any(part in self._blocked_names for part in parts):
            return True
        path_text = relative.as_posix().lower()
        return any(
            fnmatch.fnmatchcase(path_text, pattern.lower())
            or fnmatch.fnmatchcase(path_text, pattern.lower().removeprefix("**/"))
            or any(fnmatch.fnmatchcase(part, pattern.lower()) for part in parts)
            for pattern in self.policy.blocked_filesystem_patterns
        )