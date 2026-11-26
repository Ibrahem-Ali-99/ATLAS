import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.service import claim_ingestion_job, run_ingestion_job
from app.integrations.language import get_embedding_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org


@pytest.fixture
def embedded_client(client: TestClient) -> TestClient:
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    return client


def _process_one() -> None:
    worker_id = f"test-worker-{uuid.uuid4()}"
    job = claim_ingestion_job(worker_id)
    assert job is not None
    run_ingestion_job(job, worker_id, HashEmbeddingClient())


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
    _process_one()
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


def test_replace_archive_and_duplicate_keep_search_current(
    embedded_client: TestClient, db: Session
) -> None:
    user = make_user(db, "librarian@example.com")
    outsider = make_user(db, "library-out@example.org")
    atlas = make_organization(db, "Knowledge Library", "knowledge-library")
    other = make_organization(db, "Other Library", "other-library")
    make_membership(db, user, atlas, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    session = login(embedded_client, "librarian@example.com", PASSWORD)
    headers = _csrf(session)
    org = _org(session)
    original = b"kelp-yard-7744 holds the spare tide chart."
    uploaded = embedded_client.post(
        f"/api/v1/organizations/{org}/documents",
        files={"file": ("tide-chart.txt", original, "text/plain")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    duplicate = embedded_client.post(
        f"/api/v1/organizations/{org}/documents",
        files={"file": ("tide-chart-copy.txt", original, "text/plain")},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_document"
    _process_one()
    preview = embedded_client.get(f"/api/v1/organizations/{org}/documents/{document_id}/preview")
    assert preview.status_code == 200
    assert "spare tide chart" in preview.json()["excerpt"]
    same = embedded_client.post(
        f"/api/v1/organizations/{org}/documents/{document_id}/content",
        files={"file": ("tide-chart.txt", original, "text/plain")},
        headers=headers,
    )
    assert same.status_code == 200
    assert same.json()["status"] == "ready"
    replaced = embedded_client.post(
        f"/api/v1/organizations/{org}/documents/{document_id}/content",
        files={
            "file": (
                "tide-chart.txt",
                b"kelp-yard-7744 moved the spare tide chart to locker nine.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert replaced.status_code == 200
    assert replaced.json()["status"] == "pending"
    _process_one()
    stale = embedded_client.get(
        f"/api/v1/organizations/{org}/documents/search", params={"q": "holds the spare"}
    )
    assert stale.json()["items"] == []
    current = embedded_client.get(
        f"/api/v1/organizations/{org}/documents/search", params={"q": "locker nine"}
    )
    assert current.json()["items"]
    assert current.json()["items"][0]["document_id"] == document_id
    archived = embedded_client.post(
        f"/api/v1/organizations/{org}/documents/{document_id}/archive", headers=headers
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"]
    hidden = embedded_client.get(f"/api/v1/organizations/{org}/documents")
    assert document_id not in [item["id"] for item in hidden.json()["items"]]
    listed = embedded_client.get(
        f"/api/v1/organizations/{org}/documents", params={"include_archived": True}
    )
    assert document_id in [item["id"] for item in listed.json()["items"]]
    after_archive = embedded_client.get(
        f"/api/v1/organizations/{org}/documents/search", params={"q": "locker nine"}
    )
    assert after_archive.json()["items"] == []
    restored = embedded_client.post(
        f"/api/v1/organizations/{org}/documents/{document_id}/restore", headers=headers
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert restored.json()["status"] == "pending"
    _process_one()
    found = embedded_client.get(
        f"/api/v1/organizations/{org}/documents/search", params={"q": "locker nine"}
    )
    assert found.json()["items"][0]["document_id"] == document_id
    embedded_client.cookies.clear()
    login(embedded_client, "library-out@example.org", PASSWORD)
    hidden_document = embedded_client.get(f"/api/v1/organizations/{org}/documents/{document_id}")
    assert hidden_document.status_code == 404
