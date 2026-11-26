"""Answerability on the Feld development questions. The final set is not imported."""

import uuid

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.domains.assistant.rewrite import rewrite_question
from app.domains.evaluation.rag_dataset import DEVELOPMENT, DOCUMENTS
from app.domains.evaluation.rag_metrics import mean, ndcg_at_k, recall_at_k, reciprocal_rank
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.evidence import PassageView, select_answerable
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.domains.knowledge.retrieval import search_chunks
from tests.ai_clients import HashEmbeddingClient, hash_embedding
from tests.factories import make_membership, make_organization, make_user

_PASSAGES = [
    PassageView(
        item["filename"].removesuffix(".txt"),
        item["filename"].removesuffix(".txt"),
        item["text"],
    )
    for item in DOCUMENTS
]


def test_development_answerability_covers_labeled_facts() -> None:
    retrieve = [case for case in DEVELOPMENT if case["task"] == "retrieve"]
    follow_ups = [case for case in DEVELOPMENT if case["task"] == "follow_up"]
    abstain = [case for case in DEVELOPMENT if case["task"] == "abstain"]
    recalls = []
    ranks = []
    discounted = []
    for case in retrieve + follow_ups:
        question = case["question"]
        if case["task"] == "follow_up":
            history = [(str(role), str(text)) for role, text in case["history"]]
            question = rewrite_question(question, history, [])
        titles = [item.title for item in select_answerable(question, _PASSAGES)]
        relevant = set(case["relevant"])
        recalls.append(recall_at_k(titles, relevant, 5))
        ranks.append(reciprocal_rank(titles, relevant))
        discounted.append(ndcg_at_k(titles, relevant, 5))
        if set(titles) & relevant != relevant:
            print(f"DEV_ANSWER_MISS {case['kind']} {question[:90]} -> {titles[:4]}")
    abstentions = []
    for case in abstain:
        titles = [item.title for item in select_answerable(case["question"], _PASSAGES)]
        abstentions.append(1.0 if not titles else 0.0)
        if titles:
            print(f"DEV_ANSWER_LEAK {case['kind']} {case['question'][:90]} -> {titles[:4]}")
    print(
        "DEV_ANSWERABLE",
        f"recall={round(mean(recalls), 4)}",
        f"mrr={round(mean(ranks), 4)}",
        f"ndcg={round(mean(discounted), 4)}",
        f"abstain={round(mean(abstentions), 4)}",
        f"retrieve={len(recalls)}",
        f"abstain_n={len(abstain)}",
    )
    assert mean(recalls) >= 0.85
    assert mean(abstentions) >= 0.9


def test_answerable_pipeline_keeps_development_quality(db: Session) -> None:
    user = make_user(db, "evidence-pipeline@example.com")
    organization = make_organization(db, "Feld Eval", f"feld-answer-{uuid.uuid4().hex[:8]}")
    make_membership(db, user, organization, MembershipRole.admin)
    embedder = HashEmbeddingClient()
    for item in DOCUMENTS:
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
        chunk = Chunk(
            organization_id=organization.id,
            document_id=document.id,
            chunk_index=0,
            content=item["text"],
            embedding=hash_embedding(item["text"]),
        )
        db.add(chunk)
        db.flush()
        db.execute(
            update(Chunk)
            .where(Chunk.id == chunk.id)
            .values(search_vector=func.to_tsvector("english", Chunk.content))
        )
    db.commit()
    retrieve = [case for case in DEVELOPMENT if case["task"] in {"retrieve", "follow_up"}]
    abstain = [case for case in DEVELOPMENT if case["task"] == "abstain"]
    recalls = []
    ranks = []
    discounted = []
    for case in retrieve:
        question = str(case["question"])
        if case["task"] == "follow_up":
            history = [(str(role), str(text)) for role, text in case["history"]]
            question = rewrite_question(question, history, [])
        titles = [
            row.document_title
            for row in search_chunks(
                db, organization.id, question, embedder, pipeline="answerable"
            )
        ]
        relevant = set(case["relevant"])
        recalls.append(recall_at_k(titles, relevant, 5))
        ranks.append(reciprocal_rank(titles, relevant))
        discounted.append(ndcg_at_k(titles, relevant, 5))
        if set(titles) & relevant != relevant:
            print(f"DEV_DB_MISS {case['kind']} {question[:90]} -> {titles[:4]}")
    abstentions = []
    for case in abstain:
        titles = [
            row.document_title
            for row in search_chunks(
                db, organization.id, str(case["question"]), embedder, pipeline="answerable"
            )
        ]
        abstentions.append(1.0 if not titles else 0.0)
        if titles:
            print(f"DEV_DB_LEAK {case['kind']} {str(case['question'])[:90]} -> {titles[:4]}")
    print(
        "DEV_DB",
        f"recall={round(mean(recalls), 4)}",
        f"mrr={round(mean(ranks), 4)}",
        f"ndcg={round(mean(discounted), 4)}",
        f"abstain={round(mean(abstentions), 4)}",
    )
    assert mean(recalls) >= 0.85
    assert mean(abstentions) >= 0.9


def test_private_questions_require_the_stated_fact() -> None:
    directory = PassageView(
        "directory",
        "directory",
        "Ken Orry leads the depot. The work email is ken.orry@orrybeacon.example. "
        "No home address is stored. No telephone is stored.",
    )
    payroll = PassageView("payroll", "payroll", "The depot lead salary is 41000 pounds.")
    phone = PassageView("phone", "phone", "The depot telephone is 07700900421.")
    assert select_answerable("What salary does the depot lead earn?", [directory]) == []
    assert select_answerable("What is Ken Orry's mobile number?", [directory]) == []
    assert select_answerable("What is Ken Orry's home address?", [directory]) == []
    paid = select_answerable("What salary does the depot lead earn?", [payroll])
    assert [item.key for item in paid] == ["payroll"]
    found = select_answerable("What is the depot telephone?", [phone])
    assert [item.key for item in found] == ["phone"]


def test_freezer_question_uses_the_frozen_room_passage() -> None:
    room = PassageView(
        "temp",
        "temp",
        "The frozen paint store is held at minus 4 degrees Celsius.",
    )
    found = select_answerable("What temperature is the freezer kept at?", [room])
    assert [item.key for item in found] == ["temp"]


def test_multi_part_question_keeps_each_supported_document() -> None:
    bond = PassageView("bond", "bond", "The account bond is 500 pounds.")
    invoice = PassageView(
        "invoice",
        "invoice",
        "Invoices are due within 30 days. The late fee is 2 percent.",
    )
    yard = PassageView("yard", "yard", "The yard at 9 Dock Street holds 15 containers.")
    titles = [
        item.key
        for item in select_answerable(
            "What is the account bond and when are yard invoices due?",
            [bond, invoice, yard],
        )
    ]
    assert set(titles) == {"bond", "invoice"}


def test_two_part_history_question_keeps_current_and_superseded_cards() -> None:
    titles = [
        item.title
        for item in select_answerable(
            "When does the current rate start, and when did the old rate end?",
            _PASSAGES,
        )
    ]
    assert "feld-rate-2026" in titles
    assert "feld-rate-2024" in titles
