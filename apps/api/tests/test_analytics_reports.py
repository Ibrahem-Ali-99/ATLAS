from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def _org(payload: dict[str, object]) -> str:
    memberships = payload["memberships"]
    assert isinstance(memberships, list)
    first = memberships[0]
    assert isinstance(first, dict)
    return str(first["organization_id"])


def _csrf(payload: dict[str, object]) -> dict[str, str]:
    return {"X-CSRF-Token": str(payload["csrf_token"])}


def test_opportunity_archive_and_currency_safe_metrics(client: TestClient, db: Session) -> None:
    admin = make_user(db, "bi@example.com")
    outsider = make_user(db, "bi-out@example.org")
    atlas = make_organization(db, "BI Atlas", "bi-atlas")
    other = make_organization(db, "BI Other", "bi-other")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    ada = login(client, "bi@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    base = f"/api/v1/organizations/{org}"

    won = client.post(
        f"{base}/opportunities",
        json={"title": "Won shelf", "stage": "won", "value": 100, "currency": "USD"},
        headers=headers,
    )
    assert won.status_code == 201, won.text
    lost = client.post(
        f"{base}/opportunities",
        json={"title": "Lost shelf", "stage": "lost", "value": 40, "currency": "EUR"},
        headers=headers,
    )
    assert lost.status_code == 201, lost.text
    blank = client.post(
        f"{base}/opportunities",
        json={"title": "Unpriced shelf", "stage": "new", "currency": "USD"},
        headers=headers,
    )
    assert blank.status_code == 201, blank.text
    hidden = client.post(
        f"{base}/opportunities",
        json={"title": "Archived shelf", "stage": "new", "value": 999, "currency": "USD"},
        headers=headers,
    )
    assert hidden.status_code == 201, hidden.text
    archived = client.delete(f"{base}/opportunities/{hidden.json()['id']}", headers=headers)
    assert archived.status_code == 204, archived.text

    listed = client.get(f"{base}/opportunities")
    titles = {item["title"] for item in listed.json()}
    assert "Archived shelf" not in titles
    assert all(item["archived_at"] is None for item in listed.json())
    stored = client.get(f"{base}/opportunities", params={"include_archived": "true"})
    archived_row = next(item for item in stored.json() if item["title"] == "Archived shelf")
    assert archived_row["archived_at"] is not None

    metrics = client.get(f"{base}/analytics")
    assert metrics.status_code == 200, metrics.text
    sales = metrics.json()["sales"]
    assert sales["opportunities_total"] == 3
    assert sales["win_rate"] == 0.5
    assert sales["loss_rate"] == 0.5
    assert sales["average_won_value"] == 100
    unpriced = next(item for item in sales["by_stage"] if item["stage"] == "new")
    assert unpriced["value"] is None
    assert sales["won"]["value"] is None
    assert metrics.json()["comparison"]["opportunities_created"]["current"] == 3
    assert metrics.json()["comparison"]["previous_period"]["end"]
    assert len(metrics.json()["qualification_trend"]) == metrics.json()["window_days"]
    assert "not stored" in metrics.json()["campaigns"]["definition"]

    exported = client.get(f"{base}/analytics/export", params={"report": "opportunities"})
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "Won shelf" in exported.text
    assert "Archived shelf" not in exported.text
    assert exported.text.startswith("title,stage,currency,value,created_at")
    unknown = client.get(f"{base}/analytics/export", params={"report": "secrets"})
    assert unknown.status_code == 422

    restored = client.post(f"{base}/opportunities/{hidden.json()['id']}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["archived_at"] is None
    visible = client.get(f"{base}/opportunities")
    assert any(item["title"] == "Archived shelf" for item in visible.json())

    client.cookies.clear()
    other_session = login(client, "bi-out@example.org", PASSWORD)
    foreign = client.get(
        f"/api/v1/organizations/{_org(other_session)}/analytics/export",
        params={"report": "opportunities"},
    )
    assert foreign.status_code == 200
    assert "Won shelf" not in foreign.text
