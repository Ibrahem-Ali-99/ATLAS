"""Fictional Harbor & Co. records for a demonstration workspace.

The names, addresses, and documents are invented. They share one logistics
story so CRM, inbox, and retrieval describe the same yard.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

SPAN_DAYS = 119
SEEDED_CONVERSATION_TITLE = "Bonded yard capacity"
SEEDED_ASSISTANT_CONTENT = "Bonded warehousing is available at the north pier yard."
DRAFT_CAMPAIGN = "Q3 cold-storage briefing"
RECORDED_CAMPAIGN = "Yard safety bulletin"
LEAD_NOTE = "Yard visit confirmed in this demonstration."
COMPANY_COUNT = 20
CONTACT_COUNT = 40
LEAD_COUNT = 50
OPPORTUNITY_COUNT = 30
CONVERSATION_COUNT = 40
TASK_COUNT = 35
APPOINTMENT_COUNT = 20
WORKFLOW_COUNT = 8

KNOWLEDGE_TEXT = (
    "Bonded warehousing is available at the north pier yard.\n"
    "Cold storage for the third quarter is confirmed for existing customers.\n"
    "A written service sheet is issued after a person reviews the inquiry.\n"
)

# Titles are unique on purpose. Retrieval keeps a document when the question
# names one title, so the bonded note must be the only title containing "bonded".
DOCUMENTS: tuple[tuple[str, str, str], ...] = (
    ("Bonded warehousing overview", "bonded-warehousing-overview.txt", KNOWLEDGE_TEXT),
    (
        "Frozen seafood set point",
        "frozen-seafood-set-point.txt",
        "Frozen seafood is held at minus 18 C in room C2.\n"
        "Produce that must not freeze stays in a separate room.\n",
    ),
    (
        "Quay gate hours",
        "quay-gate-hours.txt",
        "The quay gate opens at 06:00 and closes at 22:00.\n"
        "The after-hours phrase for the gate office is lantern shift.\n",
    ),
    (
        "Flammable liquid refusal",
        "flammable-liquid-refusal.txt",
        "Class 3 flammable liquids are refused at the quay.\n"
        "The driver is turned away before the trailer is opened.\n",
    ),
    (
        "Customer visit window",
        "customer-visit-window.txt",
        "The visit window for existing customers is Thursday afternoon.\n"
        "The quay desk confirms the bay before the visitor arrives.\n",
    ),
    (
        "Pallet build sheet",
        "pallet-build-sheet.txt",
        "Accepted pallets are 1200 by 1000 millimetres and at most 1000 kilograms.\n"
        "Overweight pallets are split before they enter the rack.\n",
    ),
    (
        "Shortage claim timing",
        "shortage-claim-timing.txt",
        "A shortage claim must arrive within 5 business days of delivery.\n"
        "The claim names the trailer and the pallet count.\n",
    ),
    (
        "Receiving paperwork",
        "receiving-paperwork.txt",
        "Entry to the bonded area requires a packing list and a commercial invoice.\n"
        "The trailer stays closed until both papers are on the desk.\n",
    ),
    (
        "Temperature excursion",
        "temperature-excursion.txt",
        "A temperature excursion is reported to the quay desk within 30 minutes.\n"
        "The room is held until a person records the reading.\n",
    ),
    (
        "Quay clothing rule",
        "quay-clothing-rule.txt",
        "High-visibility clothing and closed shoes are required on the quay.\n"
        "Visitors without them wait in the office.\n",
    ),
    (
        "Tuesday cycle count",
        "tuesday-cycle-count.txt",
        "Inventory cycle counts run every Tuesday morning.\n"
        "A variance is written on the pallet card the same day.\n",
    ),
    (
        "Cross-dock dwell",
        "cross-dock-dwell.txt",
        "Cross-dock freight stays on the floor for under 12 hours.\n"
        "Freight that remains longer is moved into a storage bay.\n",
    ),
    (
        "Quay desk",
        "quay-desk.txt",
        "The quay desk phone for this demonstration is +1-555-0142.\n"
        "Calling that number from this note does not place a call.\n",
    ),
    (
        "Pallet-week billing",
        "pallet-week-billing.txt",
        "Storage is billed per pallet-week in USD.\n"
        "This note does not contain an account number or a card number.\n",
    ),
    (
        "Records the library omits",
        "records-the-library-omits.txt",
        "This library does not record card numbers or government identity numbers.\n"
        "A question for either of those has no passage to cite.\n",
    ),
)

EVALUATIONS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "Does the service note confirm cold storage for the third quarter?",
        "grounded",
        "answer",
        ("cold storage", "third quarter"),
    ),
    (
        "Is bonded warehousing available at the north pier?",
        "grounded",
        "answer",
        ("bonded warehousing is available at the north pier yard",),
    ),
    (
        "What temperature is frozen seafood held at?",
        "grounded",
        "answer",
        ("minus 18",),
    ),
    (
        "Can you connect me to a person?",
        "human_handoff",
        "handoff",
        (),
    ),
    (
        "What is the Swiss vault passphrase for payroll?",
        "missing_knowledge",
        "fallback",
        ("swiss vault passphrase",),
    ),
)

COMPANIES: tuple[tuple[str, str, str], ...] = (
    ("Harbor & Co.", "https://harbor.example", "Logistics"),
    ("Lumen Freight", "https://lumen.example", "Freight forwarding"),
    ("Northline Cold Chain", "https://northline.example", "Cold storage"),
    ("Cedar & Birch Timber", "https://cedar.example", "Forest products"),
    ("Marlowe Instruments", "https://marlowe.example", "Industrial equipment"),
    ("Sable Fisheries", "https://sable.example", "Seafood"),
    ("Kinship Coffee", "https://kinship.example", "Food"),
    ("Vesper Glass", "https://vesper.example", "Building materials"),
    ("Orchard Lane Produce", "https://orchard.example", "Agriculture"),
    ("Brine & Barrel", "https://brine.example", "Beverages"),
    ("Paperwharf Publishing", "https://paperwharf.example", "Print"),
    ("Helio Solar Kits", "https://helio.example", "Energy equipment"),
    ("Docklight Marine", "https://docklight.example", "Marine supplies"),
    ("Fieldnote Apparel", "https://fieldnote.example", "Apparel"),
    ("Copperline Electrical", "https://copperline.example", "Electrical goods"),
    ("Meadow Malt", "https://meadow.example", "Brewing supplies"),
    ("Quarry Stone", "https://quarry.example", "Construction materials"),
    ("Nimbus Packaging", "https://nimbus.example", "Packaging"),
    ("Red Lantern Foods", "https://redlantern.example", "Grocery"),
    ("Westline Auto Parts", "https://westline.example", "Automotive"),
)

CONTACTS: tuple[tuple[str, str, str], ...] = (
    ("Mina Patel", "Operations lead", "mina.patel"),
    ("Owen Shah", "Yard planner", "owen.shah"),
    ("Jonah Ellis", "Network planner", "jonah.ellis"),
    ("Priya Nunez", "Import clerk", "priya.nunez"),
    ("Helen Cho", "Cold-room lead", "helen.cho"),
    ("Marcus Adeyemi", "Receiver", "marcus.adeyemi"),
    ("Greta Holm", "Mill dispatcher", "greta.holm"),
    ("Luis Ortega", "Buyer", "luis.ortega"),
    ("Naomi Berg", "Plant scheduler", "naomi.berg"),
    ("Samir Qureshi", "Warehouse liaison", "samir.qureshi"),
    ("Ida Sorensen", "Fleet coordinator", "ida.sorensen"),
    ("Theo Marchetti", "Quality lead", "theo.marchetti"),
    ("Farah Siddiqui", "Roastery planner", "farah.siddiqui"),
    ("Colin Briggs", "Inbound lead", "colin.briggs"),
    ("Yara Mensah", "Site manager", "yara.mensah"),
    ("Elliot Park", "Shipping clerk", "elliot.park"),
    ("Hana Ito", "Grower liaison", "hana.ito"),
    ("Victor Almeida", "Cooler supervisor", "victor.almeida"),
    ("Ruth Keller", "Cellar planner", "ruth.keller"),
    ("Andre Costa", "Export clerk", "andre.costa"),
    ("Leah Okonkwo", "Print buyer", "leah.okonkwo"),
    ("Simon Adler", "Paper store lead", "simon.adler"),
    ("Maya Rahman", "Kit assembler", "maya.rahman"),
    ("Chris Dalton", "Outbound planner", "chris.dalton"),
    ("Ines Moreau", "Chandlery buyer", "ines.moreau"),
    ("Paul Ng", "Dock supervisor", "paul.ng"),
    ("Sofia Reyes", "Allocation lead", "sofia.reyes"),
    ("Henry Walsh", "Carton planner", "henry.walsh"),
    ("Amina Diallo", "Spares buyer", "amina.diallo"),
    ("George Ellis", "Counter lead", "george.ellis"),
    ("Nora Feldman", "Malt buyer", "nora.feldman"),
    ("Ivan Petrov", "Intake clerk", "ivan.petrov"),
    ("Claire Dubois", "Block yard lead", "claire.dubois"),
    ("Omar Hassan", "Weighbridge clerk", "omar.hassan"),
    ("Jill Palmer", "Pack planner", "jill.palmer"),
    ("Kenji Sato", "Line supervisor", "kenji.sato"),
    ("Rosa Medina", "Grocery replenisher", "rosa.medina"),
    ("Felix Bauer", "Chiller lead", "felix.bauer"),
    ("Tara Singh", "Parts planner", "tara.singh"),
    ("Will Harper", "Returns clerk", "will.harper"),
)

LEAD_STATUSES = (
    ("qualified",) * 10
    + ("contacted",) * 10
    + ("new",) * 10
    + ("unqualified",) * 6
    + ("won",) * 8
    + ("lost",) * 6
)
LEAD_PURPOSES = (
    "North pier expansion",
    "Frozen salmon holding",
    "Timber pack overflow",
    "Instrument crate intake",
    "Coffee sack reservation",
    "Glass stillage move",
    "Produce cooler booking",
    "Barrel restack",
    "Paper reel storage",
    "Solar kit cross-dock",
    "Marine spares bay",
    "Apparel carton count",
    "Electrical reel intake",
    "Malt bag overflow",
    "Stone block yard",
    "Packaging film hold",
    "Grocery chilled lane",
    "Auto parts mezzanine",
    "Bonded trailer unload",
    "Returns cage review",
)

OPPORTUNITY_STAGES = (
    ("qualified",) * 6
    + ("new",) * 5
    + ("contacted",) * 5
    + ("won",) * 7
    + ("lost",) * 5
    + ("unqualified",) * 2
)

WORKFLOWS: tuple[tuple[str, str, str, dict[str, object]], ...] = (
    (
        "qualified-lead-follow-up",
        "Qualified lead follow-up",
        "Inactive demonstration. A matching qualified lead waits for approval, then a task.",
        {
            "trigger": "lead_created",
            "condition_mode": "all",
            "conditions": [{"field": "lead_status", "operator": "equals", "value": "qualified"}],
            "actions": [
                {
                    "type": "require_approval",
                    "note": "Confirm the bonded service sheet before creating the task.",
                },
                {
                    "type": "create_task",
                    "title": "Send the bonded service sheet",
                    "priority": "high",
                },
            ],
            "otherwise_actions": [
                {"type": "create_task", "title": "Ask for the missing yard details"},
            ],
        },
    ),
    (
        "new-lead-intake",
        "New lead intake",
        "Inactive demonstration. A new lead gets an intake task. Nothing is sent.",
        {
            "trigger": "lead_created",
            "condition_mode": "all",
            "conditions": [{"field": "lead_status", "operator": "equals", "value": "new"}],
            "actions": [{"type": "create_task", "title": "Call the shipper about the new lot"}],
            "otherwise_actions": [
                {"type": "create_task", "title": "File the lead for later review"}
            ],
        },
    ),
    (
        "contacted-follow-up",
        "Contacted lead follow-up",
        "Inactive demonstration. A contacted lead gets a second-touch task.",
        {
            "trigger": "lead_status_changed",
            "condition_mode": "all",
            "conditions": [{"field": "lead_status", "operator": "equals", "value": "contacted"}],
            "actions": [{"type": "create_task", "title": "Send the yard questionnaire"}],
            "otherwise_actions": [],
        },
    ),
    (
        "lost-lead-review",
        "Lost lead review",
        "Inactive demonstration. A lost lead is reviewed. No customer message is drafted.",
        {
            "trigger": "lead_status_changed",
            "condition_mode": "any",
            "conditions": [{"field": "lead_status", "operator": "equals", "value": "lost"}],
            "actions": [{"type": "create_task", "title": "Record why the lot was lost"}],
            "otherwise_actions": [
                {"type": "create_task", "title": "Leave the open lead on the board"}
            ],
        },
    ),
    (
        "won-handoff",
        "Won opportunity handoff",
        "Inactive demonstration. A won stage creates a handoff task.",
        {
            "trigger": "opportunity_stage_changed",
            "condition_mode": "all",
            "conditions": [{"field": "opportunity_stage", "operator": "equals", "value": "won"}],
            "actions": [{"type": "create_task", "title": "Open the won lot with the quay desk"}],
            "otherwise_actions": [],
        },
    ),
    (
        "unqualified-nurture",
        "Unqualified lead note",
        "Inactive demonstration. An unqualified lead gets a note task, not a campaign.",
        {
            "trigger": "lead_status_changed",
            "condition_mode": "all",
            "conditions": [{"field": "lead_status", "operator": "equals", "value": "unqualified"}],
            "actions": [{"type": "create_task", "title": "Note the missing paperwork"}],
            "otherwise_actions": [],
        },
    ),
    (
        "quote-prep",
        "Capacity quote prep",
        "Inactive demonstration. A qualified opportunity prepares a quote task.",
        {
            "trigger": "opportunity_stage_changed",
            "condition_mode": "all",
            "conditions": [
                {"field": "opportunity_stage", "operator": "equals", "value": "qualified"}
            ],
            "actions": [
                {
                    "type": "require_approval",
                    "note": "Check the pallet-week figure before the task.",
                },
                {"type": "create_task", "title": "Draft the pallet-week quote"},
            ],
            "otherwise_actions": [
                {"type": "create_task", "title": "Ask which bay the freight needs"}
            ],
        },
    ),
    (
        "visit-prep",
        "Yard visit preparation",
        "Inactive demonstration. A manual start creates a visit checklist and does not book.",
        {
            "trigger": "manual",
            "condition_mode": "all",
            "conditions": [],
            "actions": [{"type": "create_task", "title": "Prepare the yard visit checklist"}],
            "otherwise_actions": [],
        },
    ),
)


def seeded_document_hashes() -> frozenset[str]:
    return frozenset(
        hashlib.sha256(body.encode()).hexdigest() for _title, _filename, body in DOCUMENTS
    )


def moment(index: int, count: int, *, now: datetime | None = None) -> datetime:
    """Spread timestamps across the demonstration window, oldest first."""

    current = now or datetime.now(UTC)
    if count <= 1:
        return current
    start = current - timedelta(days=SPAN_DAYS)
    return start + (current - start) * index / (count - 1)


def lead_title(index: int) -> str:
    if index == 0:
        return "North pier expansion"
    purpose = LEAD_PURPOSES[index % len(LEAD_PURPOSES)]
    cycle = index // len(LEAD_PURPOSES)
    if cycle == 0:
        return purpose
    return f"{purpose} {cycle + 1}"
