"""Session-scoped, in-memory AI chat state."""

from __future__ import annotations

from threading import Lock
from uuid import uuid4


_MAX_MESSAGES_PER_SESSION = 100
_MAX_MESSAGE_CHARACTERS = 32_000


class AiChatSessionStore:
    """Keep AI conversations isolated by opaque authenticated-session key."""

    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, str]]] = {}
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._sessions.clear()

    def clear_session(self, *, session_key: str) -> None:
        self._validate_session_key(session_key)
        with self._lock:
            self._sessions.pop(session_key, None)

    def snapshot(self, *, session_key: str) -> dict[str, list[dict[str, str]]]:
        self._validate_session_key(session_key)
        with self._lock:
            messages = self._sessions.get(session_key, [])
            return {"messages": [dict(message) for message in messages]}

    def start_turn(
        self,
        *,
        session_key: str,
        user_content: str,
        provider: str,
        model: str,
    ) -> str:
        self._validate_session_key(session_key)
        self._validate_message_text(user_content, label="user_content")
        self._validate_message_text(provider, label="provider")
        self._validate_message_text(model, label="model")
        with self._lock:
            messages = self._sessions.setdefault(session_key, [])
            if any(message["status"] == "streaming" for message in messages):
                raise RuntimeError("AI chat session already streaming a turn")
            if len(messages) + 2 > _MAX_MESSAGES_PER_SESSION:
                del messages[:2]
            user_message_id = str(uuid4())
            assistant_message_id = str(uuid4())
            messages.extend(
                [
                    {
                        "id": user_message_id,
                        "role": "user",
                        "content": user_content,
                        "thinking": "",
                        "status": "complete",
                        "error": "",
                        "provider": provider,
                        "model": model,
                    },
                    {
                        "id": assistant_message_id,
                        "role": "assistant",
                        "content": "",
                        "thinking": "",
                        "status": "streaming",
                        "error": "",
                        "provider": provider,
                        "model": model,
                    },
                ]
            )
            return assistant_message_id

    def append_delta(
        self,
        *,
        session_key: str,
        turn_id: str,
        delta_kind: str,
        text: str,
    ) -> None:
        self._validate_session_key(session_key)
        self._validate_message_text(turn_id, label="turn_id")
        if delta_kind not in {"thinking", "content"}:
            raise ValueError(f"Unsupported AI delta kind: {delta_kind}")
        if not isinstance(text, str) or text == "":
            raise ValueError("AI delta text must be a non-empty string")
        with self._lock:
            message = self._require_streaming_turn(
                session_key=session_key,
                turn_id=turn_id,
            )
            updated_text = message[delta_kind] + text
            if len(updated_text) > _MAX_MESSAGE_CHARACTERS:
                raise RuntimeError(f"AI {delta_kind} exceeded {_MAX_MESSAGE_CHARACTERS} characters")
            message[delta_kind] = updated_text

    def complete_turn(self, *, session_key: str, turn_id: str) -> None:
        self._validate_session_key(session_key)
        self._validate_message_text(turn_id, label="turn_id")
        with self._lock:
            message = self._require_streaming_turn(
                session_key=session_key,
                turn_id=turn_id,
            )
            message["status"] = "complete"

    def fail_turn(self, *, session_key: str, turn_id: str, error: str) -> None:
        self._validate_session_key(session_key)
        self._validate_message_text(turn_id, label="turn_id")
        self._validate_message_text(error, label="error")
        with self._lock:
            message = self._require_streaming_turn(
                session_key=session_key,
                turn_id=turn_id,
            )
            message["status"] = "error"
            message["error"] = error

    def provider_messages(self, *, session_key: str) -> list[dict[str, str]]:
        self._validate_session_key(session_key)
        with self._lock:
            messages = self._sessions.get(session_key, [])
            assert len(messages) % 2 == 0, "AI chat history must contain complete turn pairs"
            provider_messages: list[dict[str, str]] = []
            for index in range(0, len(messages), 2):
                user_message = messages[index]
                assistant_message = messages[index + 1]
                assert user_message["role"] == "user"
                assert user_message["status"] == "complete"
                assert assistant_message["role"] == "assistant"
                if assistant_message["status"] == "error":
                    continue
                provider_messages.append(
                    {"role": "user", "content": user_message["content"]}
                )
                if assistant_message["status"] == "streaming":
                    assert index == len(messages) - 2, "only the current turn may be streaming"
                    continue
                assert assistant_message["status"] == "complete"
                provider_messages.append(
                    {"role": "assistant", "content": assistant_message["content"]}
                )
            return provider_messages

    def _require_streaming_turn(
        self,
        *,
        session_key: str,
        turn_id: str,
    ) -> dict[str, str]:
        messages = self._sessions.get(session_key)
        if messages is None:
            raise RuntimeError("AI chat session missing")
        for message in messages:
            if message["id"] != turn_id:
                continue
            if message["role"] != "assistant":
                raise RuntimeError("AI turn id does not identify an assistant message")
            if message["status"] != "streaming":
                raise RuntimeError("AI turn is not streaming")
            return message
        raise RuntimeError("AI streaming turn missing")

    @staticmethod
    def _validate_session_key(session_key: str) -> None:
        if not isinstance(session_key, str) or session_key == "":
            raise ValueError("session_key must be a non-empty string")

    @staticmethod
    def _validate_message_text(value: str, *, label: str) -> None:
        if not isinstance(label, str) or label == "":
            raise ValueError("label must be a non-empty string")
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(f"{label} must be a non-empty string")
        if len(value) > _MAX_MESSAGE_CHARACTERS:
            raise ValueError(f"{label} exceeds {_MAX_MESSAGE_CHARACTERS} characters")


ai_chat_store = AiChatSessionStore()
