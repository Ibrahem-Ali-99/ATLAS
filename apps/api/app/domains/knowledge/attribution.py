"""Choose citations from an answer, not from retrieval rank.

Retrieved rows may be shown to the model. A citation is a row whose text
contains a specific fact the answer states. The model's claim that a row is
relevant is not checked here, because this function never reads a model-chosen id.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

QUALIFIED_ANSWER = "I could not confirm that against the company records."

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_CONTENT_WORD = re.compile(r"[a-z0-9]+")
_EMAIL = re.compile(r"[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}")
_CODE = re.compile(r"\b[a-z0-9]+(?:-[a-z0-9]+){1,}\b")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_REFUSAL = (
    "could not find",
    "could not confirm",
    "not found",
    "do not state",
    "does not state",
    "was not found",
    "no supporting",
)
_STOP_WORDS = {
    "that",
    "this",
    "with",
    "from",
    "have",
    "does",
    "your",
    "their",
    "into",
    "only",
    "what",
    "when",
    "where",
    "which",
    "about",
    "would",
    "could",
    "there",
    "them",
    "then",
    "than",
    "also",
    "such",
    "other",
    "each",
    "some",
    "more",
    "most",
    "very",
    "just",
    "like",
    "over",
    "after",
    "before",
    "while",
    "because",
    "should",
    "been",
    "were",
    "they",
    "will",
    "hold",
    "holds",
}
_UNITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_NUMBER_WORDS = re.compile(
    r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[-\s]+(one|two|three|four|five|six|seven|eight|nine))?\b"
    r"|\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)\b"
)


def attribute_answer(
    question: str, answer: str, passages: Sequence[tuple[str, str]]
) -> tuple[str, list[str]]:
    """Return the answer to store and the passage ids that support it.

    A number, code, or email the answer states must occur in the supplied text.
    Otherwise the stored answer says the fact could not be confirmed, with no citation.
    """

    cleaned = answer.strip()
    if not cleaned or not passages:
        return cleaned, []
    normalized = [_normalize(text) for _passage_id, text in passages]
    if _refusal(cleaned) and not _has_hard_facts(cleaned):
        return cleaned, []
    if _missing_hard_fact(cleaned, normalized):
        return QUALIFIED_ANSWER, []
    supported = [
        passage_id
        for (passage_id, _text), normalized_text in zip(passages, normalized, strict=True)
        if _supports(question, cleaned, normalized_text)
    ]
    return cleaned, supported


def _supports(question: str, answer: str, passage: str) -> bool:
    for sentence in _sentences(answer):
        if _sentence_supports(question, sentence, passage):
            return True
    return False


def _sentence_supports(question: str, sentence: str, passage: str) -> bool:
    emails, codes, numbers = _hard_facts(sentence)
    if emails or codes or numbers:
        return any(_contains(passage, fact) for fact in (*emails, *codes, *numbers))
    words = _content_words(sentence) - _content_words(question) - _STOP_WORDS
    if not words:
        return False
    return bool(words & _content_words(passage))


def _has_hard_facts(text: str) -> bool:
    emails, codes, numbers = _hard_facts(text)
    return bool(emails or codes or numbers)


def _missing_hard_fact(answer: str, passages: Sequence[str]) -> bool:
    emails, codes, numbers = _hard_facts(answer)
    facts = (*emails, *codes, *numbers)
    if not facts:
        return False
    return any(not any(_contains(passage, fact) for passage in passages) for fact in facts)


def _hard_facts(text: str) -> tuple[set[str], set[str], set[str]]:
    normalized = _normalize(text)
    emails = set(_EMAIL.findall(normalized))
    codes = {code for code in _CODE.findall(normalized) if any(char.isdigit() for char in code)}
    numbers = {
        number
        for number in _NUMBER.findall(normalized)
        if not any(number in code for code in codes)
    }
    return emails, codes, numbers


def _refusal(answer: str) -> bool:
    lowered = answer.lower()
    return any(phrase in lowered for phrase in _REFUSAL)


def _sentences(answer: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_SPLIT.split(answer) if part.strip()]
    return parts or [answer.strip()]


def _contains(passage: str, fact: str) -> bool:
    if fact.isdigit() or _NUMBER.fullmatch(fact):
        target = _canonical_number(fact)
        return any(_canonical_number(found) == target for found in _NUMBER.findall(passage))
    return fact in passage


def _canonical_number(value: str) -> str:
    """Drop thousands separators and leading zeros without merging 9 and 19."""

    if "." in value:
        whole, fraction = value.split(".", 1)
        return f"{whole.lstrip('0') or '0'}.{fraction}"
    return value.lstrip("0") or "0"


def _content_words(text: str) -> set[str]:
    return {word for word in _CONTENT_WORD.findall(_normalize(text)) if len(word) >= 4}


def _normalize(text: str) -> str:
    lowered = (
        text.lower()
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    lowered = re.sub(r"(?<=\d),(?=\d)", "", lowered)
    return _NUMBER_WORDS.sub(_number_word, lowered)


def _number_word(match: re.Match[str]) -> str:
    tens = match.group(1)
    unit = match.group(2)
    small = match.group(3)
    if tens and unit:
        return str(_TENS[tens] + _UNITS[unit])
    if tens:
        return str(_TENS[tens])
    if small:
        return str(_UNITS[small])
    return match.group(0)
