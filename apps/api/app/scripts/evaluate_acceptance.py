"""Score the Orry Beacon acceptance set once.

Run with ATLAS_ACCEPTANCE_EVAL=yes and ATLAS_LIVE_RAG=yes.
Rows are inserted on atlas_test. Public inference is enabled only inside this
process, for the visitor Assistant path. The setting default stays off.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, func, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domains.assistant import inference_guard
from app.domains.assistant.inference_guard import (
    assess_public_inference,
    finish_public_inference,
    reset_public_inference,
)
from app.domains.assistant.rewrite import rewrite_question
from app.domains.assistant.service import evaluate_response
from app.domains.evaluation.fact_match import statement_covers
from app.domains.evaluation.rag_acceptance import load_acceptance_dataset
from app.domains.evaluation.rag_metrics import mean, ndcg_at_k, recall_at_k, reciprocal_rank
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.chunking import chunk_pages
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.domains.knowledge.retrieval import search_chunks
from app.integrations import language
from app.integrations.doubles import DeterministicChatClient
from app.integrations.language import OpenAICompatibleChatClient, get_chat_client
from tests.ai_clients import HashEmbeddingClient, hash_embedding
from tests.factories import make_membership, make_organization, make_user

_REFUSAL = ("not found", "not stored", "could not find", "does not state", "no salary")


def main() -> None:
    if os.environ.get("ATLAS_ACCEPTANCE_EVAL") != "yes":
        raise SystemExit("acceptance evaluation is blocked")
    if os.environ.get("ATLAS_LIVE_RAG") != "yes":
        raise SystemExit("acceptance evaluation is blocked")
    default_off = Settings.model_fields["public_inference_enabled"].default is False
    print("VISITOR_SWITCH_DEFAULT", default_off)
    engine = create_engine(_test_database_url())
    with Session(engine) as db:
        try:
            _run(db)
        finally:
            db.rollback()


def _run(db: Session) -> None:
    dataset = load_acceptance_dataset()
    organization_id = _index(db, dataset["documents"])
    embedder = HashEmbeddingClient()
    questions = dataset["questions"]
    retrieve = [case for case in questions if case["task"] in {"retrieve", "follow_up"}]
    abstain = [case for case in questions if case["task"] == "abstain"]
    recalls: list[float] = []
    ranks: list[float] = []
    discounted: list[float] = []
    latencies: list[float] = []
    ready: list[tuple[dict[str, object], str]] = []
    for case in retrieve:
        question = _question(case)
        started = time.perf_counter()
        rows = search_chunks(db, organization_id, question, embedder, pipeline="answerable")
        latencies.append((time.perf_counter() - started) * 1000)
        titles = [row.document_title for row in rows]
        relevant = set(case["relevant"])
        recalls.append(recall_at_k(titles, relevant, 5))
        ranks.append(reciprocal_rank(titles, relevant))
        discounted.append(ndcg_at_k(titles, relevant, 5))
        ready.append((case, question))
        if set(titles) & relevant != relevant:
            print(f"ACCEPT_MISS {case['kind']} {question[:80]} -> {titles[:4]}")
    abstentions: list[float] = []
    for case in abstain:
        rows = search_chunks(
            db, organization_id, str(case["question"]), embedder, pipeline="answerable"
        )
        abstentions.append(1.0 if not rows else 0.0)
        if rows:
            print(
                "ACCEPT_LEAK",
                case["kind"],
                str(case["question"])[:80],
                [row.document_title for row in rows[:4]],
            )
    print(
        "ACCEPT_RETRIEVAL",
        f"n={len(questions)}",
        f"retrieve={len(retrieve)}",
        f"abstain_n={len(abstain)}",
        f"recall={round(mean(recalls), 4)}",
        f"mrr={round(mean(ranks), 4)}",
        f"ndcg={round(mean(discounted), 4)}",
        f"abstain={round(mean(abstentions), 4)}",
        f"retrieval_ms={round(mean(latencies), 2)}",
    )
    if not get_settings().llm_api_key.strip():
        print("ACCEPT_GENERATION", "skipped")
        return
    _generate(db, organization_id, embedder, ready)


def _generate(
    db: Session,
    organization_id: uuid.UUID,
    embedder: HashEmbeddingClient,
    ready: list[tuple[dict[str, object], str]],
) -> None:
    switched_off = get_chat_client(db, organization_id, public_inference=True)
    print("VISITOR_CLIENT_WHEN_OFF", type(switched_off).__name__)
    if not isinstance(switched_off, DeterministicChatClient):
        raise RuntimeError("The visitor client was live while public inference was off")
    enabled = get_settings().model_copy(update={"public_inference_enabled": True})
    language.get_settings = lambda: enabled
    inference_guard.get_settings = lambda: enabled
    reset_public_inference()
    switched_on = get_chat_client(
        db,
        organization_id,
        public_inference=True,
        max_output_tokens=enabled.public_inference_max_output_tokens,
    )
    print("VISITOR_CLIENT_WHEN_ON", type(switched_on).__name__)
    if not isinstance(switched_on, OpenAICompatibleChatClient):
        raise RuntimeError("The visitor client did not use the live model")
    factual: list[float] = []
    complete: list[float] = []
    cited: list[float] = []
    partial_scores: list[float] = []
    formatting: list[str] = []
    samples: list[tuple[str, str]] = []
    last_call = 0.0
    for index, (case, question) in enumerate(ready):
        key = f"assistant:{organization_id}:acceptance-{index // 7}"
        _wait(last_call, enabled)
        decision = assess_public_inference(key, question, hold_slot=True)
        last_call = time.monotonic()
        if not decision.allowed:
            print("ACCEPT_GUARD", decision.code, question[:60])
            factual.append(0.0)
            complete.append(0.0)
            continue
        history = [(str(role), str(text)) for role, text in case["history"]]  # type: ignore[misc]
        try:
            result = _complete(db, organization_id, question, embedder, history)
        finally:
            finish_public_inference()
        answer = str(result["response"])
        terms = [str(term) for term in case["terms"]]  # type: ignore[misc]
        forbidden = [str(term) for term in case["forbidden"]]  # type: ignore[misc]
        covered = [statement_covers(term, answer) for term in terms]
        blocked = [statement_covers(term, answer) for term in forbidden]
        factual.append(1.0 if all(covered) and not any(blocked) else 0.0)
        complete.append(mean([1.0 if item else 0.0 for item in covered]) if covered else 1.0)
        cited.append(1.0 if result["grounding"] == "grounded" else 0.0)
        for term in terms:
            if statement_covers(term, answer) and not _strict_has(term, answer):
                formatting.append(term)
                print("ACCEPT_FORMATTING", term, question[:60])
            if not statement_covers(term, answer):
                print("ACCEPT_GENUINE", term, question[:70])
                print("ACCEPT_ANSWER", _ascii(answer)[:240])
        if case["partial"]:
            partial_scores.append(1.0 if _refuses_missing(answer) and all(covered) else 0.0)
        if factual[-1] == 1.0 and len(samples) < 4:
            samples.append((question, answer))
    budget_key = f"assistant:{organization_id}:budget"
    for _ in range(enabled.public_inference_session_limit):
        _wait(last_call, enabled)
        held = assess_public_inference(budget_key, "What is the lamp oil fee?", hold_slot=True)
        last_call = time.monotonic()
        if held.allowed:
            finish_public_inference()
    _wait(last_call, enabled)
    denied = assess_public_inference(budget_key, "What is the lamp oil fee?", hold_slot=True)
    print("VISITOR_BUDGET", denied.code, denied.allowed)
    print(
        "ACCEPT_GENERATION",
        f"calls={len(factual)}",
        f"factual={round(mean(factual), 4)}",
        f"completeness={round(mean(complete), 4)}",
        f"citation={round(mean(cited), 4)}",
        f"partial={round(mean(partial_scores), 4) if partial_scores else 'n/a'}",
        f"formatting_terms={len(formatting)}",
        f"output_cap={enabled.public_inference_max_output_tokens}",
    )
    for question, answer in samples:
        print("ACCEPT_SAMPLE")
        print(_ascii(question))
        print(_ascii(answer)[:500])
    print("VISITOR_SWITCH_STILL_DEFAULT", Settings.model_fields["public_inference_enabled"].default)


def _complete(
    db: Session,
    organization_id: uuid.UUID,
    question: str,
    embedder: HashEmbeddingClient,
    history: list[tuple[str, str]],
) -> dict[str, object]:
    client = get_chat_client(
        db,
        organization_id,
        public_inference=True,
        max_output_tokens=language.get_settings().public_inference_max_output_tokens,
    )
    last_error: AppError | None = None
    for attempt in range(4):
        try:
            return evaluate_response(
                db,
                organization_id,
                question,
                embedder,
                client,
                history,
            )
        except AppError as exc:
            last_error = exc
            if exc.code != "llm_rate_limited" or attempt == 3:
                raise
            time.sleep(15 * (attempt + 1))
    raise last_error or RuntimeError("The language model was not called")


def _wait(last_call: float, settings: Settings) -> None:
    if last_call <= 0:
        return
    remaining = settings.public_inference_min_interval_seconds - (time.monotonic() - last_call)
    if remaining > 0:
        time.sleep(remaining)


def _question(case: dict[str, object]) -> str:
    question = str(case["question"])
    if case["task"] != "follow_up":
        return question
    history = [(str(role), str(text)) for role, text in case["history"]]  # type: ignore[misc]
    return rewrite_question(question, history, [])


def _strict_has(term: str, answer: str) -> bool:
    """A whitespace-normalized check that still treats 80000 and 80,000 as different."""

    def plain(text: str) -> str:
        cleaned = text.lower()
        for mark in ("\u2010", "\u2011", "\u2013", "\u2014", "\u2212"):
            cleaned = cleaned.replace(mark, "-")
        for mark in ("\u00a0", "\u202f"):
            cleaned = cleaned.replace(mark, " ")
        return " ".join(cleaned.split())

    return plain(term) in plain(answer)


def _refuses_missing(answer: str) -> bool:
    lowered = answer.lower()
    return any(phrase in lowered for phrase in _REFUSAL)


def _ascii(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def _index(db: Session, documents: list[dict[str, str]]) -> uuid.UUID:
    user = make_user(db, f"orry-{uuid.uuid4().hex[:8]}@example.com")
    slug = f"harbor-visitor-{uuid.uuid4().hex[:8]}"
    organization = make_organization(db, "Orry Acceptance", slug)
    make_membership(db, user, organization, MembershipRole.admin)
    for item in documents:
        title = item["filename"].removesuffix(".txt")
        document = Document(
            organization_id=organization.id,
            uploaded_by=user.id,
            title=title,
            filename=item["filename"],
            media_type="text/plain",
            byte_size=len(item["text"]),
            storage_path=f"tests/{title}.txt",
            status=DocumentStatus.ready,
        )
        db.add(document)
        db.flush()
        for piece in chunk_pages([(None, item["text"])]):
            chunk = Chunk(
                organization_id=organization.id,
                document_id=document.id,
                chunk_index=piece.index,
                content=piece.content,
                embedding=hash_embedding(piece.content),
            )
            db.add(chunk)
            db.flush()
            db.execute(
                update(Chunk)
                .where(Chunk.id == chunk.id)
                .values(search_vector=func.to_tsvector("english", Chunk.content))
            )
    db.flush()
    return organization.id


def _test_database_url() -> str:
    values = _postgres_values()
    user = quote_plus(values.get("POSTGRES_USER", "atlas"))
    password = quote_plus(values.get("POSTGRES_PASSWORD", "atlas"))
    host = values.get("POSTGRES_HOST", "127.0.0.1")
    port = values.get("POSTGRES_PORT", "5432")
    name = os.environ.get("ATLAS_TEST_DATABASE", "atlas_test")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def _postgres_values() -> dict[str, str]:
    root = Path(__file__).resolve().parents[4]
    env_file = root / ".env"
    found: dict[str, str] = {}
    if not env_file.is_file():
        return found
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().startswith("POSTGRES_"):
            found[key.strip()] = value.strip().strip('"').strip("'")
    return found


if __name__ == "__main__":
    main()
