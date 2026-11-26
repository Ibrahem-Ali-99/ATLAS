"""Decide what a turn is allowed to do before any model call.

Clear questions are classified here. A model is asked only when a short follow-up
uses a pronoun and the conversation does not name a record. The model may return
one of a fixed set of intents. It cannot choose an organization or run a tool.
"""

import enum
import json
import re

_MUTATION_VERB = re.compile(r"\b(update|delete|remove|create|edit|modify|send|change)\b")
_MUTATION_OBJECT = re.compile(
    r"\b(lead|leads|company|companies|contact|contacts|inquiry|inquiries|"
    r"document|documents|email|record|records|crm)\b"
)
_DOCUMENTS = re.compile(
    r"\b(which documents|what documents|documents are available|available documents|"
    r"list (the |my )?documents|show (my )?documents)\b"
)
_COMPANIES = re.compile(
    r"\b(which companies|what companies|companies in my crm|companies are in|"
    r"list (the |my )?companies|show (my )?companies)\b"
)
_INQUIRIES = re.compile(
    r"\b(recent inquiries|my inquiries|show (my )?inquiries|list (the |my )?inquiries|"
    r"which inquiries|what inquiries)\b"
)
_LEADS = re.compile(
    r"\b(leads that need attention|leads need attention|which leads need|"
    r"what leads need|open leads)\b"
)
_INVENTORY = re.compile(
    r"\b(what information do you have|what do you have access to|"
    r"what can you access|what records do you have|what data do you have|"
    r"summarize the company information|company information you can access)\b"
)
_CAPABILITY = re.compile(
    r"\b(what can you help|what can atlas help|what can you do|how can you help|what can i do|"
    r"what do you do|how do approvals work|how does approval|who are you|what are you)\b"
)
_RECALL = re.compile(
    r"\b(what did we discuss|what did we talk|what have we discussed|"
    r"earlier in this conversation|remind me what (we|i))\b"
)
_GREETING = re.compile(
    r"^(hi|hello|hey|thanks|thank you|good morning|good afternoon|how are you)\b"
)
_REFERENCE = re.compile(
    r"\b(that|this|the) (company|document|file|brochure|lead|inquiry|record)\b|"
    r"\b(document|company|lead|file) you mentioned\b|\btell me more\b"
)
_PRONOUN = re.compile(r"\b(it|that|this|those|them)\b")
_FACT = re.compile(
    r"\b(address|phone|founder|revenue|price|rate|rates|policy|contract|salary|"
    r"home|private|birthday)\b|\bwho is\b|\bwhere (is|does|do)\b|\bhow (much|many)\b"
)
_COMPANY_LOOKUP = re.compile(
    r"\b(policy|contract|invoice|customer|warehousing|shipment|quote|document|"
    r"company|lead|crm)\b"
)
_UNGROUNDED = re.compile(
    r"\b(joke|weather|translate|spell|how are you|thank you|thanks)\b|"
    r"^(ok|okay|yes|no|sure|got it)\b"
)
_REPHRASE = re.compile(r"\b(rephrase|say that again|explain that|more simply|in simpler terms)\b")
_HANDOFF = re.compile(
    r"\b(speak|talk|chat) (to|with) (a |an )?(human|person|agent|representative)\b|"
    r"\b(connect|transfer|hand) me (over )?to (a |an )?(human|person|agent|representative)\b"
)


class Intent(enum.StrEnum):
    capability = "capability"
    inventory = "inventory"
    documents = "documents"
    companies = "companies"
    inquiries = "inquiries"
    leads = "leads"
    recall = "recall"
    mutation = "mutation"
    handoff = "handoff"
    greeting = "greeting"
    grounded = "grounded"
    general = "general"
    ambiguous = "ambiguous"


CLASSIFIER_SYSTEM = (
    "Classify one short question. Reply with json only, using one of "
    '{"intent":"grounded"}, {"intent":"general"}, {"intent":"inventory"}, '
    '{"intent":"capability"}. '
    "grounded asks for a fact from this organization's documents or CRM. "
    "inventory asks what is stored. capability asks what ATLAS can do. "
    "general is conversation and is not a company fact. Do not answer the question."
)

