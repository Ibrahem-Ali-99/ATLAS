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
_SUMMARY = re.compile(r"\bsummar(?:y|ize|ise)\b.{0,40}\b(lead|customer|contact)\b")
_FOLLOW_UP = re.compile(
    r"\b(draft|write|prepare)\b.{0,40}\b(follow-up|follow up|reply|response|message)\b"
)
_APPOINTMENT = re.compile(r"\b(request|schedule|book|propose)\b.{0,40}\b(appointment|meeting)\b")
_BOOK_PERSON = re.compile(r"\b(book|schedule|arrange)\b")
_NOT_APPOINTMENT = re.compile(r"\b(campaign|delivery|invoice|report)\b")
_DRAFT_EMAIL = re.compile(
    r"\b(draft|write|prepare|compose)\b.{0,40}\b(e-mail|email)\b|"
    r"\b(e-mail|email)\s+(him|her|them|the|a|an|customer|lead|contact)\b"
)
_TASK = re.compile(r"\b(create|add|make)\b.{0,40}\btask\b")
_EXTERNAL_SEND = re.compile(
    r"\b(send|email|text)\b.{0,40}\b(message|email|customer|lead|contact)\b"
)
_RECORD_OVERRIDE = re.compile(
    r"\b(ignore|disregard|override)\b.{0,120}\b(document|documents|record|records|evidence|knowledge)\b"
    r"|\b(document|documents|record|records|evidence|knowledge)\b.{0,120}\b(ignore|disregard|override)\b"
)
_INJECTION = re.compile(
    r"ignore (all |any |the )?(previous |prior |above )?instructions|"
    r"\b(system prompt|developer message)\b|"
    r"\byou are now\b|"
    r"\bdo not follow the (system|rules)\b|"
    r"\breveal (your |the )?(hidden |system )?prompt\b"
)
_UNRELATED = re.compile(
    r"\b(weather|forecast|joke|recipe|sports score|capital of|who won the)\b|"
    r"\btranslate this\b"
)
_OBVIOUS_GENERAL = re.compile(
    r"\b(capital of|who won|weather|forecast|joke|recipe|translate|spell|"
    r"how are you|thank you|thanks)\b"
)
_CREATIVE = re.compile(
    r"\b(write|rewrite|rephrase|brainstorm|compose|outline|poem|haiku|help me think)\b"
)
_WORKSPACE_SCOPE = re.compile(
    r"\b(our|ours|workspace|stored|crm|approval|approvals|workflow|inbox|"
    r"customer|customers|company|companies|lead|leads|contact|contacts|"
    r"employee|employees|staff|document|documents|invoice|policy|policies|"
    r"rate card|according to)\b"
)
_RECORD_FACT = re.compile(
    r"\b(temperature|freezer|frozen|fee|fees|rate|rates|opening hours|"
    r"bond|bonded|yard|warehouse|warehousing|procedure|contract|"
    r"booking|superseded|salary|phone|address|pallet|storage|"
    r"insurance|deductible|occupancy)\b"
)
_BARE_TOPIC = re.compile(r"^(storage|rates?|yard|claims|cover|hours)$")


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
    summary = "summary"
    follow_up = "follow_up"
    appointment = "appointment"
    task = "task"
    greeting = "greeting"
    grounded = "grounded"
    general = "general"
    ambiguous = "ambiguous"
    unrelated = "unrelated"
    injection = "injection"


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
        "Ask me about a stored company, lead, or document and I will answer from that record.",
        "",
        "- Explain the CRM, Knowledge, Agent Runs, approvals, and workflows.",
        "- List records and documents stored in this organization.",
        "- Answer a follow-up from the record we were just discussing.",
        "- Summarize a stored lead, customer, or contact, including a linked conversation.",
        "- Propose a follow-up draft, an appointment request, or a workspace task.",
        "",
        "If a question is too broad, I will ask which record you mean. "
        "For company facts, I check the organization’s records and say when evidence is missing.",
        "",
        "A follow-up or appointment is only a proposal. An administrator approves it before "
        "anything is sent or booked. An administrator must execute it afterward. Confirming a task "
        "creates that task and does not send a message.",
    ]
)

MUTATION_ANSWER = "\n".join(
    [
        "## I can't change records from this chat",
        "",
        "This assistant is read-only for that request. "
        "I did not update, delete, create, or send anything.",
        "",
        "I can draft a follow-up, request an appointment, or create a follow-up task when you "
        "name one stored lead. A draft or appointment waits until an administrator approves it. "
        "Rejecting that approval writes nothing.",
    ]
)

