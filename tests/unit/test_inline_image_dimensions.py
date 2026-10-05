from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from app.services.inline_image_dimensions import add_inline_image_dimensions, image_size_from_header


def _encoded(fmt: str, size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "GIF", "JPEG", "WEBP"])
def test_header_size_matches_the_image(fmt: str) -> None:
    assert image_size_from_header(_encoded(fmt, (37, 23))) == (37, 23)


def test_lossless_webp_header_size() -> None:
    buffer = io.BytesIO()
    Image.new("RGBA", (41, 19), (1, 2, 3, 128)).save(buffer, format="WEBP", lossless=True)
    assert image_size_from_header(buffer.getvalue()) == (41, 19)


@pytest.mark.parametrize("data", [b"", b"not an image", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff\xe0\x00"])
def test_unrecognised_or_truncated_headers_have_no_size(data: bytes) -> None:
    assert image_size_from_header(data) is None


def _img(fmt: str, size: tuple[int, int], extra: str) -> str:
    payload = base64.b64encode(_encoded(fmt, size)).decode("ascii")
    mime = {"JPEG": "jpeg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}[fmt]
    return f'<img src="data:image/{mime};base64,{payload}"{extra}>'


def test_inline_images_gain_their_natural_size() -> None:
    html = f"<p>before</p>{_img('JPEG', (640, 480), '')}<p>after</p>"
    stamped = add_inline_image_dimensions(html)
    assert 'width="640" height="480"' in stamped
    assert stamped.startswith("<p>before</p><img ") and stamped.endswith("<p>after</p>")


def test_images_that_already_have_a_size_or_no_data_uri_are_untouched() -> None:
    sized = _img("PNG", (10, 10), ' width="5"')
    remote = '<img src="https://example.com/x.png">'
    html = sized + remote
    assert add_inline_image_dimensions(html) == html


def test_self_closing_tags_and_long_jpeg_metadata() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200)).save(buffer, format="JPEG", exif=b"Exif\x00\x00" + b"\x00" * 60_000)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    stamped = add_inline_image_dimensions(f'<img alt="" src="data:image/jpeg;base64,{payload}" />')
    assert stamped.endswith(' width="300" height="200"/>')
