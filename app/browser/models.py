"""Structured browser actions, policy, and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class BrowserAction(str, Enum):
    OPEN = "open"
    NAVIGATE = "navigate"
    SEARCH = "search"
    READ_PAGE = "read_page"
    EXTRACT_VISIBLE_TEXT = "extract_visible_text"
    UPLOAD_FILE = "upload_file"
    SUBMIT_FORM = "submit_form"
    SEND_MESSAGE = "send_message"
    ACCOUNT_CHANGE = "account_change"
    PURCHASE = "purchase"
    AUTHENTICATE = "authenticate"
    SECURITY_CHANGE = "security_change"


@dataclass(frozen=True)
class BrowserPolicy:
    """Host-owned browser boundary; an empty allowlist denies navigation."""

    allowed_hosts: tuple[str, ...] = ()
    search_url: str | None = None
    max_response_bytes: int = 1_048_576
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_hosts", tuple(host.lower().strip() for host in self.allowed_hosts if host.strip()))
        object.__setattr__(self, "blocked_actions", MappingProxyType({
            BrowserAction.UPLOAD_FILE.value: "approval_required",
            BrowserAction.SUBMIT_FORM.value: "approval_required",
            BrowserAction.SEND_MESSAGE.value: "approval_required",
            BrowserAction.ACCOUNT_CHANGE.value: "approval_required",
            BrowserAction.PURCHASE.value: "approval_required",
            BrowserAction.AUTHENTICATE.value: "approval_required",
            BrowserAction.SECURITY_CHANGE.value: "approval_required",
        }))


@dataclass(frozen=True)
class BrowserError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class BrowserResult:
    action: str
    success: bool
    url: str | None = None
    title: str | None = None
    text: str = ""
    links: tuple[str, ...] = ()
    error: BrowserError | None = None