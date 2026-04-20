from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from threading import Lock, Thread
import time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
import urllib.request

from app.config import (
    GOOGLE_DRIVE_CLIENT_ID,
    GOOGLE_DRIVE_CLIENT_SECRET,
    GOOGLE_DRIVE_ROOT_FOLDER_NAME,
)
from app.server_runtime import validate_namespace
from app.services.backup_settings_service import (
    clear_google_drive_connection,
    load_backup_settings,
    set_google_drive_connection,
)
from app.services.exception_capture import CapturedExceptionContext


_GOOGLE_DRIVE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_DRIVE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_DRIVE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_GOOGLE_DRIVE_DRIVE_ABOUT_URL = "https://www.googleapis.com/drive/v3/about?fields=user"
_GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
_GOOGLE_DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_GOOGLE_DRIVE_CONNECT_STATUS_PENDING = "pending"
_GOOGLE_DRIVE_CONNECT_STATUS_SUCCESS = "success"
_GOOGLE_DRIVE_CONNECT_STATUS_ERROR = "error"
_GOOGLE_DRIVE_CONNECT_STATUS_EXPIRED = "expired"
_GOOGLE_DRIVE_CONNECT_STATUSES = frozenset(
    {
        _GOOGLE_DRIVE_CONNECT_STATUS_PENDING,
        _GOOGLE_DRIVE_CONNECT_STATUS_SUCCESS,
        _GOOGLE_DRIVE_CONNECT_STATUS_ERROR,
        _GOOGLE_DRIVE_CONNECT_STATUS_EXPIRED,
    }
)
_PENDING_OAUTH_STATE_TTL_SECONDS = 600
_PENDING_CONNECT_REQUESTS_LOCK = Lock()


@dataclass(frozen=True)
class GoogleDriveClientConfig:
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class GoogleDriveConnectRequestStatus:
    request_id: str
    status: str
    message: str


@dataclass
class _PendingGoogleDriveConnectRequest:
    request_id: str
    token: str
    state: str
    code_verifier: str
    redirect_uri: str
    created_at_seconds: float
    updated_at_seconds: float
    status: str
    message: str
    server: ThreadingHTTPServer
    server_thread: Thread
    server_closed: bool


@dataclass(frozen=True)
class GoogleDriveBackupFile:
    file_id: str
    filename: str
    namespace: str
    created_at: str
    size_bytes: int


_PENDING_CONNECT_REQUESTS: dict[str, _PendingGoogleDriveConnectRequest] = {}


class _GoogleDriveLoopbackServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], *, request_id: str) -> None:
        self.request_id = request_id
        super().__init__(server_address, _GoogleDriveLoopbackHandler)


class _GoogleDriveLoopbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        server = self.server
        if not isinstance(server, _GoogleDriveLoopbackServer):
            raise RuntimeError("Loopback callback server has unexpected type")

        status_code, title, message = _handle_google_drive_loopback_callback(
            request_id=server.request_id,
            callback_path=self.path,
        )
        html_payload = _build_google_drive_loopback_html(title=title, message=message).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_payload)))
        self.end_headers()
        self.wfile.write(html_payload)
        _close_google_drive_connect_request_server(request_id=server.request_id)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _build_google_drive_loopback_html(*, title: str, message: str) -> str:
    if not isinstance(title, str) or title == "":
        raise ValueError("title must be a non-empty string")
    if not isinstance(message, str) or message == "":
        raise ValueError("message must be a non-empty string")
    escaped_title = html.escape(title)
    escaped_message = html.escape(message)
    return (
        "<!doctype html>"
        "<html><head><meta charset=\"utf-8\"><title>MetaList Google Drive</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "margin:0;padding:32px;background:#f6f8fb;color:#172033}"
        "main{max-width:560px;margin:0 auto;background:#fff;border:1px solid #d9e1ef;"
        "border-radius:16px;padding:24px 28px;box-shadow:0 12px 36px rgba(18,38,63,.08)}"
        "h1{margin:0 0 12px;font-size:28px}p{margin:0;font-size:17px;line-height:1.5}</style>"
        "</head><body><main>"
        f"<h1>{escaped_title}</h1><p>{escaped_message}</p>"
        "<script>window.close();</script>"
        "</main></body></html>"
    )


def _generate_pkce_code_verifier() -> str:
    code_verifier = secrets.token_urlsafe(64)
    if len(code_verifier) < 43 or len(code_verifier) > 128:
        raise RuntimeError("Generated PKCE code verifier has invalid length")
    return code_verifier


