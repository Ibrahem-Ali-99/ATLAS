"""Business questions use the matching workspace tool, not the document library."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from app.integrations.language import get_chat_client, get_embedding_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_assistant import _process_ingestion
from tests.test_assistant_routing import ForbiddenChat
from tests.test_crm import _csrf, _org


def test_customers_employees_and_leads_skip_the_document_library(
    client: TestClient, db: Session
) -> None:
    admin = make_user(db, "ada@example.com", full_name="Ada Lovelace")
    colleague = make_user(db, "mina@example.com", full_name="Mina Patel")
    outsider = make_user(db, "outsider@example.org", full_name="Other Person")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, colleague, atlas, MembershipRole.staff)
    make_membership(db, outsider, northwind, MembershipRole.admin)
    client.app.dependency_overrides[get_chat_client] = lambda: ForbiddenChat()
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    company = client.post(
        f"/api/v1/organizations/{org}/companies",
        json={"name": "Harbor & Co.", "industry": "Logistics"},
        headers=headers,
    )
    assert company.status_code == 201, company.text
    open_lead = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "Open dock inquiry", "status": "new", "notes": "Needs a reply."},
        headers=headers,
    )
    assert open_lead.status_code == 201, open_lead.text
    won = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "Closed warehouse", "status": "won"},
        headers=headers,
    )
    assert won.status_code == 201, won.text
    uploaded = client.post(
        f"/api/v1/organizations/{org}/documents",
        files={
            "file": (
                "shortage-claim.txt",
                b"Shortage claims require a pier photo and a written notice.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    _process_ingestion()

    customers = _ask(client, org, headers, "Who are our customers?")
    assert "Harbor & Co." in customers["content"]
    assert "Shortage claims" not in customers["content"]
    assert customers["tools"] == ["list_companies"]
    assert all(source["kind"] == "crm" for source in customers["sources"])

    people = _ask(client, org, headers, "What are the employee names?")
    assert "Ada Lovelace" in people["content"]
    assert "Mina Patel" in people["content"]
    assert "Other Person" not in people["content"]
    assert "Shortage claims" not in people["content"]
    assert people["tools"] == ["list_members"]

    leads = _ask(client, org, headers, "Which leads should I prioritize?")
    assert "Open dock inquiry" in leads["content"]
    assert "Closed warehouse" not in leads["content"]
    assert leads["tools"] == ["list_leads"]

    follow = _ask(
        client,
        org,
        headers,
        "What about that company?",
        customers["conversation_id"],
    )
    assert "Harbor & Co." in follow["content"]
    assert "Shortage claims" not in follow["content"]

    client.cookies.clear()
    other = login(client, "outsider@example.org", PASSWORD)
    stolen = client.get(
        f"/api/v1/organizations/{_org(other)}/assistant-executions/{customers['execution_id']}",
        headers=_csrf(other),
    )
    assert stolen.status_code == 404


def test_one_company_returns_one_record_and_one_citation(
    client: TestClient, db: Session
) -> None:
    client.app.dependency_overrides[get_chat_client] = lambda: ForbiddenChat()
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    admin = make_user(db, "ada@example.com", full_name="Ada Lovelace")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    for name in ("Harbor & Co.", "Zephyr Mills"):
        created = client.post(
            f"/api/v1/organizations/{org}/companies",
            json={"name": name, "industry": "Logistics"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
    uploaded = client.post(
        f"/api/v1/organizations/{org}/documents",
        files={
            "file": (
                "shortage-claim.txt",
                b"Shortage claims require a pier photo and a written notice.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    _process_ingestion()

    answer = _ask(client, org, headers, "Name one company stored in this workspace")
    assert "Harbor & Co." in answer["content"]
    assert "Zephyr Mills" not in answer["content"]
    assert "Shortage claims" not in answer["content"]
    assert answer["tools"] == ["list_companies"]
    assert len(answer["sources"]) == 1
    assert answer["sources"][0]["kind"] == "crm"
    assert answer["sources"][0]["title"] == "Harbor & Co."


def test_greeting_and_general_knowledge_do_not_search(
    client: TestClient, db: Session
) -> None:
    class Talk:
        def __init__(self) -> None:
            self.systems: list[str] = []

        def ensure_configured(self) -> None:
            return None

        def complete(self, system: str, user: str) -> str:
            self.systems.append(system)
            if "capital" in user.lower():
                return "Paris is the capital of France. That is general knowledge."
            if "240" in user and "15%" in user:
                return "204 pallets remain. That figure is arithmetic, not a company record."
            return "Hi. What are you working on?"

        def stream(self, system: str, user: str):
            yield self.complete(system, user)

    embedder = HashEmbeddingClient()
    talk = Talk()
    client.app.dependency_overrides[get_chat_client] = lambda: talk
    client.app.dependency_overrides[get_embedding_client] = lambda: embedder
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)

    greeting = _ask(client, org, headers, "Hello")
    assert greeting["content"] == "Hi. What are you working on?"
    assert "What I can help with" not in greeting["content"]
    assert greeting["sources"] == []
    assert greeting["tools"] == []
    assert talk.systems
    assert "capability" not in talk.systems[0].lower()

    before = embedder.calls if hasattr(embedder, "calls") else 0
    order = _ask(
        client,
        org,
        headers,
        "A customer orders 240 pallets and cancels 15% of the order. How many remain?",
    )
    assert "204" in order["content"]
    assert order["sources"] == []
    assert order["tools"] == []

    capital = _ask(client, org, headers, "What is the capital of France?")
    assert "Paris" in capital["content"]
    assert capital["sources"] == []
    assert capital["tools"] == []
    assert not hasattr(embedder, "calls") or embedder.calls == before


def test_compare_and_overdue_select_business_tools() -> None:
    from app.domains.assistant.planner import asks_for_several_sources, plan_request

    decision = plan_request("Compare our customers, open leads, and business performance", [])
    names = [name for name, _arguments in decision.tools]
    assert names == ["list_companies", "list_leads", "business_analytics"]
    overdue = plan_request("What work is overdue?", [])
    assert overdue.tools == [("list_tasks", {"overdue_only": True})]
    assert asks_for_several_sources("Compare our customers and the open leads")
    followed = plan_request(
        "What about that company?",
        [("user", "What does the bonded warehousing note say?")],
    )
    assert [name for name, _arguments in followed.tools] == ["list_companies"]
    from app.domains.assistant.routing import asks_for_stored_appointment

    assert not asks_for_stored_appointment(
        "Check whether Monday morning is open on the calendar."
    )
    assert asks_for_stored_appointment("Which appointments are stored?")
    one = plan_request("Name one company stored in this workspace", [])
    assert one.tools == [("list_companies", {"query": "", "limit": 1})]
    assert one.general is False
    hello = plan_request("Hello", [])
    assert hello.general is True
    assert hello.tools == []
    capital = plan_request("What is the capital of France?", [])
    assert capital.general is True
    assert capital.tools == []
    writing = plan_request("Write two sentences about why clear invoices matter.", [])
    assert writing.general is True
    freezer = plan_request("What temperature is the freezer kept at?", [])
    assert [name for name, _arguments in freezer.tools] == ["search_knowledge"]
    from app.domains.assistant.prompts import general_prompt
    from app.domains.assistant.routing import Intent, route_question

    pallet = (
        "A customer orders 240 pallets and cancels 15% of the order. How many remain?"
    )
    reasoning = plan_request(pallet, [])
    assert reasoning.general is True
    assert reasoning.tools == []
    assert route_question(pallet, has_history=False) is Intent.general
    assert "204" in general_prompt(pallet, [])
    yard = plan_request("How many pallets does the bonded yard hold?", [])
    assert [name for name, _arguments in yard.tools] == ["search_knowledge"]
    rate = plan_request("What is 15% of our frozen pallet rate?", [])
    assert rate.general is False
    assert [name for name, _arguments in rate.tools] == ["search_knowledge"]
    insurance = plan_request(
        "What is the cargo insurance occurrence limit and the deductible?",
        [],
    )
    assert insurance.general is False
    assert [name for name, _arguments in insurance.tools] == ["search_knowledge"]
    follow = plan_request(
        "And if they cancel 20% instead?",
        [("user", pallet), ("assistant", "204 remain.")],
    )
    assert follow.general is True
    assert follow.tools == []


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
    message = response.json()["message"]
    runs = client.get(f"/api/v1/organizations/{org}/assistant-executions")
    assert runs.status_code == 200, runs.text
    match = next(item for item in runs.json()["items"] if item["request"] == content)
    return {
        "conversation_id": conversation,
        "content": message["content"],
        "sources": message["sources"],
        "tools": match["tools"],
        "execution_id": match["id"],
        "steps": match["steps"],
    }
