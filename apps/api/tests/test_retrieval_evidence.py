import math
import uuid

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.domains.knowledge.retrieval import VECTOR_ONLY_MAX_DISTANCE, search_chunks
from tests.factories import make_membership, make_organization, make_user


class _QueryVector:
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vector for _ in texts]


def test_evidence_keeps_lexical_and_close_paraphrases_and_drops_unsupported(
    db: Session,
) -> None:
    user = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-evidence")
    other = make_organization(db, "Northwind", "northwind-evidence")
    make_membership(db, user, atlas, MembershipRole.admin)
    document = _document(db, atlas.id, user.id, "Cedar brochure")
    lexical = _chunk(
        db,
        document,
        0,
        "The bonded yard holds freight.",
        _offset(1536, VECTOR_ONLY_MAX_DISTANCE + 0.05),
    )
    paraphrase = _chunk(
        db,
        document,
        1,
        "Alpha passage about capacity.",
        _offset(1536, VECTOR_ONLY_MAX_DISTANCE - 0.05),
    )
    unsupported = _chunk(
        db,
        document,
        2,
        "Gamma passage about something else.",
        _offset(1536, VECTOR_ONLY_MAX_DISTANCE + 0.05),
    )
    hidden = _document(db, other.id, user.id, "Other brochure")
    _chunk(db, hidden, 0, "Alpha passage about capacity.", _query(1536))
    _index(db, document.id)
    _index(db, hidden.id)
    db.commit()
    embedder = _QueryVector(_query(1536))

    mixed = search_chunks(db, atlas.id, "bonded yard", embedder)
    assert [hit.chunk_id for hit in mixed] == [lexical.id, paraphrase.id]
    assert unsupported.id not in {hit.chunk_id for hit in mixed}

    address = search_chunks(db, atlas.id, "founder private home street", embedder)
    assert [hit.chunk_id for hit in address] == [paraphrase.id]

    leaked = search_chunks(db, atlas.id, "qqqqqq", embedder)
    assert hidden.id not in {hit.document_id for hit in leaked}
    assert all(hit.document_id == document.id for hit in leaked)


def test_ambiguous_shared_term_stays_citable_when_the_vector_is_weak(db: Session) -> None:
    user = make_user(db, "bea@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-ambiguous")
    make_membership(db, user, atlas, MembershipRole.admin)
    document = _document(db, atlas.id, user.id, "Public code")
    chunk = _chunk(
        db,
        document,
        0,
        "The public brochure lists a code.",
        _offset(1536, VECTOR_ONLY_MAX_DISTANCE + 0.05),
    )
    _index(db, document.id)
    db.commit()
    hits = search_chunks(db, atlas.id, "public notice", _QueryVector(_query(1536)))
    assert [hit.chunk_id for hit in hits] == [chunk.id]


def test_vector_only_rule_uses_the_configured_width(db: Session, monkeypatch) -> None:
    user = make_user(db, "cy@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-width-evidence")
    make_membership(db, user, atlas, MembershipRole.admin)
    document = _document(db, atlas.id, user.id, "Narrow")
    close = _chunk(
        db,
        document,
        0,
        "Alpha passage about capacity.",
        _offset(768, VECTOR_ONLY_MAX_DISTANCE - 0.05),
        width=768,
    )
    far = _chunk(
        db,
        document,
        1,
        "Gamma passage about something else.",
        _offset(768, VECTOR_ONLY_MAX_DISTANCE + 0.05),
        width=768,
    )
    _index(db, document.id)
    db.commit()
    settings = get_settings().model_copy(
        update={
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "embedding_dimensions": 768,
        }
    )
    monkeypatch.setattr("app.domains.knowledge.retrieval.get_settings", lambda: settings)
    hits = search_chunks(db, atlas.id, "qqqqqq", _QueryVector(_query(768)))
    assert [hit.chunk_id for hit in hits] == [close.id]
    assert far.id not in {hit.chunk_id for hit in hits}


def _query(width: int) -> list[float]:
    vector = [0.0] * width
    vector[0] = 1.0
    return vector


def _offset(width: int, distance: float) -> list[float]:
    cosine = 1 - distance
    sine = math.sqrt(max(0.0, 1 - cosine * cosine))
    vector = [0.0] * width
    vector[0] = cosine
    vector[1] = sine
    return vector


def _document(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, title: str) -> Document:
    document = Document(
        organization_id=organization_id,
        uploaded_by=user_id,
        title=title,
        filename=f"{title}.txt",
        media_type="text/plain",
        byte_size=20,
        storage_path="tests/evidence.txt",
        status=DocumentStatus.ready,
    )
    db.add(document)
    db.flush()
    return document


def _chunk(
    db: Session,
    document: Document,
    index: int,
    content: str,
    vector: list[float],
    *,
    width: int = 1536,
) -> Chunk:
    chunk = Chunk(
        organization_id=document.organization_id,
        document_id=document.id,
        chunk_index=index,
        content=content,
        embedding_model="nomic-embed-text" if width == 768 else None,
    )
    if width == 768:
        chunk.embedding_768 = vector
    else:
        chunk.embedding = vector
    db.add(chunk)
    db.flush()
    return chunk


def _index(db: Session, document_id: uuid.UUID) -> None:
    db.execute(
        update(Chunk)
        .where(Chunk.document_id == document_id)
        .values(search_vector=func.to_tsvector("english", Chunk.content))
    )
