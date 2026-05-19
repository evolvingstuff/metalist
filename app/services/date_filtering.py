from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import json
import re
from typing import Iterable

from app.services.note_store import NoteRecord


DATE_FILTER_CREATED = "created"
DATE_FILTER_UPDATED = "updated"
DATE_FILTER_METRICS = frozenset({DATE_FILTER_CREATED, DATE_FILTER_UPDATED})
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_date_filter(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("dateFilter must be an object or null")

    required_keys = {"metric", "startDate", "endDate"}
    if set(value.keys()) != required_keys:
        raise ValueError("dateFilter must contain exactly metric, startDate, and endDate")

    metric = normalize_date_filter_metric(value["metric"])
    start_date = _normalize_iso_date(value["startDate"], field_name="dateFilter.startDate")
    end_date = _normalize_iso_date(value["endDate"], field_name="dateFilter.endDate")
    if start_date > end_date:
        raise ValueError("dateFilter.startDate must be before or equal to dateFilter.endDate")

    return {
        "metric": metric,
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
    }


def normalize_date_filter_metric(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("date filter metric must be a string")
    normalized = value.strip().lower()
    if normalized not in DATE_FILTER_METRICS:
        raise ValueError(f"unsupported date filter metric: {value!r}")
    return normalized


def date_filter_signature(date_filter: dict[str, str] | None) -> str:
    if date_filter is None:
        return ""
    normalized = normalize_date_filter(date_filter)
    if normalized is None:
        raise RuntimeError("normalize_date_filter returned null for active filter")
    return json.dumps(normalized, separators=(",", ":"), sort_keys=True)


def note_matches_date_filter(record: NoteRecord, date_filter: dict[str, str]) -> bool:
    normalized = normalize_date_filter(date_filter)
    if normalized is None:
        raise RuntimeError("date_filter is required")
    note_date = get_record_local_date(record, normalized["metric"])
    start_date = date.fromisoformat(normalized["startDate"])
    end_date = date.fromisoformat(normalized["endDate"])
    return start_date <= note_date <= end_date


def get_record_local_date(record: NoteRecord, metric: str) -> date:
    normalized_metric = normalize_date_filter_metric(metric)
    if normalized_metric == DATE_FILTER_CREATED:
        timestamp = record.created_at
        field_name = "created_at"
    elif normalized_metric == DATE_FILTER_UPDATED:
        timestamp = record.updated_at
        field_name = "updated_at"
    else:
        raise RuntimeError(f"unsupported normalized metric: {normalized_metric}")
    if not isinstance(timestamp, datetime):
        raise RuntimeError(f"Note {record.id} is missing required {field_name}")
    return timestamp.astimezone().date()


def build_activity_buckets(
    *,
    records: Iterable[NoteRecord],
    metric: str,
    end_date: date | None,
) -> dict[str, object]:
    normalized_metric = normalize_date_filter_metric(metric)
    if end_date is not None and isinstance(end_date, date):
        normalized_end_date = end_date
    elif end_date is not None:
        raise TypeError("end_date must be a date or null")
    else:
        normalized_end_date = None

    counter: Counter[str] = Counter()
    total = 0
    range_start: date | None = None
    range_end: date | None = None
    for record in records:
        note_date = get_record_local_date(record, normalized_metric)
        if normalized_end_date is not None and note_date > normalized_end_date:
            continue
        counter[note_date.isoformat()] += 1
        total += 1
        if range_start is None or note_date < range_start:
            range_start = note_date
        if range_end is None or note_date > range_end:
            range_end = note_date

    if range_start is None or range_end is None:
        if normalized_end_date is not None:
            empty_range_date = normalized_end_date
        else:
            empty_range_date = date.today()
        range_start = empty_range_date
        range_end = empty_range_date

    return {
        "metric": normalized_metric,
        "rangeStart": range_start.isoformat(),
        "rangeEnd": range_end.isoformat(),
        "buckets": dict(sorted(counter.items())),
        "total": total,
    }


def _normalize_iso_date(value: object, *, field_name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date string")
    if _ISO_DATE_RE.match(value) is None:
        raise ValueError(f"{field_name} must use YYYY-MM-DD")
    return date.fromisoformat(value)
