"""Reproducible synthetic leads for a demonstration classifier.

The label uses ``budget_band``. That field is not a model input. Status, revenue,
and anything learned after the lead is scored are also excluded. The labels are
synthetic. They do not measure real conversion.
"""

import random
from typing import TypedDict

DATASET_VERSION = "lead-synthetic-1"
DATASET_SEED = 22
DATASET_ROWS = 400

SOURCES = ("referral", "partner", "website", "event", "unknown")
INDUSTRIES = ("logistics", "software", "health", "unknown")
FEATURES = ("source", "has_email", "has_company", "title_length", "notes_length", "industry")


class SyntheticLead(TypedDict):
    source: str
    has_email: int
    has_company: int
    title_length: int
    notes_length: int
    industry: str
    budget_band: int
    converted: int


def generate_leads(rows: int = DATASET_ROWS, seed: int = DATASET_SEED) -> list[SyntheticLead]:
    rng = random.Random(seed)
    generated: list[SyntheticLead] = []
    for _ in range(rows):
        source = rng.choice(SOURCES)
        has_email = int(rng.random() < 0.7)
        has_company = int(rng.random() < 0.6)
        title_length = rng.randint(4, 80)
        notes_length = 0 if rng.random() < 0.4 else rng.randint(1, 200)
        industry = rng.choice(INDUSTRIES)
        budget_band = rng.randint(0, 3)
        converted = int(_label(source, has_email, has_company, budget_band))
        generated.append(
            {
                "source": source,
                "has_email": has_email,
                "has_company": has_company,
                "title_length": title_length,
                "notes_length": notes_length,
                "industry": industry,
                "budget_band": budget_band,
                "converted": converted,
            }
        )
    return generated


def _label(source: str, has_email: int, has_company: int, budget_band: int) -> bool:
    referred = source in {"referral", "partner"} and bool(has_email) and budget_band >= 2
    inbound = source == "website" and bool(has_company) and budget_band == 3
    return referred or inbound


def matrix(rows: list[SyntheticLead]) -> tuple[list[list[object]], list[int]]:
    features = [
        [
            row["source"],
            row["has_email"],
            row["has_company"],
            row["title_length"],
            row["notes_length"],
            row["industry"],
        ]
        for row in rows
    ]
    labels = [int(row["converted"]) for row in rows]
    return features, labels


def baseline_predict(features: list[list[object]]) -> list[int]:
    """A fixed rule: only a referral source is treated as likely to convert."""

    return [1 if row[0] == "referral" else 0 for row in features]
