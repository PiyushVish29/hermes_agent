"""Restricted HTTP browser backend with visible-text extraction only."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import Request, urlopen

from app.browser.models import BrowserError, BrowserPolicy, BrowserResult
from app.browser.session import BrowserSession


class VisiblePageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(urljoin(self.base_url, href))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag in {"script", "style", "noscript", "template"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.hidden_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        elif data.strip():
            self.parts.append(data.strip())


class BrowserBackend:
    """Fetch public page content without JavaScript, cookies, or form state."""

    _secret_patterns = (
        re.compile(r"(?i)\b(password|passwd|passphrase|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|cookie|secret)\b\s*[:=]\s*[^\s,;]+"),
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    )

    def __init__(self, policy: BrowserPolicy, session: BrowserSession | None = None) -> None:
        self.policy = policy
        self.session = session or BrowserSession()

    def open(self, url: str, action: str = "open") -> BrowserResult:
        try:
            safe_url = self._validate_url(url)
            request = Request(safe_url, headers={"Accept": "text/html,text/plain;q=0.9"}, method="GET")
            with urlopen(request, timeout=self.policy.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                    return BrowserResult(action, False, safe_url, error=BrowserError("unsupported_content", "page is not readable text or HTML"))
                raw = response.read(self.policy.max_response_bytes + 1)
            if len(raw) > self.policy.max_response_bytes:
                return BrowserResult(action, False, safe_url, error=BrowserError("response_too_large", "page exceeds browser response limit"))
            text = raw.decode("utf-8", errors="replace")
            parser = VisiblePageParser(safe_url)
            parser.feed(text)
            visible = self._redact(" ".join(parser.parts))
            self.session.current_url = safe_url
            self.session.title = self._redact(" ".join(parser.title_parts)) or None
            self.session.visible_text = visible
            self.session.links = tuple(self._safe_link(link) for link in parser.links if self._safe_link(link))
            return BrowserResult(action, True, safe_url, self.session.title, visible, self.session.links)
        except ValueError as error:
            return BrowserResult(action, False, error=BrowserError("blocked_url", str(error)))
        except HTTPError as error:
            return BrowserResult(action, False, url, error=BrowserError("http_error", f"browser request returned HTTP {error.code}", error.code >= 500))
        except URLError:
            return BrowserResult(action, False, url, error=BrowserError("connection_error", "browser connection failed", True))
        except TimeoutError:
            return BrowserResult(action, False, url, error=BrowserError("timeout", "browser request timed out", True))
        except OSError:
            return BrowserResult(action, False, url, error=BrowserError("connection_error", "browser connection failed", True))

    def _validate_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
            raise ValueError("only HTTP(S) URLs without credentials are allowed")
        host = parsed.netloc.lower()
        hostname = parsed.hostname.lower()
        if not any(host == allowed or hostname == allowed for allowed in self.policy.allowed_hosts):
            raise ValueError("website host is not allowed by browser policy")
        sensitive_query_names = {"password", "passwd", "token", "access_token", "api_key", "secret", "cookie", "auth"}
        if any(key.lower() in sensitive_query_names for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            raise ValueError("URLs containing credential-like query parameters are not allowed")
        return url

    def _safe_link(self, link: str) -> str | None:
        try:
            return self._validate_url(link)
        except ValueError:
            return None

    def _redact(self, text: str) -> str:
        for pattern in self._secret_patterns:
            text = pattern.sub("[REDACTED]", text)
        return text