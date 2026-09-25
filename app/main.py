"""Command-line entry point for Hermes Local."""

from __future__ import annotations

import argparse

from app import __version__
from app.agent.controller import AgentController
from app.config.settings import Settings
from app.utils.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    """Build the intentionally small milestone CLI."""
    parser = argparse.ArgumentParser(description="Hermes Local privacy-first agent")
    parser.add_argument("--version", action="version", version=f"Hermes Local {__version__}")
    parser.add_argument(
        "--status",
        action="store_true",
        help="start Hermes, report status, and shut down safely",
    )
    return parser


def main() -> int:
    """Start Hermes, report its state, and perform a clean shutdown."""
    args = build_parser().parse_args()
    settings = Settings.from_environment()
    configure_logging(settings.log_level)

    controller = AgentController(settings)
    controller.start()
    print(controller.status_message())
    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
