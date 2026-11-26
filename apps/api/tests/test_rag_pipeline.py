"""Compare the baseline retriever with the hybrid retriever on fictional records."""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.assistant.context import retrieve_crm_records
from app.domains.assistant.rewrite import rewrite_question
from app.domains.assistant.routing import route_question
from app.domains.crm.service import search_records
from app.domains.evaluation.rag_metrics import mean, ndcg_at_k, recall_at_k, reciprocal_rank
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.attribution import attribute_answer
from app.domains.knowledge.models import Chunk, Document
from app.domains.knowledge.retrieval import search_chunks
from app.domains.knowledge.service import claim_ingestion_job, run_ingestion_job
from app.integrations.language import get_embedding_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org

CORPUS_PATH = Path(__file__).parents[1] / "app" / "domains" / "evaluation" / "rag_corpus_v1.json"
K = 5


def test_rewrite_keeps_a_new_question_and_carries_a_follow_up() -> None:
    history = [("user", "What does the Marrow bonded yard hold?"), ("assistant", "42 pallets.")]
    assert rewrite_question("What is the weekly rate?", history, []) == "What is the weekly rate?"
    rewritten = rewrite_question("Where is it?", history, ["marrow-bonded-yard"])
    assert "bonded" in rewritten
    assert "yard" in rewritten


def test_intent_and_action_labels_match_the_corpus() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    for case in corpus["intents"]:
        intent = route_question(case["question"], has_history=bool(case.get("history")))
        assert intent.value == case["intent"], case["id"]
    for case in corpus["actions"]:
        intent = route_question(case["question"], has_history=False)
        assert intent.value == case["intent"], case["id"]


