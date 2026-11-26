"""Sender-domain verification adapter.

Resend is the first provider because its authenticated domain API returns the
DNS records ATLAS must publish.  This adapter never sends email.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import httpx

from app.core.errors import AppError


@dataclass(frozen=True)
class DnsRecord:
    record_type: str
    name: str
    value: str


@dataclass(frozen=True)
class DomainStatus:
    provider_domain_id: str
    verified: bool
    records: list[DnsRecord]
    evidence: dict[str, str]


class DomainProvider(Protocol):
    def register(self, domain: str) -> DomainStatus: ...

    def status(self, provider_domain_id: str) -> DomainStatus: ...

    def start_verification(self, provider_domain_id: str) -> None: ...

    def revoke(self, provider_domain_id: str) -> None: ...


class ResendDomainProvider:
    def __init__(self, api_key: str, *, timeout: float = 10) -> None:
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout

    def register(self, domain: str) -> DomainStatus:
        return self._read(self._request("POST", "", body={"name": domain}))

    def status(self, provider_domain_id: str) -> DomainStatus:
        return self._read(self._request("GET", f"/{provider_domain_id}"))

    def start_verification(self, provider_domain_id: str) -> None:
        self._request("POST", f"/{provider_domain_id}/verify")

    def revoke(self, provider_domain_id: str) -> None:
        self._request("DELETE", f"/{provider_domain_id}")

    def _request(
        self, method: str, path: str, *, body: dict[str, str] | None = None
    ) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"https://api.resend.com/domains{path}",
                headers=self._headers,
                json=body,
                timeout=self._timeout,
            )
        except httpx.RequestError as exc:
            raise AppError(502, "resend_unavailable", "Resend could not be reached") from exc
        if response.status_code in {401, 403}:
            raise AppError(422, "resend_credentials_rejected", "Check the Resend key permissions")
        if response.status_code == 404:
            raise AppError(
                404, "resend_domain_missing", "This domain is unavailable to the Resend key"
            )
        if not response.is_success:
            raise AppError(502, "resend_domain_error", "Resend rejected the domain request")
        return response

    @staticmethod
    def _read(response: httpx.Response) -> DomainStatus:
        try:
            payload = response.json()
            if isinstance(payload, dict) and payload.get("id") and payload.get("status"):
                return _domain_status(payload)
        except (TypeError, ValueError):
            pass
        raise AppError(
            502, "resend_domain_response_invalid", "Resend returned an invalid domain response"
        )


def _domain_status(payload: dict[str, object]) -> DomainStatus:
    raw_records = payload.get("records", [])
    records = [
        DnsRecord(
            record_type=str(item.get("type", "")),
            name=str(item.get("name", "")),
            value=str(item.get("value", "")),
        )
        for item in cast(list[object], raw_records)
        if isinstance(item, dict)
    ]
    return DomainStatus(
        provider_domain_id=str(payload.get("id", "")),
        verified=payload.get("status") == "verified",
        records=records,
        evidence={"provider": "resend", "status": str(payload.get("status", "unknown"))},
    )
