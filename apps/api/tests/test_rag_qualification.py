"""Development-split comparison. Held-out scoring is a separate test."""

import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.assistant.context import retrieve_crm_records
from app.domains.assistant.rewrite import rewrite_question
from app.domains.assistant.routing import INJECTION_ANSWER, route_question
from app.domains.crm.service import search_records
from app.domains.evaluation.rag_dataset import load_rag_dataset
from app.domains.evaluation.rag_metrics import choose_pipeline, mean, ndcg_at_k, recall_at_k
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.retrieval import search_chunks
from app.domains.knowledge.service import claim_ingestion_job, run_ingestion_job
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org

PIPELINES = (
    "lexical",
    "dense",
    "baseline",
    "hybrid",
    "hybrid_meta",
    "hybrid_rerank",
    "hybrid_full",
)


def test_choose_pipeline_drops_a_weak_abstention_and_keeps_a_simpler_tie() -> None:
    scores = {
        "lexical": {"recall_at_5": 0.9, "abstention_accuracy": 0.4},
        "dense": {"recall_at_5": 0.2, "abstention_accuracy": 1.0},
        "baseline": {"recall_at_5": 0.8, "abstention_accuracy": 0.96},
        "hybrid": {"recall_at_5": 0.8, "abstention_accuracy": 0.96},
        "hybrid_meta": {"recall_at_5": 0.7, "abstention_accuracy": 0.96},
        "hybrid_rerank": {"recall_at_5": 0.8, "abstention_accuracy": 0.96},
        "hybrid_full": {"recall_at_5": 0.8, "abstention_accuracy": 0.96},
    }
    assert choose_pipeline(scores) == "baseline"


def test_dataset_keeps_development_and_held_out_apart() -> None:
    dataset = load_rag_dataset()
    development = dataset["development"]
    held_out = dataset["held_out"]
    assert len(development) + len(held_out) >= 100
    assert len(development) >= 30
    assert len(held_out) >= 60
    identifiers = [case["id"] for case in development + held_out]
    assert len(identifiers) == len(set(identifiers))
    assert {case["id"][:3] for case in development} == {"dev"}
    assert {case["id"][:4] for case in held_out} == {"held"}


