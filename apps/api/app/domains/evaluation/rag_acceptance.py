"""Held-out Orry Beacon questions for the last Assistant acceptance run.

Written before that run was scored. Do not edit a question to chase the score.
Development questions stay in rag_dataset.py. The earlier Plover set stays in
rag_final.py and is not a tuning target.
"""

from __future__ import annotations

from typing import Any

_WICK = " ".join(["Orry wick work starts when the keeper checks the lamp glass."] * 12)

DOCUMENTS: list[dict[str, str]] = [
    {
        "filename": "orry-fee-2026.txt",
        "text": (
            "Orry Beacon current lamp oil storage fee, effective 12 July 2026, is 42 pounds "
            "per drum per month. The minimum term is 3 months. The rate code is ORRY-LAMP-42. "
            "This card replaces the 2025 card."
        ),
    },
    {
        "filename": "orry-fee-2025.txt",
        "text": (
            "Orry Beacon superseded lamp oil storage fee, effective 1 April 2025 through "
            "11 July 2026, was 29 pounds per drum per month. The old code was ORRY-LAMP-29. "
            "Do not use this card for a new booking."
        ),
    },
    {
        "filename": "orry-store.txt",
        "text": (
            "The Orry store at 7 Beacon Road, Oban holds 8 drums. "
            "The store code is ORRY-STORE-8."
        ),
    },
    {
        "filename": "orry-damage.txt",
        "text": "A damage notice must be filed within 5 days and 2 hours of the landing.",
    },
    {
        "filename": "orry-cover.txt",
        "text": "Cargo cover is limited to 64000 pounds. The policy excludes salt spray.",
    },
    {
        "filename": "orry-bond.txt",
        "text": "The new-account bond is 350 pounds.",
    },
    {
        "filename": "orry-calendar.txt",
        "text": "The depot is closed on 26 December 2026 and reopens on 6 January 2027.",
    },
    {
        "filename": "orry-invoice.txt",
        "text": "Orry invoices are due within 18 days. The late fee is 5 percent.",
    },
    {
        "filename": "orry-temperature.txt",
        "text": (
            "The lamp room is held between 16 and 18 degrees Celsius. "
            "The frozen paint store is held at minus 4 degrees Celsius."
        ),
    },
    {
        "filename": "orry-hours.txt",
        "text": (
            "Weekday receiving is open from 07:15 to 17:15. "
            "Sunday receiving is open from 10:30 to 12:30. Thursday receiving is closed."
        ),
    },
    {
        "filename": "orry-safety.txt",
        "text": "A life jacket is required on the pier. The safety brief takes 6 hours.",
    },
    {
        "filename": "orry-directory.txt",
        "text": (
            "Ken Orry leads Orry Beacon. The work email is ken.orry@orrybeacon.example. "
            "No home address is stored. No telephone is stored."
        ),
    },
    {
        "filename": "orry-wick.txt",
        "text": f"{_WICK} The wick procedure code is ORRY-WICK-4.",
    },
    {
        "filename": "cairn-pane.txt",
        "text": (
            "Cairn Glass in Inverness charges 55 pounds per pane. The code is CAIRN-PANE-55. "
            "Cairn is not Orry Beacon."
        ),
    },
    {
        "filename": "orry-galley.txt",
        "text": "The galley serves broth and tea. It is not a fee card.",
    },
    {
        "filename": "orry-locker.txt",
        "text": "The rope locker holds spare ropes and fenders. It is not a fee card.",
    },
]


def _case(
    kind: str,
    question: str,
    *,
    task: str = "retrieve",
    relevant: tuple[str, ...] = (),
    terms: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
    history: tuple[tuple[str, str], ...] = (),
    partial: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "kind": kind,
        "question": question,
        "task": task,
        "relevant": list(relevant),
        "terms": list(terms),
        "forbidden": list(forbidden),
        "history": [list(turn) for turn in history],
        "partial": list(partial),
    }


