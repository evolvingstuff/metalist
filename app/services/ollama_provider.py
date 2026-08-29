"""Ollama HTTP adapter for model discovery and streamed chat."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import httpx


_CONNECT_TIMEOUT_SECONDS = 5.0
_READ_TIMEOUT_SECONDS = 300.0
_ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_ALLOWED_THINKING_LEVELS = frozenset({"off", "low", "medium", "high"})
_MAX_ERROR_DETAIL_CHARACTERS = 2_000


class OllamaProviderError(RuntimeError):
    """An expected Ollama connection or protocol failure."""


@dataclass(frozen=True, slots=True)
class OllamaModelContext:
    model: str
    maximum_tokens: int
    loaded_tokens: int

    def __post_init__(self) -> None:
        validate_ollama_model(self.model)
        for label, value in (
            ("maximum_tokens", self.maximum_tokens),
            ("loaded_tokens", self.loaded_tokens),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"Ollama model context {label} must be positive")


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

    async def inspect_model_context(
        self,
        *,
        base_url: str,
        model: str,
    ) -> OllamaModelContext:
        normalized_model = validate_ollama_model(model)
        show_url = _api_url(base_url=base_url, endpoint="/show")
        preload_url = _api_url(base_url=base_url, endpoint="/generate")
        running_url = _api_url(base_url=base_url, endpoint="/ps")
        try:
            async with self._client() as client:
                show_response = await client.post(
                    show_url,
                    json={"model": normalized_model},
                )
                show_response.raise_for_status()
                preload_response = await client.post(
                    preload_url,
                    json={"model": normalized_model, "stream": False},
                )
                preload_response.raise_for_status()
                running_response = await client.get(running_url)
                running_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaProviderError("Could not inspect Ollama model context") from exc

        show_payload = self._parse_json_object(
            response_text=show_response.text,
            label="model details",
        )
        running_payload = self._parse_json_object(
            response_text=running_response.text,
            label="running-model list",
        )
        maximum_tokens = self._parse_maximum_context_tokens(show_payload)
        loaded_tokens = self._parse_loaded_context_tokens(
            payload=running_payload,
            model=normalized_model,
        )
        return OllamaModelContext(
            model=normalized_model,
            maximum_tokens=maximum_tokens,
            loaded_tokens=loaded_tokens,
        )

    @staticmethod
    def _parse_json_object(
        *,
        response_text: str,
        label: str,
    ) -> dict[str, object]:
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise OllamaProviderError(f"Ollama {label} response is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise OllamaProviderError(f"Ollama {label} response must be an object")
        return payload

    @staticmethod
    def _parse_maximum_context_tokens(payload: dict[str, object]) -> int:
        if "model_info" not in payload:
            raise OllamaProviderError("Ollama model details omit model_info")
        model_info = payload["model_info"]
        if not isinstance(model_info, dict):
            raise OllamaProviderError("Ollama model details omit model_info")
        context_values = [
            value
            for key, value in model_info.items()
            if isinstance(key, str)
            and key.endswith(".context_length")
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value > 0
        ]
        if len(context_values) == 0:
            raise OllamaProviderError("Ollama model details omit context length")
        return max(context_values)

    @staticmethod
    def _parse_loaded_context_tokens(
        *,
        payload: dict[str, object],
        model: str,
    ) -> int:
        if "models" not in payload:
            raise OllamaProviderError("Ollama running-model list is malformed")
        records = payload["models"]
        if not isinstance(records, list):
            raise OllamaProviderError("Ollama running-model list is malformed")
        normalized_model = model.casefold()
        matching_records: list[dict[str, object]] = []
        for record in records:
            if not isinstance(record, dict):
                raise OllamaProviderError("Ollama running-model record is malformed")
            identifiers = {
                value.casefold()
                for field_name in ("name", "model")
                if isinstance((value := record.get(field_name)), str)
            }
            if normalized_model in identifiers:
                matching_records.append(record)
        if len(matching_records) != 1:
            raise OllamaProviderError(
                "Ollama did not report exactly one loaded selected model"
            )
        loaded_tokens = matching_records[0].get("context_length")
        if (
            not isinstance(loaded_tokens, int)
            or isinstance(loaded_tokens, bool)
            or loaded_tokens < 1
        ):
            raise OllamaProviderError("Ollama loaded context length is invalid")
        return loaded_tokens

    async def stream_pull(
        self,
        *,
        base_url: str,
        model: str,
    ) -> AsyncIterator[dict[str, object]]:
        normalized_model = validate_ollama_model(model)
        request_payload: dict[str, object] = {
            "model": normalized_model,
            "stream": True,
            "insecure": False,
        }
        url = _api_url(base_url=base_url, endpoint="/pull")
        did_finish = False
        last_completed = 0
        last_total = 0
        try:
            async with self._client() as client:
                async with client.stream("POST", url, json=request_payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line == "":
                            continue
                        event = self._parse_pull_stream_line(line)
                        status = event["status"]
                        completed = event["completed"]
                        total = event["total"]
                        assert isinstance(status, str)
                        assert isinstance(completed, int)
                        assert isinstance(total, int)
                        if total > 0:
                            last_total = total
                            last_completed = completed
                        if status == "success":
                            did_finish = True
                            if last_total > 0:
                                last_completed = last_total
                            yield {
                                "type": "done",
                                "status": status,
                                "completed": last_completed,
                                "total": last_total,
                            }
                            break
                        yield {
                            "type": "progress",
                            "status": status,
                            "completed": completed,
                            "total": total,
                        }
        except httpx.HTTPError as exc:
            raise OllamaProviderError("Ollama model download failed") from exc
        if not did_finish:
            raise OllamaProviderError("Ollama model download ended before completion")

    async def stream_chat(
        self,
        *,
        base_url: str,
        model: str,
        thinking_level: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
        on_request: Callable[[dict[str, object]], None],
    ) -> AsyncIterator[dict[str, object]]:
        wire_request = self._build_chat_wire_request(
            base_url=base_url,
            model=model,
            thinking_level=thinking_level,
            messages=messages,
            max_output_tokens=max_output_tokens,
        )
        on_request(wire_request)
        url = wire_request["url"]
        request_payload = wire_request["body"]
        assert isinstance(url, str)
        assert isinstance(request_payload, dict)
        did_finish = False
        try:
            async with self._client() as client:
                async with client.stream("POST", url, json=request_payload) as response:
                    if response.is_error:
                        await response.aread()
                        detail = self._parse_error_response(response_text=response.text)
                        raise OllamaProviderError(
                            f"Ollama chat request failed with HTTP "
                            f"{response.status_code}: {detail}"
                        )
                    async for event in self._stream_response_events(response=response):
                        if event["type"] == "done":
                            did_finish = True
                        yield event
        except httpx.HTTPError as exc:
            raise OllamaProviderError("Ollama chat request failed") from exc
        if not did_finish:
            raise OllamaProviderError("Ollama stream ended before completion")

    def _build_chat_wire_request(
        self,
        *,
        base_url: str,
        model: str,
        thinking_level: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
    ) -> dict[str, object]:
        normalized_model = validate_ollama_model(model)
        think_value = resolve_ollama_think_value(
            model=normalized_model,
            thinking_level=thinking_level,
        )
        self._validate_messages(messages)
        if (
            not isinstance(max_output_tokens, int)
            or isinstance(max_output_tokens, bool)
            or max_output_tokens < 1
        ):
            raise ValueError("Ollama maximum output tokens must be positive")
        request_payload: dict[str, object] = {
            "model": normalized_model,
            "messages": messages,
            "stream": True,
            "think": think_value,
            "options": {"num_predict": max_output_tokens},
        }
        url = _api_url(base_url=base_url, endpoint="/chat")
        return {"method": "POST", "url": url, "body": request_payload}

    async def _stream_response_events(
        self,
        *,
        response: httpx.Response,
    ) -> AsyncIterator[dict[str, object]]:
        async for line in response.aiter_lines():
            if line == "":
                continue
            event = self._parse_stream_line(line)
            message = event["message"]
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
                usage = self._parse_usage(payload=event)
                if usage:
                    yield {"type": "done", "usage": usage}
                else:
                    yield {"type": "done"}
                return

    @staticmethod
    def _parse_error_response(*, response_text: str) -> str:
        if not isinstance(response_text, str):
            raise TypeError("Ollama error response text must be a string")
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise OllamaProviderError(
                "Ollama returned malformed JSON for an HTTP error"
            ) from exc
        if not isinstance(payload, dict) or "error" not in payload:
            raise OllamaProviderError("Ollama HTTP error response is malformed")
        error = payload["error"]
        if not isinstance(error, str) or error.strip() == "":
            raise OllamaProviderError("Ollama HTTP error detail is malformed")
        detail = " ".join(error.split())
        return detail[:_MAX_ERROR_DETAIL_CHARACTERS]

    @staticmethod
    def _parse_usage(*, payload: dict[str, object]) -> dict[str, int]:
        usage: dict[str, int] = {}
        for field_name in ("prompt_eval_count", "eval_count"):
            if field_name not in payload:
                continue
            value = payload[field_name]
            if not isinstance(value, int) or value < 0:
                raise OllamaProviderError(f"Ollama {field_name} must be a non-negative integer")
            usage[field_name] = value
        return usage

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
    def _parse_pull_stream_line(line: str) -> dict[str, object]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OllamaProviderError("Ollama returned invalid model-download JSON") from exc
        if not isinstance(event, dict):
            raise OllamaProviderError("Ollama model-download event must be an object")
        if "error" in event:
            raise OllamaProviderError("Ollama reported a model download error")
        if "status" not in event:
            raise OllamaProviderError("Ollama model-download event is missing status")
        status = event["status"]
        if not isinstance(status, str) or status == "":
            raise OllamaProviderError("Ollama model-download event is missing status")
        completed = 0
        if "completed" in event:
            completed = event["completed"]
        total = 0
        if "total" in event:
            total = event["total"]
        if not isinstance(completed, int) or completed < 0:
            raise OllamaProviderError("Ollama model-download completed value is invalid")
        if not isinstance(total, int) or total < 0:
            raise OllamaProviderError("Ollama model-download total value is invalid")
        return {
            "status": status,
            "completed": completed,
            "total": total,
        }

    @staticmethod
    def _validate_messages(messages: list[dict[str, str]]) -> None:
        if not isinstance(messages, list) or len(messages) == 0:
            raise ValueError("Ollama chat messages must be a non-empty list")
        for message in messages:
            if not isinstance(message, dict):
                raise TypeError("Ollama chat message must be an object")
            if set(message) != {"role", "content"}:
                raise ValueError("Ollama chat message must contain role and content")
            if message["role"] not in {"system", "user", "assistant"}:
                raise ValueError("Ollama chat message has unsupported role")
            if not isinstance(message["content"], str):
                raise TypeError("Ollama chat message content must be a string")


ollama_provider = OllamaProvider(transport=None)