def test_hybrid_retrieval_is_scored_against_the_baseline(client: TestClient, db: Session) -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    application = client.app
    application.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    user = make_user(db, "marrow-eval@example.com")
    organization = make_organization(db, "Marrow Eval", f"marrow-eval-{uuid.uuid4().hex[:8]}")
    make_membership(db, user, organization, MembershipRole.admin)
    session = login(client, "marrow-eval@example.com", PASSWORD)
    headers = _csrf(session)
    org = _org(session)
    company_ids: dict[str, str] = {}
    for company in corpus["companies"]:
        created = client.post(
            f"/api/v1/organizations/{org}/companies",
            json={"name": company["name"], "industry": company["industry"]},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        company_ids[company["name"]] = created.json()["id"]
    for lead in corpus["leads"]:
        created = client.post(
            f"/api/v1/organizations/{org}/leads",
            json={
                "title": lead["title"],
                "company_id": company_ids[lead["company"]],
                "notes": lead["notes"],
                "status": "new",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
    for document in corpus["documents"]:
        uploaded = client.post(
            f"/api/v1/organizations/{org}/documents",
            files={"file": (document["filename"], document["text"].encode(), "text/plain")},
            headers=headers,
        )
        assert uploaded.status_code == 201, uploaded.text
        assert _process_one(HashEmbeddingClient())

    reports = {
        "baseline": _score_retrieval(db, organization.id, corpus["retrieval"], "baseline", False),
        "hybrid": _score_retrieval(db, organization.id, corpus["retrieval"], "hybrid", True),
    }
    crm_question = "What leads does Marrow and Co. have?"
    baseline_leads = [
        record["title"]
        for record in search_records(db, organization.id, crm_question)
        if record["record_type"] == "lead"
    ]
    hybrid_leads = [
        record["title"]
        for record in retrieve_crm_records(db, organization.id, crm_question)
        if record["record_type"] == "lead"
    ]
    assert "Quay Lane expansion" in hybrid_leads
    assert "Tea order" not in hybrid_leads
    reports["crm"] = {
        "question": crm_question,
        "baseline_lead_hit": "Quay Lane expansion" in baseline_leads,
        "hybrid_lead_hit": "Quay Lane expansion" in hybrid_leads,
    }
    intent_hits = [
        route_question(case["question"], has_history=bool(case.get("history"))).value
        == case["intent"]
        for case in corpus["intents"]
    ]
    action_hits = [
        route_question(case["question"], has_history=False).value == case["intent"]
        for case in corpus["actions"]
    ]
    reports["intent_accuracy"] = round(mean([1.0 if hit else 0.0 for hit in intent_hits]), 4)
    reports["action_accuracy"] = round(mean([1.0 if hit else 0.0 for hit in action_hits]), 4)
    assert reports["hybrid"]["abstention_accuracy"] >= reports["baseline"]["abstention_accuracy"]
    assert reports["hybrid"]["recall_at_5"] >= reports["baseline"]["recall_at_5"]
    assert reports["intent_accuracy"] == 1.0
    assert reports["action_accuracy"] == 1.0
    print("RAG_BENCHMARK " + json.dumps(reports, sort_keys=True))


def test_partial_lexical_hit_survives_when_the_vector_is_far(db: Session) -> None:
    """AND full-text misses a passage that lacks one question word. OR retrieval keeps it."""

    from app.domains.knowledge.models import DocumentStatus
    from tests.test_retrieval_evidence import (
        _chunk,
        _document,
        _index,
        _offset,
        _query,
        _QueryVector,
    )

    user = make_user(db, "partial@example.com")
    organization = make_organization(db, "Partial", f"partial-{uuid.uuid4().hex[:8]}")
    make_membership(db, user, organization, MembershipRole.admin)
    document = _document(db, organization.id, user.id, "Cold card")
    document.status = DocumentStatus.ready
    chunk = _chunk(
        db,
        document,
        0,
        "Marrow cold storage is 18 pounds per pallet per week.",
        _offset(1536, 0.9),
    )
    _index(db, document.id)
    db.commit()
    question = "What cold storage services does Marrow offer?"
    embedder = _QueryVector(_query(1536))
    baseline = search_chunks(db, organization.id, question, embedder, pipeline="baseline")
    hybrid = search_chunks(db, organization.id, question, embedder, pipeline="hybrid")
    assert chunk.id not in {hit.chunk_id for hit in baseline}
    assert chunk.id in {hit.chunk_id for hit in hybrid}
    assert db.get(Document, document.id) is not None
    assert db.get(Chunk, chunk.id) is not None


def _score_retrieval(
    db: Session,
    organization_id: uuid.UUID,
    cases: list[dict[str, Any]],
    pipeline: Literal["baseline", "hybrid"],
    rewrite: bool,
) -> dict[str, float]:
    recalls: list[float] = []
    reciprocal: list[float] = []
    discounted: list[float] = []
    relevance: list[float] = []
    faithfulness: list[float] = []
    citations: list[float] = []
    abstentions: list[float] = []
    latencies: list[float] = []
    embedder = HashEmbeddingClient()
    if cases:
        search_chunks(db, organization_id, "warmup", embedder, limit=1, pipeline=pipeline)
    for case in cases:
        history = [(str(role), str(text)) for role, text in case.get("history", [])]
        question = rewrite_question(case["question"], history, []) if rewrite else case["question"]
        started = time.perf_counter()
        hits = search_chunks(
            db,
            organization_id,
            question,
            embedder,
            limit=K,
            pipeline=pipeline,
        )
        latencies.append((time.perf_counter() - started) * 1000)
        titles = [hit.document_title for hit in hits]
        relevant = set(case["relevant"])
        if case.get("abstain"):
            abstentions.append(1.0 if not hits else 0.0)
            continue
        abstentions.append(1.0 if hits else 0.0)
        recalls.append(recall_at_k(titles, relevant, K))
        reciprocal.append(reciprocal_rank(titles, relevant))
        discounted.append(ndcg_at_k(titles, relevant, K))
        if not hits:
            relevance.append(0.0)
            faithfulness.append(0.0)
            citations.append(0.0)
            continue
        terms = [str(term) for term in case.get("answer_terms", [])]
        top = hits[0].content
        found = [term for term in terms if term.lower() in top.lower()]
        if terms:
            relevance.append(len(found) / len(terms))
        answer = " ".join(found) if found else top[:240]
        passages = [(str(hit.chunk_id), hit.content) for hit in hits]
        _stored, cited = attribute_answer(case["question"], answer, passages)
        cited_titles = {hit.document_title for hit in hits if str(hit.chunk_id) in set(cited)}
        faithfulness.append(1.0 if cited and not _stored.startswith("I could not confirm") else 0.0)
        citations.append(1.0 if cited_titles and cited_titles <= relevant else 0.0)
    return {
        "recall_at_5": round(mean(recalls), 4),
        "mrr": round(mean(reciprocal), 4),
        "ndcg_at_5": round(mean(discounted), 4),
        "answer_relevance": round(mean(relevance), 4),
        "faithfulness": round(mean(faithfulness), 4),
        "citation_accuracy": round(mean(citations), 4),
        "abstention_accuracy": round(mean(abstentions), 4),
        "latency_ms": round(mean(latencies), 2),
    }


def _process_one(embedder: HashEmbeddingClient) -> bool:
    worker_id = f"rag-{uuid.uuid4()}"
    job = claim_ingestion_job(worker_id)
    if job is None:
        return False
    run_ingestion_job(job, worker_id, embedder)
    return True
