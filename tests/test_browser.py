"""Local-server tests for the isolated browser tool."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from app.browser import BrowserPolicy, BrowserTool
from app.security.permissions import PermissionEngine, PermissionLevel, PermissionPolicy
from app.tools.base import ToolValidationError


class LocalPageHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/slow":
            import time

            time.sleep(0.2)
        if parsed.path == "/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            body = f"<html><title>Search</title><body>Search result for {query}</body></html>"
        else:
            body = (
                "<html><head><title>Local Test</title><script>secret_script()</script></head>"
                "<body><h1>Visible heading</h1><p>Public page text.</p>"
                "<input name='password' value='do-not-show'>"
                "<p>api_key=private-value</p><a href='/next'>Next</a></body></html>"
            )
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return None


@pytest.fixture
def browser_tool():
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalPageHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    permissions = PermissionEngine(PermissionPolicy({"browser.safe": PermissionLevel.SAFE}))
    tool = BrowserTool(
        permissions,
        BrowserPolicy(
            allowed_hosts=("127.0.0.1",),
            search_url=f"{base_url}/search?q=",
            timeout_seconds=1,
        ),
    )
    yield tool, base_url
    server.shutdown()
    thread.join(timeout=1)


def test_open_and_read_local_page_exposes_visible_text_only(browser_tool) -> None:
    tool, base_url = browser_tool

    result = tool.execute({"action": "open", "url": f"{base_url}/page"})

    assert result.success
    assert "Visible heading" in result.text
    assert "secret_script" not in result.text
    assert "do-not-show" not in result.text
    assert "private-value" not in result.text
    assert result.links == (f"{base_url}/next",)

    read = tool.execute({"action": "read_page"})
    assert read.success
    assert read.url == result.url


def test_search_uses_configured_endpoint(browser_tool) -> None:
    tool, _ = browser_tool

    result = tool.execute({"action": "search", "query": "Hermes local"})

    assert result.success
    assert "Hermes local" in result.text


def test_navigation_outside_allowlist_is_blocked(browser_tool) -> None:
    tool, _ = browser_tool

    result = tool.execute({"action": "navigate", "url": "https://example.com"})

    assert not result.success
    assert result.error.code == "blocked_url"


def test_sensitive_actions_require_permission_and_are_not_executed(browser_tool) -> None:
    tool, _ = browser_tool

    result = tool.execute({"action": "submit_form"})

    assert not result.success
    assert result.error.code == "permission_denied"


def test_unknown_action_and_credential_url_are_rejected(browser_tool) -> None:
    tool, base_url = browser_tool

    with pytest.raises(ToolValidationError, match="unknown browser action"):
        tool.validate({"action": "run_javascript", "script": "alert(1)"})
    result = tool.execute({"action": "open", "url": f"http://user:password@127.0.0.1:{urlsplit(base_url).port}/"})
    assert not result.success
    assert result.error.code == "blocked_url"
    query_secret = tool.execute({"action": "open", "url": f"{base_url}/?access_token=secret"})
    assert not query_secret.success
    assert query_secret.error.code == "blocked_url"


def test_timeout_and_cancellation_are_structured(browser_tool) -> None:
    tool, base_url = browser_tool
    tool.policy = BrowserPolicy(allowed_hosts=("127.0.0.1",), timeout_seconds=0.05)
    tool.backend.policy = tool.policy

    timed_out = tool.execute({"action": "open", "url": f"{base_url}/slow"})
    assert not timed_out.success
    assert timed_out.error.code == "timeout"

    tool.cancel()
    cancelled = tool.execute({"action": "read_page"})
    assert not cancelled.success
    assert cancelled.error.code == "cancelled"


def test_permission_is_required_for_safe_browser_action(browser_tool) -> None:
    _, base_url = browser_tool
    tool = BrowserTool(PermissionEngine(), BrowserPolicy(allowed_hosts=("127.0.0.1",)))

    result = tool.execute({"action": "open", "url": f"{base_url}/"})

    assert not result.success
    assert result.error.code == "permission_denied"