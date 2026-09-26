"""Private browser session state with no cookie or credential store."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BrowserSession:
    current_url: str | None = None
    title: str | None = None
    visible_text: str = ""
    links: tuple[str, ...] = ()

    def clear(self) -> None:
        self.current_url = None
        self.title = None
        self.visible_text = ""
        self.links = ()