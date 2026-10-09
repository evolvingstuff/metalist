"""Checks for the offline search-suggestion experiment (pure parts; no MetaList store needed).

    .venv/bin/python -m pytest -q experiments/search_suggestions/tests
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from experiments.search_suggestions.association import (
    ABSENT,
    CUE_KINDS,
    CueCase,
    TARGET_KINDS,
    build_tag_notes,
    keystrokes_after_cue,
    orderings_after,
    run_cue_test,
    select_cases,
)
from experiments.search_suggestions.completion import (
    PrefixLists,
    keystrokes_to_pick,
    replay,
    window_winners,
)


def _starts_with(tag: str, prefix: str) -> bool:
    return tag.startswith(prefix)


def test_keystrokes_count_letters_arrows_and_enter() -> None:
    shown = {"": ["journal", "papers", "ssm"], "s": ["ssm", "sleep"], "m": [], "ma": ["mamba"]}

    def ranking(prefix: str) -> list[str]:
        if prefix in shown:
            return shown[prefix]
        return []

    assert keystrokes_to_pick(tag="journal", ranking=ranking) == 1      # Enter
    assert keystrokes_to_pick(tag="papers", ranking=ranking) == 2       # down, Enter
    assert keystrokes_to_pick(tag="ssm", ranking=ranking) == 2          # "s", Enter (beats down, down, Enter)
    assert keystrokes_to_pick(tag="mamba", ranking=ranking) == 3        # "ma", Enter
    assert keystrokes_to_pick(tag="zzz", ranking=ranking) == 4          # typed in full, Enter


def test_today_window_picks_take_the_most_used_matching_tag_per_window() -> None:
    lists = PrefixLists(tags_by_note_count=["journal", "papers", "ssm", "sleep"], matches=_starts_with)
    orders = [["ssm", "journal"], ["journal", "ssm"], ["journal", "papers"]]
    assert window_winners(totals_by_window=orders, prefix="", lists=lists) == ["ssm", "journal", "papers"]
    # A window whose only tag was already picked contributes nothing.
    assert window_winners(totals_by_window=orders, prefix="s", lists=lists) == ["ssm"]


def test_the_replay_only_learns_from_earlier_days() -> None:
    lists = PrefixLists(tags_by_note_count=["journal", "mamba"], matches=_starts_with)
    by_day = {date(2026, 1, 1) + timedelta(days=offset): {"journal": 1} for offset in range(40)}
    by_day[date(2026, 2, 15)] = {"mamba": 1}
    costs = replay(by_day=by_day, lists=lists)
    first_mamba = [cost for cost in costs if cost.tag == "mamba"]
    assert len(first_mamba) == 1 and first_mamba[0].prior_uses == 0
    # Never used before that day: every history method still ranks journal first.
    assert first_mamba[0].keystrokes["decay_14d"] == 2


def test_orderings_after_a_common_tag() -> None:
    # 40,000 notes: papers on 500, ssm on 50 (40 of them papers), todo on 8,000 (100 of them papers).
    effective: dict[str, frozenset[str]] = {}
    for index in range(40000):
        tags = set()
        if index < 500:
            tags.add("papers")
        if index < 40 or 500 <= index < 510:
            tags.add("ssm")
        if 400 <= index < 500 or 1000 <= index < 8900:
            tags.add("todo")
        effective[f"n{index}"] = frozenset(tags)
    tag_notes = build_tag_notes(effective)
    after_papers = orderings_after(anchors=("papers",), tag_notes=tag_notes)
    assert after_papers["count"] == ["todo", "ssm"]
    assert after_papers["specificity"][0] == "ssm"
    assert after_papers["balanced"][0] == "ssm"
    lift = (40 / 500) / (50 / 40000)
    assert math.isclose(lift, 64.0)
    after_ssm = orderings_after(anchors=("ssm",), tag_notes=tag_notes)
    assert after_ssm["balanced"][0] == "papers"


def test_cue_cases_offer_each_kind_of_cue_the_note_has() -> None:
    effective = {f"n{index}": frozenset({"journal"}) for index in range(150)}
    for index in range(30):
        effective[f"n{index}"] = frozenset({"journal", "papers"})
    effective["n0"] = frozenset({"journal", "papers", "mamba"})
    effective["n1"] = frozenset({"journal", "papers", "mamba"})
    tag_notes = build_tag_notes(effective)
    cases = select_cases(tag_notes=tag_notes, explicit_tags_by_note={"n0": ("mamba",), "n1": ("mamba",), "n2": ()})
    rare_cases = [case for case in cases if case.target_kind == TARGET_KINDS[0]]
    assert sorted((case.note_id, case.cue_kind, case.anchors) for case in rare_cases) == [
        ("n0", CUE_KINDS[0], ("journal",)), ("n0", CUE_KINDS[1], ("papers",)),
        ("n0", CUE_KINDS[2], ("journal", "papers")),
        ("n1", CUE_KINDS[0], ("journal",)), ("n1", CUE_KINDS[1], ("papers",)),
        ("n1", CUE_KINDS[2], ("journal", "papers")),
    ]
    # journal is on every papers note: adding it would not narrow, so it is no common-target case.
    assert [case for case in cases if case.target_kind == TARGET_KINDS[1]] == []
    two = orderings_after(anchors=("journal", "papers"), tag_notes=tag_notes)
    assert two["count"] == ["mamba"]
    results = run_cue_test(cases=cases, tag_notes=tag_notes, today_after=lambda anchors: ["Mamba"], orderings_by_anchors={})
    assert all(result.positions["today"] == 0 for result in results)
    assert all(result.positions["today+specificity"] == 0 for result in results)
    missing = run_cue_test(cases=cases[:1], tag_notes=tag_notes, today_after=lambda anchors: [], orderings_by_anchors={})
    assert missing[0].positions["today"] == ABSENT


def test_a_common_second_tag_is_a_target_when_it_narrows_the_cue() -> None:
    # papers (30 notes) is the mid-sized cue; todo (120 notes) is on 10 of the papers notes.
    effective = {f"n{index}": frozenset() for index in range(300)}
    for index in range(30):
        effective[f"n{index}"] = frozenset({"papers"})
    for index in range(20, 140):
        effective[f"n{index}"] = effective[f"n{index}"] | {"todo"}
    tag_notes = build_tag_notes(effective)
    cases = select_cases(tag_notes=tag_notes, explicit_tags_by_note={"n25": ("papers", "todo")})
    assert [(case.target_kind, case.anchors, case.rare_tag) for case in cases] == [
        (TARGET_KINDS[1], ("papers",), "todo")]
    results = run_cue_test(cases=cases, tag_notes=tag_notes, today_after=lambda anchors: ["todo"], orderings_by_anchors={})
    assert results[0].positions["count"] == 0


def test_keystrokes_after_a_cue_filter_each_ordering_by_the_letters_typed() -> None:
    case = CueCase(note_id="n", target_kind=TARGET_KINDS[1], cue_kind=CUE_KINDS[1], anchors=("papers",),
                   rare_tag="journal")
    orderings = {"specificity": ["jax", "jamba", "ssm", "journal"], "today": ["journal", "jax"]}
    costs = keystrokes_after_cue(case=case, orderings=orderings, today_typed=lambda anchors, prefix: ["journal"],
                                 matches=_starts_with, list_length=20, memo={})
    assert costs["today"] == 1          # first with nothing typed
    assert costs["specificity"] == 3    # "jo" narrows to journal: two letters, Enter


def test_smoothing_keeps_a_one_off_tag_below_a_real_subtopic() -> None:
    # Under papers (40 notes): typo on 1 note (inside), subtopic ssm on 30 notes (27 inside).
    effective = {f"n{index}": frozenset() for index in range(1000)}
    for index in range(40):
        effective[f"n{index}"] = frozenset({"papers"})
    for index in range(27):
        effective[f"n{index}"] = effective[f"n{index}"] | {"ssm"}
    for index in range(500, 503):
        effective[f"n{index}"] = frozenset({"ssm"})
    effective["n39"] = effective["n39"] | {"mamab"}
    tag_notes = build_tag_notes(effective)
    orderings = orderings_after(anchors=("papers",), tag_notes=tag_notes)
    assert orderings["specificity"][0] == "mamab"
    assert orderings["specificity, smoothed k=2"][0] == "ssm"
