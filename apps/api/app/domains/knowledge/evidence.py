"""Decide whether a retrieved passage can answer the question.

Candidate search is allowed to be broad. A shared topic is not an answer.
A passage is evidence only when the question's rare constraints occur together
in that passage and the passage has the kind of fact the question asks for.
A superseded card is dropped when the question asks for the current fact and
a current card is also in the pool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9]+")
_CODE = re.compile(r"\b[A-Za-z]{2,}(?:-[A-Za-z0-9]+){1,}\b")
_EMAIL = re.compile(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DATE = re.compile(
    r"\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+\d{4}\b",
    re.IGNORECASE,
)
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_CLAUSE_SPLIT = re.compile(
    r",?\s+and\s+(?=what\b|how\b|when\b|where\b|who\b|the\b|whether\b)",
    re.IGNORECASE,
)
_CONTRAST = re.compile(
    r"\b(?:distinct from|rather than|instead of|other than)\s+([a-z0-9]+)",
    re.IGNORECASE,
)
_PRIVATE = re.compile(
    r"\b(?:home (?:address|postcode|phone)|mobile(?: number)?|telephone|phone number|"
    r"salary|wages?)\b",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")
_SALARY = re.compile(
    r"\b(?:salary|wages?)\b.{0,48}\d|\d.{0,48}\b(?:salary|wages?)\b",
    re.IGNORECASE,
)
_HOME = re.compile(r"\bhome (?:address|postcode|phone)\b", re.IGNORECASE)
_STEM = {
    "chilled": "chilled",
    "chiller": "chilled",
    "chillers": "chilled",
    "freezer": "frozen",
    "freezers": "frozen",
    "frozen": "frozen",
}
_SUPERSEDED = re.compile(r"\b(?:superseded|do not use this)\b", re.IGNORECASE)
_WANTS_OLD = re.compile(r"\b(?:superseded|previous|former|old)\b", re.IGNORECASE)
_STOP = {
    "about",
    "after",
    "also",
    "another",
    "before",
    "both",
    "card",
    "could",
    "does",
    "each",
    "from",
    "have",
    "into",
    "just",
    "more",
    "most",
    "only",
    "other",
    "should",
    "some",
    "such",
    "that",
    "their",
    "them",
    "then",
    "there",
    "this",
    "very",
    "what",
    "when",
    "date",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
}
_VERBS = {
    "arrive",
    "arrived",
    "arrives",
    "arriving",
    "come",
    "comes",
    "coming",
    "give",
    "given",
    "held",
    "hold",
    "holds",
    "keep",
    "keeps",
    "kept",
    "made",
    "make",
    "makes",
    "need",
    "needed",
    "needs",
    "store",
    "stored",
    "stores",
    "storing",
    "take",
    "taken",
    "takes",
}


@dataclass(frozen=True)
class PassageView:
    key: str
    title: str
    content: str
    score: float = 0.0


def select_answerable(
    question: str, passages: list[PassageView], *, limit: int = 5
) -> list[PassageView]:
    """Return passages that can answer ``question``, best first."""

    cleaned = " ".join(question.split())
    if len(cleaned) < 2 or not passages:
        return []
    clauses = _clauses(cleaned)
    if len(clauses) == 1 and _private_kind(cleaned):
        return [item for item in passages if _private_value(cleaned, item.content)][:limit]
    identified = _identified(cleaned, passages)
    if identified is not None:
        return _prefer_version(cleaned, identified)[:limit]
    chosen: list[PassageView] = []
    seen: set[str] = set()
    strict = len(clauses) == 1
    for clause in clauses:
        matches = _matches_for_clause(clause, passages, strict=strict)
        for item in _prefer_version(clause, matches):
            if item.key in seen:
                continue
            seen.add(item.key)
            chosen.append(item)
    return chosen[:limit]


def unanswered_parts(question: str, passages: list[PassageView]) -> list[str]:
    """Name clauses that have no supporting passage.

    A multi-part question can still be answered in part. The caller tells the
    model which part was not found instead of dropping the supported parts.
    """

    clauses = _clauses(" ".join(question.split()))
    if len(clauses) < 2:
        return []
    return [
        clause
        for clause in clauses
        if not _matches_for_clause(clause, passages, strict=False)
    ]


def _identified(question: str, passages: list[PassageView]) -> list[PassageView] | None:
    codes = [
        code.lower()
        for code in _CODE.findall(question)
        if any(mark.isdigit() for mark in code)
    ]
    emails = [email.lower() for email in _EMAIL.findall(question)]
    if not codes and not emails:
        return None
    kept = [
        item
        for item in passages
        if all(code in item.content.lower() for code in codes)
        and all(email in item.content.lower() for email in emails)
    ]
    return _rank(question, kept)


def _clauses(question: str) -> list[str]:
    parts = [part.strip() for part in _CLAUSE_SPLIT.split(question) if part.strip()]
    return parts or [question]


def _matches_for_clause(
    clause: str, passages: list[PassageView], *, strict: bool
) -> list[PassageView]:
    if _private_kind(clause):
        return [item for item in passages if _private_value(clause, item.content)]
    return _clause_matches(clause, passages, strict=strict)


def _private_kind(question: str) -> bool:
    return _PRIVATE.search(question) is not None


def _private_value(question: str, content: str) -> bool:
    """A salary, telephone, or home address must be written as that fact."""

    if _SUPERSEDED.search(content):
        return False
    if _HOME.search(question):
        return _home_value(content)
    if re.search(r"\b(?:salary|wages?)\b", question, re.IGNORECASE):
        return _SALARY.search(content) is not None
    if re.search(r"\b(?:mobile(?: number)?|telephone|phone number)\b", question, re.IGNORECASE):
        return _phone_value(content)
    return False


def _phone_value(content: str) -> bool:
    for match in _PHONE.finditer(content):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 10:
            return True
    return False


def _clause_matches(
    clause: str, passages: list[PassageView], *, strict: bool = True
) -> list[PassageView]:
    excluded = {match.group(1).lower() for match in _CONTRAST.finditer(clause)}
    pool = passages
    if excluded:
        kept = [item for item in passages if not any(_has_token(item, token) for token in excluded)]
        pool = kept or passages
    frequency = _frequency(pool)
    attested = []
    for token in _tokens(clause):
        if token in excluded or token in _VERBS:
            continue
        if _document_frequency(token, frequency) > 0:
            attested.append(token)
    locators = [
        token
        for token in attested
        if _document_frequency(token, frequency) <= 2
    ]
    shaped = [item for item in pool if _answer_shape(clause, item.content)]
    in_answer = [token for token in locators if any(_has_token(item, token) for item in shaped)]
    if strict and any(token not in in_answer for token in locators):
        return []
    if not strict and locators and not in_answer:
        return []
    active = locators if strict or not in_answer else in_answer
    if not active:
        eligible = _best_overlap(clause, shaped)
    else:
        together = [item for item in shaped if _contains_all(item, active)]
        if together:
            eligible = together
        else:
            eligible = _majority(active, shaped)
    if _missing_family(attested, locators, eligible, pool):
        return []
    return _rank(clause, eligible)


def _majority(locators: list[str], passages: list[PassageView]) -> list[PassageView]:
    """Keep the passage that covers more than half of a split constraint set."""

    if not passages:
        return []
    scored = [(item, sum(_has_token(item, token) for token in locators)) for item in passages]
    best = max(score for _item, score in scored)
    if best * 2 <= len(locators):
        return []
    return [item for item, score in scored if score == best]


def _missing_family(
    attested: list[str],
    locators: list[str],
    eligible: list[PassageView],
    passages: list[PassageView],
) -> bool:
    """A place and a company that never appear together do not answer the question."""

    if not eligible:
        return False
    locator_set = set(locators)
    for token in attested:
        if token in locator_set:
            continue
        if any(_has_token(item, token) for item in eligible):
            continue
        if any(_has_token(item, token) for item in passages):
            return True
    return False


def _prefer_version(question: str, passages: list[PassageView]) -> list[PassageView]:
    superseded = [item for item in passages if _SUPERSEDED.search(item.content)]
    current = [item for item in passages if item not in superseded]
    if _WANTS_OLD.search(question) and superseded:
        return _rank(question, superseded)
    if current and superseded:
        return _rank(question, current)
    return _rank(question, passages)


def _best_overlap(clause: str, passages: list[PassageView]) -> list[PassageView]:
    if not passages:
        return []
    best = max(_overlap(clause, item) for item in passages)
    if best < 1:
        return []
    return [item for item in passages if _overlap(clause, item) >= best]


def _rank(question: str, passages: list[PassageView]) -> list[PassageView]:
    return sorted(
        passages,
        key=lambda item: (_overlap(question, item), item.score),
        reverse=True,
    )


def _duration(content: str) -> bool:
    return (
        re.search(
            r"\b\d+\s+(?:business\s+)?(?:days|day|weeks|week|hours|hour)\b",
            content,
            re.IGNORECASE,
        )
        is not None
    )


def _answer_shape(clause: str, content: str) -> bool:
    text = clause.lower()
    if any(word in text for word in ("exclude", "exclusion", "excludes")):
        return "exclud" in content.lower()
    if text.startswith("who") or " email" in f" {text}":
        return bool(_EMAIL.search(content) or re.search(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", content))
    if text.startswith("where") or " where " in f" {text}" or "located" in text:
        return bool(
            re.search(r"\b\d+\s+[A-Za-z]+", content)
            or re.search(r"\b(?:street|lane|road|avenue|dock|quay)\b", content, re.IGNORECASE)
        )
    if "which date" in text or "what date" in text:
        return bool(_DATE.search(content))
    if "when" in text or "reopen" in text:
        if any(word in text for word in ("due", "long", "window", "within", "invoice", "notice")):
            return bool(_DATE.search(content) or _duration(content))
        return bool(_DATE.search(content))
    if any(
        word in text
        for word in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "hours",
            "receiving",
            "open",
        )
    ):
        clock = _TIME.search(content) is not None
        state = re.search(r"\b(?:open|closed)\b", content, re.IGNORECASE) is not None
        return clock or state
    if any(
        word in text
        for word in ("temperature", "celsius", "frozen", "freezer", "chilled", "chiller", "degrees")
    ):
        return bool(re.search(r"\d|minus|degrees", content, re.IGNORECASE))
    if any(
        word in text
        for word in (
            "how many",
            "how much",
            "how quickly",
            "how soon",
            "how long",
            "charge",
            "rate",
            "price",
            "fee",
            "cost",
            "deposit",
            "paid",
            "pay",
            "percent",
            "limit",
            "hold",
        )
    ):
        return bool(re.search(r"\d", content))
    if "code" in text:
        return bool(_CODE.search(content))
    return True


def _home_value(content: str) -> bool:
    if _SUPERSEDED.search(content):
        return False
    return bool(re.search(r"\bhome address is \d", content, re.IGNORECASE))


def _frequency(passages: list[PassageView]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in passages:
        for token in set(_tokens(f"{item.title} {item.content}")):
            counts[token] = counts.get(token, 0) + 1
    return counts


def _document_frequency(token: str, frequency: dict[str, int]) -> int:
    if token in frequency:
        return frequency[token]
    total = 0
    for other, count in frequency.items():
        if _same_token(token, other):
            total += count
    return total


def _contains_all(item: PassageView, tokens: list[str]) -> bool:
    return all(_has_token(item, token) for token in tokens)


def _overlaps(item: PassageView, tokens: list[str]) -> bool:
    if not tokens:
        return True
    return any(_has_token(item, token) for token in tokens)


def _overlap(question: str, item: PassageView) -> int:
    return sum(1 for token in _tokens(question) if _has_token(item, token))


def _has_token(item: PassageView, token: str) -> bool:
    words = _TOKEN.findall(f"{item.title} {item.content}".lower())
    for index, word in enumerate(words):
        if not _same_token(token, word):
            continue
        earlier = words[max(0, index - 3) : index]
        if "not" in earlier or "never" in earlier:
            continue
        return True
    return False


def _same_token(left: str, right: str) -> bool:
    left = _STEM.get(left, left)
    right = _STEM.get(right, right)
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 4 and longer.startswith(shorter)


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) >= 4 and token not in _STOP
    ]