GREETING_ANSWER = "Hello. What would you like to work on?"

MODEL_CHAT_UNAVAILABLE = (
    "I can answer that once the language model is available. "
    "I can still look up a stored company, lead, or document."
)

INJECTION_ANSWER = (
    "I won't follow an instruction to ignore the workspace rules or to invent a fact. "
    "Ask a question about a stored record, or ask what I can help with."
)

RECORD_OVERRIDE_ANSWER = (
    "I cannot ignore the stored records or replace them with a fact from this message. "
    "Ask for the stored record and I will answer from it."
)

AMBIGUOUS_ANSWER = (
    "That word matches more than one kind of record. Name the company or the document "
    "you mean, such as a rate card, a yard, a claim rule, or a lead title, and I will "
    "look up that one."
)

NO_HISTORY = "We have not discussed anything earlier in this conversation."


def normalize_question(question: str) -> str:
    return " ".join(question.strip().lower().split())


def is_prompt_injection(question: str) -> bool:
    return bool(_INJECTION.search(normalize_question(question)))


def is_bare_topic(question: str) -> bool:
    return bool(_BARE_TOPIC.fullmatch(normalize_question(question).strip(" ?.!")))


def is_record_override(question: str) -> bool:
    """An instruction to discard stored records and assert a different fact."""

    return bool(_RECORD_OVERRIDE.search(normalize_question(question)))


_CALENDAR_STATUS = re.compile(
    r"\b(appointment|appointments|booking|bookings|calendar|meeting|meetings)\b"
)


def asks_for_stored_appointment(question: str) -> bool:
    """A question about an appointment already on file, not a request to create one."""

    text = normalize_question(question)
    if _BOOK_PERSON.search(text) or _APPOINTMENT.search(text) or _FOLLOW_UP.search(text):
        return False
    if re.search(r"\b(free|available|availability)\b", text):
        return False
    if re.search(r"\bcheck\b", text) and _CALENDAR_STATUS.search(text):
        return False
    return bool(_CALENDAR_STATUS.search(text))


def operation_intents(question: str) -> list[Intent]:
    """Actions this turn may prepare. A direct send stays a refusal, not a draft."""

    text = normalize_question(question)
    if _EXTERNAL_SEND.search(text) and not _FOLLOW_UP.search(text):
        return []
    found: list[Intent] = []
    if _FOLLOW_UP.search(text) or _DRAFT_EMAIL.search(text):
        found.append(Intent.follow_up)
    if _APPOINTMENT.search(text) or (
        _BOOK_PERSON.search(text) and not _NOT_APPOINTMENT.search(text)
    ):
        found.append(Intent.appointment)
    if _TASK.search(text):
        found.append(Intent.task)
    return found


def route_question(question: str, *, has_history: bool) -> Intent:
    text = normalize_question(question)
    if is_prompt_injection(text):
        return Intent.injection
    if _UNRELATED.search(text):
        return Intent.unrelated
    if _HANDOFF.search(text):
        return Intent.handoff
    if _EXTERNAL_SEND.search(text) and not _FOLLOW_UP.search(text):
        return Intent.mutation
    if _FOLLOW_UP.search(text):
        return Intent.follow_up
    if _APPOINTMENT.search(text):
        return Intent.appointment
    if _TASK.search(text):
        return Intent.task
    if _SUMMARY.search(text):
        return Intent.summary
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
    if is_bare_topic(text):
        return Intent.ambiguous
    if is_self_contained_reasoning(text):
        return Intent.general
    if has_history and _REPHRASE.search(text):
        return Intent.general
    if _REFERENCE.search(text):
        return Intent.grounded
    dangling = bool(_PRONOUN.search(text)) and not _WORKSPACE_SCOPE.search(text)
    if has_history and dangling and not _FACT.search(text) and len(text.split()) <= 12:
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


_STORED_LOOKUP = re.compile(
    r"\b(our|ours|stored|according to|on file|in the crm|in this workspace|"
    r"rate card|the document|the policy|the contract|do we (?:have|charge|store)|"
    r"does the (?:yard|warehouse|document|policy)|what does the)\b"
)
_MISSING_FIGURE = re.compile(
    r"\b(?:the|our|current|frozen|chilled|ambient|bonded|weekly|storage)\s+"
    r"(?:rate|fee|price|tariff|charge|salary)\b"
)
_RESULT_ASK = re.compile(
    r"\b(how many|how much|remain(?:ing|s)?|left|total|difference|calculate|compute|"
    r"multiplied|times|plus|minus|divided)\b"
)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)")
_PHONE_LIKE = re.compile(r"\+\d[\d\-]{6,}\d")


