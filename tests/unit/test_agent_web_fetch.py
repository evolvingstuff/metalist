from __future__ import annotations

import asyncio
from io import BytesIO
from threading import Barrier, Lock

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject
from pypdf.generic import DictionaryObject
from pypdf.generic import NameObject

from app.services.agent import web_fetch
from app.services.agent.web_fetch import WebPageFetchResult
from app.services.agent.web_fetch import _DownloadedWebResponse
from app.services.agent.web_fetch import _ReadableHtmlParser
from app.services.agent.web_fetch import _extract_web_content
from app.services.agent.web_fetch import fetch_web_page
from app.services.agent.web_fetch import fetch_web_pages
from app.services.public_http import PublicHttpTargetRejected
from app.services.public_http import ResolvedPublicHttpTarget


PUBLIC_TARGET = ResolvedPublicHttpTarget(
    hostname="example.com",
    port=443,
    public_addresses=("93.184.216.34",),
)


def test_html_parser_excludes_page_chrome_and_scripts() -> None:
    parser = _ReadableHtmlParser(base_url="https://example.com/page")
    parser.feed(
        "<html><head><title> Example title </title></head>"
        "<body><header>Navigation</header><main><h1>Heading</h1>"
        "<p>Readable <strong>body</strong>.</p><script>ignore()</script>"
        "<ul><li>First</li><li>Second</li></ul></main></body></html>"
    )
    assert parser.title == "Example title"
    assert "Navigation" not in parser.readable_text
    assert "ignore" not in parser.readable_text
    assert "Heading" in parser.readable_text
    assert "Readable body." in parser.readable_text
    assert "- First" in parser.readable_text


def test_html_parser_exposes_result_links_as_page_evidence() -> None:
    parser = _ReadableHtmlParser(
        base_url="https://www.google.com/search?q=QQQ+price"
    )
    parser.feed(
        '<main><a href="https://finance.example/quote/QQQ">QQQ current price</a>'
        '<a href="/url?q=https%3A%2F%2Fmarkets.example%2FQQQ">Second quote</a></main>'
    )

    assert (
        "QQQ current price (https://finance.example/quote/QQQ)"
        in parser.readable_text
    )
    assert (
        "Second quote "
        "(https://www.google.com/url?q=https%3A%2F%2Fmarkets.example%2FQQQ)"
        in parser.readable_text
    )
    assert parser.outgoing_links == (
        ("QQQ current price", "https://finance.example/quote/QQQ"),
        (
            "Second quote",
            "https://www.google.com/url?q=https%3A%2F%2Fmarkets.example%2FQQQ",
        ),
    )


def test_html_parser_ignores_malformed_external_links() -> None:
    parser = _ReadableHtmlParser(base_url="https://example.com/")
    parser.feed('<main><a href="//[invalid">Broken link</a><p>Still readable</p></main>')

    assert "Broken link" in parser.readable_text
    assert "Still readable" in parser.readable_text


def test_extraction_tolerates_malformed_html_and_plain_text() -> None:
    html_title, html_text, html_links, html_truncated, html_error = _extract_web_content(
        content=b"<title>Broken</title><main><p>Still <b>readable<script>hidden",
        content_type="text/html",
        encoding="utf-8",
        base_url="https://example.com/",
    )
    assert html_title == "Broken"
    assert html_text == "Still readable"
    assert html_links == ()
    assert html_truncated is False
    assert html_error == ""

    plain_title, plain_text, plain_links, plain_truncated, plain_error = _extract_web_content(
        content=b"First line\r\n\r\n  Second   line  ",
        content_type="text/plain",
        encoding="utf-8",
        base_url="https://example.com/",
    )
    assert plain_title == ""
    assert plain_text == "First line\n\nSecond line"
    assert plain_links == ()
    assert plain_truncated is False
    assert plain_error == ""

    _title, fallback_text, fallback_links, _truncated, fallback_error = _extract_web_content(
        content="Café".encode(),
        content_type="text/plain",
        encoding="not-a-real-encoding",
        base_url="https://example.com/",
    )
    assert fallback_text == "Café"
    assert fallback_links == ()
    assert fallback_error == ""


