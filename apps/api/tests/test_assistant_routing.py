from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.assistant.prompts import MAX_HISTORY_MESSAGES, render_history
from app.domains.assistant.routing import Intent, parse_classifier_intent, route_question
from app.domains.assistant.service import NO_RECORDS
from app.domains.identity.models import MembershipRole
from app.integrations.language import get_chat_client, get_embedding_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_assistant import _process_ingestion
from tests.test_crm import _csrf, _org


def test_clear_questions_route_without_a_model() -> None:
    assert route_question("What can you help me with?", has_history=False) is Intent.capability
    assert route_question("What can ATLAS help me with?", has_history=False) is Intent.capability
    assert route_question("What can I do in ATLAS?", has_history=False) is Intent.capability
    assert route_question("How do approvals work?", has_history=False) is Intent.capability
    assert route_question("What information do you have?", has_history=False) is Intent.inventory
    assert route_question("Which companies are in my CRM?", has_history=False) is Intent.companies
    assert route_question("What documents are available?", has_history=False) is Intent.documents
    assert route_question("Show my recent inquiries.", has_history=False) is Intent.inquiries
    assert route_question("What leads need attention?", has_history=False) is Intent.leads
    assert route_question("What did we discuss earlier?", has_history=True) is Intent.recall
    assert route_question("Please delete the North pier lead", has_history=False) is Intent.mutation
    assert route_question("Summarize the lead Harbor Desk", has_history=False) is Intent.summary
    assert (
        route_question("Draft a follow-up for Harbor Desk", has_history=False) is Intent.follow_up
    )
    assert (
        route_question("Request an appointment for Harbor Desk", has_history=False)
        is Intent.appointment
    )
    assert (
        route_question("Create a follow-up task for Harbor Desk", has_history=False) is Intent.task
    )
    assert route_question("Send the customer an email", has_history=False) is Intent.mutation
    assert route_question("Hello", has_history=False) is Intent.greeting
    assert parse_classifier_intent('{"intent":"general"}') is Intent.general
    assert parse_classifier_intent("not json") is None


def test_history_keeps_the_latest_turns_and_drops_the_oldest() -> None:
    turns = [("user", f"question {index}") for index in range(20)]
    rendered = render_history(turns)
    assert "question 19" in rendered
    assert "question 0" not in rendered
    assert rendered.count("User:") <= MAX_HISTORY_MESSAGES


class ForbiddenChat:
    def ensure_configured(self) -> None:
        raise AssertionError("this turn must not call the model")

    def complete(self, system: str, user: str) -> str:
        raise AssertionError("this turn must not call the model")

    def stream(self, system: str, user: str) -> Iterator[str]:
        if False:
            yield ""
        raise AssertionError("this turn must not call the model")


class CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return HashEmbeddingClient().embed(texts)


class SpyChat:
    def __init__(self) -> None:
        self.prompts: list[tuple[str, str]] = []

    def ensure_configured(self) -> None:
        return None

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        return "Grounded answer from the supplied company records."

    def stream(self, system: str, user: str) -> Iterator[str]:
        yield self.complete(system, user)


def _session(
    client: TestClient, db: Session, email: str, org_name: str, slug: str
) -> tuple[str, dict[str, str]]:
    user = make_user(db, email)
    org = make_organization(db, org_name, slug)
    make_membership(db, user, org, MembershipRole.admin)
    logged_in = login(client, email, PASSWORD)
    return _org(logged_in), _csrf(logged_in)


