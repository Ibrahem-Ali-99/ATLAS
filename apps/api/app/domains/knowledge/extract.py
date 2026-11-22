from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import AppError


def extract_text(filename: str, payload: bytes) -> list[tuple[int | None, str]]:
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        return _pdf_pages(payload)
    if lowered.endswith(".txt"):
        return [(None, _decode_text(payload))]
    raise AppError(415, "unsupported_media", "Only PDF and TXT documents can be uploaded")


def _decode_text(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AppError(422, "invalid_document", "TXT documents must be UTF-8") from exc


def _pdf_pages(payload: bytes) -> list[tuple[int | None, str]]:
    if not payload.startswith(b"%PDF"):
        raise AppError(422, "invalid_document", "The file is not a readable PDF")
    try:
        reader = PdfReader(BytesIO(payload))
    except PdfReadError as exc:
        raise AppError(422, "invalid_document", "The file is not a readable PDF") from exc
    pages: list[tuple[int | None, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append((index, page.extract_text() or ""))
    return pages
