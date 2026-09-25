"""Configuration parsing and security-boundary tests."""

from pathlib import Path

import pytest

from app.config.settings import ConfigurationError, SecurityPolicy, Settings


def valid_environment(tmp_path: Path) -> dict[str, str]:
    return {
        "HERMES_ALLOWED_FILESYSTEM_ROOTS": str(tmp_path / "sandbox"),
        "HERMES_BLOCKED_FILESYSTEM_PATTERNS": "**/.env;**/*.pem",
        "HERMES_MODEL_PROVIDER": "ollama",
        "HERMES_MODEL": "qwen2.5:7b",
        "HERMES_OLLAMA_HOST": "http://127.0.0.1:11434",
        "HERMES_LOG_LEVEL": "debug",
        "HERMES_MAX_AGENT_ITERATIONS": "25",
        "HERMES_TOOL_TIMEOUT_SECONDS": "12.5",
        "HERMES_MEMORY_DATABASE": str(tmp_path / "memory.sqlite3"),
        "HERMES_RAG_DATABASE": str(tmp_path / "rag.sqlite3"),
    }


def test_valid_environment_loads_typed_configuration(tmp_path: Path) -> None:
    settings = Settings.from_environment(valid_environment(tmp_path))

    assert settings.log_level == "DEBUG"
    assert settings.max_agent_iterations == 25
    assert settings.tool_timeout_seconds == 12.5
    assert settings.security_policy.allowed_filesystem_roots == ((tmp_path / "sandbox").resolve(),)
    assert settings.memory_database_location == (tmp_path / "memory.sqlite3").resolve()


def test_default_configuration_is_bounded_and_immutable() -> None:
    settings = Settings()

    assert settings.security_policy.allowed_filesystem_roots == ((Path("data/sandbox")).resolve(),)
    with pytest.raises((AttributeError, TypeError)):
        settings.security_policy = SecurityPolicy()


def test_missing_security_allowlist_fails_closed() -> None:
    with pytest.raises(ConfigurationError, match="ALLOWED_FILESYSTEM_ROOTS"):
        Settings.from_environment({})


@pytest.mark.parametrize(
    "updates",
    [
        {"HERMES_ALLOWED_FILESYSTEM_ROOTS": ""},
        {"HERMES_ALLOWED_FILESYSTEM_ROOTS": "."},
        {"HERMES_MAX_AGENT_ITERATIONS": "many"},
        {"HERMES_OLLAMA_HOST": "file:///unsafe"},
    ],
)
def test_invalid_or_unsafe_environment_is_rejected(tmp_path: Path, updates: dict[str, str]) -> None:
    environment = valid_environment(tmp_path)
    environment.update(updates)

    with pytest.raises(ConfigurationError):
        Settings.from_environment(environment)