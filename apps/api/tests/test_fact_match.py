"""Formatting equivalents are not factual errors. Omitted facts still fail."""

from app.domains.evaluation.fact_match import statement_covers
from app.domains.knowledge.attribution import QUALIFIED_ANSWER, attribute_answer


def test_grouped_digits_match_an_unbroken_number() -> None:
    assert statement_covers("64000", "The cover is 64,000 pounds.")
    assert statement_covers("64000", "The cover is 64 000 pounds.")
    assert statement_covers("80,000", "Cargo cover is 80000 pounds.")


def test_clock_and_unit_plurals_match() -> None:
    assert statement_covers("09:15", "Sunday receiving opens at 9:15.")
    assert statement_covers("18 pounds", "The fee is 18 pound per drum.")
    assert statement_covers("5 percent", "The late fee is 5%.")
    assert statement_covers("minus 4", "The freezer is held at -4 degrees.")


def test_a_different_figure_or_a_missing_code_does_not_match() -> None:
    assert not statement_covers("18 pounds", "The fee is 19 pounds.")
    assert not statement_covers("09:15", "Sunday receiving opens at 10:15.")
    assert not statement_covers("8 drums", "The store holds 18 drums.")
    assert not statement_covers("ORRY-LAMP-42", "The fee is 42 pounds.")
    assert not statement_covers("10:30", "Sunday receiving opens at 10:00.")


def test_citation_accepts_grouped_digits_and_rejects_a_different_number() -> None:
    stored, cited = attribute_answer(
        "What is the cover limit?",
        "The cover is 64,000 pounds.",
        [("cover", "Cargo cover is limited to 64000 pounds.")],
    )
    assert stored == "The cover is 64,000 pounds."
    assert cited == ["cover"]
    refused, empty = attribute_answer(
        "What is the fee?",
        "The fee is 19 pounds.",
        [("rate", "The fee is 18 pounds. The code is ORRY-LAMP-18.")],
    )
    assert refused == QUALIFIED_ANSWER
    assert empty == []


def test_citation_accepts_a_clock_without_a_leading_zero() -> None:
    stored, cited = attribute_answer(
        "When does Sunday receiving open?",
        "Sunday receiving opens at 9:15.",
        [("hours", "Sunday receiving is open from 09:15 to 12:30.")],
    )
    assert "9:15" in stored
    assert cited == ["hours"]
    refused, empty = attribute_answer(
        "When does Sunday receiving open?",
        "Sunday receiving opens at 9:16.",
        [("hours", "Sunday receiving is open from 09:15 to 12:30.")],
    )
    assert refused == QUALIFIED_ANSWER
    assert empty == []
