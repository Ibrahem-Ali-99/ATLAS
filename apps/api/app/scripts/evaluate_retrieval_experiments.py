"""Development retrieval experiment with Ollama embeddings.

Run with ATLAS_LIVE_RAG=yes. Uses the Feld development split only.
Does not read the fresh final set and does not write the demo database.
"""

from __future__ import annotations

import math
import os
import re

from app.core.errors import AppError
from app.domains.evaluation.rag_dataset import DEVELOPMENT, DOCUMENTS
from app.domains.evaluation.rag_metrics import mean, ndcg_at_k, recall_at_k, reciprocal_rank
from app.domains.knowledge.evidence import PassageView, select_answerable
from app.integrations.language import get_embedding_client

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"what", "when", "where", "which", "with", "from", "that", "this", "does", "have"}


def main() -> None:
    if os.environ.get("ATLAS_LIVE_RAG") != "yes":
        raise SystemExit("retrieval experiment is blocked: set ATLAS_LIVE_RAG=yes")
    passages = []
    for item in DOCUMENTS:
        title = item["filename"].removesuffix(".txt")
        passages.append(PassageView(title, title, item["text"]))
    questions = [case for case in DEVELOPMENT if case["task"] in {"retrieve", "abstain"}]
    texts = [str(case["question"]) for case in questions] + [item.content for item in passages]
    try:
        vectors = get_embedding_client().embed(texts)
    except AppError as exc:
        print("ollama_ok", False)
        print("ollama_code", exc.code)
        return
    print("ollama_ok", True)
    print("ollama_dimensions", len(vectors[0]))
    query_vectors = vectors[: len(questions)]
    document_vectors = vectors[len(questions) :]
    dense_rows = []
    hybrid_rows = []
    answerable_rows = []
    lexical_rows = []
    for case, query_vector in zip(questions, query_vectors, strict=True):
        question = str(case["question"])
        ranked = sorted(
            (
                (item, _distance(query_vector, document_vector))
                for item, document_vector in zip(passages, document_vectors, strict=True)
            ),
            key=lambda pair: pair[1],
        )
        if case["task"] == "abstain":
            title, distance = ranked[0]
            print("HARD_NEGATIVE", case["kind"], title.title, round(distance, 4), question[:70])
        lexical = _lexical(question, passages)
        dense = [item for item, distance in ranked if distance <= 0.45][:5]
        fused = _fuse(lexical, [item for item, distance in ranked if distance <= 0.55][:8])
        lexical_rows.append((case, [item.title for item in lexical[:5]]))
        dense_rows.append((case, [item.title for item in dense]))
        hybrid_rows.append((case, [item.title for item in fused[:5]]))
        answerable_rows.append((case, [item.title for item in select_answerable(question, fused)]))
    for name, rows in (
        ("lexical", lexical_rows),
        ("dense", dense_rows),
        ("hybrid", hybrid_rows),
        ("answerable", answerable_rows),
    ):
        print("OLLAMA_DEV", name, _metrics(rows))
    _cross_encoder()


def _metrics(rows: list[tuple[dict[str, object], list[str]]]) -> str:
    recalls = []
    ranks = []
    discounted = []
    abstentions = []
    for case, titles in rows:
        if case["task"] == "abstain":
            abstentions.append(1.0 if not titles else 0.0)
            continue
        relevant = set(case["relevant"])  # type: ignore[arg-type]
        recalls.append(recall_at_k(titles, relevant, 5))
        ranks.append(reciprocal_rank(titles, relevant))
        discounted.append(ndcg_at_k(titles, relevant, 5))
    return (
        f"recall={round(mean(recalls), 4)} mrr={round(mean(ranks), 4)} "
        f"ndcg={round(mean(discounted), 4)} abstain={round(mean(abstentions), 4)}"
    )


def _lexical(question: str, passages: list[PassageView]) -> list[PassageView]:
    tokens = _terms(question)
    scored = [(item, len(tokens & _terms(item.content))) for item in passages]
    scored = [pair for pair in scored if pair[1] > 0]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _count in scored]


def _fuse(lexical: list[PassageView], dense: list[PassageView]) -> list[PassageView]:
    scores: dict[str, float] = {}
    items: dict[str, PassageView] = {}
    for position, item in enumerate(lexical, start=1):
        scores[item.key] = scores.get(item.key, 0.0) + 1 / (60 + position)
        items[item.key] = item
    for position, item in enumerate(dense, start=1):
        scores[item.key] = scores.get(item.key, 0.0) + 1 / (60 + position)
        items[item.key] = item
    ordered = sorted(items.values(), key=lambda item: scores[item.key], reverse=True)
    return [
        PassageView(item.key, item.title, item.content, scores[item.key]) for item in ordered
    ]


def _terms(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) >= 4 and token not in _STOP
    }


def _distance(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return 1 - dot / (left_norm * right_norm)


def _cross_encoder() -> None:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        print("cross_encoder", "unavailable")
        return
    print("cross_encoder", "importable")


if __name__ == "__main__":
    main()
