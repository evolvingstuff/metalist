"""Ollama HTTP adapter for model discovery and streamed chat."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import httpx


_CONNECT_TIMEOUT_SECONDS = 5.0
_READ_TIMEOUT_SECONDS = 300.0
_ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_ALLOWED_THINKING_LEVELS = frozenset({"off", "low", "medium", "high"})


class OllamaProviderError(RuntimeError):
    """An expected Ollama connection or protocol failure."""


def normalize_ollama_base_url(base_url: str) -> str:
    if not isinstance(base_url, str) or base_url.strip() == "":
        raise ValueError("Ollama URL must be a non-empty string")
    if len(base_url) > 2048:
        raise ValueError("Ollama URL is too long")
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Ollama URL must use http or https")
    if parsed.hostname is None:
        raise ValueError("Ollama URL must include a host")
    normalized_hostname = parsed.hostname.casefold()
    if normalized_hostname not in _ALLOWED_LOOPBACK_HOSTS:
        raise ValueError("Ollama URL must use localhost, 127.0.0.1, or [::1]")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Ollama URL must not include credentials")
    if parsed.query != "" or parsed.fragment != "":
        raise ValueError("Ollama URL must not include a query or fragment")
    path = parsed.path.rstrip("/")
    if path not in {"", "/api"}:
        raise ValueError("Ollama URL path must be empty or /api")
    if path == "/api":
        path = ""
    port = parsed.port
    if port == 0:
        raise ValueError("Ollama URL port must be between 1 and 65535")
    host = normalized_hostname
    if normalized_hostname == "localhost":
        host = "127.0.0.1"
    if normalized_hostname == "::1":
        host = f"[{normalized_hostname}]"
    netloc = host
    if port is not None:
        netloc = f"{host}:{port}"
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def validate_ollama_model(model: str) -> str:
    if not isinstance(model, str) or model.strip() == "":
        raise ValueError("Ollama model must be a non-empty string")
    normalized = model.strip()
    if len(normalized) > 200:
        raise ValueError("Ollama model is too long")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError("Ollama model contains control characters")
    return normalized


def resolve_ollama_think_value(*, model: str, thinking_level: str) -> bool | str:
    normalized_model = validate_ollama_model(model)
    if thinking_level not in _ALLOWED_THINKING_LEVELS:
        raise ValueError(f"Unsupported Ollama thinking level: {thinking_level}")
    if normalized_model.casefold().startswith("gpt-oss") and thinking_level == "off":
        raise ValueError("GPT-OSS does not support disabling thinking")
    if thinking_level == "off":
        return False
    return thinking_level


def _api_url(*, base_url: str, endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint.startswith("/"):
        raise ValueError("Ollama endpoint must be an absolute path")
    return f"{normalize_ollama_base_url(base_url)}/api{endpoint}"


class OllamaProvider:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None) -> None:
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT_SECONDS,
            read=_READ_TIMEOUT_SECONDS,
            write=_CONNECT_TIMEOUT_SECONDS,
            pool=_CONNECT_TIMEOUT_SECONDS,
        )
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=timeout,
            trust_env=False,
        )

    async def list_models(self, *, base_url: str) -> list[str]:
        url = _api_url(base_url=base_url, endpoint="/tags")
        try:
            async with self._client() as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaProviderError("Could not connect to Ollama") from exc

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise OllamaProviderError("Ollama returned invalid model-list JSON") from exc
        if not isinstance(payload, dict) or "models" not in payload:
            raise OllamaProviderError("Ollama model-list response is malformed")
        if not isinstance(payload["models"], list):
            raise OllamaProviderError("Ollama model-list response is malformed")
        models: list[str] = []
        for record in payload["models"]:
            if not isinstance(record, dict):
                raise OllamaProviderError("Ollama model record is malformed")
            model = record.get("model")
            if not isinstance(model, str) or model.strip() == "":
                raise OllamaProviderError("Ollama model record is missing model name")
            models.append(validate_ollama_model(model))
        return sorted(set(models), key=str.casefold)

    async def stream_chat(
        self,
        *,
        base_url: str,
        model: str,
        thinking_level: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, str]]:
        normalized_model = validate_ollama_model(model)
        think_value = resolve_ollama_think_value(
            model=normalized_model,
            thinking_level=thinking_level,
        )
        self._validate_messages(messages)
        request_payload: dict[str, object] = {
            "model": normalized_model,
            "messages": messages,
            "stream": True,
            "think": think_value,
        }
        url = _api_url(base_url=base_url, endpoint="/chat")
        did_finish = False
        try:
            async with self._client() as client:
                async with client.stream("POST", url, json=request_payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line == "":
                            continue
                        event = self._parse_stream_line(line)
                        message = event["message"]
                        # Ollama omits whichever optional stream channel is idle.
                        normalized_message = {"thinking": "", "content": ""}
                        normalized_message.update(message)
                        thinking = normalized_message["thinking"]
                        content = normalized_message["content"]
                        if not isinstance(thinking, str) or not isinstance(content, str):
                            raise OllamaProviderError("Ollama stream message fields must be strings")
                        if thinking != "":
                            yield {"type": "thinking_delta", "text": thinking}
                        if content != "":
                            yield {"type": "content_delta", "text": content}
                        if "done" not in event:
                            raise OllamaProviderError("Ollama stream event is missing done flag")
                        done = event["done"]
                        if not isinstance(done, bool):
                            raise OllamaProviderError("Ollama stream event is missing done flag")
                        if done:
                            did_finish = True
                            yield {"type": "done"}
                            break
        except httpx.HTTPError as exc:
            raise OllamaProviderError("Ollama chat request failed") from exc
        if not did_finish:
            raise OllamaProviderError("Ollama stream ended before completion")

    @staticmethod
    def _parse_stream_line(line: str) -> dict[str, object]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OllamaProviderError("Ollama returned invalid streaming JSON") from exc
        if not isinstance(event, dict):
            raise OllamaProviderError("Ollama stream event must be an object")
        if "error" in event:
            raise OllamaProviderError("Ollama reported a chat generation error")
        if "message" not in event or not isinstance(event["message"], dict):
            raise OllamaProviderError("Ollama stream event is missing message")
        return event

    @staticmethod
    def _validate_messages(messages: list[dict[str, str]]) -> None:
        if not isinstance(messages, list) or len(messages) == 0:
            raise ValueError("Ollama chat messages must be a non-empty list")
        for message in messages:
            if not isinstance(message, dict):
                raise TypeError("Ollama chat message must be an object")
            if set(message) != {"role", "content"}:
                raise ValueError("Ollama chat message must contain role and content")
            if message["role"] not in {"user", "assistant"}:
                raise ValueError("Ollama chat message has unsupported role")
            if not isinstance(message["content"], str):
                raise TypeError("Ollama chat message content must be a string")


ollama_provider = OllamaProvider(transport=None)
