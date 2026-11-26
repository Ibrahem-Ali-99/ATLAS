"""Fresh Plover Dock questions. Written before this set was scored.

Do not add, remove, or reword a question after reading a score from this file.
Development tuning must not import it.
"""

from __future__ import annotations

from typing import Any

_CRANE = " ".join(
    ["Plover crane checks start when the hatch opens and the clerk reads the lift plan."] * 12
)

DOCUMENTS: list[dict[str, str]] = [
    {
        "filename": "plover-fee-2026.txt",
        "text": (
            "Plover Dock current quay fee, effective 4 May 2026, is 27 pounds per tonne "
            "per day. The minimum call is 2 days. The fee code is PLOVER-QUAY-27. "
            "This card replaces the 2023 card."
        ),
    },
    {
        "filename": "plover-fee-2023.txt",
        "text": (
            "Plover Dock superseded quay fee, effective 1 June 2023 through 3 May 2026, "
            "was 19 pounds per tonne per day. The old code was PLOVER-QUAY-19. "
            "Do not use this card for a new booking."
        ),
    },
    {
        "filename": "plover-shed.txt",
        "text": (
            "The Plover container shed at 9 Dock Street, Hull holds 15 containers. "
            "The shed code is PLOVER-SHED-15. Welding is prohibited in the container shed."
        ),
    },
    {
        "filename": "plover-damage.txt",
        "text": (
            "Plover answers radio calls within 3 hours. "
            "Damage notices must be filed within 9 days of discharge."
        ),
    },
    {
        "filename": "plover-insurance.txt",
        "text": (
            "Plover hull insurance pays up to 80000 pounds. "
            "Cover excludes freshwater rust and delay."
        ),
    },
    {
        "filename": "plover-bond.txt",
        "text": (
            "A new Plover account needs a signed tariff and a bond of 750 pounds "
            "before the first container is landed."
        ),
    },
    {
        "filename": "plover-closure.txt",
        "text": (
            "Plover Dock gates are closed on 26 December 2026. "
            "The gates reopen on 4 January 2027."
        ),
    },
    {
        "filename": "plover-invoice.txt",
        "text": (
            "Plover invoices are due within 21 days. "
            "A late fee of 3 percent applies after the due date."
        ),
    },
    {
        "filename": "plover-temperature.txt",
        "text": (
            "Plover chilled rooms are held between 0 and 1 degrees Celsius. "
            "Frozen rooms are held at minus 22 degrees Celsius."
        ),
    },
    {
        "filename": "plover-hours.txt",
        "text": (
            "Plover gate access is open Monday to Friday from 06:30 to 16:30. "
            "Sunday gate access is 09:00 to 11:00. Wednesday gate access is closed."
        ),
    },
    {
        "filename": "plover-safety.txt",
        "text": (
            "Plover requires a hard hat in the shed. "
            "Report an incident within 12 hours to the dock office."
        ),
    },
    {
        "filename": "plover-directory.txt",
        "text": (
            "The Plover dock office lead is Ivo Plover. "
            "His work email is ivo.plover@ploverdock.example. No home address is stored."
        ),
    },
    {
        "filename": "plover-crane-sop.txt",
        "text": _CRANE + " The crane check code is PLOVER-CRANE-3.",
    },
    {
        "filename": "bramble-rate.txt",
        "text": (
            "Bramble Freight road storage in Leeds is 31 pounds per tonne per day. "
            "The Bramble code is BRAMBLE-ROAD-31. Bramble is not Plover Dock."
        ),
    },
    {
        "filename": "canteen-menu.txt",
        "text": "The dock canteen lists stew, bread, and tea. It does not describe freight.",
    },
    {
        "filename": "stationery-cupboard.txt",
        "text": "The stationery cupboard holds pencils, envelopes, and spare clips.",
    },
]

COMPANIES: list[dict[str, str]] = [
    {"name": "Plover Dock", "industry": "port services"},
    {"name": "Bramble Freight", "industry": "road freight"},
    {"name": "Canteen Co", "industry": "catering"},
]

LEADS: list[dict[str, str]] = [
    {
        "title": "Dock Street extension",
        "company": "Plover Dock",
        "notes": "6 containers inbound on 18 June 2026.",
    },
    {
        "title": "Bramble Leeds quote",
        "company": "Bramble Freight",
        "notes": "Asked for the Leeds 31 pound rate.",
    },
    {
        "title": "Stew order",
        "company": "Canteen Co",
        "notes": "Order more stew for the dock canteen.",
    },
]

