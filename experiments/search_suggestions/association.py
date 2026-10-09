"""Association: after a common tag, does a forgotten rare tag on the note you want come up?

Cue test: for a note carrying a rare tag, pretend the search starts from a
common tag that is also on it (the kind you remember). Each ordering ranks the
tags that still leave results after that first tag; we check where the rare
tag lands. The note already exists, so nothing is hidden: this is re-finding.

Orderings after first tag c, for a candidate t (P = share of notes):
  count            notes with both c and t (today's main key)
  specificity      P(t | c) / P(t)  ("lift": how much more common under c)
  balanced         P(t | c) * ln(lift)
  smoothed k       notes with both / (t's notes + k): specificity with k pretend notes outside c,
                   so a one-off tag cannot outrank a real subtopic
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from experiments.search_suggestions.completion import keystrokes_to_pick

RARE_MIN_NOTES = 2
RARE_MAX_NOTES = 20
MID_MIN_NOTES = 21
COMMON_MIN_NOTES = 100
MAX_CASES = 1500
SAMPLE_SEED = 5

# What you might remember about the note: its broadest tag, a mid-sized tag, or its two broadest tags.
CUE_KINDS = ("broad tag (100+ notes)", "mid-sized tag (21-100 notes)", "two tags together (21+ notes each)")

# Smoothed specificity pretends every tag has k extra notes outside the first tag(s):
# share = notes with both / (tag's notes + k). k = 2 is the version decided on; 1 and 5
# only show whether the result depends on the exact value.
SMOOTHING_NOTES = (1, 2, 5)
ORDERING_NAMES = ("today", "count", "specificity") + tuple(
    f"specificity, smoothed k={k}" for k in SMOOTHING_NOTES) + ("balanced", "today+specificity")
TARGET_KINDS = ("rare tag (2-20 notes)", "common tag (100+ notes)")
# Reciprocal rank fusion constant.
FUSION_K = 60


@dataclass(frozen=True)
class CueCase:
    note_id: str
    target_kind: str
    cue_kind: str
    # The tag or tags typed first; the rare tag is looked for in the list after them.
    anchors: tuple[str, ...]
    rare_tag: str


@dataclass(frozen=True)
class TagNotes:
    """Effective (search) tags: tag -> notes, casefolded, meta tags left out."""

    notes_by_tag: dict[str, frozenset[str]]
    tags_by_note: dict[str, frozenset[str]]
    total_notes: int


def build_tag_notes(effective_tags_by_note: dict[str, frozenset[str]]) -> TagNotes:
    lists: dict[str, list[str]] = {}
    tags_by_note: dict[str, frozenset[str]] = {}
    for note_id, tags in effective_tags_by_note.items():
        kept = frozenset(tag.casefold() for tag in tags if not tag.startswith("@"))
        tags_by_note[note_id] = kept
        for tag in kept:
            if tag not in lists:
                lists[tag] = []
            lists[tag].append(note_id)
    return TagNotes(notes_by_tag={tag: frozenset(ids) for tag, ids in lists.items()},
                    tags_by_note=tags_by_note, total_notes=len(effective_tags_by_note))


def select_cases(*, tag_notes: TagNotes, explicit_tags_by_note: dict[str, tuple[str, ...]]) -> list[CueCase]:
    """For notes with an explicit rare tag: one case per kind of cue the note offers, up to MAX_CASES each."""
    by_kind: dict[tuple[str, str], list[CueCase]] = {(TARGET_KINDS[0], kind): [] for kind in CUE_KINDS}
    by_kind[(TARGET_KINDS[1], CUE_KINDS[1])] = []
    by_kind[(TARGET_KINDS[1], CUE_KINDS[0])] = []
    for note_id in sorted(explicit_tags_by_note):
        effective = tag_notes.tags_by_note[note_id]
        rare = sorted(tag.casefold() for tag in explicit_tags_by_note[note_id]
                      if tag.casefold() in tag_notes.notes_by_tag
                      and RARE_MIN_NOTES <= len(tag_notes.notes_by_tag[tag.casefold()]) <= RARE_MAX_NOTES)
        by_size = sorted(effective, key=lambda tag: (-len(tag_notes.notes_by_tag[tag]), tag))
        broad = [tag for tag in by_size if len(tag_notes.notes_by_tag[tag]) >= COMMON_MIN_NOTES]
        mid = [tag for tag in by_size if MID_MIN_NOTES <= len(tag_notes.notes_by_tag[tag]) < COMMON_MIN_NOTES]
        usable = [tag for tag in by_size if len(tag_notes.notes_by_tag[tag]) >= MID_MIN_NOTES]
        cues: list[tuple[str, tuple[str, ...]]] = []
        if broad:
            cues.append((CUE_KINDS[0], (broad[0],)))
        if mid:
            cues.append((CUE_KINDS[1], (mid[0],)))
        if len(usable) >= 2:
            cues.append((CUE_KINDS[2], (usable[0], usable[1])))
        for rare_tag in rare:
            for kind, anchors in cues:
                by_kind[(TARGET_KINDS[0], kind)].append(CueCase(
                    note_id=note_id, target_kind=TARGET_KINDS[0], cue_kind=kind, anchors=anchors, rare_tag=rare_tag))
        # A common second tag (the everyday narrowing case), after a mid-sized or a broad first
        # tag, unless it is on every note under the cue (then adding it would not narrow anything).
        for cue_kind, cue_tags in ((CUE_KINDS[1], mid[:1]), (CUE_KINDS[0], broad[:1])):
            for cue in cue_tags:
                cue_notes = tag_notes.notes_by_tag[cue]
                for target in broad:
                    if target != cue and not cue_notes <= tag_notes.notes_by_tag[target]:
                        by_kind[(TARGET_KINDS[1], cue_kind)].append(CueCase(
                            note_id=note_id, target_kind=TARGET_KINDS[1], cue_kind=cue_kind, anchors=(cue,),
                            rare_tag=target))
    cases: list[CueCase] = []
    for key in sorted(by_kind):
        random.Random(SAMPLE_SEED).shuffle(by_kind[key])
        cases.extend(by_kind[key][:MAX_CASES])
    return cases


def orderings_after(*, anchors: tuple[str, ...], tag_notes: TagNotes) -> dict[str, list[str]]:
    """Every candidate after the anchors (it leaves results), in each ordering but today's."""
    assert anchors
    anchor_notes = tag_notes.notes_by_tag[anchors[0]].intersection(
        *(tag_notes.notes_by_tag[anchor] for anchor in anchors[1:]))
    assert anchor_notes, "the anchors must share at least one note"
    together: Counter[str] = Counter()
    for note_id in anchor_notes:
        together.update(tag_notes.tags_by_note[note_id])
    for anchor in anchors:
        del together[anchor]
    scores: dict[str, dict[str, float]] = {name: {} for name in ORDERING_NAMES
                                           if name not in ("today", "today+specificity")}
    for tag, both in together.items():
        share_under_anchor = both / len(anchor_notes)
        share_overall = len(tag_notes.notes_by_tag[tag]) / tag_notes.total_notes
        lift = share_under_anchor / share_overall
        scores["count"][tag] = float(both)
        scores["specificity"][tag] = lift
        scores["balanced"][tag] = share_under_anchor * math.log(lift)
        for smoothing in SMOOTHING_NOTES:
            scores[f"specificity, smoothed k={smoothing}"][tag] = both / (len(tag_notes.notes_by_tag[tag]) + smoothing)
    return {name: sorted(values, key=lambda tag: (-values[tag], -len(tag_notes.notes_by_tag[tag]), tag))
            for name, values in scores.items()}