def is_self_contained_reasoning(question: str) -> bool:
    """A word problem that already states the quantities needed to compute an answer.

    Business nouns in that problem are the subject of the arithmetic. They are not
    a request to search the CRM or the document library.
    """

    text = normalize_question(question)
    if not text or is_prompt_injection(text) or is_record_override(text):
        return False
    if _FOLLOW_UP.search(text) or _APPOINTMENT.search(text) or _TASK.search(text):
        return False
    if _DRAFT_EMAIL.search(text) or _EXTERNAL_SEND.search(text):
        return False
    if _MUTATION_VERB.search(text) and _MUTATION_OBJECT.search(text):
        return False
    if _STORED_LOOKUP.search(text) or _MISSING_FIGURE.search(text):
        return False
    without_phones = _PHONE_LIKE.sub(" ", text)
    numbers = re.findall(r"\d+(?:\.\d+)?", without_phones)
    percent = _PERCENT.search(without_phones)
    operator = bool(
        re.search(r"\b(multiplied|times|plus|minus|divided|calculate|compute)\b", without_phones)
    )
    asks = bool(_RESULT_ASK.search(without_phones))
    if percent and len(numbers) >= 2 and (asks or operator):
        return True
    if operator and len(numbers) >= 2:
        return True
    if (
        asks
        and len(numbers) >= 2
        and re.search(r"\b(remain(?:ing|s)?|left|total|difference)\b", text)
    ):
        return True
    return False


def continues_supplied_reasoning(question: str, history: list[tuple[str, str]]) -> bool:
    """A short change to a calculation that was already stated in this conversation."""

    text = normalize_question(question)
    if not text or _STORED_LOOKUP.search(text) or _MISSING_FIGURE.search(text):
        return False
    if re.search(r"\b(company|companies|lead|document|policy)\b", text):
        return False
    if _REFERENCE.search(text):
        return False
    prior = next((content for role, content in reversed(history) if role == "user"), "")
    if not prior or not is_self_contained_reasoning(prior):
        return False
    return bool(re.search(r"(%|percent|instead|what if|remain|remaining|left|another)", text))


def arithmetic_hint(question: str) -> str | None:
    """State a figure that is fully determined by the quantities in the question."""

    if not is_self_contained_reasoning(question):
        return None
    text = normalize_question(_PHONE_LIKE.sub(" ", question))
    percent = _PERCENT.search(text)
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if percent and re.search(r"\b(cancel(?:led|s|ing)?|reduce[ds]?)\b", text):
        rate = float(percent.group(1))
        bases = [item for item in numbers if item != rate]
        if len(bases) == 1 and 0 <= rate <= 100:
            remain = bases[0] * (1 - rate / 100)
            cancelled = bases[0] * (rate / 100)
            if re.search(r"\b(remain(?:ing|s)?|left)\b", text):
                return _arithmetic_sentence(remain)
            if re.search(r"\b(were cancelled|canceled amount|cancelled amount)\b", text):
                return _arithmetic_sentence(cancelled)
    product = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:multiplied by|times)\s*(\d+(?:\.\d+)?)",
        text,
    )
    if product:
        return _arithmetic_sentence(float(product.group(1)) * float(product.group(2)))
    portion = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(\d+(?:\.\d+)?)",
        text,
    )
    if portion:
        return _arithmetic_sentence(float(portion.group(1)) / 100 * float(portion.group(2)))
    return None


def _arithmetic_sentence(value: float) -> str:
    shown = str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")
    return (
        f"The quantities in the question produce {shown}. "
        "That figure is arithmetic, not a stored company record."
    )


def is_open_conversation(question: str) -> bool:
    """General talk, knowledge, writing, or reasoning that should not search the workspace."""

    text = normalize_question(question)
    if not text or is_prompt_injection(text) or is_record_override(text):
        return False
    if is_self_contained_reasoning(text):
        return True
    if _GREETING.search(text) or _OBVIOUS_GENERAL.search(text):
        return True
    if _CREATIVE.search(text) and not re.search(
        r"\b(our|stored|according to|workspace|the document|follow-up|follow up)\b", text
    ):
        return True
    if _WORKSPACE_SCOPE.search(text) or _RECORD_FACT.search(text):
        return False
    if re.search(r"\bstatus of\b", text):
        return False
    return bool(
        re.search(
            r"\b(explain|why|what is|what's|who is|how does|how do i|brainstorm)\b",
            text,
        )
    )


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