CONTACTS: list[dict[str, str]] = [
    {
        "full_name": "Ivo Plover",
        "company": "Plover Dock",
        "email": "ivo.plover@ploverdock.example",
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
) -> dict[str, Any]:
    return {
        "kind": kind,
        "question": question,
        "task": task,
        "relevant": list(relevant),
        "terms": list(terms),
        "forbidden": list(forbidden),
        "history": [list(turn) for turn in history],
    }


FINAL: list[dict[str, Any]] = [
    _case(
        "paraphrase",
        "What does Plover Dock charge per tonne for one day on the quay now?",
        relevant=("plover-fee-2026",),
        terms=("27 pounds", "PLOVER-QUAY-27"),
        forbidden=("19 pounds", "PLOVER-QUAY-19", "BRAMBLE-ROAD-31"),
    ),
    _case(
        "paraphrase",
        "Where is the container shed in Hull?",
        relevant=("plover-shed",),
        terms=("9 Dock Street", "15 containers"),
    ),
    _case(
        "paraphrase",
        "How quickly must damage be notified after discharge?",
        relevant=("plover-damage",),
        terms=("9 days",),
    ),
    _case(
        "paraphrase",
        "When is the gate shut for Christmas 2026?",
        relevant=("plover-closure",),
        terms=("26 December 2026",),
    ),
    _case(
        "paraphrase",
        "What temperature is the freezer store kept at?",
        relevant=("plover-temperature",),
        terms=("minus 22",),
    ),
    _case(
        "paraphrase",
        "Who leads the dock office and what is his work email?",
        relevant=("plover-directory",),
        terms=("Ivo Plover", "ivo.plover@ploverdock.example"),
    ),
    _case(
        "paraphrase",
        "What bond is required before the first container is landed?",
        relevant=("plover-bond",),
        terms=("750 pounds",),
    ),
    _case(
        "paraphrase",
        "Does Sunday morning gate access run?",
        relevant=("plover-hours",),
        terms=("09:00",),
    ),
    _case(
        "paraphrase",
        "Is the gate open on Wednesday?",
        relevant=("plover-hours",),
        terms=("Wednesday", "closed"),
    ),
    _case(
        "paraphrase",
        "What protective item does the shed require?",
        relevant=("plover-safety",),
        terms=("hard hat",),
    ),
    _case(
        "paraphrase",
        "How soon must a shed incident be reported?",
        relevant=("plover-safety",),
        terms=("12 hours",),
    ),
    _case("keyword", "PLOVER-QUAY-27", relevant=("plover-fee-2026",), terms=("PLOVER-QUAY-27",)),
    _case("keyword", "PLOVER-SHED-15", relevant=("plover-shed",), terms=("PLOVER-SHED-15",)),
    _case("keyword", "PLOVER-CRANE-3", relevant=("plover-crane-sop",), terms=("PLOVER-CRANE-3",)),
    _case(
        "keyword",
        "ivo.plover@ploverdock.example",
        relevant=("plover-directory",),
        terms=("ivo.plover@ploverdock.example",),
    ),
    _case("keyword", "BRAMBLE-ROAD-31", relevant=("bramble-rate",), terms=("BRAMBLE-ROAD-31",)),
    _case(
        "multi_document",
        "What is the current daily quay fee and what is the minimum call?",
        relevant=("plover-fee-2026",),
        terms=("27 pounds", "2 days"),
        forbidden=("19 pounds",),
    ),
    _case(
        "multi_document",
        "What is the current Plover fee and what does hull insurance exclude?",
        relevant=("plover-fee-2026", "plover-insurance"),
        terms=("27 pounds", "freshwater rust"),
        forbidden=("19 pounds",),
    ),
    _case(
        "multi_document",
        "How many containers can the Hull shed hold, and how long is the damage notice?",
        relevant=("plover-shed", "plover-damage"),
        terms=("15 containers", "9 days"),
    ),
    _case(
        "multi_document",
        "What is the account bond and when are dock invoices due?",
        relevant=("plover-bond", "plover-invoice"),
        terms=("750 pounds", "21 days"),
    ),
    _case(
        "conflict",
        "What is the current Plover quay fee?",
        relevant=("plover-fee-2026",),
        terms=("27 pounds", "PLOVER-QUAY-27"),
        forbidden=("19 pounds", "PLOVER-QUAY-19"),
    ),
    _case(
        "conflict",
        "Which Plover fee card is superseded?",
        relevant=("plover-fee-2023",),
        terms=("19 pounds", "PLOVER-QUAY-19"),
    ),
    _case(
        "conflict",
        "What does Plover charge, as distinct from Bramble?",
        relevant=("plover-fee-2026",),
        terms=("27 pounds",),
        forbidden=("BRAMBLE-ROAD-31",),
    ),
    _case(
        "conflict",
        "What does Bramble charge in Leeds?",
        relevant=("bramble-rate",),
        terms=("31 pounds", "BRAMBLE-ROAD-31"),
        forbidden=("PLOVER-QUAY-27",),
    ),
    _case(
        "numeric",
        "How many containers does the Plover shed hold?",
        relevant=("plover-shed",),
        terms=("15 containers",),
    ),
    _case(
        "numeric",
        "What is the late fee percent on a Plover invoice?",
        relevant=("plover-invoice",),
        terms=("3 percent",),
    ),
    _case(
        "numeric",
        "How many days does Plover allow for a damage notice?",
        relevant=("plover-damage",),
        terms=("9 days",),
    ),
    _case(
        "numeric",
        "What is the hull insurance limit in pounds?",
        relevant=("plover-insurance",),
        terms=("80000",),
    ),
    _case(
        "date",
        "On which date does the current Plover fee take effect?",
        relevant=("plover-fee-2026",),
        terms=("4 May 2026",),
    ),
    _case(
        "date",
        "When did the old Plover fee end?",
        relevant=("plover-fee-2023",),
        terms=("3 May 2026",),
    ),
    _case(
        "date",
        "When do the gates reopen after the December 2026 closure?",
        relevant=("plover-closure",),
        terms=("4 January 2027",),
    ),
    _case(
        "follow_up",
        "Where is it?",
        task="follow_up",
        relevant=("plover-shed",),
        terms=("9 Dock Street",),
        history=(("user", "What does the Plover container shed hold?"),),
    ),
    _case(
        "follow_up",
        "What code is that?",
        task="follow_up",
        relevant=("plover-fee-2026",),
        terms=("PLOVER-QUAY-27",),
        history=(("user", "What is the current Plover quay fee?"),),
    ),
    _case(
        "follow_up",
        "What does it exclude?",
        task="follow_up",
        relevant=("plover-insurance",),
        terms=("freshwater rust",),
        history=(("user", "Tell me about Plover hull insurance."),),
    ),
    _case(
        "follow_up",
        "And when does it reopen?",
        task="follow_up",
        relevant=("plover-closure",),
        terms=("4 January 2027",),
        history=(("user", "When is Plover Dock closed in December 2026?"),),
    ),
    _case(
        "hard_negative",
        "What does the dock canteen charge for quay storage?",
        task="abstain",
        forbidden=("27 pounds", "stew"),
    ),
    _case(
        "hard_negative",
        "What is Plover Dock's Leeds road rate?",
        task="abstain",
        forbidden=("31 pounds", "BRAMBLE-ROAD-31"),
    ),
    _case(
        "hard_negative",
        "How many pencils are stored in the container shed?",
        task="abstain",
        forbidden=("pencils",),
    ),
    _case(
        "hard_negative",
        "What is the canteen freezer temperature?",
        task="abstain",
        forbidden=("minus 22",),
    ),
    _case(
        "hard_negative",
        "How many envelopes are kept in the Hull shed?",
        task="abstain",
        forbidden=("envelopes",),
    ),
    _case(
        "hard_negative",
        "What does the stationery cupboard charge per tonne?",
        task="abstain",
        forbidden=("27 pounds", "pencils"),
    ),
    _case(
        "hard_negative",
        "When does Bramble close its Hull gate in December 2026?",
        task="abstain",
        forbidden=("26 December 2026",),
    ),
    _case(
        "unsupported",
        "What is Ivo Plover's home address?",
        task="abstain",
        forbidden=("Dock Street",),
    ),
    _case(
        "unsupported",
        "What is Ivo Plover's mobile number?",
        task="abstain",
        forbidden=("ivo.plover@",),
    ),
    _case(
        "unsupported",
        "What salary does the dock office lead earn?",
        task="abstain",
        forbidden=("750 pounds",),
    ),
]


def load_final_dataset() -> dict[str, Any]:
    questions = []
    for index, case in enumerate(FINAL, start=1):
        numbered = dict(case)
        numbered["id"] = f"final-{index:03d}"
        questions.append(numbered)
    return {
        "version": "rag-final-v1",
        "notice": "Fictional Plover Dock records. They were not used to tune retrieval.",
        "documents": DOCUMENTS,
        "companies": COMPANIES,
        "leads": LEADS,
        "contacts": CONTACTS,
        "questions": questions,
    }