def _build_pkce_code_challenge(*, code_verifier: str) -> str:
    if not isinstance(code_verifier, str) or code_verifier == "":
        raise ValueError("code_verifier must be a non-empty string")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _parse_loopback_callback_params(*, callback_path: str) -> dict[str, str]:
    if not isinstance(callback_path, str) or callback_path == "":
        raise ValueError("callback_path must be a non-empty string")
    split_result = urlsplit(callback_path)
    params: dict[str, str] = {}
    for key, value in parse_qsl(split_result.query, keep_blank_values=True):
        if key in params:
            raise RuntimeError(f"Loopback callback query parameter repeated: {key}")
        params[key] = value
    return params


def _require_query_param(*, params: dict[str, str], key: str) -> str:
    if not isinstance(key, str) or key == "":
        raise ValueError("key must be a non-empty string")
    if key not in params:
        raise RuntimeError(f"Loopback callback missing query parameter: {key}")
    value = params[key]
    if not isinstance(value, str) or value == "":
        raise RuntimeError(f"Loopback callback query parameter {key} must be a non-empty string")
    return value


def is_google_drive_oauth_available() -> bool:
    return GOOGLE_DRIVE_CLIENT_ID != ""


def _require_google_drive_client_config() -> GoogleDriveClientConfig:
    if not is_google_drive_oauth_available():
        raise RuntimeError("METALIST_GOOGLE_DRIVE_CLIENT_ID is required for Google Drive backups")
    return GoogleDriveClientConfig(
        client_id=GOOGLE_DRIVE_CLIENT_ID,
        client_secret=GOOGLE_DRIVE_CLIENT_SECRET,
    )


def _shutdown_google_drive_loopback_server(*, server: ThreadingHTTPServer, server_thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    if server_thread.is_alive():
        server_thread.join(timeout=2)


def _close_google_drive_connect_request_server(*, request_id: str) -> None:
    if not isinstance(request_id, str) or request_id == "":
        raise ValueError("request_id must be a non-empty string")
    request_to_close = None
    with _PENDING_CONNECT_REQUESTS_LOCK:
        if request_id not in _PENDING_CONNECT_REQUESTS:
            return
        request = _PENDING_CONNECT_REQUESTS[request_id]
        if request.server_closed:
            return
        request.server_closed = True
        request_to_close = request
    if request_to_close is None:
        return
    _shutdown_google_drive_loopback_server(
        server=request_to_close.server,
        server_thread=request_to_close.server_thread,
    )


def _purge_expired_google_drive_connect_requests() -> None:
    now_seconds = time.time()
    requests_to_close: list[str] = []
    request_ids_to_remove: list[str] = []
    with _PENDING_CONNECT_REQUESTS_LOCK:
        for request_id, request in _PENDING_CONNECT_REQUESTS.items():
            if request.status == _GOOGLE_DRIVE_CONNECT_STATUS_PENDING:
                if now_seconds - request.created_at_seconds > _PENDING_OAUTH_STATE_TTL_SECONDS:
                    request.status = _GOOGLE_DRIVE_CONNECT_STATUS_EXPIRED
                    request.message = "Google Drive authorization timed out. Start again."
                    request.updated_at_seconds = now_seconds
                    requests_to_close.append(request_id)
                    continue

            if now_seconds - request.updated_at_seconds > _PENDING_OAUTH_STATE_TTL_SECONDS:
                request_ids_to_remove.append(request_id)
                requests_to_close.append(request_id)

        for request_id in request_ids_to_remove:
            del _PENDING_CONNECT_REQUESTS[request_id]

    for request_id in requests_to_close:
        _close_google_drive_connect_request_server(request_id=request_id)


def _parse_json_payload(payload_bytes: bytes) -> dict[str, object]:
    decode_capture = CapturedExceptionContext(UnicodeDecodeError, json.JSONDecodeError)
    payload = None
    with decode_capture:
        payload = json.loads(payload_bytes.decode("utf-8"))
    if decode_capture.captured_exception is not None:
        exc = decode_capture.captured_exception
        raise RuntimeError(f"Google Drive response was not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Google Drive response payload must be an object")
    return payload


def _request_bytes(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
) -> bytes:
    request = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    response = None
    request_capture = CapturedExceptionContext(OSError)
    with request_capture:
        response = urllib.request.urlopen(request, timeout=30)
    if request_capture.captured_exception is not None:
        exc = request_capture.captured_exception
        response_body = b""
        if hasattr(exc, "read") and callable(exc.read):
            response_body = exc.read()
        detail = str(exc)
        if response_body:
            decode_capture = CapturedExceptionContext(UnicodeDecodeError)
            decoded_body = None
            with decode_capture:
                decoded_body = response_body.decode("utf-8")
            if decode_capture.captured_exception is None and isinstance(decoded_body, str) and decoded_body != "":
                detail = decoded_body
        raise RuntimeError(f"Google Drive request failed: {detail}") from exc
    if response is None:
        raise RuntimeError("Google Drive request returned no response")
    with response:
        return response.read()


def _request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
) -> dict[str, object]:
    return _parse_json_payload(
        _request_bytes(method=method, url=url, headers=headers, body=body)
    )


