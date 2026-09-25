"""Central logging setup for Hermes Local."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure one predictable console logger for the CLI."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
