"""Ollama implementation of the provider-neutral model contract."""

from __future__ import annotations

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models.provider import (
    ModelError,
    ModelMetadata,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
    ToolCallRequest,
)


class OllamaModelProvider(ModelProvider):
    """Call Ollama without exposing its HTTP or response format to the agent."""

    def __init__(self, host: str, model: str, default_timeout_seconds: float = 30.0) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.default_timeout_seconds = default_timeout_seconds

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages(request),
            "stream": False,
        }
        if request.tools:
            payload["tools"] = [self._tool_definition(tool) for tool in request.tools]
        if request.response_schema is not None:
            payload["format"] = request.response_schema

        body = json.dumps(payload).encode("utf-8")
        http_request = Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = request.timeout_seconds or self.default_timeout_seconds
        try:
            with urlopen(http_request, timeout=timeout) as response:
                raw_response = response.read()
        except (TimeoutError, socket.timeout) as error:
            raise ModelTimeoutError() from error
        except HTTPError as error:
            raise ModelError(
                f"Ollama returned HTTP {error.code}",
                code="connection_error",
                retryable=error.code >= 500,
            ) from error
        except URLError as error:
            raise ModelError(
                "Unable to connect to Ollama",
                code="connection_error",
                retryable=True,
            ) from error
        except OSError as error:
            raise ModelError(
                "Unable to communicate with Ollama",
                code="connection_error",
                retryable=True,
            ) from error

        return self._parse_response(raw_response, request)

    def _messages(self, request: ModelRequest) -> list[dict[str, str]]:
        if request.conversation:
            return [dict(message) for message in request.conversation]
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        return messages

    @staticmethod
    def _tool_definition(tool: Any) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": dict(tool.parameters),
            },
        }

    def _parse_response(self, raw_response: bytes, request: ModelRequest) -> ModelResponse:
        try:
            response = json.loads(raw_response)
            if not isinstance(response, dict) or not isinstance(response.get("message"), dict):
                raise TypeError
            message = response["message"]
            content = message.get("content", "")
            if not isinstance(content, str):
                raise TypeError
            tool_calls = self._tool_calls(message.get("tool_calls", []))
            structured_data = None
            if request.response_schema is not None:
                structured_data = json.loads(content)
                if not isinstance(structured_data, dict):
                    raise TypeError
            return ModelResponse(
                text=content,
                structured_data=structured_data,
                tool_calls=tool_calls,
                metadata=ModelMetadata(
                    provider="ollama",
                    model=self.model,
                    capabilities=frozenset({"text", "structured", "tools"}),
                ),
                finish_reason=response.get("done_reason", "stop"),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ModelError("Ollama returned a malformed response", code="malformed_response") from error

    @staticmethod
    def _tool_calls(raw_tool_calls: object) -> tuple[ToolCallRequest, ...]:
        if not isinstance(raw_tool_calls, list):
            raise TypeError("tool_calls must be a list")
        calls: list[ToolCallRequest] = []
        for index, raw_call in enumerate(raw_tool_calls):
            if not isinstance(raw_call, dict) or not isinstance(raw_call.get("function"), dict):
                raise TypeError("tool call must contain a function")
            function = raw_call["function"]
            name = function.get("name")
            arguments = function.get("arguments", {})
            if not isinstance(name, str):
                raise TypeError("tool name must be a string")
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            if not isinstance(arguments, dict):
                raise TypeError("tool arguments must be an object")
            calls.append(
                ToolCallRequest(
                    call_id=str(raw_call.get("id", f"ollama-call-{index}")),
                    name=name,
                    arguments=arguments,
                )
            )
        return tuple(calls)