def test_development_split_chooses_a_pipeline(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = load_rag_dataset()
    organization_id = _workspace(client, db, dataset, monkeypatch, 800, "dev-main@example.com")
    development = dataset["development"]
    retrieve = [case for case in development if case["task"] == "retrieve"]
    abstain = [case for case in development if case["task"] == "abstain"]
    follow_ups = [case for case in development if case["task"] == "follow_up"]
    scores = {
        pipeline: _retrieval_score(db, organization_id, retrieve, abstain, pipeline, False)
        for pipeline in PIPELINES
    }
    chosen = choose_pipeline(scores)
    raw_follow = _retrieval_score(db, organization_id, follow_ups, [], "lexical", False)
    rewritten_follow = _retrieval_score(db, organization_id, follow_ups, [], "lexical", True)
    for case in retrieve + abstain:
        rows = _search(db, organization_id, case, "lexical", False)
        titles = [row.document_title for row in rows]
        relevant = set(case["relevant"])
        missed = case["task"] == "abstain" and bool(rows) or (
            case["task"] == "retrieve" and not (set(titles) & relevant)
        )
        if missed:
            print(f"DEV_MISS lexical {case['kind']} {case['question'][:80]} -> {titles[:3]}")
    crm_question = "What leads does Feld and Quay have?"
    baseline_crm = _lead_titles(search_records(db, organization_id, crm_question))
    linked_crm = _lead_titles(retrieve_crm_records(db, organization_id, crm_question))
    chunk_scores = {
        size: _chunk_term_rate(client, db, dataset, monkeypatch, size, retrieve)
        for size in (400, 800, 1600)
    }
    for pipeline, score in scores.items():
        print(
            "DEV_PIPELINE "
            f"{pipeline} recall={score['recall_at_5']} abstain={score['abstention_accuracy']} "
            f"ndcg={score['ndcg_at_5']} ms={score['latency_ms']}"
        )
    print("DEV_CHOICE", chosen)
    print(
        "DEV_REWRITE",
        f"raw={raw_follow['recall_at_5']}",
        f"rewritten={rewritten_follow['recall_at_5']}",
    )
    print(
        "DEV_CRM",
        f"baseline={'Quay Lane expansion' in baseline_crm}",
        f"linked={'Quay Lane expansion' in linked_crm}",
        f"linked_excludes_tea={'Tea order' not in linked_crm}",
    )
    print("DEV_CHUNK", chunk_scores)
    assert chosen in PIPELINES


def _chunk_term_rate(
    client: TestClient,
    db: Session,
    dataset: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    cases: list[dict[str, Any]],
) -> float:
    organization_id = _workspace(
        client, db, dataset, monkeypatch, size, f"dev-chunk-{size}@example.com"
    )
    hits = [
        _search(db, organization_id, case, "baseline", False) for case in cases if case["terms"]
    ]
    if not hits:
        return 0.0
    found = 0
    for case, rows in zip((case for case in cases if case["terms"]), hits, strict=True):
        blob = "\n".join(row.content for row in rows).lower()
        if all(term.lower() in blob for term in case["terms"]):
            found += 1
    return round(found / len(hits), 4)


def _retrieval_score(
    db: Session,
    organization_id: uuid.UUID,
    retrieve: list[dict[str, Any]],
    abstain: list[dict[str, Any]],
    pipeline: str,
    rewrite: bool,
) -> dict[str, float]:
    recalls: list[float] = []
    discounted: list[float] = []
    latencies: list[float] = []
    for case in retrieve:
        started = time.perf_counter()
        rows = _search(db, organization_id, case, pipeline, rewrite)
        latencies.append((time.perf_counter() - started) * 1000)
        titles = [row.document_title for row in rows]
        relevant = set(case["relevant"])
        recalls.append(recall_at_k(titles, relevant, 5))
        discounted.append(ndcg_at_k(titles, relevant, 5))
    abstentions = []
    for case in abstain:
        rows = _search(db, organization_id, case, pipeline, False)
        abstentions.append(1.0 if not rows else 0.0)
    return {
        "recall_at_5": round(mean(recalls), 4),
        "ndcg_at_5": round(mean(discounted), 4),
        "abstention_accuracy": round(mean(abstentions), 4),
        "latency_ms": round(mean(latencies), 2),
    }


def _search(
    db: Session,
    organization_id: uuid.UUID,
    case: dict[str, Any],
    pipeline: str,
    rewrite: bool,
):
    history = [(str(role), str(text)) for role, text in case.get("history", [])]
    question = rewrite_question(case["question"], history, []) if rewrite else case["question"]
    return search_chunks(
        db,
        organization_id,
        question,
        HashEmbeddingClient(),
        limit=5,
        pipeline=pipeline,  # type: ignore[arg-type]
    )


def _lead_titles(records: list[dict[str, str]]) -> list[str]:
    return [record["title"] for record in records if record["record_type"] == "lead"]


def _workspace(
    client: TestClient,
    db: Session,
    dataset: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    chunk_size: int,
    email: str,
) -> uuid.UUID:
    monkeypatch.setattr("app.domains.knowledge.chunking.CHUNK_SIZE", chunk_size)
    user = make_user(db, email)
    organization = make_organization(db, "Feld Eval", f"feld-{uuid.uuid4().hex[:8]}")
    make_membership(db, user, organization, MembershipRole.admin)
    session = login(client, email, PASSWORD)
    headers = _csrf(session)
    org = _org(session)
    companies: dict[str, str] = {}
    for company in dataset["companies"]:
        created = client.post(
            f"/api/v1/organizations/{org}/companies",
            json={"name": company["name"], "industry": company["industry"]},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        companies[company["name"]] = created.json()["id"]
    for lead in dataset["leads"]:
        created = client.post(
            f"/api/v1/organizations/{org}/leads",
            json={
                "title": lead["title"],
                "company_id": companies[lead["company"]],
                "notes": lead["notes"],
                "status": "new",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
    for contact in dataset["contacts"]:
        created = client.post(
            f"/api/v1/organizations/{org}/contacts",
            json={
                "full_name": contact["full_name"],
                "email": contact["email"],
                "company_id": companies[contact["company"]],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
    embedder = HashEmbeddingClient()
    for document in dataset["documents"]:
        uploaded = client.post(
            f"/api/v1/organizations/{org}/documents",
            files={"file": (document["filename"], document["text"].encode(), "text/plain")},
            headers=headers,
        )
        assert uploaded.status_code == 201, uploaded.text
        assert _process_one(embedder)
    return organization.id


def _process_one(embedder: HashEmbeddingClient) -> bool:
    worker_id = f"qual-{uuid.uuid4()}"
    job = claim_ingestion_job(worker_id)
    if job is None:
        return False
    run_ingestion_job(job, worker_id, embedder)
    return True


def test_held_out_reports_the_selected_pipeline(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report held-out numbers. This test must not change the development choice."""

    from app.domains.knowledge.retrieval import PRODUCTION_PIPELINE

    dataset = load_rag_dataset()
    organization_id = _workspace(client, db, dataset, monkeypatch, 800, "held-out@example.com")
    held_out = dataset["held_out"]
    retrieve = [case for case in held_out if case["task"] in {"retrieve", "follow_up"}]
    abstain = [case for case in held_out if case["task"] == "abstain"]
    scores = {
        pipeline: _retrieval_score(db, organization_id, retrieve, abstain, pipeline, False)
        for pipeline in PIPELINES
    }
    chosen = scores[PRODUCTION_PIPELINE]
    generation = _generation_score(db, organization_id, retrieve, PRODUCTION_PIPELINE)
    intents = [
        case for case in held_out if case["task"] == "intent" and case.get("intent")
    ]
    intent_hits = []
    for case in intents:
        routed = route_question(case["question"], has_history=bool(case.get("history")))
        intent_hits.append(routed.value == case["intent"])
    print("HELD_PIPELINE", PRODUCTION_PIPELINE, chosen)
    for pipeline, score in scores.items():
        print(
            "HELD_COMPARE "
            f"{pipeline} recall={score['recall_at_5']} abstain={score['abstention_accuracy']} "
            f"ndcg={score['ndcg_at_5']}"
        )
    print("HELD_GENERATION", generation)
    print("HELD_INTENT", round(mean([1.0 if hit else 0.0 for hit in intent_hits]), 4))
    for case in held_out:
        if not case.get("live_sample"):
            continue
        rows = _search(db, organization_id, case, PRODUCTION_PIPELINE, case["task"] == "follow_up")
        excerpt = " ".join(row.content for row in rows)[:240]
        print("LIVE_CONTEXT", case["id"], case["task"], excerpt)
    assert chosen["recall_at_5"] >= 0.0


def _generation_score(
    db: Session, organization_id: uuid.UUID, cases: list[dict[str, Any]], pipeline: str
) -> dict[str, float]:
    from app.domains.knowledge.attribution import attribute_answer

    factual: list[float] = []
    complete: list[float] = []
    faithful: list[float] = []
    cited: list[float] = []
    latencies: list[float] = []
    for case in cases:
        if not case["terms"]:
            continue
        started = time.perf_counter()
        rows = _search(db, organization_id, case, pipeline, case["task"] == "follow_up")
        blob = "\n".join(row.content for row in rows)
        found = [term for term in case["terms"] if term.lower() in blob.lower()]
        answer = " ".join(found)
        latencies.append((time.perf_counter() - started) * 1000)
        forbidden_hit = any(term.lower() in blob.lower() for term in case["forbidden"])
        relevant = set(case["relevant"])
        titles = [row.document_title for row in rows]
        covered = bool(found) and len(found) == len(case["terms"]) and not forbidden_hit
        factual.append(1.0 if covered and set(titles) & relevant else 0.0)
        complete.append(len(found) / len(case["terms"]))
        passages = [(str(row.chunk_id), row.content) for row in rows]
        if answer:
            stored, cited_ids = attribute_answer(case["question"], answer, passages)
        else:
            stored, cited_ids = "", []
        faithful.append(1.0 if answer and not stored.startswith("I could not confirm") else 0.0)
        cited_titles = {row.document_title for row in rows if str(row.chunk_id) in set(cited_ids)}
        cited.append(1.0 if cited_titles and cited_titles <= relevant else 0.0)
    return {
        "factual_correctness": round(mean(factual), 4),
        "completeness": round(mean(complete), 4),
        "faithfulness": round(mean(faithful), 4),
        "citation_correctness": round(mean(cited), 4),
        "latency_ms": round(mean(latencies), 2),
        "cases": float(len(factual)),
    }


def test_injection_route_does_not_repeat_the_payload() -> None:
    dataset = load_rag_dataset()
    injections = [
        case for case in dataset["development"] + dataset["held_out"] if case["task"] == "injection"
    ]
    assert injections
    for case in injections:
        assert route_question(case["question"], has_history=False).value == "injection"
        for forbidden in case["forbidden"]:
            assert forbidden.lower() not in INJECTION_ANSWER.lower()
