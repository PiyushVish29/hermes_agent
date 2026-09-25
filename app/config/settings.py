"""Typed, environment-backed application settings and security policy."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when Hermes configuration is missing or unsafe."""


def _path_from(value: str | Path, field_name: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.parent == path:
        raise ConfigurationError(f"{field_name} must not be a filesystem root")
    if Path.cwd() == path or Path.cwd().is_relative_to(path):
        raise ConfigurationError(f"{field_name} must not contain the application directory")
    return path


def _split(value: str, field_name: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in value.split(os.pathsep) if item.strip())
    if not values:
        raise ConfigurationError(f"{field_name} must contain at least one value")
    return values


@dataclass(frozen=True)
class SecurityPolicy:
    """Immutable policy controlling future filesystem capabilities."""

    allowed_filesystem_roots: tuple[Path, ...] = (Path("data/sandbox"),)
    blocked_filesystem_patterns: tuple[str, ...] = (
        "**/.env",
        "**/.env.*",
        "**/.ssh/**",
        "**/.aws/**",
        "**/credentials*",
        "**/secrets*",
        "**/id_rsa*",
        "**/*.key",
        "**/*.pem",
        "**/*.p12",
        "**/*.pfx",
    )
    max_filesystem_file_size_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        roots = tuple(
            _path_from(root, "allowed_filesystem_roots")
            for root in self.allowed_filesystem_roots
        )
        patterns = tuple(pattern.strip() for pattern in self.blocked_filesystem_patterns)
        if not roots:
            raise ConfigurationError("allowed_filesystem_roots must not be empty")
        if any(not pattern for pattern in patterns):
            raise ConfigurationError("blocked_filesystem_patterns must not contain empty values")
        if self.max_filesystem_file_size_bytes < 1 or self.max_filesystem_file_size_bytes > 100 * 1024 * 1024:
            raise ConfigurationError("max_filesystem_file_size_bytes must be between 1 and 104857600")
        object.__setattr__(self, "allowed_filesystem_roots", roots)
        object.__setattr__(self, "blocked_filesystem_patterns", patterns)

    @classmethod
    def from_environment(
        cls,
        environ: dict[str, str] | None = None,
        max_filesystem_file_size_bytes: int | None = None,
    ) -> "SecurityPolicy":
        """Load policy and fail closed when its allowlist is absent or invalid."""
        values = os.environ if environ is None else environ
        raw_roots = values.get("HERMES_ALLOWED_FILESYSTEM_ROOTS")
        if raw_roots is None:
            raise ConfigurationError("HERMES_ALLOWED_FILESYSTEM_ROOTS is required")
        roots = tuple(_path_from(root, "allowed_filesystem_roots") for root in _split(raw_roots, "HERMES_ALLOWED_FILESYSTEM_ROOTS"))
        raw_patterns = values.get("HERMES_BLOCKED_FILESYSTEM_PATTERNS")
        patterns = (
            _split(raw_patterns, "HERMES_BLOCKED_FILESYSTEM_PATTERNS")
            if raw_patterns is not None
            else cls().blocked_filesystem_patterns
        )
        return cls(
            allowed_filesystem_roots=roots,
            blocked_filesystem_patterns=patterns,
            max_filesystem_file_size_bytes=(
                cls().max_filesystem_file_size_bytes
                if max_filesystem_file_size_bytes is None
                else max_filesystem_file_size_bytes
            ),
        )


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration; security policy is a separate object."""

    app_name: str = "Hermes Local"
    active_model_provider: str = "ollama"
    active_model: str = "llama3.2"
    ollama_host: str = "http://127.0.0.1:11434"
    log_level: str = "INFO"
    max_agent_iterations: int = 10
    tool_timeout_seconds: float = 30.0
    memory_database_location: Path = Path("data/memory/hermes.sqlite3")
    rag_database_location: Path = Path("data/rag/hermes.sqlite3")
    security_policy: SecurityPolicy = SecurityPolicy()

    def __post_init__(self) -> None:
        if not self.app_name.strip() or not self.active_model_provider.strip() or not self.active_model.strip():
            raise ConfigurationError("app_name, active_model_provider, and active_model are required")
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("log_level is invalid")
        if self.max_agent_iterations < 1 or self.max_agent_iterations > 1000:
            raise ConfigurationError("max_agent_iterations must be between 1 and 1000")
        if self.tool_timeout_seconds <= 0 or self.tool_timeout_seconds > 3600:
            raise ConfigurationError("tool_timeout_seconds must be between 0 and 3600")
        parsed_host = urlparse(self.ollama_host)
        if parsed_host.scheme not in {"http", "https"} or not parsed_host.netloc:
            raise ConfigurationError("ollama_host must be an HTTP(S) URL")
        object.__setattr__(self, "log_level", self.log_level.upper())
        object.__setattr__(self, "memory_database_location", _path_from(self.memory_database_location, "memory_database_location"))
        object.__setattr__(self, "rag_database_location", _path_from(self.rag_database_location, "rag_database_location"))

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> "Settings":
        """Load allowlisted values and require an explicit security allowlist."""
        values = os.environ if environ is None else environ

        def get(name: str, default: str) -> str:
            return values.get(name, default)

        try:
            max_agent_iterations = int(get("HERMES_MAX_AGENT_ITERATIONS", str(cls.max_agent_iterations)))
            tool_timeout_seconds = float(get("HERMES_TOOL_TIMEOUT_SECONDS", str(cls.tool_timeout_seconds)))
            max_filesystem_file_size_bytes = int(
                get(
                    "HERMES_MAX_FILESYSTEM_FILE_SIZE_BYTES",
                    str(cls.security_policy.max_filesystem_file_size_bytes),
                )
            )
        except ValueError as error:
            raise ConfigurationError("numeric configuration values are invalid") from error

        return cls(
            app_name=get("HERMES_APP_NAME", cls.app_name),
            active_model_provider=get("HERMES_MODEL_PROVIDER", cls.active_model_provider),
            active_model=get("HERMES_MODEL", cls.active_model),
            ollama_host=get("HERMES_OLLAMA_HOST", cls.ollama_host),
            log_level=get("HERMES_LOG_LEVEL", cls.log_level),
            max_agent_iterations=max_agent_iterations,
            tool_timeout_seconds=tool_timeout_seconds,
            memory_database_location=Path(get("HERMES_MEMORY_DATABASE", str(cls.memory_database_location))),
            rag_database_location=Path(get("HERMES_RAG_DATABASE", str(cls.rag_database_location))),
            security_policy=SecurityPolicy.from_environment(values, max_filesystem_file_size_bytes),
        )
