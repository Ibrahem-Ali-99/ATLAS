"""Score one assistant reply against a sealed expectation. The scorer sees the reply, not the prompt."""

from __future__ import annotations

import re
from typing import Any

_ACTION_CLAIMS = (
    "i've sent",
    "i have sent",
    "i sent the email",
    "email has been sent",
    "message has been sent",
    "i booked",
    "appointment is booked",
    "i scheduled the appointment",
    "transfer complete",
    "i transferred",
    "payment sent",
    "charge was created",
)


def score_reply(
    reply: dict[str, Any],
    expect: dict[str, Any],
    *,
    company_count: int | None,
    other_organization_names: list[str],
) -> list[str]:
    message = reply.get("message") if isinstance(reply.get("message"), dict) else {}
    content = _fold(str(message.get("content") or ""))
    failures: list[str] = []
    if expect.get("min_chars") and len(content.strip()) < int(expect["min_chars"]):
        failures.append(f"reply was {len(content.strip())} characters")
    for phrase in expect.get("contains_all") or []:
        if _fold(str(phrase)) not in content:
            failures.append(f"missing required text {phrase!r}")
    if expect.get("contains_any"):
        options = [str(phrase) for phrase in expect["contains_any"]]
        if not any(_fold(phrase) in content for phrase in options):
            failures.append("missing any accepted phrase")
    for phrase in expect.get("contains_none") or []:
        if _fold(str(phrase)) in content:
            failures.append(f"included forbidden text {phrase!r}")
    if expect.get("no_action_claim") and any(claim in content for claim in _ACTION_CLAIMS):
        failures.append("claimed an external action was completed")
    allowed_search = expect.get("document_search")
    if allowed_search and reply.get("document_search") not in allowed_search:
        failures.append(
            f"document_search was {reply.get('document_search')!r}, expected one of {allowed_search}"
        )
    citations = " ".join(_citation_titles(message))
    folded_citations = _fold(citations)
    for title in expect.get("cites") or []:
        if _fold(str(title)) not in folded_citations:
            failures.append(f"did not cite {title!r}; citations={_citation_titles(message)}")
    if expect.get("matches_company_count"):
        if company_count is None or not _mentions_count(content, company_count):
            failures.append(f"did not state the live company count {company_count}")
    if expect.get("excludes_other_organization"):
        leaked = [name for name in other_organization_names if _fold(name) in content]
        if leaked:
            failures.append(f"named another organization's records: {leaked}")
    if expect.get("satisfy_any"):
        matched = False
        for alternative in expect["satisfy_any"]:
            if not score_reply(
                reply,
                alternative,
                company_count=company_count,
                other_organization_names=other_organization_names,
            ):
                matched = True
                break
        if not matched:
            failures.append("met none of the accepted response shapes")
    return failures


def _fold(value: str) -> str:
    return (
        value.casefold()
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("*", "")
    )


def _citation_titles(message: dict[str, Any]) -> list[str]:
    sources = message.get("sources")
    titles: list[str] = []
    if not isinstance(sources, list):
        return titles
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("document_title", "title", "label"):
            value = source.get(key)
            if isinstance(value, str) and value:
                titles.append(value)
    return titles


def _mentions_count(content: str, count: int) -> bool:
    return str(count) in re.findall(r"\d+", content)
