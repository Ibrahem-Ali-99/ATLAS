import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.identity.models import MembershipRole
from app.integrations.language import get_embedding_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org


@pytest.fixture
def embedded_client(client: TestClient) -> TestClient:
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    return client


def test_upload_indexes_text_and_rejects_invalid_files(
    embedded_client: TestClient, db: Session
) -> None:
    user = make_user(db, "ada@example.com")
    outsider = make_user(db, "outsider@example.org")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    other = make_organization(db, "Northwind", "northwind")
    make_membership(db, user, atlas, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    ada = login(embedded_client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    uploaded = embedded_client.post(
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
    document_id = uploaded.json()["id"]
    ready = embedded_client.get(f"/api/v1/organizations/{org}/documents/{document_id}")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    found = embedded_client.get(
        f"/api/v1/organizations/{org}/documents/search",
        params={"q": "cold storage"},
    )
    assert found.status_code == 200, found.text
    assert found.json()["items"]
    assert "cold storage" in found.json()["items"][0]["content"]
    assert found.json()["items"][0]["document_title"] == "harbor-services"

    rejected = embedded_client.post(
        f"/api/v1/organizations/{org}/documents",
        files={"file": ("notes.exe", b"MZ", "application/octet-stream")},
        headers=headers,
    )
    assert rejected.status_code == 415
    model_file = embedded_client.post(
        f"/api/v1/organizations/{org}/documents",
        files={"file": ("lead-model.joblib", b"not-a-document", "application/octet-stream")},
        headers=headers,
    )
    assert model_file.status_code == 415
    oversized = embedded_client.post(
        f"/api/v1/organizations/{org}/documents",
        files={"file": ("big.txt", b"a" * (get_settings().max_upload_bytes + 1), "text/plain")},
        headers=headers,
    )
    assert oversized.status_code == 413

    embedded_client.cookies.clear()
    login(embedded_client, "outsider@example.org", PASSWORD)
    hidden = embedded_client.get(f"/api/v1/organizations/{org}/documents/{document_id}")
    assert hidden.status_code == 404
