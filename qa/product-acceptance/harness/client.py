"""HTTP session for the isolated acceptance API.

The client never prints cookies, CSRF tokens, or passwords.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

_SECRET_KEYS = ("password", "secret", "token", "csrf", "authorization", "cookie", "api_key", "credential")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if any(part in key.lower() for part in _SECRET_KEYS):
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value[:40]]
    if isinstance(value, str) and len(value) > 1200:
        return value[:1200] + "…"
    return value


class ApiSession:
    def __init__(self, base_url: str, email: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.http = httpx.Client(base_url=self.base_url, timeout=180)
        response = self.http.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        body = _json(response)
        if response.status_code != 200:
            code = _error_code(body)
            raise RuntimeError(f"login failed status={response.status_code} code={code}")
        token = body.get("csrf_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("login did not return a CSRF token")
        self.http.headers["X-CSRF-Token"] = token
        memberships = body.get("memberships")
        self.memberships = memberships if isinstance(memberships, list) else []
        self.user_id = (body.get("user") or {}).get("id")

    def close(self) -> None:
        self.http.close()

    def organization(self, slug: str) -> dict[str, Any]:
        for row in self.memberships:
            if isinstance(row, dict) and row.get("organization_slug") == slug:
                return row
        raise RuntimeError(f"membership not found for slug {slug}")

    def call(
        self,
        method: str,
        organization_id: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
        files: Any | None = None,
        data: dict[str, Any] | None = None,
        csrf: bool = True,
    ) -> tuple[int, Any]:
        headers = {}
        if not csrf:
            headers["X-CSRF-Token"] = ""
        response = self.http.request(
            method,
            f"/api/v1/organizations/{organization_id}{path}",
            json=json_body,
            params=params,
            files=files,
            data=data,
            headers=headers,
        )
        return response.status_code, _json(response)


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError:
        return {"raw": response.text[:500]}


def _error_code(body: Any) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return error["code"]
    return "none"
