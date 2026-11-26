"""Turn a follow-up into a standalone retrieval query without a model call.

A pronoun or a short continuation is resolved from the previous user question
and the titles already cited in the thread. A new question that names its
own subject is left unchanged.
"""

import re

from app.domains.assistant.routing import refers_to_earlier_record

_TOKEN = re.compile(r"[a-z0-9]+")
_FOLLOW_UP = re.compile(
    r"^(and|also|what about|how about)\b|"
    r"\b(it|that|this|those|them|their|its|there)\b"
)
_STOP = {
    "about",
    "does",
    "from",
    "have",
    "into",
    "only",
    "that",
    "their",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "your",
}


def rewrite_question(question: str, history: list[tuple[str, str]], titles: list[str]) -> str:
    text = " ".join(question.split())
    if len(text) < 2:
        return text
    prior = [turn.strip() for role, turn in history if role == "user" and turn.strip()]
    if not prior and not titles:
        return text
    if not _FOLLOW_UP.search(text.lower()) and not refers_to_earlier_record(text):
        return text
    current = _terms(text)
    carried: list[str] = []
    if prior:
        for word in _TOKEN.findall(prior[-1].lower()):
            if word in current or word in _STOP or len(word) < 4 or word in carried:
                continue
            carried.append(word)
            if len(carried) == 8:
                break
    title_terms: list[str] = []
    for title in titles[:2]:
        for word in _TOKEN.findall(title.lower()):
            if len(word) < 5 or word in current or word in title_terms or word in _STOP:
                continue
            title_terms.append(word)
            if len(title_terms) == 4:
                break
    extra = carried + [term for term in title_terms if term not in carried]
    if not extra:
        return text
    return f"{text} {' '.join(extra)}"


def _terms(text: str) -> set[str]:
    return {word for word in _TOKEN.findall(text.lower()) if len(word) >= 4 and word not in _STOP}
