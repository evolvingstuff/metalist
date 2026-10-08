"""The rankers compared in the experiment.

Every learned ranker orders the same candidates (features.py). The baseline is
MetaList's own list. Training uses out-of-fold features; early stopping uses
the latest training notes (a time-ordered validation slice).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import lightgbm
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from experiments.tag_suggestions.features import FEATURE_NAMES, CaseCandidates

RANDOM_SEED = 7

# LightGBM names its columns itself; scikit-learn then warns on every prediction
# from a plain array. The columns are always FEATURE_NAMES, in order.
warnings.filterwarnings("ignore", message="X does not have valid feature names")

# +1: more never lowers the score; -1: more never raises it (a larger rank is worse).
_MONOTONE = {
    "knn_score": 1, "knn_rank": -1, "nb_gap": 1, "nb_rank": -1,
    "present_cooc_max": 1, "inherited_cooc_max": 1, "parent_has": 1, "sibling_fraction": 1,
    "descendant_fraction": 1, "name_in_text": 1, "joint_fraction": 1,
}
MONOTONE_CONSTRAINTS = [0] * len(FEATURE_NAMES)
for _name, _direction in _MONOTONE.items():
    MONOTONE_CONSTRAINTS[FEATURE_NAMES.index(_name)] = _direction


@dataclass(frozen=True)
class TrainingData:
    features: np.ndarray
    labels: np.ndarray
    group_sizes: list[int]


def stack(items: list[CaseCandidates]) -> TrainingData:
    kept = [item for item in items if len(item.candidates) > 0]
    assert kept, "no candidates to train on"
    return TrainingData(
        features=np.vstack([item.features for item in kept]),
        labels=np.concatenate([item.labels for item in kept]),
        group_sizes=[len(item.candidates) for item in kept],
    )


def with_positives(items: list[CaseCandidates]) -> list[CaseCandidates]:
    """Ranking objectives learn nothing from a list with no correct tag."""
    return [item for item in items if item.labels.sum() > 0]


def rank_by_column(item: CaseCandidates, column: str) -> list[str]:
    """Order candidates by one input (higher first), e.g. neighbor score alone."""
    index = FEATURE_NAMES.index(column)
    return _order(item, item.features[:, index])


def _order(item: CaseCandidates, scores: np.ndarray) -> list[str]:
    assert len(scores) == len(item.candidates)
    # Stable: ties keep generator order (neighbors first).
    order = np.argsort(-scores, kind="stable")
    return [item.candidates[position] for position in order]


# Reciprocal rank fusion constant (the usual choice; larger flattens rank differences).
FUSION_K = 60


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


class FormulaRanker:
    """A fixed formula, no model: neighbor vote + a*name in text + b*fits the bar + c*recency + d*usage.

    The four weights are chosen once by grid search on the training moments
    (best mean reciprocal rank); in the app they would be constants.
    """

    GRID_NAME = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0)
    GRID_JOINT = (0.0, 0.25, 0.5, 1.0, 2.0)
    GRID_RECENCY = (0.0, 0.1, 0.25, 0.5, 1.0)
    GRID_USAGE = (0.0, 0.02, 0.05, 0.1, 0.2)
    RECENCY_DAYS = 30.0

    def __init__(self, training: list[CaseCandidates]) -> None:
        weights = np.array([(1.0, name, joint, recency, usage)
                            for name in self.GRID_NAME for joint in self.GRID_JOINT
                            for recency in self.GRID_RECENCY for usage in self.GRID_USAGE]).T
        totals = np.zeros(weights.shape[1])
        for item in training:
            if item.labels.sum() == 0:
                continue
            scores = self._signals(item) @ weights
            # Reciprocal rank of the first correct tag, for every weight setting at once.
            order = np.argsort(-scores, axis=0, kind="stable")
            correct = item.labels[order] > 0
            first = np.argmax(correct, axis=0)
            totals += 1.0 / (first + 1)
        best = int(np.argmax(totals))
        self.weights = weights[:, best]

    def _signals(self, item: CaseCandidates) -> np.ndarray:
        def column(name: str) -> np.ndarray:
            return item.features[:, FEATURE_NAMES.index(name)]
        recency = 1.0 / (1.0 + column("days_since_last_use") / self.RECENCY_DAYS)
        return np.stack([column("knn_score"), column("name_in_text"), column("joint_fraction"), recency,
                         column("log_tag_count")], axis=1)

    def rank(self, item: CaseCandidates) -> list[str]:
        if not item.candidates:
            return []
        return _order(item, self._signals(item) @ self.weights)

    def describe(self) -> str:
        _vote, name, joint, recency, usage = self.weights
        return (f"neighbor vote + {name:g} x name in text + {joint:g} x fits the bar + "
                f"{recency:g} x recency + {usage:g} x usage")


class LogisticRanker:
    def __init__(self, training: list[CaseCandidates]) -> None:
        data = stack(training)
        self.model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
        self.model.fit(data.features, data.labels)

    def rank(self, item: CaseCandidates) -> list[str]:
        if not item.candidates:
            return []
        return _order(item, self.model.predict_proba(item.features)[:, 1])


class BoostedRanker:
    """Gradient-boosted trees, as a yes/no classifier or with a ranking objective."""

    def __init__(self, *, training: list[CaseCandidates], validation: list[CaseCandidates], objective: str) -> None:
        assert objective in {"binary", "lambdarank"}
        self.objective = objective
        parameters = dict(
            n_estimators=2000, learning_rate=0.05, num_leaves=15, max_depth=5, min_child_samples=40,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
            monotone_constraints=MONOTONE_CONSTRAINTS, random_state=RANDOM_SEED, verbose=-1, n_jobs=4,
        )
        stopping = [lightgbm.early_stopping(stopping_rounds=50, verbose=False)]
        if objective == "binary":
            train = stack(training)
            valid = stack(validation)
            self.model = lightgbm.LGBMClassifier(**parameters)
            self.model.fit(train.features, train.labels, eval_set=[(valid.features, valid.labels)],
                           eval_metric="binary_logloss", callbacks=stopping)
        else:
            train = stack(with_positives(training))
            valid = stack(with_positives(validation))
            self.model = lightgbm.LGBMRanker(objective="lambdarank", **parameters)
            self.model.fit(train.features, train.labels, group=train.group_sizes,
                           eval_set=[(valid.features, valid.labels)], eval_group=[valid.group_sizes],
                           eval_at=[5], callbacks=stopping)
        self.trees = int(self.model.best_iteration_)

    def rank(self, item: CaseCandidates) -> list[str]:
        if not item.candidates:
            return []
        if self.objective == "binary":
            return _order(item, self.model.predict_proba(item.features)[:, 1])
        return _order(item, self.model.predict(item.features))

    def importance(self) -> list[tuple[str, float]]:
        gains = self.model.booster_.feature_importance(importance_type="gain")
        total = float(gains.sum())
        assert total > 0
        return sorted(((name, float(gain) / total) for name, gain in zip(FEATURE_NAMES, gains)),
                      key=lambda pair: -pair[1])
