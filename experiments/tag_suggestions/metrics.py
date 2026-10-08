"""Scores for ranked suggestion lists. Only totals are ever reported."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

LIST_LENGTH = 20
TOP = 5


@dataclass(frozen=True)
class CaseScore:
    hit_at_5: float
    recall_at_5: float
    reciprocal_rank: float
    precision_at_1: float


def score_case(*, ranked: list[str], targets: frozenset[str]) -> CaseScore:
    """`ranked` is a model's list for one moment, best first; `targets` are the correct tags."""
    assert targets, "a scored case needs at least one reachable target"
    shown = ranked[:LIST_LENGTH]
    assert len(shown) == len(set(shown)), "a suggestion list repeats a tag"
    top = shown[:TOP]
    found_in_top = sum(1 for tag in top if tag in targets)
    reciprocal_rank = 0.0
    for position, tag in enumerate(shown, start=1):
        if tag in targets:
            reciprocal_rank = 1.0 / position
            break
    precision_at_1 = 0.0
    if top and top[0] in targets:
        precision_at_1 = 1.0
    return CaseScore(
        hit_at_5=float(found_in_top > 0),
        recall_at_5=found_in_top / min(len(targets), TOP),
        reciprocal_rank=reciprocal_rank,
        precision_at_1=precision_at_1,
    )


@dataclass(frozen=True)
class Summary:
    cases: int
    hit_at_5: float
    recall_at_5: float
    mrr: float
    precision_at_1: float


def summarize(scores: list[CaseScore]) -> Summary:
    assert scores
    count = len(scores)
    return Summary(
        cases=count,
        hit_at_5=sum(score.hit_at_5 for score in scores) / count,
        recall_at_5=sum(score.recall_at_5 for score in scores) / count,
        mrr=sum(score.reciprocal_rank for score in scores) / count,
        precision_at_1=sum(score.precision_at_1 for score in scores) / count,
    )


def frequency_bucket(training_uses: int) -> str:
    """How common a target tag was in what the models learned from."""
    assert training_uses >= 0
    if training_uses == 0:
        return "new (0)"
    if training_uses <= 3:
        return "rare (1-3)"
    if training_uses <= 20:
        return "medium (4-20)"
    return "common (21+)"


def per_target_hits(*, ranked: list[str], targets: frozenset[str], training_uses: Counter[str]) -> list[tuple[str, float]]:
    """(frequency bucket, found in top 5) for each target of one case."""
    top = set(ranked[:TOP])
    return [(frequency_bucket(training_uses[target]), float(target in top)) for target in sorted(targets)]
