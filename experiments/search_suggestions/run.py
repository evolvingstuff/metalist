"""Run both search-suggestion tests on a loaded namespace and print totals only.

Imported only after __main__ has pointed MetaList's settings at the scratch copy.
Nothing printed names a tag or note: only counts, shares and keystrokes.
"""

from __future__ import annotations

import random
import time
from collections import Counter
from datetime import date, timedelta

from app.models.database import SafeSession
from app.services.note_store import store
from app.services.search_history import rank_tag_activity_window_selections, search_history_store
from app.services.search_index import search_index
from app.services.tag_term_matching import tag_term_matches_prefix

from experiments.search_suggestions.association import (
    CUE_KINDS,
    ORDERING_NAMES,
    TARGET_KINDS,
    CueResult,
    build_tag_notes,
    keystrokes_after_cue,
    run_cue_test,
    select_cases,
)
from experiments.search_suggestions.completion import (
    LIST_LENGTH,
    METHOD_NAMES,
    TODAY_WINDOWS,
    PrefixLists,
    daily_counts_by_day,
    replay,
    window_orders,
    window_winners,
)

# Days on which the replay's window picks are compared with MetaList's own function.
WINDOW_CHECK_DAYS = 20
from experiments.tag_suggestions.corpus import Corpus


def load_tag_history() -> dict[str, dict[str, int]]:
    """The namespace's daily tag activity, decrypted with the session key already set."""
    session = SafeSession()
    with SafeSession.allow_reads("experiment:search-history"):
        search_history_store.bootstrap(connection=session.connection())
    search_history_store.ensure_decrypted(token="")
    return search_history_store.copy_daily_counts(token="")


def run(*, corpus: Corpus, counts_by_date: dict[str, dict[str, int]]) -> None:
    """Both tests against MetaList's store and search index as currently loaded."""
    tags_by_note_count = [tag for tag in search_index.suggest_all_tag_completions(query="")
                          if not tag.startswith("@")]
    lists = PrefixLists(tags_by_note_count=tags_by_note_count,
                        matches=lambda tag, prefix: tag_term_matches_prefix(term=tag, prefix=prefix))
    _check_base_lists(lists)
    print(f"Notes: {len(corpus.notes)}, tags in search: {len(tags_by_note_count)}, "
          f"days of tag history: {len(counts_by_date)}")
    _completion(lists=lists, counts_by_date=counts_by_date)
    _association(corpus=corpus, spelling={tag.casefold(): tag for tag in tags_by_note_count})


def _check_base_lists(lists: PrefixLists) -> None:
    """The cached base list must equal MetaList's own list for a first prefix (no history applied)."""
    for prefix in ("", "a", "m", "s", "j", "ma", "pro"):
        own = [tag for tag in search_index.suggest_all_tag_completions(query=prefix) if not tag.startswith("@")]
        assert lists.base(prefix) == own[:LIST_LENGTH], f"base list differs for a {len(prefix)}-letter prefix"


def _completion(*, lists: PrefixLists, counts_by_date: dict[str, dict[str, int]]) -> None:
    print("\n=== Completion: keystrokes to pick each tag you used, replaying your daily history ===")
    if not counts_by_date:
        print("No tag history recorded: skipped.")
        return
    started = time.perf_counter()
    by_day = daily_counts_by_day(counts_by_date, {tag.casefold(): tag for tag in lists.tags_by_note_count})
    _check_window_picks(by_day=by_day, lists=lists)
    costs = replay(by_day=by_day, lists=lists)
    print(f"Tag uses scored: {len(costs)} from {len(by_day)} days of history "
          f"({time.perf_counter() - started:.0f}s)")
    if not costs:
        print("Not enough history after the 30-day warm-up.")
        return
    buckets = [("all", lambda cost: True), ("used 21+ times before", lambda cost: cost.prior_uses >= 21),
               ("4-20 times", lambda cost: 4 <= cost.prior_uses <= 20),
               ("1-3 times", lambda cost: 1 <= cost.prior_uses <= 3), ("never before", lambda cost: cost.prior_uses == 0)]
    print(f"  {'tags':24s} {'method':12s} {'keystrokes':>10s} {'first, empty bar':>17s} {'<=2 keys':>9s} {'n':>6s}")
    for label, keep in buckets:
        chosen = [cost for cost in costs if keep(cost)]
        if not chosen:
            continue
        for name in METHOD_NAMES:
            strokes = [cost.keystrokes[name] for cost in chosen]
            print(f"  {label:24s} {name:12s} {sum(strokes) / len(strokes):10.2f} "
                  f"{sum(1 for value in strokes if value == 1) / len(strokes):17.1%} "
                  f"{sum(1 for value in strokes if value <= 2) / len(strokes):9.1%} {len(strokes):6d}")