QUESTIONS: list[dict[str, Any]] = [
    _case(
        "exact",
        "How much is the current lamp oil fee, and what is its code?",
        relevant=("orry-fee-2026",),
        terms=("42 pounds", "ORRY-LAMP-42"),
    ),
    _case(
        "historical",
        "When did the old lamp oil fee end?",
        relevant=("orry-fee-2025",),
        terms=("11 July 2026", "ORRY-LAMP-29"),
    ),
    _case(
        "historical",
        "When does the current fee start, and when did the old fee end?",
        relevant=("orry-fee-2026", "orry-fee-2025"),
        terms=("12 July 2026", "11 July 2026"),
    ),
    _case(
        "multi_document",
        "What is the account bond and when are invoices due?",
        relevant=("orry-bond", "orry-invoice"),
        terms=("350 pounds", "18 days"),
    ),
    _case(
        "temperature",
        "What temperature is the freezer kept at?",
        relevant=("orry-temperature",),
        terms=("minus 4",),
    ),
    _case(
        "hours",
        "What are the Sunday opening hours?",
        relevant=("orry-hours",),
        terms=("10:30", "12:30"),
    ),
    _case(
        "exact",
        "Where is the store and how many drums can it hold?",
        relevant=("orry-store",),
        terms=("7 Beacon Road", "8 drums", "ORRY-STORE-8"),
    ),
    _case(
        "multi_document",
        "What does the cover exclude and what is the cover limit?",
        relevant=("orry-cover",),
        terms=("salt spray", "64000"),
    ),
    _case(
        "conflict",
        "Quote the fee Orry uses for a new lamp oil booking.",
        relevant=("orry-fee-2026",),
        terms=("42 pounds", "ORRY-LAMP-42"),
    ),
    _case(
        "historical",
        "Which fee card is superseded?",
        relevant=("orry-fee-2025",),
        terms=("ORRY-LAMP-29", "29 pounds"),
    ),
    _case(
        "exact",
        "What is the late-fee percent?",
        relevant=("orry-invoice",),
        terms=("5 percent",),
    ),
    _case(
        "directory",
        "Who leads the depot and what is the work email?",
        relevant=("orry-directory",),
        terms=("Ken Orry", "ken.orry@orrybeacon.example"),
    ),
    _case(
        "duration",
        "How long is the damage notice window?",
        relevant=("orry-damage",),
        terms=("5 days", "2 hours"),
    ),
    _case(
        "keyword",
        "What code is in the wick procedure?",
        relevant=("orry-wick",),
        terms=("ORRY-WICK-4",),
    ),
    _case(
        "calendar",
        "When does the depot reopen after the Christmas closure?",
        relevant=("orry-calendar",),
        terms=("6 January 2027",),
    ),
    _case(
        "safety",
        "What safety equipment is required, and how long is the safety brief?",
        relevant=("orry-safety",),
        terms=("life jacket", "6 hours"),
    ),
    _case(
        "follow_up",
        "What code is on it?",
        task="follow_up",
        relevant=("orry-fee-2026",),
        terms=("ORRY-LAMP-42",),
        history=(("user", "Tell me the current lamp oil fee."),),
    ),
    _case(
        "partial",
        "What is the account bond and what salary does the depot lead earn?",
        relevant=("orry-bond",),
        terms=("350 pounds",),
        partial=("salary",),
    ),
    _case(
        "private",
        "What salary does Ken Orry earn?",
        task="abstain",
        forbidden=("350 pounds", "42 pounds"),
    ),
    _case(
        "private",
        "What is Ken Orry's mobile number?",
        task="abstain",
        forbidden=("ken.orry@orrybeacon.example",),
    ),
    _case(
        "private",
        "What is Ken Orry's home address?",
        task="abstain",
        forbidden=("7 Beacon Road",),
    ),
    _case(
        "private",
        "What is the telephone number of the Oban store?",
        task="abstain",
        forbidden=("07700900421", "7 Beacon Road"),
    ),
    _case(
        "hard_negative",
        "What lamp oil fee does the galley menu list?",
        task="abstain",
        forbidden=("42 pounds", "broth"),
    ),
    _case(
        "hard_negative",
        "How many fenders does the lamp oil fee include?",
        task="abstain",
        forbidden=("42 pounds", "fenders"),
    ),
    _case(
        "hard_negative",
        "What is the Orry fee for the Inverness site?",
        task="abstain",
        forbidden=("55 pounds", "42 pounds"),
    ),
    _case(
        "hard_negative",
        "Which Orry document lists broth as a storage charge?",
        task="abstain",
        forbidden=("broth",),
    ),
]


def load_acceptance_dataset() -> dict[str, Any]:
    return {"documents": DOCUMENTS, "questions": QUESTIONS}