def _ask(
    client: TestClient,
    org: str,
    headers: dict[str, str],
    content: str,
    conversation: str | None = None,
) -> dict[str, object]:
    if conversation is None:
        created = client.post(
            f"/api/v1/organizations/{org}/conversations", json={}, headers=headers
        )
        assert created.status_code == 201, created.text
        conversation = created.json()["id"]
    response = client.post(
        f"/api/v1/organizations/{org}/conversations/{conversation}/messages",
        json={"content": content},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    body["conversation_id"] = conversation
    return body


def test_capability_inventory_and_records_do_not_call_the_model(
    client: TestClient, db: Session
) -> None:
    embedder = CountingEmbedder()
    client.app.dependency_overrides[get_embedding_client] = lambda: embedder
    client.app.dependency_overrides[get_chat_client] = lambda: ForbiddenChat()
    org, headers = _session(client, db, "ada@example.com", "Atlas Demo", "atlas-demo")
    company = client.post(
        f"/api/v1/organizations/{org}/companies",
        json={"name": "Harbor & Co.", "industry": "Logistics"},
        headers=headers,
    )
    assert company.status_code == 201, company.text
    uploaded = client.post(
        f"/api/v1/organizations/{org}/documents",
        files={"file": ("cedar-brochure.txt", b"UNIQUEBODYTOKEN pallet storage.", "text/plain")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    _process_ingestion()
    ready = client.get(f"/api/v1/organizations/{org}/documents/{uploaded.json()['id']}")
    assert ready.json()["status"] == "ready"
    after_index = embedder.calls
    won = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "Closed warehouse", "status": "won"},
        headers=headers,
    )
    assert won.status_code == 201, won.text
    open_lead = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "Open dock inquiry", "status": "new", "notes": "Needs a reply."},
        headers=headers,
    )
    assert open_lead.status_code == 201, open_lead.text
    inquiry = client.post(
        f"/api/v1/organizations/{org}/inquiries",
        json={"subject": "South shed rates", "body": "Ask about the south shed."},
        headers=headers,
    )
    assert inquiry.status_code == 201, inquiry.text

    capability = _ask(client, org, headers, "What can you help me with?")
    assert "What I can help with" in capability["message"]["content"]
    assert "approve" in capability["message"]["content"].lower()
    assert NO_RECORDS not in capability["message"]["content"]
    assert capability["document_search"] == "skipped"
    assert capability["message"]["sources"] == []

    inventory = _ask(client, org, headers, "What information do you have?")
    assert "Harbor & Co." in inventory["message"]["content"]
    assert "cedar-brochure" in inventory["message"]["content"]
    assert "UNIQUEBODYTOKEN" not in inventory["message"]["content"]
    assert NO_RECORDS not in inventory["message"]["content"]
    kinds = {item["kind"] for item in inventory["message"]["sources"]}
    assert kinds == {"crm", "document"}

    companies = _ask(client, org, headers, "Which companies are in my CRM?")
    assert "Harbor & Co." in companies["message"]["content"]
    assert all(item["kind"] == "crm" for item in companies["message"]["sources"])

    documents = _ask(client, org, headers, "What documents are available?")
    assert "cedar-brochure" in documents["message"]["content"]
    assert "ready" in documents["message"]["content"]
    assert "UNIQUEBODYTOKEN" not in documents["message"]["content"]

    inquiries = _ask(client, org, headers, "Show my recent inquiries.")
    assert "South shed rates" in inquiries["message"]["content"]

    leads = _ask(client, org, headers, "What leads need attention?")
    assert "Open dock inquiry" in leads["message"]["content"]
    assert "Closed warehouse" not in leads["message"]["content"]

    approvals = _ask(client, org, headers, "How do approvals work?")
    assert "execute" in approvals["message"]["content"].lower()
    assert embedder.calls == after_index


