import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.crm.service import create_inquiry, create_lead
from app.domains.identity.models import MembershipRole
from app.domains.integrations.calendar_models import (
    GoogleCalendarAuthorization,
    GoogleCalendarConnection,
)
from app.integrations import google_calendar
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def test_google_calendar_oauth_booking_cancellation_and_disconnect(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "google_calendar_client_id", "fixture-client")
    monkeypatch.setattr(settings, "google_calendar_client_secret", "fixture-secret")
    monkeypatch.setattr(
        settings,
        "google_calendar_redirect_uri",
        "https://atlas.example.net/api/v1/calendar/google/callback",
    )
    monkeypatch.setattr(settings, "google_calendar_web_origin", "https://atlas.example.net")
    org = make_organization(db, "Calendar workspace", "calendar-workspace")
    admin = make_user(db, "calendar-admin@example.com")
    other = make_user(db, "other-calendar-admin@example.com")
    for user in (admin, other):
        make_membership(db, user, org, MembershipRole.admin)
    root = f"/api/v1/organizations/{org.id}"
    auth = _csrf(login(client, admin.email, PASSWORD))
    started = client.post(f"{root}/calendar/google/connect", headers=auth)
    assert started.status_code == 200, started.text
    query = parse_qs(urlsplit(started.json()["url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    assert db.get(GoogleCalendarAuthorization, hashlib.sha256(state.encode()).hexdigest())
    callback = "/api/v1/calendar/google/callback"
    issued_session = dict(client.cookies)
    login(client, other.email, PASSWORD)
    assert client.get(callback, params={"state": state, "code": "fixture"}).status_code == 400
    client.cookies.clear()
    client.cookies.update(issued_session)

    events = {}
    methods = []
    busy = False
    expired = False

    def oauth(url, *, data, timeout):
        if url == "https://oauth2.googleapis.com/revoke":
            assert data == {"token": "fixture-refresh"}
            return httpx.Response(200)
        assert url == "https://oauth2.googleapis.com/token"
        tokens = {"access_token": "fixture-access"}
        if data["grant_type"] == "authorization_code":
            assert len(data["code_verifier"]) > 43
            tokens.update({"refresh_token": "fixture-refresh", "scope": query["scope"][0]})
        else:
            assert data["refresh_token"] == "fixture-refresh"
            if expired:
                return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json=tokens)

    def request(method, url, *, headers, json, timeout):
        assert headers["Authorization"] == "Bearer fixture-access"
        if url.endswith("/users/me/calendarList/primary"):
            return httpx.Response(
                200,
                json={
                    "id": "calendar@example.com",
                    "summary": "Customer appointments",
                    "accessRole": "owner",
                },
            )
        if url.endswith("/freeBusy"):
            return httpx.Response(
                200,
                json={
                    "calendars": {
                        "calendar@example.com": {"busy": [{"start": "now"}] if busy else []},
                    }
                },
            )
        methods.append(method)
        event_id = url.rsplit("/", 1)[1]
        if method == "POST":
            events[json["id"]] = json
            return httpx.Response(200, json=json)
        if method == "DELETE":
            events.pop(event_id)
            return httpx.Response(204)
        return (
            httpx.Response(200, json=events[event_id])
            if event_id in events
            else httpx.Response(404)
        )

    monkeypatch.setattr(google_calendar.httpx, "post", oauth)
    monkeypatch.setattr(google_calendar.httpx, "request", request)
    got = client.get(callback, params={"state": state, "code": "fixture"}, follow_redirects=False)
    assert got.status_code == 303 and got.headers["location"].endswith("calendar=connected")
    assert client.get(callback, params={"state": state, "code": "fixture"}).status_code == 400
    assert db.get(GoogleCalendarConnection, org.id).encrypted_token != "fixture-refresh"
    lead = create_lead(db, org.id, admin.id, {"title": "Storage", "status": "new"})
    create_inquiry(db, org.id, {"subject": "Request", "body": "Book a tour", "lead_id": lead.id})
    start = datetime.now(UTC) + timedelta(days=1)
    times = {"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=1)).isoformat()}
    busy = True
    assert client.post(f"{root}/calendar/availability", json=times, headers=auth).json() == {
        "available": False,
        "provider": "google",
    }
    expired = True
    assert client.post(f"{root}/calendar/availability", json=times, headers=auth).status_code == 409
    assert (
        client.get(f"{root}/calendar/google").json()["connection_error"]
        == "calendar_reconnect_required"
    )
    expired = False
    busy = False
    assert client.post(f"{root}/calendar/availability", json=times, headers=auth).json()[
        "available"
    ]
    assert client.get(f"{root}/calendar/google").json()["connection_error"] is None
    submitted = client.post(
        f"{root}/calendar/requests", headers=auth, json={**times, "lead_id": str(lead.id)}
    )
    assert submitted.status_code == 201, submitted.text
    approval = submitted.json()["approval_id"]
    assert not events
    assert client.post(f"{root}/approvals/{approval}/approve", headers=auth).status_code == 200
    executed = client.post(f"{root}/approvals/{approval}/execute", headers=auth)
    assert executed.status_code == 200, executed.text
    booking = executed.json()["execution_result"]["booking_id"]
    assert len(events) == 1 and methods.count("POST") == 1
    cancelled = client.post(f"{root}/calendar/bookings/{booking}/cancel", headers=auth)
    assert cancelled.status_code == 200 and not events
    assert client.post(f"{root}/calendar/google/disconnect", headers=auth).json() == {
        "grant_revoked": True
    }
    assert not client.get(f"{root}/calendar/google").json()["connected"]
