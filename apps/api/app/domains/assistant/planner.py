"""Choose workspace tools from the question when the model is not selecting them.

The same choice is the fallback when a provider rejects tool calling. It does not
search the document library unless the question is about that library.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.domains.assistant.routing import allows_ungrounded_chat

_PRIVATE = re.compile(r"\b(private home|home address|salary|birthday|date of birth)\b")
_EMPLOYEES = re.compile(
    r"\b(employees?|staff|team members?|who works|colleagues?|workspace members?)\b"
)
_CUSTOMERS = re.compile(r"\b(customers?|companies|clients|accounts)\b")
_LEADS = re.compile(r"\b(leads?|prioriti[sz]e|status of)\b")
_CONTACTS = re.compile(r"\bcontacts?\b")
_OPPORTUNITIES = re.compile(r"\b(opportunit(?:y|ies)|deals?|sales pipeline)\b")
_TASKS = re.compile(r"\b(tasks?|deadlines?|due dates?|follow-ups|follow ups)\b")
_INBOX = re.compile(r"\b(inbox|unread|emails? from|messages from)\b")
_ANALYTICS = re.compile(
    r"\b(analytics|revenue|how is the business|how are we doing|sales performance|"
    r"business performance|how the business)\b"
)
_OVERDUE = re.compile(r"\b(overdue|past due|behind schedule)\b")
_COMPARE = re.compile(r"\b(compare|comparison|versus|vs\.?)\b")
_WORKFLOWS = re.compile(r"\b(workflows?|failed runs?|automation)\b")
_CALENDAR = re.compile(r"\b(calendar|availability|free on|are we free)\b")
_PROVIDERS = re.compile(
    r"\b(provider health|connection health|which providers|integrations? connected)\b"
)
_DRAFT = re.compile(r"\b(draft|write)\b.{0,48}\b(message|email|reply|follow-up|follow up)\b")
_APPOINTMENT = re.compile(r"\b(appointment|meeting)\b")
_KNOWLEDGE = re.compile(
    r"\b(polic(?:y|ies)|procedure|documents?|warehous\w*|storage|bonded|contract|"
    r"rate card|knowledge|according to|offers?|services)\b"
)
_REFERENCE = re.compile(r"\b(that|this|those|them|it|mentioned|earlier)\b")
_NOISE = re.compile(
    r"\b(what|whats|what's|is|the|a|an|of|our|my|please|show|me|list|who|are|does|do|"
    r"how|many|tell|about|can|you|there|any|which|in|for|to|with|status|names|name|"
    r"should|i|we|need|attention|does|did)\b"
)
_GENERIC = {
    "customer",
    "customers",
    "company",
    "companies",
    "client",
    "clients",
    "lead",
    "leads",
    "employee",
    "employees",
    "contact",
    "contacts",
    "task",
    "tasks",
    "people",
    "staff",
}

PRIVATE_ANSWER = (
    "I could not find a private home address, salary, or birthday in this workspace, "
    "and I will not guess one."
)
CLARIFY_ANSWER = (
    "Which part of this workspace should I use? I can look at customers, people, leads, "
    "the inbox, analytics, a document, or a workflow."
)
UNKNOWN_REFERENCE = (
    "I could not find an earlier record in this conversation. "
    "Name the customer, person, or document you mean."
)


@dataclass
class LocalDecision:
    tools: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    direct: str | None = None
    general: bool = False


def asks_for_several_sources(question: str) -> bool:
    """True when one request names more than one workspace source."""

    text = " ".join(question.lower().split())
    if _COMPARE.search(text):
        return True
    hits = sum(
        1
        for pattern in (
            _CUSTOMERS,
            _LEADS,
            _ANALYTICS,
            _TASKS,
            _OVERDUE,
            _WORKFLOWS,
            _INBOX,
            _OPPORTUNITIES,
        )
        if pattern.search(text)
    )
    return hits >= 2


def plan_request(question: str, history: list[tuple[str, str]]) -> LocalDecision:
    text = " ".join(question.lower().split())
    if _PRIVATE.search(text):
        return LocalDecision(direct=PRIVATE_ANSWER)
    if allows_ungrounded_chat(text) and not _business(text):
        return LocalDecision(general=True)
    prior = _prior_topic(history) if _REFERENCE.search(text) else None
    combined = f"{text} {prior.lower()}" if prior else text
    if _REFERENCE.search(text) and prior is None and not _business(text):
        return LocalDecision(direct=UNKNOWN_REFERENCE)
    named = [
        (name, arguments)
        for name, arguments in _select(text, _query(question))
        if name != "search_knowledge"
    ]
    if named:
        return LocalDecision(tools=named[:3])
    query = _query(prior if prior else question)
    tools = _select(combined, query)
    if tools:
        return LocalDecision(tools=tools[:3])
    if _REFERENCE.search(text) and prior is None:
        return LocalDecision(direct=UNKNOWN_REFERENCE)
    return LocalDecision(direct=CLARIFY_ANSWER)


def compose_answer(question: str, payloads: list[dict[str, Any]]) -> str:
    """Write a direct answer from tool payloads. No document text is mixed in."""

    parts: list[str] = []
    for payload in payloads:
        part = _compose_one(payload)
        if part:
            parts.append(part)
    if not parts:
        return CLARIFY_ANSWER
    if len(parts) == 1:
        return parts[0]
    return "\n\n".join(parts)


def answer_uses_results(text: str, payloads: list[dict[str, Any]]) -> bool:
    if not text.strip():
        return False
    totals = [
        str(payload.get("companies_total"))
        for payload in payloads
        if isinstance(payload.get("companies_total"), int)
    ]
    if totals and not any(item in text for item in totals):
        return False
    names = _names(payloads)
    if not names:
        return True
    lowered = text.lower()
    mentioned = sum(1 for name in names if len(name) > 2 and name.lower() in lowered)
    if len(names) >= 3:
        return mentioned >= 3
    return mentioned >= 1


def _select(text: str, query: str) -> list[tuple[str, dict[str, Any]]]:
    tools: list[tuple[str, dict[str, Any]]] = []
    knowledge = bool(_KNOWLEDGE.search(text))
    if _EMPLOYEES.search(text):
        tools.append(("list_members", {}))
    if _CUSTOMERS.search(text) and not knowledge:
        tools.append(("list_companies", {"query": "" if _generic(query) else query}))
    if _LEADS.search(text) and not (knowledge and "lead" not in text and "priorit" not in text):
        attention = bool(re.search(r"priorit|attention|open lead|need", text))
        tools.append(
            (
                "list_leads",
                {
                    "query": "" if _generic(query) or attention else query,
                    "needs_attention": attention,
                },
            )
        )
    if _CONTACTS.search(text):
        tools.append(("list_contacts", {"query": "" if _generic(query) else query}))
    if _OPPORTUNITIES.search(text):
        tools.append(("list_opportunities", {"query": "" if _generic(query) else query}))
    if (_TASKS.search(text) or _OVERDUE.search(text)) and not _DRAFT.search(text):
        tools.append(("list_tasks", {"overdue_only": bool(_OVERDUE.search(text))}))
    if _INBOX.search(text):
        tools.append(("search_inbox", {"query": "" if _generic(query) else query}))
    if _ANALYTICS.search(text):
        tools.append(("business_analytics", {}))
    if _WORKFLOWS.search(text):
        tools.append(("list_workflow_runs", {"failed_only": "fail" in text}))
    if _CALENDAR.search(text) and not knowledge:
        tools.append(("check_availability", {}))
    if _PROVIDERS.search(text):
        tools.append(("provider_health", {}))
    lead_name = re.split(
        r"[.?!]|\s+\b(?:about|including|before|then|and)\b",
        query or text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()[:80]
    if _DRAFT.search(text):
        tools.append(("draft_customer_message", {"lead_name": lead_name or "the lead"}))
    elif _APPOINTMENT.search(text) and "available" not in text:
        tools.append(("propose_appointment", {"lead_name": lead_name or "the lead"}))
    if knowledge:
        tools.append(("search_knowledge", {"query": query or text[:500]}))
    return tools


def _business(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (
            _EMPLOYEES,
            _CUSTOMERS,
            _LEADS,
            _CONTACTS,
            _OPPORTUNITIES,
            _TASKS,
            _INBOX,
            _ANALYTICS,
            _WORKFLOWS,
            _CALENDAR,
            _PROVIDERS,
            _DRAFT,
            _APPOINTMENT,
            _KNOWLEDGE,
            _OVERDUE,
        )
    )


_SKIP_TOPIC = re.compile(r"\b(mentioned|tell me more|what about that|that document)\b")


def _prior_topic(history: list[tuple[str, str]]) -> str | None:
    fallback: str | None = None
    for role, content in reversed(history):
        if role != "user" or not content.strip():
            continue
        text = " ".join(content.split())[:500]
        lower = text.lower()
        if _SKIP_TOPIC.search(lower):
            continue
        if fallback is None:
            fallback = text
        if _KNOWLEDGE.search(lower) or _CUSTOMERS.search(lower) or _LEADS.search(lower):
            return text
    return fallback


def _query(question: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", question.lower())
    cleaned = _NOISE.sub(" ", cleaned)
    return " ".join(cleaned.split())[:200]


def _generic(query: str) -> bool:
    words = set(query.split())
    return not query or words <= _GENERIC


def _names(payloads: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for payload in payloads:
        for key in ("companies", "contacts", "leads", "members", "opportunities", "tasks"):
            rows = payload.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = row.get("name") or row.get("title")
                if isinstance(name, str) and name.strip():
                    found.append(name.strip())
    return found


def _compose_one(payload: dict[str, Any]) -> str:
    if "companies" in payload:
        return _companies(payload)
    if "members" in payload:
        return _members(payload)
    if "leads" in payload:
        return _leads(payload)
    if "contacts" in payload:
        return _people(payload, "contacts", "contact")
    if "opportunities" in payload:
        return _opportunities(payload)
    if "tasks" in payload:
        return _tasks(payload)
    if "conversations" in payload:
        return _inbox(payload)
    if "companies_total" in payload:
        return _analytics(payload)
    if "runs" in payload:
        return _runs(payload)
    if "available" in payload:
        return _calendar(payload)
    if "connections" in payload:
        return _providers(payload)
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return ""


def _companies(payload: dict[str, Any]) -> str:
    rows = _rows(payload, "companies")
    total = int(payload.get("total") or len(rows))
    if not rows:
        return "No companies are stored in this workspace."
    if len(rows) == 1:
        industry = rows[0].get("industry") or "no industry is stored"
        return f"{rows[0]['name']} is the company on file. Industry: {industry}."
    lines = [f"- {row['name']} ({row.get('industry') or 'industry not stored'})" for row in rows]
    extra = "" if total <= len(rows) else f" Showing {len(rows)} of {total}."
    return f"This workspace has {total} companies.{extra}\n" + "\n".join(lines)


def _members(payload: dict[str, Any]) -> str:
    rows = _rows(payload, "members")
    if not rows:
        return "No workspace members are stored."
    lines = [f"- {row['name']} ({row.get('role') or 'member'})" for row in rows]
    if len(rows) == 1:
        return f"{rows[0]['name']} is the person in this workspace ({rows[0].get('role')})."
    return "People in this workspace:\n" + "\n".join(lines)


def _leads(payload: dict[str, Any]) -> str:
    rows = _rows(payload, "leads")
    if not rows:
        if payload.get("needs_attention"):
            return "No leads need attention. Nothing is new, contacted, or qualified."
        return "No leads match that request."
    total = int(payload.get("total") or len(rows))
    extra = "" if total <= len(rows) else f" Showing {len(rows)} of {total}."
    lines = []
    for row in rows:
        note = f" — {row['notes']}" if row.get("notes") else ""
        contact = f" Contact: {row['contact']}." if row.get("contact") else ""
        lines.append(f"- {row['title']} is {row.get('status') or 'open'}{note}.{contact}")
    if payload.get("needs_attention"):
        return f"Leads to handle first.{extra}\n" + "\n".join(lines)
    if len(rows) == 1:
        return lines[0][2:] + "."
    return "Leads in this workspace:\n" + "\n".join(lines)


def _people(payload: dict[str, Any], key: str, label: str) -> str:
    rows = _rows(payload, key)
    if not rows:
        return f"No {label}s match that request."
    lines = [f"- {row.get('name') or row.get('title')}" for row in rows]
    return f"{label.capitalize()}s:\n" + "\n".join(lines)


def _opportunities(payload: dict[str, Any]) -> str:
    rows = _rows(payload, "opportunities")
    if not rows:
        return "No opportunities are stored in this pipeline."
    lines = []
    for row in rows:
        value = row.get("value")
        money = f", {value} {row.get('currency') or ''}".rstrip() if value else ""
        lines.append(f"- {row['title']} is in {row.get('stage') or 'a stage'}{money}")
    return "Sales pipeline:\n" + "\n".join(lines)


def _tasks(payload: dict[str, Any]) -> str:
    rows = _rows(payload, "tasks")
    overdue_only = bool(payload.get("overdue_only"))
    if not rows:
        if overdue_only:
            return "No open task is past its due time."
        return "No open tasks are stored."
    lines = []
    for row in rows:
        due = f" due {row['due_at']}" if row.get("due_at") else ""
        late = " overdue" if row.get("overdue") else ""
        lines.append(f"- {row['title']}{late}{due}")
    first = next((row for row in rows if row.get("overdue")), rows[0])
    opening = f"Handle {first['title']} first."
    if first.get("overdue"):
        opening += " It is already past its due time."
    return opening + "\n" + "\n".join(lines)


def _inbox(payload: dict[str, Any]) -> str:
    rows = _rows(payload, "conversations")
    if not rows:
        return "No inbox conversations match that request."
    lines = [
        f"- {row.get('subject') or 'Untitled'} ({row.get('channel') or 'message'})"
        for row in rows
    ]
    return "Inbox conversations:\n" + "\n".join(lines)


def _analytics(payload: dict[str, Any]) -> str:
    notice = payload.get("notice")
    sentence = (
        f"In this workspace there are {payload.get('companies_total', 0)} companies, "
        f"{payload.get('leads_total', 0)} leads, and "
        f"{payload.get('inquiries_total', 0)} inquiries. "
        f"Open leads: {payload.get('open_leads', 0)}. "
        f"Qualified leads: {payload.get('qualified_leads', 0)}. "
        f"Failed workflow runs: {payload.get('failed_runs', 0)}."
    )
    if isinstance(notice, str) and notice.strip():
        return f"{sentence} {notice.strip()}"
    return sentence


def _runs(payload: dict[str, Any]) -> str:
    rows = _rows(payload, "runs")
    if not rows:
        if payload.get("failed_only"):
            return "No failed workflow runs are stored."
        return "No workflow runs are stored."
    lines = []
    for row in rows:
        error = row.get("error") or "no error text was stored"
        attempts = row.get("attempts")
        tried = f" Tried {attempts} times." if isinstance(attempts, int) and attempts else ""
        lines.append(
            f"- {row.get('kind') or 'workflow'} is {row.get('status')}: {error}.{tried}"
        )
    return "Workflow runs:\n" + "\n".join(lines)


def _calendar(payload: dict[str, Any]) -> str:
    if payload.get("needs_time"):
        return "Tell me the start and end time and I will check whether that slot is open."
    if payload.get("available") is None:
        return "The connected calendar could not be checked, so this slot was not treated as open."
    state = "open" if payload.get("available") else "already booked"
    provider = payload.get("provider") or "workspace"
    return f"That time is {state} on the {provider} calendar."


def _providers(payload: dict[str, Any]) -> str:
    rows = _rows(payload, "connections")
    if not rows:
        return "No provider connection is stored for this workspace."
    lines = [
        f"- {row.get('kind') or 'provider'} is {row.get('status') or 'unknown'}" for row in rows
    ]
    return "Provider connections:\n" + "\n".join(lines)


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = payload.get(key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]
