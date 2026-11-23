"""Sender-domain verification adapter.

Resend is the first provider because its authenticated domain API returns the
DNS records ATLAS must publish.  This adapter never sends email.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import httpx


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

    def revoke(self, provider_domain_id: str) -> None: ...


class ResendDomainProvider:
    def __init__(self, api_key: str, *, timeout: float = 10) -> None:
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout

    def register(self, domain: str) -> DomainStatus:
        response = httpx.post(
            "https://api.resend.com/domains",
            headers=self._headers,
            json={"name": domain},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return _domain_status(response.json())

    def status(self, provider_domain_id: str) -> DomainStatus:
        response = httpx.get(
            f"https://api.resend.com/domains/{provider_domain_id}",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return _domain_status(response.json())

    def revoke(self, provider_domain_id: str) -> None:
        response = httpx.delete(
            f"https://api.resend.com/domains/{provider_domain_id}",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()


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
