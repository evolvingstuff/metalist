"""Open web pages for the agent: permission checks, fetching, evidence retention."""

from __future__ import annotations

from app.services.agent.web_capabilities import WebUrlCapabilitySet
from app.services.agent.web_evidence import WebEvidenceCapacityError
from app.services.agent.web_evidence import WebPageEvidence
from app.services.agent.web_evidence import web_evidence_store
from app.services.agent.web_fetch import WebPageFetchResult
from app.services.agent.web_fetch import fetch_web_pages
from app.services.agent.web_settings import AgentWebSettings
from app.services.exception_capture import CapturedExceptionContext
from app.services.public_http import normalize_public_http_url


async def open_web_pages(
    *,
    session_key: str,
    web_settings: AgentWebSettings,
    capabilities: WebUrlCapabilitySet,
    urls: list[str],
) -> tuple[list[dict[str, object]], tuple[WebPageEvidence, ...]]:
    """Open pages the settings allow; one result per requested URL, in order.

    Contextual mode allows only addresses already in context, for the requested
    URL and every redirect hop; full mode allows any public page.
    """
    if not web_settings.can_open_pages:
        raise RuntimeError("Web pages may be opened only in contextual or full web mode")

    def allows_target(url: str) -> bool:
        if web_settings.mode == "contextual":
            return capabilities.allows(url)
        return True

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
