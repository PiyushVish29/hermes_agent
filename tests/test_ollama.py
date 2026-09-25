"""Deterministic tests for the Ollama provider adapter."""

import json

import pytest

from app.config.settings import Settings
from app.models.ollama import OllamaModelProvider
from app.models.provider import ModelError, ModelRequest, ModelTimeoutError, ToolDefinition


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_ollama_provider_normalizes_text_and_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    response = {
        "message": {
            "content": "I can help",
            "tool_calls": [
                {"id": "call-1", "function": {"name": "safe_tool", "arguments": {"value": 1}}}
            ],
        },
        "done_reason": "stop",
    }

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(json.dumps(response).encode())

    monkeypatch.setattr("app.models.ollama.urlopen", fake_urlopen)
    provider = OllamaModelProvider("http://localhost:11434/", "configured-model")

    result = provider.generate(
        ModelRequest(
            prompt="hello",
            system_prompt="Be concise",
            tools=(ToolDefinition("safe_tool", "A safe test tool", {"type": "object"}),),
            timeout_seconds=4,
        )
    )

    assert result.text == "I can help"
    assert result.tool_calls[0].name == "safe_tool"
    assert result.tool_calls[0].arguments == {"value": 1}
    assert captured["timeout"] == 4
    request_body = json.loads(captured["request"].data)
    assert request_body["model"] == "configured-model"
    assert request_body["tools"][0]["function"]["name"] == "safe_tool"


def test_ollama_provider_parses_structured_response(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"message": {"content": '{"answer": "yes"}'}}
    monkeypatch.setattr(
        "app.models.ollama.urlopen",
        lambda request, timeout: FakeResponse(json.dumps(body).encode()),
    )

    result = OllamaModelProvider("http://localhost:11434", "configured-model").generate(
        ModelRequest("hello", response_schema={"type": "object"})
    )

    assert result.structured_data == {"answer": "yes"}


@pytest.mark.parametrize(
    "body",
    [b"not-json", b"{}", b'{"message": {"content": 42}}', b'{"message": {"tool_calls": {}}}'],
)
def test_ollama_provider_rejects_malformed_responses(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    monkeypatch.setattr(
        "app.models.ollama.urlopen",
        lambda request, timeout: FakeResponse(body),
    )

    with pytest.raises(ModelError, match="malformed"):
        OllamaModelProvider("http://localhost:11434", "configured-model").generate(
            ModelRequest("hello")
        )


def test_ollama_provider_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(request: object, timeout: float) -> None:
        raise TimeoutError

    monkeypatch.setattr("app.models.ollama.urlopen", timeout)

    with pytest.raises(ModelTimeoutError):
        OllamaModelProvider("http://localhost:11434", "configured-model").generate(
            ModelRequest("hello")
        )


def test_ollama_integration_when_available() -> None:
    provider = OllamaModelProvider(
        Settings().ollama_host,
        Settings().active_model,
        default_timeout_seconds=2,
    )
    try:
        response = provider.generate(ModelRequest("Reply with one short greeting."))
    except ModelError as error:
        if error.code == "connection_error":
            pytest.skip("Ollama is unavailable")
        raise

    assert response.text or response.tool_calls