def _build_auth_headers(access_token: str) -> dict[str, str]:
    if not isinstance(access_token, str) or access_token == "":
        raise ValueError("access_token must be a non-empty string")
    return {
        "Authorization": f"Bearer {access_token}",
    }


def _quote_drive_query_literal(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _ensure_google_drive_settings_shape(settings: dict[str, object]) -> dict[str, object]:
    if "google_drive" not in settings:
        raise RuntimeError("backup settings missing google_drive")
    google_drive = settings["google_drive"]
    if not isinstance(google_drive, dict):
        raise RuntimeError("backup settings google_drive must be an object")
    return google_drive


def _parse_token_expiry(token_expiry: str) -> datetime:
    if not isinstance(token_expiry, str) or token_expiry == "":
        raise RuntimeError("Google Drive token_expiry must be a non-empty string")
    parsed = datetime.fromisoformat(token_expiry)
    if parsed.tzinfo is None:
        raise RuntimeError("Google Drive token_expiry must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def start_google_drive_connect_request(*, token: str) -> dict[str, str]:
    if not isinstance(token, str) or token == "":
        raise ValueError("token must be a non-empty string")
    client_config = _require_google_drive_client_config()
    request_id = secrets.token_urlsafe(24)
    state = secrets.token_urlsafe(32)
    code_verifier = _generate_pkce_code_verifier()
    code_challenge = _build_pkce_code_challenge(code_verifier=code_verifier)
    loopback_server = _GoogleDriveLoopbackServer(("127.0.0.1", 0), request_id=request_id)
    redirect_uri = f"http://127.0.0.1:{loopback_server.server_port}"
    server_thread = Thread(
        target=loopback_server.serve_forever,
        name=f"google-drive-oauth-{request_id}",
        daemon=True,
    )
    request = _PendingGoogleDriveConnectRequest(
        request_id=request_id,
        token=token,
        state=state,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        created_at_seconds=time.time(),
        updated_at_seconds=time.time(),
        status=_GOOGLE_DRIVE_CONNECT_STATUS_PENDING,
        message="Waiting for Google Drive authorization.",
        server=loopback_server,
        server_thread=server_thread,
        server_closed=False,
    )
    _purge_expired_google_drive_connect_requests()
    with _PENDING_CONNECT_REQUESTS_LOCK:
        if request_id in _PENDING_CONNECT_REQUESTS:
            raise RuntimeError(f"Google Drive connect request already exists: {request_id}")
        _PENDING_CONNECT_REQUESTS[request_id] = request
    server_thread.start()

    query = urlencode(
        {
            "client_id": client_config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _GOOGLE_DRIVE_SCOPE,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return {
        "request_id": request_id,
        "authorization_url": f"{_GOOGLE_DRIVE_AUTH_URL}?{query}",
    }


def _exchange_code_for_tokens(
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
    code_verifier: str,
) -> dict[str, object]:
    if not isinstance(code, str) or code == "":
        raise ValueError("code must be a non-empty string")
    if not isinstance(redirect_uri, str) or redirect_uri == "":
        raise ValueError("redirect_uri must be a non-empty string")
    if not isinstance(client_id, str) or client_id == "":
        raise ValueError("client_id must be a non-empty string")
    if not isinstance(client_secret, str):
        raise ValueError("client_secret must be a string")
    if not isinstance(code_verifier, str) or code_verifier == "":
        raise ValueError("code_verifier must be a non-empty string")
    request_fields = {
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    if client_secret != "":
        request_fields["client_secret"] = client_secret
    request_body = urlencode(request_fields).encode("utf-8")
    return _request_json(
        method="POST",
        url=_GOOGLE_DRIVE_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=request_body,
    )


def _refresh_access_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, object]:
    if not isinstance(refresh_token, str) or refresh_token == "":
        raise RuntimeError("Google Drive refresh token is missing")
    if not isinstance(client_id, str) or client_id == "":
        raise ValueError("client_id must be a non-empty string")
    if not isinstance(client_secret, str):
        raise ValueError("client_secret must be a string")
    request_fields = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "grant_type": "refresh_token",
    }
    if client_secret != "":
        request_fields["client_secret"] = client_secret
    request_body = urlencode(request_fields).encode("utf-8")
    return _request_json(
        method="POST",
        url=_GOOGLE_DRIVE_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=request_body,
    )


def _extract_access_token_payload(payload: dict[str, object], *, prior_refresh_token: str) -> dict[str, str]:
    if "access_token" not in payload:
        raise RuntimeError("Google OAuth token response missing access_token")
    access_token = payload["access_token"]
    if not isinstance(access_token, str) or access_token == "":
        raise RuntimeError("Google OAuth token response access_token must be a non-empty string")

    if "expires_in" not in payload:
        raise RuntimeError("Google OAuth token response missing expires_in")
    expires_in = payload["expires_in"]
    if not isinstance(expires_in, int) or expires_in <= 0:
        raise RuntimeError("Google OAuth token response expires_in must be a positive integer")

    refresh_token = prior_refresh_token
    if "refresh_token" in payload:
        next_refresh_token = payload["refresh_token"]
        if not isinstance(next_refresh_token, str):
            raise RuntimeError("Google OAuth token response refresh_token must be a string")
        if next_refresh_token != "":
            refresh_token = next_refresh_token

    token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expiry": token_expiry.isoformat(),
    }


def _get_google_account_email(*, access_token: str) -> str:
    payload = _request_json(
        method="GET",
        url=_GOOGLE_DRIVE_DRIVE_ABOUT_URL,
        headers=_build_auth_headers(access_token),
        body=None,
    )
    if "user" not in payload:
        return ""
    user = payload["user"]
    if not isinstance(user, dict):
        return ""
    if "emailAddress" not in user:
        return ""
    email_address = user["emailAddress"]
    if not isinstance(email_address, str):
        return ""
    return email_address


def _drive_query_files(*, access_token: str, query: str, fields: str) -> list[dict[str, object]]:
    url = (
        f"{_GOOGLE_DRIVE_DRIVE_FILES_URL}?"
        + urlencode(
            {
                "q": query,
                "fields": fields,
                "pageSize": "1000",
                "supportsAllDrives": "false",
            }
        )
    )
    payload = _request_json(
        method="GET",
        url=url,
        headers=_build_auth_headers(access_token),
        body=None,
    )
    if "files" not in payload:
        raise RuntimeError("Google Drive files response missing files")
    files = payload["files"]
    if not isinstance(files, list):
        raise RuntimeError("Google Drive files response files must be a list")
    normalized: list[dict[str, object]] = []
    for raw_entry in files:
        if not isinstance(raw_entry, dict):
            raise RuntimeError("Google Drive files entries must be objects")
        normalized.append(raw_entry)
    return normalized


def _create_drive_folder(*, access_token: str, name: str, parent_id: str) -> str:
    metadata = {
        "name": name,
        "mimeType": _GOOGLE_DRIVE_FOLDER_MIME_TYPE,
        "parents": [parent_id],
    }
    payload = _request_json(
        method="POST",
        url=f"{_GOOGLE_DRIVE_DRIVE_FILES_URL}?fields=id,name",
        headers={
            **_build_auth_headers(access_token),
            "Content-Type": "application/json",
        },
        body=json.dumps(metadata).encode("utf-8"),
    )
    if "id" not in payload:
        raise RuntimeError("Google Drive folder create response missing id")
    folder_id = payload["id"]
    if not isinstance(folder_id, str) or folder_id == "":
        raise RuntimeError("Google Drive folder id must be a non-empty string")
    return folder_id


def _ensure_folder(*, access_token: str, name: str, parent_id: str) -> str:
    query = (
        f"name = '{_quote_drive_query_literal(name)}' "
        f"and mimeType = '{_GOOGLE_DRIVE_FOLDER_MIME_TYPE}' "
        f"and trashed = false "
        f"and '{_quote_drive_query_literal(parent_id)}' in parents"
    )
    files = _drive_query_files(
        access_token=access_token,
        query=query,
        fields="files(id,name)",
    )
    if files:
        first = files[0]
        if "id" not in first:
            raise RuntimeError("Google Drive folder search result missing id")
        folder_id = first["id"]
        if not isinstance(folder_id, str) or folder_id == "":
            raise RuntimeError("Google Drive folder id must be a non-empty string")
        return folder_id
    return _create_drive_folder(access_token=access_token, name=name, parent_id=parent_id)


def _ensure_root_folder(*, access_token: str, root_folder_name: str) -> str:
    return _ensure_folder(access_token=access_token, name=root_folder_name, parent_id="root")


def _ensure_connected_settings(*, token: str) -> tuple[dict[str, object], dict[str, object], str]:
    settings = load_backup_settings(token=token)
    google_drive = _ensure_google_drive_settings_shape(settings)
    if "status" not in google_drive:
        raise RuntimeError("Google Drive settings missing status")
    status = google_drive["status"]
    if status != "connected":
        raise RuntimeError("Google Drive is not connected")
    if "access_token" not in google_drive or "refresh_token" not in google_drive or "token_expiry" not in google_drive:
        raise RuntimeError("Google Drive settings missing token fields")
    access_token = google_drive["access_token"]
    refresh_token = google_drive["refresh_token"]
    token_expiry = google_drive["token_expiry"]
    if not isinstance(access_token, str) or not isinstance(refresh_token, str) or not isinstance(token_expiry, str):
        raise RuntimeError("Google Drive token settings must be strings")
    expiry_utc = _parse_token_expiry(token_expiry)
    if expiry_utc <= datetime.now(timezone.utc) + timedelta(minutes=1):
        client_config = _require_google_drive_client_config()
        refreshed_payload = _refresh_access_token(
            refresh_token=refresh_token,
            client_id=client_config.client_id,
            client_secret=client_config.client_secret,
        )
        refreshed_tokens = _extract_access_token_payload(
            refreshed_payload,
            prior_refresh_token=refresh_token,
        )
        account_email = google_drive["account_email"]
        root_folder_id = google_drive["root_folder_id"]
        root_folder_name = google_drive["root_folder_name"]
        if not isinstance(account_email, str) or not isinstance(root_folder_id, str) or not isinstance(root_folder_name, str):
            raise RuntimeError("Google Drive settings fields must be strings")
        settings = set_google_drive_connection(
            token=token,
            status="connected",
            account_email=account_email,
            access_token=refreshed_tokens["access_token"],
            refresh_token=refreshed_tokens["refresh_token"],
            token_expiry=refreshed_tokens["token_expiry"],
            root_folder_id=root_folder_id,
            root_folder_name=root_folder_name,
        )
        google_drive = _ensure_google_drive_settings_shape(settings)
        access_token = refreshed_tokens["access_token"]
    return settings, google_drive, access_token


def _require_google_drive_connect_request(*, request_id: str) -> _PendingGoogleDriveConnectRequest:
    if not isinstance(request_id, str) or request_id == "":
        raise ValueError("request_id must be a non-empty string")
    _purge_expired_google_drive_connect_requests()
    with _PENDING_CONNECT_REQUESTS_LOCK:
        if request_id not in _PENDING_CONNECT_REQUESTS:
            raise RuntimeError("Google Drive authorization request is missing or expired")
        return _PENDING_CONNECT_REQUESTS[request_id]


def _set_google_drive_connect_request_status(
    *,
    request_id: str,
    status: str,
    message: str,
) -> None:
    if not isinstance(status, str) or status not in _GOOGLE_DRIVE_CONNECT_STATUSES:
        raise ValueError(f"Unsupported Google Drive connect request status: {status!r}")
    if not isinstance(message, str) or message == "":
        raise ValueError("message must be a non-empty string")
    request = _require_google_drive_connect_request(request_id=request_id)
    with _PENDING_CONNECT_REQUESTS_LOCK:
        request.status = status
        request.message = message
        request.updated_at_seconds = time.time()


def _complete_google_drive_connect_request(*, request_id: str, code: str) -> None:
    if not isinstance(code, str) or code == "":
        raise ValueError("code must be a non-empty string")
    request = _require_google_drive_connect_request(request_id=request_id)
    if request.status != _GOOGLE_DRIVE_CONNECT_STATUS_PENDING:
        raise RuntimeError(f"Google Drive authorization request is not pending: {request.status}")

    existing_settings = load_backup_settings(token=request.token)
    existing_google_drive = _ensure_google_drive_settings_shape(existing_settings)
    prior_refresh_token = existing_google_drive["refresh_token"]
    if not isinstance(prior_refresh_token, str):
        raise RuntimeError("Google Drive refresh_token setting must be a string")

    client_config = _require_google_drive_client_config()
    token_payload = _exchange_code_for_tokens(
        code=code,
        redirect_uri=request.redirect_uri,
        client_id=client_config.client_id,
        client_secret=client_config.client_secret,
        code_verifier=request.code_verifier,
    )
    tokens = _extract_access_token_payload(token_payload, prior_refresh_token=prior_refresh_token)
    access_token = tokens["access_token"]
    root_folder_name = GOOGLE_DRIVE_ROOT_FOLDER_NAME
    root_folder_id = _ensure_root_folder(access_token=access_token, root_folder_name=root_folder_name)
    account_email = _get_google_account_email(access_token=access_token)

    set_google_drive_connection(
        token=request.token,
        status="connected",
        account_email=account_email,
        access_token=access_token,
        refresh_token=tokens["refresh_token"],
        token_expiry=tokens["token_expiry"],
        root_folder_id=root_folder_id,
        root_folder_name=root_folder_name,
    )


def _handle_google_drive_loopback_callback(*, request_id: str, callback_path: str) -> tuple[int, str, str]:
    request = _require_google_drive_connect_request(request_id=request_id)
    callback_params = _parse_loopback_callback_params(callback_path=callback_path)
    if "error" in callback_params:
        oauth_error = callback_params["error"]
        if not isinstance(oauth_error, str) or oauth_error == "":
            raise RuntimeError("Google Drive OAuth callback error parameter must be a non-empty string")
        error_message = f"Google Drive authorization was cancelled or denied: {oauth_error}"
        _set_google_drive_connect_request_status(
            request_id=request_id,
            status=_GOOGLE_DRIVE_CONNECT_STATUS_ERROR,
            message=error_message,
        )
        return 400, "Google Drive connection failed", error_message

    state = _require_query_param(params=callback_params, key="state")
    if state != request.state:
        error_message = "Google Drive authorization state did not match the original request."
        _set_google_drive_connect_request_status(
            request_id=request_id,
            status=_GOOGLE_DRIVE_CONNECT_STATUS_ERROR,
            message=error_message,
        )
        return 400, "Google Drive connection failed", error_message

    code = _require_query_param(params=callback_params, key="code")
    exchange_capture = CapturedExceptionContext(RuntimeError, ValueError, OSError)
    with exchange_capture:
        _complete_google_drive_connect_request(request_id=request_id, code=code)
    if exchange_capture.captured_exception is not None:
        error_message = f"Google Drive connection failed: {exchange_capture.captured_exception}"
        _set_google_drive_connect_request_status(
            request_id=request_id,
            status=_GOOGLE_DRIVE_CONNECT_STATUS_ERROR,
            message=error_message,
        )
        return 500, "Google Drive connection failed", error_message

    success_message = "Google Drive connected. Return to MetaList."
    _set_google_drive_connect_request_status(
        request_id=request_id,
        status=_GOOGLE_DRIVE_CONNECT_STATUS_SUCCESS,
        message=success_message,
    )
    return 200, "Google Drive connected", success_message


def get_google_drive_connect_request_status(*, request_id: str) -> GoogleDriveConnectRequestStatus:
    request = _require_google_drive_connect_request(request_id=request_id)
    return GoogleDriveConnectRequestStatus(
        request_id=request.request_id,
        status=request.status,
        message=request.message,
    )


def get_google_drive_connection_status(*, token: str) -> dict[str, object]:
    settings = load_backup_settings(token=token)
    google_drive = _ensure_google_drive_settings_shape(settings)
    return {
        "status": google_drive["status"],
        "account_email": google_drive["account_email"],
        "root_folder_name": google_drive["root_folder_name"],
        "connected": google_drive["status"] == "connected",
    }


def disconnect_google_drive(*, token: str) -> dict[str, object]:
    return clear_google_drive_connection(token=token)


def validate_google_drive_connection(*, token: str) -> dict[str, object]:
    settings, google_drive, access_token = _ensure_connected_settings(token=token)
    root_folder_name = google_drive["root_folder_name"]
    if not isinstance(root_folder_name, str):
        raise RuntimeError("Google Drive root_folder_name must be a string")
    effective_root_folder_name = root_folder_name
    if effective_root_folder_name == "":
        effective_root_folder_name = GOOGLE_DRIVE_ROOT_FOLDER_NAME
    root_folder_id = _ensure_root_folder(
        access_token=access_token,
        root_folder_name=effective_root_folder_name,
    )
    account_email = _get_google_account_email(access_token=access_token)
    updated_settings = set_google_drive_connection(
        token=token,
        status="connected",
        account_email=account_email,
        access_token=access_token,
        refresh_token=str(google_drive["refresh_token"]),
        token_expiry=str(google_drive["token_expiry"]),
        root_folder_id=root_folder_id,
        root_folder_name=effective_root_folder_name,
    )
    updated_google_drive = _ensure_google_drive_settings_shape(updated_settings)
    return {
        "status": updated_google_drive["status"],
        "account_email": updated_google_drive["account_email"],
        "root_folder_name": updated_google_drive["root_folder_name"],
        "connected": updated_google_drive["status"] == "connected",
    }


def _list_namespace_folders(*, access_token: str, root_folder_id: str) -> list[dict[str, object]]:
    query = (
        f"mimeType = '{_GOOGLE_DRIVE_FOLDER_MIME_TYPE}' "
        f"and trashed = false "
        f"and '{_quote_drive_query_literal(root_folder_id)}' in parents"
    )
    return _drive_query_files(
        access_token=access_token,
        query=query,
        fields="files(id,name,createdTime)",
    )


def _list_backup_files_in_folder(
    *,
    access_token: str,
    folder_id: str,
    namespace: str,
) -> list[GoogleDriveBackupFile]:
    query = f"trashed = false and '{_quote_drive_query_literal(folder_id)}' in parents"
    files = _drive_query_files(
        access_token=access_token,
        query=query,
        fields="files(id,name,createdTime,modifiedTime,size)",
    )
    backups: list[GoogleDriveBackupFile] = []
    for raw_entry in files:
        if "name" not in raw_entry or "id" not in raw_entry:
            raise RuntimeError("Google Drive backup entry is missing id or name")
        filename = raw_entry["name"]
        file_id = raw_entry["id"]
        if not isinstance(filename, str) or not isinstance(file_id, str):
            raise RuntimeError("Google Drive backup id/name must be strings")
        if not filename.endswith(".metalist-backup.tar.gz"):
            continue
        created_at = ""
        if "modifiedTime" in raw_entry and isinstance(raw_entry["modifiedTime"], str):
            created_at = raw_entry["modifiedTime"]
        elif "createdTime" in raw_entry and isinstance(raw_entry["createdTime"], str):
            created_at = raw_entry["createdTime"]
        if created_at == "":
            raise RuntimeError("Google Drive backup entry missing created time")
        size_bytes = 0
        if "size" in raw_entry:
            raw_size = raw_entry["size"]
            if isinstance(raw_size, str) and raw_size.isdigit():
                size_bytes = int(raw_size)
        backups.append(
            GoogleDriveBackupFile(
                file_id=file_id,
                filename=filename,
                namespace=namespace,
                created_at=created_at,
                size_bytes=size_bytes,
            )
        )
    backups.sort(key=lambda entry: entry.created_at, reverse=True)
    return backups


def list_google_drive_backups(*, token: str) -> list[GoogleDriveBackupFile]:
    settings, google_drive, access_token = _ensure_connected_settings(token=token)
    root_folder_id = google_drive["root_folder_id"]
    root_folder_name = google_drive["root_folder_name"]
    if not isinstance(root_folder_id, str) or not isinstance(root_folder_name, str):
        raise RuntimeError("Google Drive folder settings must be strings")
    if root_folder_id == "":
        effective_root_folder_name = root_folder_name
        if effective_root_folder_name == "":
            effective_root_folder_name = GOOGLE_DRIVE_ROOT_FOLDER_NAME
        root_folder_id = _ensure_root_folder(
            access_token=access_token,
            root_folder_name=effective_root_folder_name,
        )
        settings = set_google_drive_connection(
            token=token,
            status="connected",
            account_email=str(google_drive["account_email"]),
            access_token=access_token,
            refresh_token=str(google_drive["refresh_token"]),
            token_expiry=str(google_drive["token_expiry"]),
            root_folder_id=root_folder_id,
            root_folder_name=effective_root_folder_name,
        )
        google_drive = _ensure_google_drive_settings_shape(settings)

    namespace_folders = _list_namespace_folders(access_token=access_token, root_folder_id=root_folder_id)
    backups: list[GoogleDriveBackupFile] = []
    for folder in namespace_folders:
        if "name" not in folder or "id" not in folder:
            raise RuntimeError("Google Drive namespace folder is missing id or name")
        folder_name = folder["name"]
        folder_id = folder["id"]
        if not isinstance(folder_name, str) or not isinstance(folder_id, str):
            raise RuntimeError("Google Drive namespace folder id/name must be strings")
        validate_capture = CapturedExceptionContext(RuntimeError)
        normalized_namespace = None
        with validate_capture:
            normalized_namespace = validate_namespace(namespace=folder_name)
        if validate_capture.captured_exception is not None:
            continue
        if normalized_namespace is None:
            raise RuntimeError("Namespace validation finished without a namespace")
        backups.extend(
            _list_backup_files_in_folder(
                access_token=access_token,
                folder_id=folder_id,
                namespace=normalized_namespace,
            )
        )

    backups.sort(key=lambda entry: entry.created_at, reverse=True)
    return backups


def list_google_drive_backups_for_namespace(*, token: str, namespace: str) -> list[GoogleDriveBackupFile]:
    normalized_namespace = validate_namespace(namespace=namespace)
    all_backups = list_google_drive_backups(token=token)
    return [backup for backup in all_backups if backup.namespace == normalized_namespace]


def _build_multipart_upload_body(*, filename: str, parent_id: str, archive_bytes: bytes) -> tuple[bytes, str]:
    boundary = f"metalist-boundary-{secrets.token_hex(16)}"
    metadata = json.dumps(
        {
            "name": filename,
            "parents": [parent_id],
        }
    ).encode("utf-8")
    body = (
        b"--" + boundary.encode("utf-8") + b"\r\n"
        + b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + metadata
        + b"\r\n--" + boundary.encode("utf-8") + b"\r\n"
        + b"Content-Type: application/gzip\r\n\r\n"
        + archive_bytes
        + b"\r\n--" + boundary.encode("utf-8") + b"--\r\n"
    )
    return body, boundary


def upload_google_drive_backup(
    *,
    token: str,
    namespace: str,
    archive_path: str,
) -> GoogleDriveBackupFile:
    normalized_namespace = validate_namespace(namespace=namespace)
    if not isinstance(archive_path, str) or archive_path == "":
        raise ValueError("archive_path must be a non-empty string")

    archive_file_path = Path(archive_path)
    if not archive_file_path.exists():
        raise FileNotFoundError(f"Archive file not found: {archive_file_path}")
    archive_bytes = archive_file_path.read_bytes()

    settings, google_drive, access_token = _ensure_connected_settings(token=token)
    root_folder_name = google_drive["root_folder_name"]
    if not isinstance(root_folder_name, str):
        raise RuntimeError("Google Drive root_folder_name must be a string")
    root_folder_id = google_drive["root_folder_id"]
    if not isinstance(root_folder_id, str) or root_folder_id == "":
        effective_root_folder_name = root_folder_name
        if effective_root_folder_name == "":
            effective_root_folder_name = GOOGLE_DRIVE_ROOT_FOLDER_NAME
        root_folder_id = _ensure_root_folder(
            access_token=access_token,
            root_folder_name=effective_root_folder_name,
        )
        settings = set_google_drive_connection(
            token=token,
            status="connected",
            account_email=str(google_drive["account_email"]),
            access_token=access_token,
            refresh_token=str(google_drive["refresh_token"]),
            token_expiry=str(google_drive["token_expiry"]),
            root_folder_id=root_folder_id,
            root_folder_name=effective_root_folder_name,
        )
        google_drive = _ensure_google_drive_settings_shape(settings)

    namespace_folder_id = _ensure_folder(
        access_token=access_token,
        name=normalized_namespace,
        parent_id=root_folder_id,
    )
    upload_body, boundary = _build_multipart_upload_body(
        filename=archive_file_path.name,
        parent_id=namespace_folder_id,
        archive_bytes=archive_bytes,
    )
    payload = _request_json(
        method="POST",
        url="https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,createdTime,modifiedTime,size",
        headers={
            **_build_auth_headers(access_token),
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        body=upload_body,
    )
    if "id" not in payload or "name" not in payload:
        raise RuntimeError("Google Drive upload response missing id or name")
    file_id = payload["id"]
    filename = payload["name"]
    if not isinstance(file_id, str) or not isinstance(filename, str):
        raise RuntimeError("Google Drive upload id/name must be strings")
    created_at = ""
    if "modifiedTime" in payload and isinstance(payload["modifiedTime"], str):
        created_at = payload["modifiedTime"]
    elif "createdTime" in payload and isinstance(payload["createdTime"], str):
        created_at = payload["createdTime"]
    if created_at == "":
        created_at = datetime.now(timezone.utc).isoformat()
    size_bytes = archive_file_path.stat().st_size
    return GoogleDriveBackupFile(
        file_id=file_id,
        filename=filename,
        namespace=normalized_namespace,
        created_at=created_at,
        size_bytes=size_bytes,
    )


def delete_google_drive_backup(*, token: str, file_id: str) -> None:
    if not isinstance(file_id, str) or file_id == "":
        raise ValueError("file_id must be a non-empty string")
    _, _, access_token = _ensure_connected_settings(token=token)
    _request_bytes(
        method="DELETE",
        url=f"{_GOOGLE_DRIVE_DRIVE_FILES_URL}/{quote(file_id)}",
        headers=_build_auth_headers(access_token),
        body=None,
    )


def download_google_drive_backup(*, token: str, file_id: str, target_path: str) -> None:
    if not isinstance(file_id, str) or file_id == "":
        raise ValueError("file_id must be a non-empty string")
    if not isinstance(target_path, str) or target_path == "":
        raise ValueError("target_path must be a non-empty string")

    _, _, access_token = _ensure_connected_settings(token=token)
    payload = _request_bytes(
        method="GET",
        url=f"{_GOOGLE_DRIVE_DRIVE_FILES_URL}/{quote(file_id)}?alt=media",
        headers=_build_auth_headers(access_token),
        body=None,
    )
    destination_path = Path(target_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(payload)
