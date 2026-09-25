import pytest

from app.services.public_http import ResolvedPublicHttpTarget
from app.services.public_http import normalize_public_http_url


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        (" HTTPS://Example.COM:443/a?q=1#fragment ", "https://example.com/a?q=1"),
        ("http://example.com:80", "http://example.com"),
        ("https://[2606:2800:220:1:248:1893:25c8:1946]/a", "https://[2606:2800:220:1:248:1893:25c8:1946]/a"),
        ("https://user:secret@example.com/a", None),
        ("file:///private/file", None),
        ("https://example.com:invalid/a", None),
        ("https://[broken/a", None),
    ],
)
def test_normalize_public_http_url_is_conservative(raw_url: str, expected: str | None) -> None:
    assert normalize_public_http_url(raw_url) == expected


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "fe80::1"],
)
def test_resolved_public_target_rejects_non_global_addresses(address: str) -> None:
    with pytest.raises(ValueError, match="not public"):
        ResolvedPublicHttpTarget(
            hostname="example.com",
            port=443,
            public_addresses=(address,),
        )
