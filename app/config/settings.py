"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Small, typed configuration surface for the application shell."""

    app_name: str = "Hermes Local"
    log_level: str = "INFO"

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load supported values without reading arbitrary environment state."""
        return cls(
            app_name=os.getenv("HERMES_APP_NAME", cls.app_name),
            log_level=os.getenv("HERMES_LOG_LEVEL", cls.log_level).upper(),
        )
