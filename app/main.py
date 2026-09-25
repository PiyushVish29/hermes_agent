"""Command-line entry point for Hermes Local."""

from __future__ import annotations

import argparse

from app import __version__
from app.agent.controller import AgentController
from app.config.settings import Settings
from app.models.factory import ModelProviderFactory
from app.models.provider import ModelError
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
    parser.add_argument(
        "--chat",
        action="store_true",
        help="start a local conversational session",
    )
    return parser


def run_chat(controller: AgentController) -> None:
    """Run a text-only session; model tool requests are displayed, never executed."""
    print("Hermes Local chat. Type 'exit' or press Ctrl+C to quit.")
    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if prompt.lower() in {"exit", "quit"}:
            return
        if not prompt:
            continue
        try:
            response = controller.run_task(prompt)
        except ModelError as error:
            print(f"Hermes error ({error.code}): {error}")
            continue
        if response.text:
            print(f"Hermes: {response.text}")
        for tool_call in response.tool_calls:
            print(f"Hermes requested tool '{tool_call.name}', but tool execution is disabled.")


def main() -> int:
    """Start Hermes, report its state, and perform a clean shutdown."""
    args = build_parser().parse_args()
    settings = Settings.from_environment()
    configure_logging(settings.log_level)

    provider = ModelProviderFactory.create(settings) if args.chat else None
    controller = AgentController(settings, model_provider=provider)
    controller.start()
    try:
        if args.chat:
            run_chat(controller)
        else:
            print(controller.status_message())
    finally:
        controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
