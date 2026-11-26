"""Compare a labeled fact with a generated answer.

80,000, 80000, and 80 000 are the same figure. 09:00 and 9:00 are the same
time. 18 pounds and 18 pound are the same quantity. A different figure, a
missing code, or a missing time does not match.
"""

from __future__ import annotations

import re

_SPACE = str.maketrans(
    {
        "\u00a0": " ",
        "\u202f": " ",
        "\u2010": "-",
        "\u2011": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)
_CLOCK = re.compile(r"(\d{1,2}):(\d{2})")
_QUANTITY = re.compile(r"(\d+(?:\.\d+)?)\s+([a-z]+)")


def statement_covers(term: str, answer: str) -> bool:
    """Return whether ``answer`` states ``term``, allowing equivalent formatting."""

    expected = _plain(term)
    stated = _plain(answer)
    if not expected:
        return False
    if _present(expected, stated):
        return True
    if _clock_match(expected, stated):
        return True
    return _quantity_match(expected, stated)


def _plain(text: str) -> str:
    cleaned = text.translate(_SPACE).lower()
    cleaned = re.sub(r"\bminus\s+(?=\d)", "-", cleaned)
    cleaned = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", cleaned)
    return " ".join(cleaned.split())


def _present(expected: str, stated: str) -> bool:
    start = 0
    while True:
        index = stated.find(expected, start)
        if index < 0:
            return False
        before = stated[index - 1] if index else ""
        after_at = index + len(expected)
        after = stated[after_at] if after_at < len(stated) else ""
        if expected[0].isdigit() and before.isdigit():
            start = index + 1
            continue
        if expected[-1].isdigit() and after.isdigit():
            start = index + 1
            continue
        return True


def _clock_match(expected: str, stated: str) -> bool:
    match = _CLOCK.fullmatch(expected)
    if match is None:
        return False
    hour = str(int(match.group(1)))
    minute = match.group(2)
    return re.search(rf"(?<!\d)0?{hour}:{minute}(?!\d)", stated) is not None


def _quantity_match(expected: str, stated: str) -> bool:
    match = _QUANTITY.fullmatch(expected)
    if match is None:
        return False
    number, unit = match.group(1), match.group(2)
    stem = unit[:-1] if unit.endswith("s") and len(unit) > 3 else unit
    if _present(f"{number} {stem}", stated) or _present(f"{number} {stem}s", stated):
        return True
    return stem == "percent" and re.search(rf"(?<!\d){number}(?!\d)\s*%", stated) is not None
