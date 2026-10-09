"""Completion: how many keystrokes it takes to pick a tag you used, replaying your daily history.

For each day D the rankings see only the days before D. For every tag used on D
we find the cheapest way to pick it: type k letters of its name, press the
down arrow until it is selected, press Enter. Cost = k + position + 1, so the
first suggestion with an empty bar costs 1. A tag never in the 20 shown for
any prefix up to its full name costs its length + 1 (typed in full).

The history only says which tags were used each day (searched, picked, or on
notes worked on), not what was typed into the search bar, so this approximates
what you looked for that day.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

LIST_LENGTH = 20
MAX_TYPED_LETTERS = 8
# Days of history every ranking gets before a day is scored.
WARMUP_DAYS = 30
TODAY_WINDOWS = (1, 7, 30)
DECAY_HALF_LIVES = (3, 14, 60)


@dataclass(frozen=True)
class DayRankings:
    """Each method's ordering for one day, as a function from typed prefix to the 20 shown."""

    day: date
    lists: dict[str, Callable[[str], list[str]]]


class PrefixLists:
    """Shared, cached pieces: which tags match a prefix, and the note-count order (today's base list)."""

    def __init__(self, *, tags_by_note_count: list[str], matches: Callable[[str, str], bool]) -> None:
        self.tags_by_note_count = tags_by_note_count
        self._matches = matches
        self._match_cache: dict[tuple[str, str], bool] = {}
        self._base_cache: dict[str, list[str]] = {}

    def matches(self, tag: str, prefix: str) -> bool:
        key = (tag, prefix)
        if key not in self._match_cache:
            self._match_cache[key] = self._matches(tag, prefix)
        return self._match_cache[key]

    def base(self, prefix: str) -> list[str]:
        """Today's base list: matching tags by note count, the first LIST_LENGTH."""
        if prefix not in self._base_cache:
            found: list[str] = []
            for tag in self.tags_by_note_count:
                if self.matches(tag, prefix):
                    found.append(tag)
                    if len(found) == LIST_LENGTH:
                        break
            self._base_cache[prefix] = found
        return self._base_cache[prefix]

    def scored(self, *, ordered_scored: list[str], prefix: str, exclude: set[str]) -> list[str]:
        """Matching tags with a positive score in score order, then the base list for the rest."""
        shown: list[str] = []
        for tag in ordered_scored:
            if tag not in exclude and self.matches(tag, prefix):
                shown.append(tag)
                if len(shown) == LIST_LENGTH:
                    return shown
        taken = set(shown)
        for tag in self.base(prefix):
            if tag not in taken and tag not in exclude:
                shown.append(tag)
                if len(shown) == LIST_LENGTH:
                    break
        return shown


def window_winners(*, totals_by_window: list[list[str]], prefix: str, lists: PrefixLists) -> list[str]:
    """Today's personalization: per window, the most-used matching tag not already picked.

    `totals_by_window[i]` holds the tags used in window i, most used first (ties in
    note-count order), exactly as rank_tag_activity_window_selections orders them.
    """
    winners: list[str] = []
    for ordered in totals_by_window:
        for tag in ordered:
            if tag not in winners and lists.matches(tag, prefix):
                winners.append(tag)
                break
    return winners


def keystrokes_to_pick(*, tag: str, ranking: Callable[[str], list[str]]) -> int:
    """The cheapest of: type k letters, arrow down to the tag, Enter; or type it in full and Enter."""
    cheapest = len(tag) + 1
    for typed in range(0, min(len(tag), MAX_TYPED_LETTERS) + 1):
        if typed >= cheapest:
            break
        shown = ranking(tag[:typed])
        if tag in shown:
            cheapest = min(cheapest, typed + shown.index(tag) + 1)
    return cheapest


def daily_counts_by_day(counts_by_date: dict[str, dict[str, int]], known: dict[str, str]) -> dict[date, dict[str, int]]:
    """History keyed by day, tags mapped to the spelling the search index uses (unknown tags dropped)."""
    by_day: dict[date, dict[str, int]] = {}
    for day_text, counts in counts_by_date.items():
        day_counts: dict[str, int] = {}
        for tag, count in counts.items():
            if tag.casefold() not in known:
                continue
            spelled = known[tag.casefold()]
            if spelled not in day_counts:
                day_counts[spelled] = 0
            day_counts[spelled] += count
        by_day[date.fromisoformat(day_text)] = day_counts
    return by_day