def fuse_ranks(lists: list[list[str]]) -> list[str]:
    """Combine ranked lists with no weights: score = sum of 1 / (FUSION_K + rank)."""
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    for ranked in lists:
        for rank, tag in enumerate(ranked, start=1):
            if tag not in scores:
                scores[tag] = 0.0
                first_seen[tag] = len(first_seen)
            scores[tag] += 1.0 / (FUSION_K + rank)
    return sorted(scores, key=lambda tag: (-scores[tag], first_seen[tag]))


# Position recorded when the rare tag is not in an ordering at all.
ABSENT = 10**9


@dataclass(frozen=True)
class CueResult:
    case: CueCase
    # Position of the rare tag in each ordering (0 = first), ABSENT if missing.
    positions: dict[str, int]


def all_orderings(*, anchors: tuple[str, ...], tag_notes: TagNotes, today: list[str]) -> dict[str, list[str]]:
    """Every ordering after the anchors; `today` is MetaList's own list after them (casefolded)."""
    orderings = orderings_after(anchors=anchors, tag_notes=tag_notes)
    orderings["today"] = today
    orderings["today+specificity"] = fuse_ranks([orderings["today"], orderings["specificity"]])
    return orderings


def run_cue_test(*, cases: list[CueCase], tag_notes: TagNotes,
                 today_after: Callable[[tuple[str, ...]], list[str]],
                 orderings_by_anchors: dict[tuple[str, ...], dict[str, list[str]]]) -> list[CueResult]:
    """`today_after(anchors)` is MetaList's own list after typing the anchors and a space.

    Fills `orderings_by_anchors` so later measures can reuse the orderings.
    """
    positions_by_anchors: dict[tuple[str, ...], dict[str, dict[str, int]]] = {}
    results: list[CueResult] = []
    for case in cases:
        if case.anchors not in orderings_by_anchors:
            orderings_by_anchors[case.anchors] = all_orderings(
                anchors=case.anchors, tag_notes=tag_notes,
                today=[tag.casefold() for tag in today_after(case.anchors)])
        if case.anchors not in positions_by_anchors:
            positions_by_anchors[case.anchors] = {
                name: {tag: position for position, tag in reversed(list(enumerate(ordered)))}
                for name, ordered in orderings_by_anchors[case.anchors].items()}
        positions: dict[str, int] = {}
        for name, position_by_tag in positions_by_anchors[case.anchors].items():
            positions[name] = ABSENT
            if case.rare_tag in position_by_tag:
                positions[name] = position_by_tag[case.rare_tag]
        results.append(CueResult(case=case, positions=positions))
    return results


