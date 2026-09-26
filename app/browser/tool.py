"""Dedicated structured browser tool; no arbitrary browser scripting."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from app.browser.backend import BrowserBackend
from app.browser.models import BrowserAction, BrowserError, BrowserPolicy, BrowserResult
from app.browser.session import BrowserSession
from app.security.permissions import PermissionEngine, PermissionRequest
from app.tools.base import Tool, ToolValidationError


class BrowserTool(Tool):
    name = "browser"
    description = "Open approved websites, navigate, search, and read visible page information."
    permission_requirement = "browser.safe"
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "url": {"type": "string"},
            "query": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }
    _safe_actions = {
        BrowserAction.OPEN.value,
        BrowserAction.NAVIGATE.value,
        BrowserAction.SEARCH.value,
        BrowserAction.READ_PAGE.value,
        BrowserAction.EXTRACT_VISIBLE_TEXT.value,
    }
    _sensitive_actions = {action.value for action in BrowserAction} - _safe_actions

    def __init__(self, permission_engine: PermissionEngine, policy: BrowserPolicy) -> None:
        self.permission_engine = permission_engine
        self.policy = policy
        self.backend = BrowserBackend(policy, BrowserSession())
        self._cancelled = False

    def validate(self, arguments: dict[str, Any]) -> None:
        action = arguments.get("action")
        if action not in {item.value for item in BrowserAction}:
            raise ToolValidationError("unknown browser action", code="unknown_browser_action")
        super().validate(arguments)
        if action in {BrowserAction.OPEN.value, BrowserAction.NAVIGATE.value} and not isinstance(arguments.get("url"), str):
            raise ToolValidationError("browser navigation requires a URL")
        if action == BrowserAction.SEARCH.value and not isinstance(arguments.get("query"), str):
            raise ToolValidationError("browser search requires a query")

    def execute(self, arguments: dict[str, Any]) -> BrowserResult:
        self.validate(arguments)
        action = arguments["action"]
        if self._cancelled:
            self._cancelled = False
            return BrowserResult(action, False, error=BrowserError("cancelled", "browser action was cancelled", True))
        requirement = "browser.sensitive" if action in self._sensitive_actions else "browser.safe"
        decision = self.permission_engine.decide(
            PermissionRequest(action=f"browser:{action}", permission_requirement=requirement, arguments={"action": action}, source="browser_tool")
        )
        if not decision.permitted:
            return BrowserResult(action, False, error=BrowserError("permission_denied", decision.reason))
        if action in self._sensitive_actions:
            return BrowserResult(action, False, error=BrowserError("not_implemented", "sensitive browser actions require a host approval workflow"))
        if self._cancelled:
            return BrowserResult(action, False, error=BrowserError("cancelled", "browser action was cancelled", True))
        if action in {BrowserAction.OPEN.value, BrowserAction.NAVIGATE.value}:
            result = self.backend.open(arguments["url"], action)
            return self._cancelled_result(action, result)
        if action == BrowserAction.SEARCH.value:
            if not self.policy.search_url:
                return BrowserResult(action, False, error=BrowserError("search_not_configured", "browser search is not configured"))
            result = self.backend.open(self.policy.search_url + quote_plus(arguments["query"]), action)
            return self._cancelled_result(action, result)
        if not self.backend.session.current_url:
            return BrowserResult(action, False, error=BrowserError("no_page", "no page is open"))
        return BrowserResult(
            action,
            True,
            self.backend.session.current_url,
            self.backend.session.title,
            self.backend.session.visible_text,
            self.backend.session.links,
        )

    def _cancelled_result(self, action: str, result: BrowserResult) -> BrowserResult:
        if self._cancelled:
            self._cancelled = False
            return BrowserResult(action, False, error=BrowserError("cancelled", "browser action was cancelled", True))
        return result

    def cancel(self) -> None:
        """Cancel the next/current action without exposing browser internals."""
        self._cancelled = True