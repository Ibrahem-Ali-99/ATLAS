"""Ranking metrics for one retrieved list.

Relevant ids are the documents that contain the answer. A list with no
relevant document scores zero. Abstention is scored separately by the caller.
"""

from __future__ import annotations

import math


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0 if not retrieved else 0.0
    found = set(retrieved[:k]) & relevant
    return len(found) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for index, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    gains = [1.0 if item in relevant else 0.0 for item in retrieved[:k]]
    ideal_hits = min(k, len(relevant))
    if ideal_hits == 0:
        return 1.0 if not any(gains) else 0.0
    return _dcg(gains) / _dcg([1.0] * ideal_hits)


# Simpler pipelines win a tie. This order is the selection rule, not a score.
PIPELINE_PREFERENCE = (
    "lexical",
    "dense",
    "baseline",
    "hybrid",
    "hybrid_meta",
    "hybrid_rerank",
    "hybrid_full",
)


def choose_pipeline(scores: dict[str, dict[str, float]]) -> str:
    """Pick a pipeline from development scores only.

    A candidate more than 0.05 below the best abstention accuracy is dropped.
    Among the rest, the highest Recall@5 wins. An equal recall keeps the simpler pipeline.
    """

    best_abstention = max(item["abstention_accuracy"] for item in scores.values())
    eligible = [
        name
        for name in PIPELINE_PREFERENCE
        if name in scores and scores[name]["abstention_accuracy"] >= best_abstention - 0.05
    ]
    return max(
        eligible,
        key=lambda name: (scores[name]["recall_at_5"], -PIPELINE_PREFERENCE.index(name)),
    )


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _dcg(gains: list[float]) -> float:
    return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
