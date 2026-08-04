from __future__ import annotations

import base64

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from app.api.request_auth import AUTH_COOKIE_NAME
from app.api.routes import remote_images as remote_images_route
from app.services.remote_image_proxy import (
    RemoteImageFetchError,
    RemoteImagePayload,
    RemoteImageProxyRegistry,
    fetch_remote_image,
    rewrite_remote_image_sources_for_proxy,
)


def _token_factory() -> str:
    return "A" * 32


def _request(*, auth_cookie: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if auth_cookie is not None:
        headers.append((b"cookie", f"{AUTH_COOKIE_NAME}={auth_cookie}".encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api2/remote-images/token",
            "raw_path": b"/api2/remote-images/token",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 9443),
        }
    )


def test_rendered_remote_images_use_opaque_same_origin_proxy_urls() -> None:
    registry = RemoteImageProxyRegistry(
        max_entries=10,
        token_factory=_token_factory,
    )
    content = (
        '<div><img width="320" src="https://images.example/cat.png" alt="cat"></div>'
        '<img src="data:image/png;base64,AAAA">'
        '<a href="https://images.example/cat.png">ordinary link</a>'
    )

    rendered = rewrite_remote_image_sources_for_proxy(
        content_html=content,
        registry=registry,
    )

    assert (
        'data-remote-image-proxy-src="/api2/remote-images/'
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"'
    ) in rendered
    assert '<img width="320" src=' not in rendered
    assert 'src="https://images.example/cat.png"' not in rendered
    assert 'src="data:image/png;base64,AAAA"' in rendered
    assert 'href="https://images.example/cat.png"' in rendered
    assert registry.resolve("A" * 32) == "https://images.example/cat.png"


def test_registration_route_returns_authenticated_opaque_proxy_paths(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        remote_images_route.remote_image_proxy_registry,
        "register",
        lambda url: "A" * 32
        if url == "https://images.example/cat.png"
        else (_ for _ in ()).throw(AssertionError(url)),
    )

    register_remote_images = remote_images_route.register_remote_images.__wrapped__
    with pytest.raises(HTTPException) as unauthenticated:
        register_remote_images(
            _request(auth_cookie=None),
            remote_images_route.RemoteImageRegistrationRequest(
                source_urls=["https://images.example/cat.png"],
            ),
        )
    assert unauthenticated.value.status_code == 401

    response = register_remote_images(
        _request(auth_cookie="session-token"),
        remote_images_route.RemoteImageRegistrationRequest(
            source_urls=["https://images.example/cat.png"],
        ),
    )

    assert response.model_dump() == {
        "images": [
            {
                "source_url": "https://images.example/cat.png",
                "proxy_path": "/api2/remote-images/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            }
        ]
    }


def test_remote_image_registry_reuses_tokens_and_rejects_unknown_tokens() -> None:
    generated_tokens = iter(("A" * 32, "B" * 32))
    registry = RemoteImageProxyRegistry(
        max_entries=10,
        token_factory=lambda: next(generated_tokens),
    )

    first = registry.register("https://images.example/cat.png")
    second = registry.register("https://images.example/cat.png")

    assert first == "A" * 32
    assert second == first
    with pytest.raises(KeyError, match="Unknown remote image proxy token"):
        registry.resolve("Z" * 32)


def test_remote_image_fetch_rejects_signature_only_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.remote_image_proxy._download_one_url",
        lambda _url: (b"\x89PNG\r\n\x1a\n", None, None),
    )

    with pytest.raises(RemoteImageFetchError, match="invalid_image"):
        fetch_remote_image("https://images.example/broken.png")


def test_remote_image_fetch_revalidates_redirect_and_returns_valid_image(
    monkeypatch,
) -> None:
    one_pixel_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    calls: list[str] = []

    def download(url: str):
        calls.append(url)
        if len(calls) == 1:
            return None, "https://cdn.example/final.png", None
        return one_pixel_png, None, None

    monkeypatch.setattr(
        "app.services.remote_image_proxy._download_one_url",
        download,
    )

    payload = fetch_remote_image("https://images.example/start.png")

    assert calls == [
        "https://images.example/start.png",
        "https://cdn.example/final.png",
    ]
    assert payload.content == one_pixel_png
    assert payload.mime_type == "image/png"


def test_proxy_route_requires_auth_and_returns_non_persistent_image(
    monkeypatch,
) -> None:
    token = "A" * 32
    monkeypatch.setattr(
        remote_images_route.remote_image_proxy_registry,
        "resolve",
        lambda candidate: "https://images.example/cat.png"
        if candidate == token
        else (_ for _ in ()).throw(KeyError(candidate)),
    )
    monkeypatch.setattr(
        remote_images_route,
        "fetch_remote_image",
        lambda url: RemoteImagePayload(content=b"image bytes", mime_type="image/png")
        if url == "https://images.example/cat.png"
        else (_ for _ in ()).throw(AssertionError(url)),
    )

    with pytest.raises(HTTPException) as unauthenticated:
        remote_images_route.proxy_remote_image(
            _request(auth_cookie=None),
            token,
        )
    assert unauthenticated.value.status_code == 401

    response = remote_images_route.proxy_remote_image(
        _request(auth_cookie="session-token"),
        token,
    )

    assert response.body == b"image bytes"
    assert response.media_type == "image/png"
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