def keystrokes_after_cue(*, case: CueCase, orderings: dict[str, list[str]],
                         today_typed: Callable[[tuple[str, ...], str], list[str]],
                         matches: Callable[[str, str], bool], list_length: int,
                         memo: dict[tuple[tuple[str, ...], str, str], list[str]]) -> dict[str, int]:
    """Letters typed after the cue + arrows + Enter to pick the target, per ordering.

    Every ordering is filtered by the letters typed (typing narrows the list). For
    `today`, MetaList's own list after the cue and the letters is asked for directly.
    `memo` is shared across cases: lists per (cue, ordering, letters typed).
    """
    return {name: keystrokes_to_pick(tag=case.rare_tag, ranking=_typed_ranking(
                case=case, name=name, ordered=ordered, today_typed=today_typed, matches=matches,
                list_length=list_length, memo=memo))
            for name, ordered in orderings.items()}


def _typed_ranking(*, case: CueCase, name: str, ordered: list[str],
                   today_typed: Callable[[tuple[str, ...], str], list[str]], matches: Callable[[str, str], bool],
                   list_length: int, memo: dict[tuple[tuple[str, ...], str, str], list[str]]) -> Callable[[str], list[str]]:
    def ranking(prefix: str) -> list[str]:
        key = (case.anchors, name, prefix)
        if key not in memo:
            if name == "today" and prefix != "":
                memo[key] = [tag.casefold() for tag in today_typed(case.anchors, prefix)][:list_length]
            else:
                memo[key] = [tag for tag in ordered if matches(tag, prefix)][:list_length]
        return memo[key]
    return ranking
