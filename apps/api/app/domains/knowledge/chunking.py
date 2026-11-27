from dataclasses import dataclass

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_CHUNKS = 2000


@dataclass(frozen=True)
class TextChunk:
    index: int
    page_number: int | None
    content: str


def chunk_pages(pages: list[tuple[int | None, str]]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for page_number, text in pages:
        normalized = " ".join(text.split())
        if not normalized:
            continue
        start = 0
        while start < len(normalized):
            end = min(start + CHUNK_SIZE, len(normalized))
            if end < len(normalized):
                space = normalized.rfind(" ", start, end)
                if space > start:
                    end = space
            piece = normalized[start:end].strip()
            if piece:
                chunks.append(TextChunk(index=len(chunks), page_number=page_number, content=piece))
            if len(chunks) > MAX_CHUNKS:
                raise ValueError("Document is too long to index")
            if end >= len(normalized):
                break
            next_start = end - CHUNK_OVERLAP
            if next_start <= start:
                next_start = end
            start = next_start
    return chunks