def test_follow_up_uses_conversation_and_retrieves_again(client: TestClient, db: Session) -> None:
    spy = SpyChat()
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    client.app.dependency_overrides[get_chat_client] = lambda: spy
    org, headers = _session(client, db, "ada@example.com", "Atlas Demo", "atlas-demo")
    uploaded = client.post(
        f"/api/v1/organizations/{org}/documents",
        files={
            "file": (
                "cedar-brochure.txt",
                b"Cedar & Pine Logistics offers pallet storage in a bonded yard.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    _process_ingestion()
    first = _ask(client, org, headers, "What does Cedar & Pine Logistics offer?")
    assert first["message"]["content"] == "Grounded answer from the supplied company records."
    assert first["message"]["sources"] == []
    conversation = str(first["conversation_id"])
    second = _ask(
        client,
        org,
        headers,
        "What does the document you mentioned say?",
        conversation,
    )
    assert second["message"]["sources"] == []
    between = _ask(client, org, headers, "What can you help me with?", conversation)
    assert between["message"]["sources"] == []
    third = _ask(client, org, headers, "What does the document you mentioned say?", conversation)
    assert third["message"]["sources"] == []
    assert len(spy.prompts) == 3
    system, prompt = spy.prompts[1]
    assert "not company evidence" in system
    assert "json" not in system.lower()
    conversation_section, evidence = prompt.split("DOCUMENT EXCERPTS", maxsplit=1)
    assert "What does Cedar & Pine Logistics offer?" in conversation_section
    assert "Grounded answer from the supplied company records." in conversation_section
    excerpt = evidence.split("QUESTION:", maxsplit=1)[0]
    assert "bonded yard" in excerpt
    assert "Grounded answer from the supplied company records." not in excerpt

    other = client.post(f"/api/v1/organizations/{org}/conversations", json={}, headers=headers)
    before = len(spy.prompts)
    isolated = _ask(
        client,
        org,
        headers,
        "What does the document you mentioned say?",
        other.json()["id"],
    )
    if len(spy.prompts) > before:
        assert "What does Cedar & Pine Logistics offer?" not in spy.prompts[-1][1]
    else:
        assert "could not find" in isolated["message"]["content"].lower()
        assert isolated["message"]["sources"] == []


def test_unsupported_fact_is_refused_and_a_write_does_not_change_crm(
    client: TestClient, db: Session
) -> None:
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    client.app.dependency_overrides[get_chat_client] = lambda: ForbiddenChat()
    org, headers = _session(client, db, "ada@example.com", "Atlas Demo", "atlas-demo")
    uploaded = client.post(
        f"/api/v1/organizations/{org}/documents",
        files={
            "file": (
                "harbor-services.txt",
                b"Harbor warehousing includes cold storage and bonded yards.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    lead = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "North pier expansion", "status": "new", "notes": "keep these notes"},
        headers=headers,
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]

    missing = _ask(client, org, headers, "What is the founder's private home address?")
    assert missing["message"]["sources"] == []
    assert "could not find" in missing["message"]["content"].lower()
    assert "street" not in missing["message"]["content"].lower()

    denied = _ask(client, org, headers, "Please delete the North pier expansion lead")
    assert "read-only" in denied["message"]["content"].lower()
    assert "approve" in denied["message"]["content"].lower()
    assert denied["message"]["sources"] == []
    stored = client.get(f"/api/v1/organizations/{org}/leads/{lead_id}")
    assert stored.status_code == 200
    assert stored.json()["notes"] == "keep these notes"
    assert stored.json()["status"] == "new"


def test_inventory_cannot_see_another_organization(client: TestClient, db: Session) -> None:
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    client.app.dependency_overrides[get_chat_client] = lambda: ForbiddenChat()
    ada = make_user(db, "ada@example.com")
    outsider = make_user(db, "outsider@example.org")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    make_membership(db, ada, atlas, MembershipRole.admin)
    make_membership(db, outsider, northwind, MembershipRole.admin)
    ada_session = login(client, "ada@example.com", PASSWORD)
    org = _org(ada_session)
    headers = _csrf(ada_session)
    company = client.post(
        f"/api/v1/organizations/{org}/companies",
        json={"name": "Harbor & Co.", "industry": "Logistics"},
        headers=headers,
    )
    assert company.status_code == 201, company.text
    visible = _ask(client, org, headers, "Which companies are in my CRM?")
    conversation = str(visible["conversation_id"])
    assert "Harbor & Co." in visible["message"]["content"]

    client.cookies.clear()
    other = login(client, "outsider@example.org", PASSWORD)
    other_org = _org(other)
    other_headers = _csrf(other)
    secret = client.post(
        f"/api/v1/organizations/{other_org}/companies",
        json={"name": "Zephyr Confidential", "industry": "Private"},
        headers=other_headers,
    )
    assert secret.status_code == 201, secret.text
    own = _ask(client, other_org, other_headers, "Which companies are in my CRM?")
    assert "Zephyr Confidential" in own["message"]["content"]
    assert "Harbor & Co." not in own["message"]["content"]
    stolen = client.get(f"/api/v1/organizations/{other_org}/conversations/{conversation}")
    assert stolen.status_code == 404
    assert "Harbor" not in stolen.text
    crossed = client.post(
        f"/api/v1/organizations/{org}/conversations/{conversation}/messages",
        json={"content": "Which companies are in my CRM?"},
        headers=other_headers,
    )
    assert crossed.status_code == 404
    assert "Zephyr" not in crossed.text
    assert "Harbor" not in crossed.text


def test_recall_uses_this_conversation_only(client: TestClient, db: Session) -> None:
    client.app.dependency_overrides[get_chat_client] = lambda: ForbiddenChat()
    org, headers = _session(client, db, "ada@example.com", "Atlas Demo", "atlas-demo")
    first = _ask(client, org, headers, "What can I do in ATLAS?")
    recalled = _ask(
        client,
        org,
        headers,
        "What did we discuss earlier?",
        str(first["conversation_id"]),
    )
    assert "What can I do in ATLAS?" in recalled["message"]["content"]
    assert recalled["message"]["sources"] == []
    fresh = _ask(client, org, headers, "What did we discuss earlier?")
    assert "have not discussed" in fresh["message"]["content"].lower()
    long_id = str(first["conversation_id"])
    for _ in range(6):
        _ask(client, org, headers, "How do approvals work?", long_id)
    later = _ask(client, org, headers, "What did we discuss earlier?", long_id)
    assert "What can I do in ATLAS?" in later["message"]["content"]


def test_capability_stream_reports_preparing_and_not_a_search(
    client: TestClient, db: Session
) -> None:
    client.app.dependency_overrides[get_chat_client] = lambda: ForbiddenChat()
    org, headers = _session(client, db, "ada@example.com", "Atlas Demo", "atlas-demo")
    created = client.post(f"/api/v1/organizations/{org}/conversations", json={}, headers=headers)
    streamed = client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages/stream",
        json={"content": "What can you help me with?"},
        headers=headers,
    )
    assert streamed.status_code == 200, streamed.text
    assert '"phase": "preparing"' in streamed.text
    assert "searching_crm" not in streamed.text
    assert "retrieving_documents" not in streamed.text
    assert "What I can help with" in streamed.text
    assert "event: done" in streamed.text


def test_general_stream_still_sends_tokens_as_they_arrive(client: TestClient, db: Session) -> None:
    class Pieces:
        def ensure_configured(self) -> None:
            return None

        def complete(self, system: str, user: str) -> str:
            return "One warehouse."

        def stream(self, system: str, user: str) -> Iterator[str]:
            yield "One "
            yield "warehouse."

    client.app.dependency_overrides[get_chat_client] = lambda: Pieces()
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    org, headers = _session(client, db, "ada@example.com", "Atlas Demo", "atlas-demo")
    created = client.post(f"/api/v1/organizations/{org}/conversations", json={}, headers=headers)
    streamed = client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages/stream",
        json={"content": "Tell me a joke about a warehouse."},
        headers=headers,
    )
    assert streamed.status_code == 200, streamed.text
    assert '"phase": "streaming"' in streamed.text
    assert "verifying" not in streamed.text
    assert '"text": "One "' in streamed.text
    assert streamed.text.index('"text": "One "') < streamed.text.index("event: done")


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Update the lead notes", Intent.mutation),
        ("Thanks", Intent.greeting),
        ("Summarize the company information you can access.", Intent.inventory),
    ],
)
def test_more_routes(question: str, intent: Intent) -> None:
    assert route_question(question, has_history=False) is intent
