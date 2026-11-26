"""Google Calendar OAuth and tenant-scoped event operations."""

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlencode, urlsplit

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domains.automation.signatures import open_integration_secret, seal_integration_secret
from app.domains.identity.models import Organization
from app.domains.integrations.calendar_models import (
    GoogleCalendarAuthorization,
    GoogleCalendarConnection,
)
from app.integrations.outcomes import OutcomeUncertain

if TYPE_CHECKING:
    from app.integrations.calendar import Slot

_API = "https://www.googleapis.com/calendar/v3"
_TOKEN = "https://oauth2.googleapis.com/token"
_CALLBACK = "/api/v1/calendar/google/callback"
_SCOPES = tuple(
    f"https://www.googleapis.com/auth/{scope}"
    for scope in (
        "calendar.events.owned",
        "calendar.events.freebusy",
        "calendar.calendarlist.readonly",
    )
)


def _safe_url(value: str, path: str) -> bool:
    try:
        url = urlsplit(value)
        return bool(
            url.hostname
            and url.username is None
            and url.password is None
            and not url.query
            and not url.fragment
            and url.path == path
            and (
                url.scheme == "https"
                or (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"})
            )
        )
    except ValueError:
        return False


def configured(settings: Settings) -> bool:
    return bool(
        not settings.public_demo
        and settings.google_calendar_client_id
        and settings.google_calendar_client_secret
        and _safe_url(settings.google_calendar_redirect_uri, _CALLBACK)
        and _safe_url(settings.google_calendar_web_origin, "")
    )


def _settings() -> Settings:
    settings = get_settings()
    if not configured(settings):
        raise AppError(
            503, "calendar_unavailable", "Google Calendar is unavailable in this environment"
        )
    return settings


def lock_workspace(db: Session, organization_id: uuid.UUID) -> None:
    db.execute(select(Organization.id).where(Organization.id == organization_id).with_for_update())


def connect_url(db: Session, organization_id: uuid.UUID, session_id: uuid.UUID) -> str:
    settings = _settings()
    lock_workspace(db, organization_id)
    now = datetime.now(UTC)
    db.execute(
        delete(GoogleCalendarAuthorization).where(
            (GoogleCalendarAuthorization.organization_id == organization_id)
            | (GoogleCalendarAuthorization.expires_at < now)
        )
    )
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    db.add(
        GoogleCalendarAuthorization(
            state_digest=hashlib.sha256(state.encode()).hexdigest(),
            organization_id=organization_id,
            session_id=session_id,
            encrypted_verifier=seal_integration_secret(verifier),
            expires_at=now + timedelta(minutes=10),
        )
    )
    db.commit()
    query = urlencode(
        {
            "client_id": settings.google_calendar_client_id,
            "redirect_uri": settings.google_calendar_redirect_uri,
            "response_type": "code",
            "scope": " ".join(_SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge_method": "S256",
            "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("="),
        }
    )
    return "https://accounts.google.com/o/oauth2/v2/auth?" + query


def authorization(db: Session, state: str, session_id: uuid.UUID) -> GoogleCalendarAuthorization:
    digest = hashlib.sha256(state.encode()).hexdigest()
    row = db.get(GoogleCalendarAuthorization, digest)
    if row is None or row.session_id != session_id or row.expires_at <= datetime.now(UTC):
        raise AppError(400, "calendar_state_invalid", "Start a new Calendar connection")
    lock_workspace(db, row.organization_id)
    current = db.scalar(
        select(GoogleCalendarAuthorization)
        .where(
            GoogleCalendarAuthorization.state_digest == digest,
            GoogleCalendarAuthorization.session_id == session_id,
            GoogleCalendarAuthorization.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if current is None:
        raise AppError(400, "calendar_state_invalid", "Start a new Calendar connection")
    return current


def finish(db: Session, row: GoogleCalendarAuthorization, code: str | None) -> str:
    settings = _settings()
    destination = settings.google_calendar_web_origin + "/integrations?calendar="
    organization_id = row.organization_id
    verifier = open_integration_secret(row.encrypted_verifier)
    db.delete(row)
    if not code:
        db.commit()
        return destination + "cancelled"
    try:
        data = _oauth(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": settings.google_calendar_redirect_uri,
            }
        )
        scope = data.get("scope")
        refresh = data.get("refresh_token")
        access = data.get("access_token")
        if (
            not isinstance(scope, str)
            or not set(_SCOPES).issubset(scope.split())
            or not isinstance(refresh, str)
            or not refresh
            or not isinstance(access, str)
            or not access
        ):
            raise AppError(
                403, "calendar_permissions_missing", "Grant the requested Calendar permissions"
            )
        primary = _json(_request("GET", "/users/me/calendarList/primary", access))
        calendar_id, name = primary.get("id"), primary.get("summary")
        if (
            not isinstance(calendar_id, str)
            or not 1 <= len(calendar_id) <= 512
            or primary.get("accessRole") != "owner"
        ):
            raise AppError(
                409, "calendar_not_owned", "Choose a Google account with an owned calendar"
            )
    except AppError:
        db.commit()
        return destination + "failed"
    existing = db.get(GoogleCalendarConnection, organization_id)
    if existing is None:
        existing = GoogleCalendarConnection(organization_id=organization_id)
        db.add(existing)
    existing.calendar_id = calendar_id
    existing.calendar_name = name[:200] if isinstance(name, str) and name else "Primary calendar"
    existing.encrypted_token = seal_integration_secret(refresh)
    existing.connected_at = datetime.now(UTC)
    existing.connection_error = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.execute(
            delete(GoogleCalendarAuthorization).where(
                GoogleCalendarAuthorization.state_digest == row.state_digest
            )
        )
        db.commit()
        return destination + "failed"
    return destination + "connected"


def active_connection(db: Session, organization_id: uuid.UUID) -> GoogleCalendarConnection | None:
    row = db.get(GoogleCalendarConnection, organization_id)
    return row if row is not None and row.encrypted_token else None


def record_connection_check(
    db: Session, connection: GoogleCalendarConnection, error: str | None
) -> None:
    if connection.connection_error == error:
        return
    db.execute(
        update(GoogleCalendarConnection)
        .where(
            GoogleCalendarConnection.organization_id == connection.organization_id,
            GoogleCalendarConnection.encrypted_token == connection.encrypted_token,
        )
        .values(connection_error=error)
    )


def disconnect(db: Session, organization_id: uuid.UUID) -> bool:
    lock_workspace(db, organization_id)
    row = active_connection(db, organization_id)
    revoked = True
    if row is not None:
        try:
            token = open_integration_secret(row.encrypted_token or "")
            response = httpx.post(
                "https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=5
            )
            revoked = response.is_success
        except (httpx.RequestError, AppError):
            revoked = False
        row.encrypted_token = None
        row.connection_error = None
    db.execute(
        delete(GoogleCalendarAuthorization).where(
            GoogleCalendarAuthorization.organization_id == organization_id
        )
    )
    db.commit()
    return revoked


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except ValueError:
        pass
    raise AppError(502, "calendar_invalid_response", "Google Calendar returned an invalid response")


def _oauth(data: dict[str, str]) -> dict[str, Any]:
    settings = _settings()
    try:
        response = httpx.post(
            _TOKEN,
            data={
                **data,
                "client_id": settings.google_calendar_client_id,
                "client_secret": settings.google_calendar_client_secret,
            },
            timeout=10,
        )
    except httpx.RequestError:
        raise AppError(
            503, "calendar_unreachable", "Google Calendar could not be reached"
        ) from None
    if not response.is_success:
        if response.status_code == 400 and _json(response).get("error") == "invalid_grant":
            raise AppError(409, "calendar_reconnect_required", "Reconnect Google Calendar")
        raise AppError(502, "calendar_authorization_failed", "Google Calendar authorization failed")
    return _json(response)


def _access(connection: GoogleCalendarConnection) -> str:
    if not connection.encrypted_token:
        raise AppError(409, "calendar_disconnected", "Connect Google Calendar to continue")
    data = _oauth(
        {
            "grant_type": "refresh_token",
            "refresh_token": open_integration_secret(connection.encrypted_token),
        }
    )
    access = data.get("access_token")
    if not isinstance(access, str) or not access:
        raise AppError(
            502, "calendar_invalid_response", "Google Calendar returned an invalid token"
        )
    return access


def _request(
    method: str,
    path: str,
    access: str,
    *,
    body: dict[str, Any] | None = None,
    missing_ok: bool = False,
    conflict_ok: bool = False,
) -> httpx.Response:
    try:
        response = httpx.request(
            method,
            _API + path,
            headers={"Authorization": f"Bearer {access}"},
            json=body,
            timeout=10,
        )
    except httpx.RequestError:
        if method == "POST" and path != "/freeBusy":
            raise OutcomeUncertain("calendar_create_unconfirmed") from None
        raise AppError(
            503, "calendar_unreachable", "Google Calendar could not be reached"
        ) from None
    if (response.status_code >= 500 or response.status_code == 408) and (
        method == "POST" and path != "/freeBusy"
    ):
        raise OutcomeUncertain("calendar_create_unconfirmed")
    if response.status_code in {401, 403}:
        raise AppError(409, "calendar_reconnect_required", "Reconnect Google Calendar")
    if (
        response.is_success
        or (missing_ok and response.status_code in {404, 410})
        or (conflict_ok and response.status_code == 409)
    ):
        return response
    raise AppError(502, "calendar_provider_error", "Google Calendar could not complete the request")


def _free(
    connection: GoogleCalendarConnection, access: str, start: datetime, end: datetime
) -> bool:
    data = _json(
        _request(
            "POST",
            "/freeBusy",
            access,
            body={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "items": [{"id": connection.calendar_id}],
            },
        )
    )
    calendars = data.get("calendars")
    result = calendars.get(connection.calendar_id) if isinstance(calendars, dict) else None
    if (
        not isinstance(result, dict)
        or result.get("errors")
        or not isinstance(result.get("busy"), list)
    ):
        raise AppError(
            502, "calendar_availability_unknown", "Google Calendar availability is unavailable"
        )
    return not result["busy"]


def available(connection: GoogleCalendarConnection, start: datetime, end: datetime) -> bool:
    return _free(connection, _access(connection), start, end)


def create_event(connection: GoogleCalendarConnection, slot: "Slot") -> str:
    access = _access(connection)
    events = f"/calendars/{quote(connection.calendar_id, safe='')}/events"
    event_id = slot.intent_id.hex
    intent_ref = str(slot.intent_id)

    def existing(response: httpx.Response) -> bool:
        if response.status_code in {404, 410}:
            return False
        event = _json(response)
        properties = event.get("extendedProperties")
        private = properties.get("private") if isinstance(properties, dict) else None
        if (
            event.get("status") == "cancelled"
            or not isinstance(private, dict)
            or (private.get("atlasIntent") != intent_ref)
        ):
            raise AppError(
                409, "calendar_event_conflict", "The existing Calendar event requires review"
            )
        return True

    if existing(_request("GET", f"{events}/{event_id}", access, missing_ok=True)):
        return event_id
    if not _free(connection, access, slot.starts_at, slot.ends_at):
        raise AppError(409, "slot_unavailable", "That time is busy on Google Calendar")
    body = {
        "id": event_id,
        "summary": "ATLAS customer appointment",
        "visibility": "private",
        "start": {"dateTime": slot.starts_at.isoformat()},
        "end": {"dateTime": slot.ends_at.isoformat()},
        "extendedProperties": {"private": {"atlasIntent": intent_ref}},
    }
    try:
        result = _request("POST", events, access, body=body, conflict_ok=True)
        if result.status_code != 409 and _json(result).get("id") == event_id:
            return event_id
    except (OutcomeUncertain, AppError) as exc:
        if isinstance(exc, AppError) and exc.code != "calendar_invalid_response":
            raise
    try:
        confirmation = _request("GET", f"{events}/{event_id}", access, missing_ok=True)
    except AppError:
        raise OutcomeUncertain("calendar_create_unconfirmed") from None
    if existing(confirmation):
        return event_id
    raise OutcomeUncertain("calendar_create_unconfirmed")


def cancel_event(connection: GoogleCalendarConnection, calendar_id: str, event_id: str) -> None:
    if connection.calendar_id != calendar_id:
        raise AppError(
            409, "calendar_account_changed", "Reconnect the calendar that owns this event"
        )
    path = f"/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}"
    _request("DELETE", path, _access(connection), missing_ok=True)