def calendar_days(first: date, last: date) -> list[date]:
    assert first <= last
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


@dataclass(frozen=True)
class PickCost:
    tag: str
    # Times the tag was used before that day (how rare it was then).
    prior_uses: int
    keystrokes: dict[str, int]


METHOD_NAMES = ("today", "note_count", "all_time") + tuple(f"decay_{days}d" for days in DECAY_HALF_LIVES)


def replay(*, by_day: dict[date, dict[str, int]], lists: PrefixLists) -> list[PickCost]:
    """Score every day after the warm-up; each day sees only the days before it."""
    assert by_day, "no tag history to replay"
    note_rank = {tag: rank for rank, tag in enumerate(lists.tags_by_note_count)}
    days = calendar_days(min(by_day), max(by_day))
    all_time: Counter[str] = Counter()
    decayed: dict[int, dict[str, float]] = {half_life: {} for half_life in DECAY_HALF_LIVES}
    costs: list[PickCost] = []
    for index, day in enumerate(days):
        if index >= WARMUP_DAYS and day in by_day and by_day[day]:
            rankings = _rankings_for_day(day=day, by_day=by_day, lists=lists, note_rank=note_rank,
                                         all_time=all_time, decayed=decayed)
            for tag in sorted(by_day[day]):
                costs.append(PickCost(tag=tag, prior_uses=all_time[tag], keystrokes={
                    name: keystrokes_to_pick(tag=tag, ranking=ranking) for name, ranking in rankings.items()}))
        todays: dict[str, int] = {}
        if day in by_day:
            todays = by_day[day]
        all_time.update(todays)
        for half_life, scores in decayed.items():
            factor = 0.5 ** (1.0 / half_life)
            for tag in scores:
                scores[tag] *= factor
            for tag, count in todays.items():
                if tag not in scores:
                    scores[tag] = 0.0
                scores[tag] += count
    return costs


def window_orders(*, day: date, by_day: dict[date, dict[str, int]], note_rank: dict[str, int]) -> list[list[str]]:
    """For each of today's windows ending the day before `day`: tags used, most used first."""
    orders: list[list[str]] = []
    for window in TODAY_WINDOWS:
        totals: Counter[str] = Counter()
        for back in range(1, window + 1):
            earlier = day - timedelta(days=back)
            if earlier in by_day:
                totals.update(by_day[earlier])
        orders.append(_by_score(dict(totals), note_rank))
    return orders


def _by_score(scores: dict[str, float], note_rank: dict[str, int]) -> list[str]:
    return sorted((tag for tag, score in scores.items() if score > 0), key=lambda tag: (-scores[tag], note_rank[tag]))


def _rankings_for_day(*, day: date, by_day: dict[date, dict[str, int]], lists: PrefixLists,
                      note_rank: dict[str, int], all_time: Counter[str],
                      decayed: dict[int, dict[str, float]]) -> dict[str, Callable[[str], list[str]]]:
    totals_by_window = window_orders(day=day, by_day=by_day, note_rank=note_rank)

    def today(prefix: str) -> list[str]:
        winners = window_winners(totals_by_window=totals_by_window, prefix=prefix, lists=lists)
        return (winners + [tag for tag in lists.base(prefix) if tag not in winners])[:LIST_LENGTH]

    rankings: dict[str, Callable[[str], list[str]]] = {"today": today, "note_count": lists.base}
    by_all_time = _by_score(dict(all_time), note_rank)
    rankings["all_time"] = lambda prefix: lists.scored(ordered_scored=by_all_time, prefix=prefix, exclude=set())
    for half_life, scores in decayed.items():
        ordered = _by_score(scores, note_rank)
        rankings[f"decay_{half_life}d"] = (
            lambda prefix, ordered=ordered: lists.scored(ordered_scored=ordered, prefix=prefix, exclude=set()))
    return rankings
