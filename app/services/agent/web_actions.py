"""Open web pages for the agent: permission checks, fetching, evidence retention."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote_plus, urlsplit

from app.services.agent.web_capabilities import WebUrlCapabilitySet
from app.services.agent.web_evidence import WebEvidenceCapacityError
from app.services.agent.web_evidence import WebPageEvidence
from app.services.agent.web_evidence import web_evidence_store
from app.services.agent.web_fetch import WebPageFetchResult
from app.services.agent.web_fetch import fetch_web_pages
from app.services.agent.web_settings import AgentWebSettings
from app.services.exception_capture import CapturedExceptionContext
from app.services.public_http import normalize_public_http_url


_ADDRESS_WORD_RE = re.compile(r"[a-z0-9]+")
# Pieces of address syntax that say nothing about the user's notes.
_ADDRESS_SYNTAX_WORDS = frozenset({"http", "https", "www", "com", "org", "net", "html", "htm", "php"})
# Google Search and Google Finance only send the words to Google itself, never to
# a site that could collect them, so they never need the user's confirmation.
_GOOGLE_HOSTS = frozenset({"google.com", "www.google.com"})


def _address_words(text: str) -> frozenset[str]:
    return frozenset(_ADDRESS_WORD_RE.findall(unquote_plus(text).lower()))


def _is_google_search_or_quote(normalized_url: str) -> bool:
    parts = urlsplit(normalized_url)
    if parts.hostname not in _GOOGLE_HOSTS:
        return False
    if parts.path == "/search":
        return True
    return parts.path.startswith("/finance/")


@dataclass(frozen=True, slots=True)
class NoteTextGuard:
    """Full web mode: keeps text from the user's notes from leaving in a web address.

    A prompt-injected page could ask the model to open an address that carries note
    text to another site. An address needs the user's Yes when it contains a word from
    the notes shown to the model that the user did not type and that was not already
    part of an address the model saw. Google Search and Google Finance are exempt.
    The same check applies to every redirect hop.
    """

    private_words: frozenset[str]
    approved_urls: frozenset[str]

    @classmethod
    def build(
        cls, *, note_text: str, typed_text: str, known_urls: frozenset[str], approved_urls: frozenset[str],
    ) -> NoteTextGuard:
        assert isinstance(note_text, str) and isinstance(typed_text, str)
        assert isinstance(known_urls, frozenset) and isinstance(approved_urls, frozenset)
        shared_words = _address_words(typed_text) | _ADDRESS_SYNTAX_WORDS
        for known_url in known_urls:
            shared_words |= _address_words(known_url)
        return cls(private_words=_address_words(note_text) - shared_words, approved_urls=approved_urls)

    def needs_confirmation(self, normalized_url: str) -> bool:
        assert normalize_public_http_url(normalized_url) == normalized_url
        if normalized_url in self.approved_urls or _is_google_search_or_quote(normalized_url):
            return False
        parts = urlsplit(normalized_url)
        address_text = " ".join((parts.netloc, parts.path, parts.query, parts.fragment))
        return bool(_address_words(address_text) & self.private_words)

    def allows(self, url: str) -> bool:
        normalized = normalize_public_http_url(url)
        return normalized is not None and not self.needs_confirmation(normalized)

    def addresses_needing_confirmation(self, urls: list[str]) -> tuple[str, ...]:
        """Normalized addresses in order, each once; invalid ones are left to the opener."""
        needing: list[str] = []
        for url in urls:
            normalized = normalize_public_http_url(url)
            if normalized is not None and normalized not in needing and self.needs_confirmation(normalized):
                needing.append(normalized)
        return tuple(needing)


async def open_web_pages(
    *,
    session_key: str,
    web_settings: AgentWebSettings,
    capabilities: WebUrlCapabilitySet,
    note_text_guard: NoteTextGuard,
    urls: list[str],
) -> tuple[list[dict[str, object]], tuple[WebPageEvidence, ...]]:
    """Open pages the settings allow; one result per requested URL, in order.

    Contextual mode allows only addresses already in context; full mode allows any
    public page whose address carries no unconfirmed note text. Both checks apply
    to the requested URL and every redirect hop.
    """
    if not web_settings.can_open_pages:
        raise RuntimeError("Web pages may be opened only in contextual or full web mode")

    def allows_target(url: str) -> bool:
        if web_settings.mode == "contextual":
            return capabilities.allows(url)
        return note_text_guard.allows(url)

    pending_urls: list[str] = []
    pending_indexes: list[int] = []
    cached_by_index: dict[int, WebPageEvidence] = {}
    blocked_indexes: set[int] = set()
    for index, url in enumerate(urls):
        normalized = normalize_public_http_url(url)
        if normalized is None:
            blocked_indexes.add(index)
            continue
        if not allows_target(normalized):
            blocked_indexes.add(index)
            continue
        cached = web_evidence_store.find_by_url(
            session_key=session_key,
            url=normalized,
        )
        if cached is not None:
            cached_by_index[index] = cached
        else:
            pending_urls.append(normalized)
            pending_indexes.append(index)
    fetched_results: tuple[WebPageFetchResult, ...] = ()
    if pending_urls:
        fetched_results = await fetch_web_pages(pending_urls, allows_target=allows_target)
    fetched_by_index = dict(zip(pending_indexes, fetched_results, strict=True))
    payload: list[dict[str, object]] = []
    evidence_items: list[WebPageEvidence] = []
    for index, url in enumerate(urls):
        if index in blocked_indexes:
            payload.append({
                "requested_url": url,
                "status": "blocked",
                "error_kind": "not_available_in_permitted_context",
                "cached": False,
                "truncated": False,
            })
            continue
        if index in cached_by_index:
            evidence = cached_by_index[index]
            status = "ok"
            error_kind = ""
            was_cached = True
        else:
            fetched = fetched_by_index[index]
            status = fetched.status
            error_kind = fetched.error_kind
            was_cached = False
            if fetched.status != "ok":
                payload.append({
                    "requested_url": fetched.requested_url,
                    "final_url": fetched.final_url,
                    "status": fetched.status,
                    "error_kind": fetched.error_kind,
                    "cached": False,
                    "truncated": fetched.truncated,
                })
                continue
            evidence_capacity_capture = CapturedExceptionContext(
                WebEvidenceCapacityError,
                boundary='app/services/agent/web_actions.py:open_web_pages:evidence_capacity_capture',
            )
            evidence = None
            with evidence_capacity_capture:
                evidence = web_evidence_store.retain_success(
                    session_key=session_key,
                    result=fetched,
                )
            if evidence_capacity_capture.captured_exception is not None:
                payload.append({
                    "requested_url": fetched.requested_url,
                    "final_url": fetched.final_url,
                    "status": "failed",
                    "error_kind": "evidence_capacity",
                    "cached": False,
                    "truncated": fetched.truncated,
                })
                continue
            if evidence is None:
                raise RuntimeError("Web evidence retention returned no result")
        evidence_items.append(evidence)
        payload.append({
            **evidence.as_model_payload(),
            "status": status,
            "error_kind": error_kind,
            "cached": was_cached,
        })
    return payload, tuple(evidence_items)
