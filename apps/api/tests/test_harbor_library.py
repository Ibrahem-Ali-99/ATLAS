"""The Harbor enterprise library is a connected set of fictional documents."""

import uuid

from app.domains.assistant.prompts import grounded_prompt
from app.domains.demo.harbor_library import library_documents
from app.domains.knowledge.chunking import chunk_pages
from app.domains.knowledge.retrieval import RetrievedChunk


def test_harbor_library_is_a_connected_set() -> None:
    documents = library_documents()
    assert 30 <= len(documents) <= 50
    filenames = [filename for _title, filename, _body in documents]
    assert len(filenames) == len(set(filenames))
    titles = [title for title, _filename, _body in documents]
    assert len(titles) == len(set(titles))
    bodies = {title: body for title, _filename, body in documents}
    assert all(len(body) >= 900 for body in bodies.values())
    current = bodies["Rate card effective 1 March 2026"]
    superseded = bodies["Superseded rate card"]
    sable = bodies["Sable Fisheries service schedule"]
    assert "HBR-FRZ-240" in current and "USD 24.00" in current
    assert "HBR-FRZ-210" in superseded and "superseded" in superseded.lower()
    assert "HBR-FRZ-240" in sable and "SF-1044" in sable
    assert "USD 18,640,000" in bodies["FY2026 financial report"]
    assert "USD 2,000,000" in bodies["Cargo insurance policy"]
    assert "5 business days" in bodies["Shortage and damage claims"]
    assert "24 hours" in bodies["Historical bonded policy of 2019"]
    assert "under 12 hours" in bodies["Cross-dock procedure"]
    assert "card number" in bodies["Records retention"].lower()


def test_chunk_keeps_a_rate_code_whole() -> None:
    text = ("alpha " * 132) + "code HBR-FRZ-240 is the current frozen rate."
    pieces = chunk_pages([(None, text)])
    assert any("HBR-FRZ-240" in piece.content for piece in pieces)
    assert all(not piece.content.endswith("HBR-FR") for piece in pieces)
    assert all("HBR-FR " not in piece.content for piece in pieces)


def test_prompt_excerpt_keeps_a_rate_code_whole() -> None:
    content = ("x" * 694) + "HBR-FRZ-240 applies."
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Rate card effective 1 March 2026",
        chunk_index=0,
        page_number=None,
        content=content,
        score=1.0,
        confidence=0.9,
    )
    prompt = grounded_prompt("What is the frozen rate code?", [chunk], [], [])
    assert "HBR-FRZ-240" in prompt