def _check_window_picks(*, by_day: dict[date, dict[str, int]], lists: PrefixLists) -> None:
    """The replay's window picks must equal MetaList's own rank_tag_activity_window_selections."""
    note_rank = {tag: rank for rank, tag in enumerate(lists.tags_by_note_count)}
    days = sorted(by_day)
    for day in days[len(days) // 2:][:WINDOW_CHECK_DAYS]:
        orders = window_orders(day=day, by_day=by_day, note_rank=note_rank)
        recent = {earlier.isoformat(): counts for earlier, counts in by_day.items()
                  if day - timedelta(days=max(TODAY_WINDOWS)) <= earlier < day and counts}
        for prefix in ("", "a", "m", "s"):
            candidates = [tag for tag in lists.tags_by_note_count if lists.matches(tag, prefix)]
            own = rank_tag_activity_window_selections(counts_by_date=recent, candidate_tags=candidates,
                                                      window_days=TODAY_WINDOWS, today=day - timedelta(days=1))
            mine = window_winners(totals_by_window=orders, prefix=prefix, lists=lists)
            assert [selection.tag for selection in own] == mine, "replay window picks differ from MetaList's"


def _association(*, corpus: Corpus, spelling: dict[str, str]) -> None:
    print("\n=== Association: after a common tag on a note, where does its rare tag land? ===")
    started = time.perf_counter()
    effective = {note_id: frozenset(search_index.list_effective_tag_terms_for_note(note_id))
                 for note_id in store.list_note_ids()}
    tag_notes = build_tag_notes(effective)
    cases = select_cases(tag_notes=tag_notes,
                         explicit_tags_by_note={note_id: note.explicit_tags for note_id, note in corpus.notes.items()})
    if not cases:
        print("No notes with both a rare tag (2-20 notes) and a common tag (100+ notes): skipped.")
        return

    def today_after(anchors: tuple[str, ...]) -> list[str]:
        return search_index.suggest_all_tag_completions(query=" ".join(spelling[anchor] for anchor in anchors) + " ")

    orderings_by_anchors: dict[tuple[str, ...], dict[str, list[str]]] = {}
    results = run_cue_test(cases=cases, tag_notes=tag_notes, today_after=today_after,
                           orderings_by_anchors=orderings_by_anchors)
    print(f"({time.perf_counter() - started:.0f}s)")
    for target_kind in TARGET_KINDS:
        for kind in CUE_KINDS:
            chosen = [result for result in results
                      if result.case.cue_kind == kind and result.case.target_kind == target_kind]
            if not chosen:
                continue
            print(f"\nLooking for a {target_kind}, cue: {kind}: {len(chosen)} cases, "
                  f"{len({result.case.anchors for result in chosen})} different cues")
            print(f"  {'ordering':28s} {'top 5':>7s} {'top 10':>7s} {'top 20':>7s} {'MRR':>6s}")
            for name in ORDERING_NAMES:
                _print_cue_row(name, chosen)
    _keystrokes_after_mid_cue(results=results, orderings_by_anchors=orderings_by_anchors, spelling=spelling)


def _keystrokes_after_mid_cue(*, results: list[CueResult],
                              orderings_by_anchors: dict[tuple[str, ...], dict[str, list[str]]],
                              spelling: dict[str, str]) -> None:
    """After a mid-sized cue, keystrokes to pick the target when letters may be typed."""
    started = time.perf_counter()

    def today_typed(anchors: tuple[str, ...], prefix: str) -> list[str]:
        return search_index.suggest_all_tag_completions(
            query=" ".join(spelling[anchor] for anchor in anchors) + " " + prefix)

    memo: dict[tuple[tuple[str, ...], str, str], list[str]] = {}
    match_memo: dict[tuple[str, str], bool] = {}

    def matches(tag: str, prefix: str) -> bool:
        if (tag, prefix) not in match_memo:
            match_memo[(tag, prefix)] = tag_term_matches_prefix(term=tag, prefix=prefix)
        return match_memo[(tag, prefix)]

    print("\n=== Keystrokes to pick the target after the first tag (letters typed narrow each ordering) ===")
    for target_kind, cue_kind in ((TARGET_KINDS[0], CUE_KINDS[1]), (TARGET_KINDS[1], CUE_KINDS[1]),
                                  (TARGET_KINDS[1], CUE_KINDS[0])):
        chosen = [result for result in results
                  if result.case.cue_kind == cue_kind and result.case.target_kind == target_kind]
        if not chosen:
            continue
        costs = [keystrokes_after_cue(case=result.case, orderings=orderings_by_anchors[result.case.anchors],
                                      today_typed=today_typed, matches=matches, list_length=LIST_LENGTH, memo=memo)
                 for result in chosen]
        print(f"\nLooking for a {target_kind}, cue: {cue_kind}: {len(chosen)} cases")
        print(f"  {'ordering':28s} {'keystrokes':>10s} {'Enter only':>11s} {'<=2 keys':>9s}")
        for name in ORDERING_NAMES:
            values = [cost[name] for cost in costs]
            print(f"  {name:28s} {sum(values) / len(values):10.2f} "
                  f"{sum(1 for value in values if value == 1) / len(values):11.1%} "
                  f"{sum(1 for value in values if value <= 2) / len(values):9.1%}")
    print(f"({time.perf_counter() - started:.0f}s)")


def _print_cue_row(name: str, results: list[CueResult]) -> None:
    positions = [result.positions[name] for result in results]
    count = len(positions)
    reciprocal = sum(1.0 / (position + 1) for position in positions if position < LIST_LENGTH) / count
    print(f"  {name:28s} {sum(1 for p in positions if p < 5) / count:7.1%} "
          f"{sum(1 for p in positions if p < 10) / count:7.1%} {sum(1 for p in positions if p < 20) / count:7.1%} "
          f"{reciprocal:6.3f}")


def synthetic_history(*, corpus: Corpus, seed: int) -> dict[str, dict[str, int]]:
    """A plausible history for the synthetic namespace: tags credited on creation days and on revisits."""
    rng = random.Random(seed)
    counts: dict[str, Counter[str]] = {}
    for note in sorted(corpus.notes.values(), key=lambda note_: note_.created_at):
        visits = [note.created_at.date()]
        for _revisit in range(rng.randrange(3)):
            visits.append(note.created_at.date() + timedelta(days=rng.randrange(1, 60)))
        for day in visits:
            key = day.isoformat()
            if key not in counts:
                counts[key] = Counter()
            counts[key].update(note.explicit_tags)
    return {day: dict(tags) for day, tags in counts.items() if tags}
