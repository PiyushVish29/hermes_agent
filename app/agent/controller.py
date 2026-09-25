"""Lifecycle coordinator for the Hermes Local application."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app import __version__
from app.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class AgentController:
    """Own application lifecycle; future orchestration will be added here."""

    settings: Settings
    running: bool = False

    def start(self) -> None:
        """Initialize the safe application shell."""
        self.running = True
        logger.info("Hermes Local started")

    def status_message(self) -> str:
        """Return human-readable status without invoking any external capability."""
        state = "running" if self.running else "stopped"
        return f"Hermes Local {__version__} - {state} - model: disconnected"

    def shutdown(self) -> None:
        """Stop the application and release future resources in one place."""
        if self.running:
            logger.info("Hermes Local shutting down")
        self.running = False