CAPABILITY_ANSWER = "\n".join(
    [
        "## What I can help with",
        "",
        "I can help you understand ATLAS and find supported information in this workspace.",
        "",
        "- Explain the CRM, Knowledge, Agent Runs, approvals, and workflows.",
        "- List records and documents stored in this organization.",
        "- Answer questions from retrieved records or documents with supporting sources.",
        "",
        "For company facts, I check the organization’s records and say when evidence is missing.",
        "",
        "I do not change records, send email, or book meetings from chat. "
        "Those actions require an Agent Run; an admin must approve and execute them.",
    ]
)

MUTATION_ANSWER = "\n".join(
    [
        "## I can't change records from this chat",
        "",
        "This assistant is read-only. I did not update, delete, create, or send anything.",
        "",
        "To change a lead, start an agent run from the inquiry. The run proposes the change. "
        "An admin approves that proposal, then executes it. Email and calendar actions use "
        "the same approval and execute steps. Rejecting the proposal writes nothing.",
    ]
)

GREETING_ANSWER = (
    "Hello. I can explain ATLAS, list what this organization has stored, "
    "and answer from those CRM records and documents. "
    "I will not guess a company fact that is not in those records."
)

NO_HISTORY = "We have not discussed anything earlier in this conversation."


def normalize_question(question: str) -> str:
    return " ".join(question.strip().lower().split())


def route_question(question: str, *, has_history: bool) -> Intent:
    text = normalize_question(question)
    if _HANDOFF.search(text):
        return Intent.handoff
    if _MUTATION_VERB.search(text) and _MUTATION_OBJECT.search(text):
        return Intent.mutation
    if _DOCUMENTS.search(text):
        return Intent.documents
    if _COMPANIES.search(text):
        return Intent.companies
    if _INQUIRIES.search(text):
        return Intent.inquiries
    if _LEADS.search(text):
        return Intent.leads
    if _INVENTORY.search(text):
        return Intent.inventory
    if _CAPABILITY.search(text):
        return Intent.capability
    if _RECALL.search(text):
        return Intent.recall
    if _GREETING.search(text):
        return Intent.greeting
    if has_history and _REPHRASE.search(text):
        return Intent.general
    if _REFERENCE.search(text):
        return Intent.grounded
    if has_history and _PRONOUN.search(text) and not _FACT.search(text) and len(text.split()) <= 12:
        return Intent.ambiguous
    return Intent.grounded


def parse_classifier_intent(raw: str) -> Intent | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    intent = payload.get("intent")
    allowed = {
        Intent.grounded.value: Intent.grounded,
        Intent.general.value: Intent.general,
        Intent.inventory.value: Intent.inventory,
        Intent.capability.value: Intent.capability,
    }
    if not isinstance(intent, str):
        return None
    return allowed.get(intent)


def allows_ungrounded_chat(question: str) -> bool:
    """A question with no retrieved record may reach the model only as conversation."""
    return bool(_UNGROUNDED.search(normalize_question(question)))


def unsupported_without_evidence(question: str) -> bool:
    text = normalize_question(question)
    return bool(_FACT.search(text) or _COMPANY_LOOKUP.search(text))


def refers_to_earlier_record(question: str) -> bool:
    return bool(_REFERENCE.search(normalize_question(question)))


def recall_answer(turns: list[tuple[str, str]], opening: str | None = None) -> str:
    if not turns and not opening:
        return NO_HISTORY
    lines = [
        "## Earlier in this conversation",
        "",
        "This is the recent chat, plus the first question when the thread is longer. "
        "It is not a company record, and it is not a citation.",
        "",
    ]
    if opening:
        started = " ".join(opening.split())[:180]
        already = any(role == "user" and started in content for role, content in turns)
        if started and not already:
            lines.append(f"- You started with: {started}")
    for role, content in turns[-8:]:
        label = "You" if role == "user" else "Assistant"
        clipped = " ".join(content.split())[:180]
        lines.append(f"- {label}: {clipped}")
    return "\n".join(lines)