def test_pdf_extraction_reads_text_and_rejects_malformed_documents() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )
    content_stream = DecodedStreamObject()
    content_stream.set_data(b"BT /F1 12 Tf 72 200 Td (Hello web PDF) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content_stream)
    writer.add_metadata({"/Title": "PDF title"})
    output = BytesIO()
    writer.write(output)

    title, text, links, truncated, error = _extract_web_content(
        content=output.getvalue(),
        content_type="application/pdf",
        encoding="",
        base_url="https://example.com/report.pdf",
    )
    assert title == "PDF title"
    assert text == "Hello web PDF"
    assert links == ()
    assert truncated is False
    assert error == ""

    malformed = _extract_web_content(
        content=b"%PDF-1.7 definitely not a complete PDF",
        content_type="application/pdf",
        encoding="",
        base_url="https://example.com/report.pdf",
    )
    assert malformed == ("", "", (), False, "malformed_pdf")


def test_fetch_web_page_resolves_every_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved: list[str] = []
    downloaded: list[str] = []

    def resolve(url: str) -> ResolvedPublicHttpTarget:
        resolved.append(url)
        return PUBLIC_TARGET

    def download(url: str, target: ResolvedPublicHttpTarget) -> _DownloadedWebResponse:
        assert target == PUBLIC_TARGET
        downloaded.append(url)
        if len(downloaded) == 1:
            return _DownloadedWebResponse(
                kind="redirect",
                final_url="https://example.com/final",
                content=b"",
                content_type="",
                encoding="",
                truncated=False,
                error_kind="",
            )
        return _DownloadedWebResponse(
            kind="content",
            final_url=url,
            content=b"<title>Final</title><main>Readable final page</main>",
            content_type="text/html",
            encoding="utf-8",
            truncated=False,
            error_kind="",
        )

    monkeypatch.setattr(web_fetch, "resolve_public_http_target", resolve)
    monkeypatch.setattr(web_fetch, "_download_one_url", download)

    result = fetch_web_page("https://example.com/start")

    assert resolved == ["https://example.com/start", "https://example.com/final"]
    assert downloaded == resolved
    assert result.status == "ok"
    assert result.final_url == "https://example.com/final"
    assert result.title == "Final"
    assert result.content_text == "Readable final page"


def test_fetch_web_page_blocks_private_resolution_before_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject(_url: str) -> ResolvedPublicHttpTarget:
        raise PublicHttpTargetRejected("blocked_private_address")

    monkeypatch.setattr(web_fetch, "resolve_public_http_target", reject)
    monkeypatch.setattr(
        web_fetch,
        "_download_one_url",
        lambda _url, _target: pytest.fail("blocked target reached downloader"),
    )

    result = fetch_web_page("https://private.example/")

    assert result.status == "blocked"
    assert result.error_kind == "blocked_private_address"


def test_batch_deduplicates_fetch_and_preserves_submitted_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_fetch(url: str) -> WebPageFetchResult:
        calls.append(url)
        return WebPageFetchResult(
            requested_url=url,
            final_url=url,
            status="ok",
            title=url.rsplit("/", 1)[-1],
            content_text=f"Content for {url}",
            outgoing_links=(),
            fetched_at="2026-09-24T00:00:00+00:00",
            truncated=False,
            error_kind="",
        )

    monkeypatch.setattr(web_fetch, "fetch_web_page", fake_fetch)
    results = asyncio.run(
        fetch_web_pages(
            [
                "https://example.com/a#one",
                "https://example.com/b",
                "https://EXAMPLE.com/a#two",
            ]
        )
    )

    assert calls == ["https://example.com/a", "https://example.com/b"]
    assert [result.final_url for result in results] == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/a",
    ]
    assert results[0] is results[2]


def test_batch_reports_invalid_url_without_losing_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_fetch,
        "fetch_web_page",
        lambda url: WebPageFetchResult(
            requested_url=url,
            final_url=url,
            status="ok",
            title="Good",
            content_text="Readable",
            outgoing_links=(),
            fetched_at="2026-09-24T00:00:00+00:00",
            truncated=False,
            error_kind="",
        ),
    )
    results = asyncio.run(fetch_web_pages(["file:///secret", "https://example.com/"]))
    assert results[0].status == "blocked"
    assert results[0].error_kind == "unsupported_scheme_or_url"
    assert results[1].status == "ok"


def test_batch_fetches_concurrently_with_a_four_request_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    maximum_active = 0
    lock = Lock()
    four_workers_started = Barrier(web_fetch.MAX_WEB_FETCH_CONCURRENCY)

    def fake_fetch(url: str) -> WebPageFetchResult:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            four_workers_started.wait(timeout=3)
            return WebPageFetchResult(
                requested_url=url,
                final_url=url,
                status="ok",
                title=url,
                content_text="Readable",
                outgoing_links=(),
                fetched_at="2026-09-24T00:00:00+00:00",
                truncated=False,
                error_kind="",
            )
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(web_fetch, "fetch_web_page", fake_fetch)
    urls = [f"https://example.com/{index}" for index in range(8)]

    results = asyncio.run(fetch_web_pages(urls))

    assert len(results) == 8
    assert maximum_active == web_fetch.MAX_WEB_FETCH_CONCURRENCY == 4


def test_batch_rejects_more_than_eight_urls() -> None:
    with pytest.raises(ValueError, match="1–8 URLs"):
        asyncio.run(fetch_web_pages(["https://example.com"] * 9))
