import uuid
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import sign_session_id
from app.domains.identity.login_limit import clear_login_attempts
from app.domains.identity.models import MembershipRole, UserSession
from app.integrations.email import OutboundEmail
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def test_password_recovery_delivers_one_time_link_and_revokes_sessions(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    user = make_user(db, "recovery@example.com")
    login(client, user.email, PASSWORD)
    outbound: list[OutboundEmail] = []
    monkeypatch.setattr("app.api.v1.auth.send_email", outbound.append)

    request = client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    repeat = client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    assert request.status_code == unknown.status_code == repeat.status_code == 202
    assert request.json() == unknown.json() == repeat.json()
    assert len(outbound) == 1
    link = urlsplit(outbound[0].body.splitlines()[-1])
    assert link.path == "/reset-password"
    assert not link.query
    token = parse_qs(link.fragment)["token"][0]
    assert token not in outbound[0].idempotency_key

    change = {"token": token, "password": "replacement-password"}
    assert client.post("/api/v1/auth/reset-password", json=change).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/reset-password", json=change).status_code == 400
    assert login(client, user.email, change["password"])["user"]


def test_login_and_current_user(client: TestClient, db: Session) -> None:
    user = make_user(db, "ada@example.com", full_name="Ada Admin")
    organization = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, user, organization, MembershipRole.admin)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "Ada@Example.com", "password": PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["full_name"] == "Ada Admin"
    assert "password_hash" not in body["user"]
    assert PASSWORD not in response.text
    assert body["csrf_token"]
    assert body["memberships"][0]["role"] == "admin"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["id"] == str(user.id)
    assert me.json()["csrf_token"] == body["csrf_token"]


def test_login_cookie_is_httponly(client: TestClient, db: Session) -> None:
    make_user(db, "ada@example.com")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": PASSWORD},
    )
    header = response.headers["set-cookie"].lower()
    assert "atlas_session=" in header
    assert "httponly" in header
    assert "samesite=lax" in header


def test_invalid_credentials_are_indistinguishable(client: TestClient, db: Session) -> None:
    make_user(db, "ada@example.com")
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": PASSWORD},
    )
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "wrong-password"},
    )
    inactive_user = make_user(db, "inactive@example.com", is_active=False)
    inactive = client.post(
        "/api/v1/auth/login",
        json={"email": inactive_user.email, "password": PASSWORD},
    )
    assert unknown.status_code == wrong.status_code == inactive.status_code == 401
    assert unknown.json() == wrong.json() == inactive.json()
    assert unknown.json()["error"]["code"] == "invalid_credentials"


def test_login_rate_limit_does_not_reveal_the_account(
    client: TestClient, db: Session, monkeypatch
) -> None:
    clear_login_attempts()
    tight = get_settings().model_copy(update={"login_email_limit": 8, "login_client_limit": 2})
    monkeypatch.setattr("app.domains.identity.login_limit.get_settings", lambda: tight)
    make_user(db, "limited@example.com")
    for _ in range(2):
        failed = client.post(
            "/api/v1/auth/login",
            json={"email": "limited@example.com", "password": "wrong-password"},
        )
        assert failed.status_code == 401
        assert failed.json()["error"]["code"] == "invalid_credentials"
    known = client.post(
        "/api/v1/auth/login",
        json={"email": "limited@example.com", "password": "wrong-password"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password"},
    )
    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json()
    assert known.json()["error"]["code"] == "rate_limited"
    assert "limited@example.com" not in known.text
    clear_login_attempts()


def test_password_is_stored_as_argon2_hash(db: Session) -> None:
    user = make_user(db, "ada@example.com")
    assert user.password_hash != PASSWORD
    assert user.password_hash.startswith("$argon2")


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_tampered_cookie_is_rejected(client: TestClient, db: Session) -> None:
    make_user(db, "ada@example.com")
    login(client, "ada@example.com", PASSWORD)
    client.cookies.clear()
    client.cookies.set("atlas_session", "tampered-value")
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_signed_cookie_without_server_session_is_rejected(client: TestClient) -> None:
    token = sign_session_id(uuid.uuid4(), get_settings().secret_key)
    client.cookies.set("atlas_session", token)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_logout_rejects_wrong_csrf_without_revoking(client: TestClient, db: Session) -> None:
    make_user(db, "ada@example.com")
    login(client, "ada@example.com", PASSWORD)
    rejected = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "not-the-session-token"})
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "csrf_failed"
    assert client.get("/api/v1/auth/me").status_code == 200
    db.expire_all()
    record = db.scalar(select(UserSession))
    assert record is not None
    assert record.revoked_at is None


def test_logout_requires_csrf_and_revokes_session(client: TestClient, db: Session) -> None:
    make_user(db, "ada@example.com")
    body = login(client, "ada@example.com", PASSWORD)
    missing = client.post("/api/v1/auth/logout")
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "csrf_failed"
    assert client.get("/api/v1/auth/me").status_code == 200

    logged_out = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": str(body["csrf_token"])},
    )
    assert logged_out.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    db.expire_all()
    record = db.scalar(select(UserSession))
    assert record is not None
    assert record.revoked_at is not None


def test_password_change_checks_the_current_password_and_keeps_this_session(
    client: TestClient, db: Session
) -> None:
    user = make_user(db, "change-password@example.com")
    session = login(client, user.email, PASSWORD)
    headers = {"X-CSRF-Token": str(session["csrf_token"])}
    missing = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "replacement-password"},
    )
    assert missing.status_code == 403
    wrong = client.post(
        "/api/v1/auth/password",
        json={"current_password": "not-the-password", "new_password": "replacement-password"},
        headers=headers,
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "current_password_incorrect"
    assert PASSWORD not in wrong.text
    same = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": PASSWORD},
        headers=headers,
    )
    assert same.status_code == 422
    changed = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "replacement-password"},
        headers=headers,
    )
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 200
    client.cookies.clear()
    assert client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}).status_code == 401
    assert login(client, user.email, "replacement-password")["user"]["email"] == user.email
