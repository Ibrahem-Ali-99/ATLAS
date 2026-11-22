"""Citation precision on a fixed set of passages. Rank is not the gold label."""

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from app.domains.knowledge.attribution import QUALIFIED_ANSWER, attribute_answer
from app.integrations.language import get_chat_client, get_embedding_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org

YARD = "Acceptance Yard stores 42 bonded pallets. Token YARD-42-PALLETS."
CEDAR = "Cedar brochure offers 180 pallets of general freight."
LEAD = "Acceptance pier. Status: qualified. Asked about bonded pallet capacity."
NOISE = "Cedar mailing. Status: new. Brochure mailing list for Cedar."
CONTACT = "Nora Yard. nora.yard@example.com"
PASSAGES = [
    ("yard", YARD),
    ("cedar", CEDAR),
    ("lead", LEAD),
    ("noise", NOISE),
    ("contact", CONTACT),
]


class _FactChat:
    def ensure_configured(self) -> None:
        return None

    def complete(self, system: str, user: str) -> str:
        question = user.split("QUESTION:", 1)[-1].lower()
        if "street address" in question:
            return "The address is 99 Main Street."
        return "Acceptance Yard stores 42 bonded pallets."

    def stream(self, system: str, user: str) -> Iterator[str]:
        yield self.complete(system, user)


def test_citation_metrics_cover_exact_paraphrase_conflict_and_unsupported() -> None:
    cases = [
        (
            "How many bonded pallets does Acceptance Yard store?",
            "Acceptance Yard stores 42 bonded pallets.",
            {"yard"},
            None,
        ),
        (
            "What is the bonded pallet capacity?",
            "The bonded yard can hold forty-two pallets.",
            {"yard"},
            None,
        ),
        (
            "What is the yard token?",
            "The yard token is YARD-42-PALLETS.",
            {"yard"},
            None,
        ),
        (
            "What about storage?",
            "The records do not state a specific capacity.",
            set(),
            None,
        ),
        (
            "What is the street address of the yard?",
            "The address is 99 Main Street.",
            set(),
            QUALIFIED_ANSWER,
        ),
        (
            "What pallet counts are listed?",
            "Acceptance Yard stores 42 pallets and the Cedar brochure lists 180.",
            {"yard", "cedar"},
            None,
        ),
        (
            "What is Nora's email?",
            "Nora's email is nora.yard@example.com.",
            {"contact"},
            None,
        ),
        (
            "How many pallets are stored, and what is the lead status?",
            "There are 42 pallets. The lead is qualified.",
            {"yard", "lead"},
            None,
        ),
        (
            "What token was that?",
            "The token is YARD-42-PALLETS.",
            {"yard"},
            None,
        ),
        (
            "What does the Cedar brochure offer?",
            "The Cedar brochure offers 180 pallets of general freight.",
            {"cedar"},
            None,
        ),
    ]
    correct = 0
    cited_total = 0
    gold_total = 0
    true_positive = 0
    unsupported = 0
    for question, answer, gold, expected in cases:
        stored, cited = attribute_answer(question, answer, PASSAGES)
        cited_ids = set(cited)
        assert cited_ids <= {passage_id for passage_id, _text in PASSAGES}
        if expected is None:
            correct += int(stored == answer)
        else:
            correct += int(stored == expected)
        cited_total += len(cited_ids)
        gold_total += len(gold)
        true_positive += len(cited_ids & gold)
        unsupported += len(cited_ids - gold)
        if gold == {"yard"}:
            assert "cedar" not in cited_ids
            assert "noise" not in cited_ids

    assert (correct, len(cases)) == (10, 10)
    assert (true_positive, cited_total) == (10, 10)
    assert (true_positive, gold_total) == (10, 10)
    assert (unsupported, cited_total) == (0, 10)


def test_assistant_cites_the_42_pallet_passage_and_not_the_brochure(
    client: TestClient, db: Session
) -> None:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    client.app.dependency_overrides[get_chat_client] = lambda: _FactChat()
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    for name, body in (
        ("acceptance-yard.txt", YARD.encode()),
        ("cedar-brochure.txt", CEDAR.encode()),
    ):
        uploaded = client.post(
            f"/api/v1/organizations/{org}/documents",
            files={"file": (name, body, "text/plain")},
            headers=headers,
        )
        assert uploaded.status_code == 201, uploaded.text
        ready = client.get(f"/api/v1/organizations/{org}/documents/{uploaded.json()['id']}")
        assert ready.json()["status"] == "ready"
    created = client.post(
        f"/api/v1/organizations/{org}/conversations", json={"title": "Yard"}, headers=headers
    )
    assert created.status_code == 201, created.text
    reply = client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages",
        json={"content": "How many bonded pallets does Acceptance Yard store?"},
        headers=headers,
    )
    assert reply.status_code == 200, reply.text
    message = reply.json()["message"]
    assert message["content"] == "Acceptance Yard stores 42 bonded pallets."
    titles = [source["title"] for source in message["sources"]]
    assert len(titles) == 1
    assert titles[0].startswith("acceptance-yard")
    assert all("cedar" not in title.lower() for title in titles)
    assert all(source["chunk_id"] for source in message["sources"])
    refused = client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages",
        json={"content": "What is the street address of the yard?"},
        headers=headers,
    )
    assert refused.status_code == 200, refused.text
    refused_message = refused.json()["message"]
    assert "99" not in refused_message["content"]
    assert refused_message["sources"] == []


class _SplitDraft:
    def __init__(self) -> None:
        self.calls = 0

    def ensure_configured(self) -> None:
        return None

    def complete(self, system: str, user: str) -> str:
        return "".join(self.stream(system, user))

    def stream(self, system: str, user: str) -> Iterator[str]:
        self.calls += 1
        if self.calls > 1:
            yield "The yard stores "
            yield "99"
            yield " extra pallets."
            return
        yield "Acceptance Yard stores "
        yield "42 bonded pallets."


def test_grounded_stream_emits_the_verified_answer_only(client: TestClient, db: Session) -> None:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    draft = _SplitDraft()
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    client.app.dependency_overrides[get_chat_client] = lambda: draft
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    uploaded = client.post(
        f"/api/v1/organizations/{org}/documents",
        files={"file": ("acceptance-yard.txt", YARD.encode(), "text/plain")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    created = client.post(
        f"/api/v1/organizations/{org}/conversations", json={"title": "Stream"}, headers=headers
    )
    supported = client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages/stream",
        json={"content": "How many bonded pallets does Acceptance Yard store?"},
        headers=headers,
    )
    assert supported.status_code == 200, supported.text
    assert '"phase": "verifying"' in supported.text
    assert supported.text.index('"phase": "verifying"') < supported.text.index("event: token")
    assert '"text": "Acceptance Yard stores "' not in supported.text
    assert '"text": "Acceptance Yard stores 42 bonded pallets."' in supported.text
    refused = client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages/stream",
        json={"content": "How many bonded pallets does Acceptance Yard store?"},
        headers=headers,
    )
    assert refused.status_code == 200, refused.text
    assert '"text": "The yard stores "' not in refused.text
    assert '"text": "99"' not in refused.text
    assert f'"text": "{QUALIFIED_ANSWER}"' in refused.text
    done = refused.text.rsplit("event: done\n", 1)[-1]
    assert QUALIFIED_ANSWER in done
    assert "99 extra pallets" not in done
